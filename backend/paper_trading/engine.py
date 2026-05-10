"""Autonomous Paper Trading Engine.

Background asyncio task that wakes up at NSE market open,
scans every 30 minutes, places simulated trades when the
AI is bullish-and-confident, monitors exits live, and
self-tunes its confidence threshold every 10 closed trades.

Strictly simulated — never places real orders.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite
import pytz

from backtest.database import DB_PATH, get_config, set_config

# RULE 2: paper trading is Kite-only. yfinance is NOT imported here —
# any live price / monitoring path that needed yfinance previously is
# now routed through the Kite client. Backtest pipeline still uses
# yfinance, but it lives in backend/backtest/ and never crosses this
# module's boundary.

IST = pytz.timezone("Asia/Kolkata")

# ── Engine constants (RULE 3: budget cap removed, symbol lock added) ──
MAX_CONCURRENT_POSITIONS = 8
INTRADAY_ENTRY_CUTOFF_HOUR = 14   # RULE 10: no NEW intraday entries after 2:00 PM IST
FORCE_CLOSE_HOUR   = 15           # 3:15 PM IST
FORCE_CLOSE_MINUTE = 15

# ── Engine state (in-memory) ──────────────────────────────────────────
_active_trades: Dict[str, Dict[str, Any]] = {}
_active_symbol_lock: set[str] = set()  # RULE 3: symbols with open trades
_engine_running: bool = False
_live_events: List[Dict[str, Any]] = []
_last_scan_time: Optional[datetime] = None
_last_token_refresh_date: Optional[Any] = None


def push_event(event_type: str, data: Dict[str, Any]) -> None:
    """Append a real-time event to the SSE buffer (cap at 100)."""
    _live_events.append(
        {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(IST).isoformat(),
        }
    )
    if len(_live_events) > 100:
        _live_events.pop(0)


# ── Market hours helpers ──────────────────────────────────────────────

def is_nse_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    open_t = now.replace(hour=9, minute=15, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= now <= close_t


def is_near_market_close() -> bool:
    """Within last 15 minutes of trading day (force-exit zone)."""
    now = datetime.now(IST)
    force = now.replace(hour=15, minute=15, second=0, microsecond=0)
    close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return force <= now <= close


def time_until_next_scan_minutes() -> int:
    if _last_scan_time is None:
        return 0
    elapsed = (datetime.now(IST) - _last_scan_time).total_seconds() // 60
    return int(max(0, 30 - elapsed))


# ── RULE 7: rejection logging with full indicator snapshot ──────────────

async def _log_rejection(
    sym: str, horizon: str, confidence: float, reason: str,
    score: float, indicators: Dict[str, Any] | None,
) -> None:
    """Persist a trade rejection — every rejection is research data."""
    try:
        threshold = int(await get_config("confidence_threshold") or "65")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO scan_rejections
                     (stock, scan_time, horizon, ai_confidence, threshold_at_time,
                      reject_reason, score_at_rejection, indicators_snapshot)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    sym, datetime.now(IST).isoformat(), horizon,
                    float(confidence), threshold, reason, float(score),
                    json.dumps(indicators or {}),
                ),
            )
            await db.commit()
        push_event("trade_rejected", {
            "stock": sym, "horizon": horizon,
            "confidence": confidence, "reason": reason,
        })
    except Exception as e:  # noqa: BLE001
        print(f"[reject_log] {sym} failed: {e}")


# ── Live price fetcher (Kite ONLY — RULE 2) ───────────────────────────

def _fetch_prices_sync(symbols: List[str]) -> Dict[str, float]:
    """Fetch live prices for paper-trade monitoring. Kite-only.

    No yfinance fallback. If Kite is unavailable or a quote is missing
    the symbol is dropped from the result and the failure is logged
    inside the Kite client. Callers must treat a missing entry as
    'price not available right now' — never as 'use stale data'.
    """
    if not symbols:
        return {}
    try:
        from data.kite_client import kite as _kite  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        print(f"[paper_trading] kite_client import failed: {e}")
        return {}
    return _kite.get_batch_prices(symbols)


async def fetch_live_prices(symbols: List[str]) -> Dict[str, float]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_prices_sync, symbols)


# ── Morning scan: find candidates, place paper trades ─────────────────

async def morning_scan() -> None:
    """Scan top screener candidates and place paper trades for qualifying ones."""
    global _last_scan_time
    _last_scan_time = datetime.now(IST)

    try:
        from ai.llm import get_recommendation
        from data.indicators import compute_indicators
        from data.market import fetch_daily_6mo, fetch_price
        from data.screener import run_screener

        confidence_threshold = int(await get_config("confidence_threshold") or "65")
        trades_placed = 0
        candidates_found = 0

        push_event(
            "scan_started",
            {
                "time": _last_scan_time.strftime("%I:%M %p"),
                "confidence_threshold": confidence_threshold,
            },
        )

        loop = asyncio.get_event_loop()

        # RULE 3: cap on concurrent positions only (no budget cap)
        if len(_active_trades) >= MAX_CONCURRENT_POSITIONS:
            push_event("scan_skipped", {
                "reason": f"At capacity ({MAX_CONCURRENT_POSITIONS} active trades)",
            })
            return

        # RULE 10: dual horizon — intraday gated by 2:00 PM IST cutoff,
        # shortterm runs anytime market is open.
        scan_modes: List[str] = []
        if _last_scan_time and _last_scan_time.hour < INTRADAY_ENTRY_CUTOFF_HOUR:
            scan_modes.append("intraday")
        scan_modes.append("shortterm")

        for mode in scan_modes:
            try:
                screener_payload = await run_screener(mode)
                stocks = screener_payload.get("stocks", []) if isinstance(screener_payload, dict) else []
                top_stocks = [s for s in stocks if s.get("score", 0) >= 70][:5]
                candidates_found += len(top_stocks)

                for candidate in top_stocks:
                    sym = candidate["symbol"]

                    # RULE 1 + RULE 2: full live-symbol validation BEFORE any
                    # trade. Skips on unmapped / kite_unavailable / missing
                    # quote / invalid price / stale quote — never silent fallback.
                    try:
                        from data.kite_client import validate_live_symbol  # noqa: PLC0415
                        ok, reason = validate_live_symbol(sym)
                    except Exception as e:  # noqa: BLE001
                        ok, reason = False, f"kite_client_import_error:{e.__class__.__name__}"
                    if not ok:
                        print(f"[paper_trading] reject {sym}: {reason}")
                        await _log_rejection(
                            sym, mode, 0.0, f"live_validation_failed:{reason}",
                            float(candidate.get("score", 0)), {},
                        )
                        continue

                    # RULE 3: per-symbol lock
                    if sym in _active_symbol_lock or any(t["stock"] == sym for t in _active_trades.values()):
                        await _log_rejection(sym, mode, 0.0,
                                             "already_has_active_trade",
                                             float(candidate.get("score", 0)), {})
                        continue

                    # Total positions cap
                    if len(_active_trades) >= MAX_CONCURRENT_POSITIONS:
                        break

                    try:
                        # Fetch live data
                        price_data = await loop.run_in_executor(None, fetch_price, sym)
                        df = await loop.run_in_executor(None, fetch_daily_6mo, sym)
                        indicators = await loop.run_in_executor(None, compute_indicators, df)

                        if not price_data or not indicators:
                            continue

                        live_price = float(price_data.get("price") or indicators.get("last_close") or 0)
                        if live_price <= 0:
                            continue

                        # Get AI recommendation (sync wrapped in executor)
                        rec = await loop.run_in_executor(
                            None,
                            get_recommendation,
                            sym,
                            candidate.get("name") or price_data.get("name") or sym,
                            live_price,
                            indicators,
                            mode,
                        )

                        analysis = rec.get("analysis", {}) if rec else {}
                        if not analysis:
                            continue

                        bias = (analysis.get("bias") or "NEUTRAL").upper()
                        confidence = int(analysis.get("confidence") or 0)

                        if bias != "BULLISH" or confidence < confidence_threshold:
                            # RULE 7: persist rejection with full indicator snapshot
                            await _log_rejection(
                                sym, mode, float(confidence),
                                f"bias_{bias.lower()}_or_conf_{confidence}_lt_{confidence_threshold}",
                                float(candidate.get("score", 0)), indicators,
                            )
                            continue

                        intraday = analysis.get("intraday") or {}
                        entry_low = float(intraday.get("entry_low") or live_price)
                        entry_high = float(intraday.get("entry_high") or live_price)
                        entry_price = (entry_low + entry_high) / 2 if entry_high >= entry_low else live_price
                        target_1 = float(intraday.get("target_1") or entry_price * 1.015)
                        target_2 = float(intraday.get("target_2") or entry_price * 1.025)
                        stop_loss = float(intraday.get("stop_loss") or entry_price * 0.993)

                        # Allocate ₹5,000 per trade — compute share quantity at entry
                        qty = max(1, int(PER_TRADE_INR / entry_price))
                        allocated_inr = round(qty * entry_price, 2)

                        # RULE 5: pre-trade integrity log (one line per placement)
                        try:
                            from data.kite_client import kite as _kite_log, SYMBOL_MAP as _MAP_LOG  # noqa: PLC0415
                            _kite_sym_log = _MAP_LOG.get(sym, "<unmapped>")
                            _live_log = _kite_log.get_live_price(sym)
                            _cache_entry = _kite_log.price_cache.get(sym, {})
                            _age_log = round(time.time() - float(_cache_entry.get("ts", 0)), 2) if _cache_entry else None
                            print(
                                f"[pre_trade_log] symbol={sym} kite_symbol={_kite_sym_log} "
                                f"live_price={_live_log} quote_age_s={_age_log} "
                                f"entry_price={round(entry_price,2)}"
                            )
                        except Exception as _log_e:  # noqa: BLE001
                            print(f"[pre_trade_log] log failed for {sym}: {_log_e}")

                        trade = {
                            "trade_id": str(uuid.uuid4())[:12],
                            "stock": sym,
                            "trade_type": "LONG",
                            "entry_price": round(entry_price, 2),
                            "entry_time": datetime.now(IST).isoformat(),
                            "target_1": round(target_1, 2),
                            "target_2": round(target_2, 2),
                            "stop_loss": round(stop_loss, 2),
                            "horizon": "intraday",  # forced — ₹20K intraday spec
                            "ai_bias": bias,
                            "ai_confidence": confidence,
                            "ai_conviction": analysis.get("conviction", "MEDIUM"),
                            "ai_reasons": json.dumps(analysis.get("key_reasons", [])),
                            "score_at_entry": float(candidate.get("score", 0)),
                            "indicators_at_entry": json.dumps(indicators),
                            "status": "ACTIVE",
                            "exit_price": None,
                            "exit_time": None,
                            "exit_reason": None,
                            "result": None,
                            "pnl_pct": None,
                            "created_date": datetime.now(IST).strftime("%Y-%m-%d"),
                            "sector": candidate.get("sector", ""),
                            "name": candidate.get("name", sym),
                            "qty": qty,
                            "allocated_inr": allocated_inr,
                        }

                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                """INSERT INTO paper_trades
                                     (trade_id, stock, trade_type, entry_price, entry_time,
                                      target_1, target_2, stop_loss, horizon, ai_bias,
                                      ai_confidence, ai_conviction, ai_reasons,
                                      score_at_entry, indicators_at_entry, status,
                                      created_date, sector, name)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    trade["trade_id"], trade["stock"], trade["trade_type"],
                                    trade["entry_price"], trade["entry_time"],
                                    trade["target_1"], trade["target_2"], trade["stop_loss"],
                                    trade["horizon"], trade["ai_bias"], trade["ai_confidence"],
                                    trade["ai_conviction"], trade["ai_reasons"],
                                    trade["score_at_entry"], trade["indicators_at_entry"],
                                    trade["status"], trade["created_date"],
                                    trade["sector"], trade["name"],
                                ),
                            )
                            await db.commit()

                        _active_trades[trade["trade_id"]] = trade
                        _active_symbol_lock.add(sym)  # RULE 3
                        trades_placed += 1

                        push_event(
                            "trade_opened",
                            {
                                "trade_id": trade["trade_id"],
                                "stock": sym,
                                "entry": trade["entry_price"],
                                "target_1": trade["target_1"],
                                "stop_loss": trade["stop_loss"],
                                "confidence": confidence,
                                "mode": "intraday",
                                "qty": qty,
                                "allocated_inr": allocated_inr,
                            },
                        )

                        # Stop placing trades if we've filled all slots
                        if len(_active_trades) >= MAX_CONCURRENT_POSITIONS:
                            break

                    except Exception as e:  # noqa: BLE001
                        print(f"[paper_trading] Error processing {sym}: {e}")
                        continue

            except Exception as e:  # noqa: BLE001
                print(f"[paper_trading] Screener error for {mode}: {e}")
                continue

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO paper_trading_scans
                     (scan_time, mode, candidates_found, trades_placed, reason_summary)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    datetime.now(IST).isoformat(),
                    "intraday+shortterm",
                    candidates_found,
                    trades_placed,
                    f"Scanned at {_last_scan_time.strftime('%H:%M IST')}",
                ),
            )
            await db.commit()

        push_event(
            "scan_complete",
            {
                "candidates_found": candidates_found,
                "trades_placed": trades_placed,
                "time": _last_scan_time.strftime("%I:%M %p"),
            },
        )

    except Exception as e:  # noqa: BLE001
        print(f"[paper_trading] Morning scan error: {e}")


# ── Trade monitoring ──────────────────────────────────────────────────

async def monitor_active_trades() -> None:
    if not _active_trades:
        return

    symbols = list({t["stock"] for t in _active_trades.values()})
    prices = await fetch_live_prices(symbols)

    closed_ids: List[str] = []

    for trade_id, trade in list(_active_trades.items()):
        sym = trade["stock"]
        current = prices.get(sym)
        if current is None:
            continue

        entry = float(trade["entry_price"])
        t1 = float(trade["target_1"])
        sl = float(trade["stop_loss"])
        live_pnl = round((current - entry) / entry * 100, 3)

        push_event(
            "price_update",
            {
                "trade_id": trade_id,
                "stock": sym,
                "current_price": round(current, 2),
                "live_pnl_pct": live_pnl,
            },
        )

        result = None
        exit_reason = None
        exit_price = current

        if current >= t1:
            result = "WIN_T1"; exit_reason = "Target 1 Hit"
        elif current <= sl:
            result = "LOSS"; exit_reason = "Stop Loss Hit"
        elif trade.get("horizon") == "intraday" and is_near_market_close():
            result = "EXPIRED"; exit_reason = "Intraday Expiry"

        if not result:
            continue

        pnl_pct = round((exit_price - entry) / entry * 100, 3)
        exit_time = datetime.now(IST).isoformat()

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE paper_trades SET
                     status='CLOSED', exit_price=?, exit_time=?,
                     exit_reason=?, result=?, pnl_pct=?
                   WHERE trade_id=?""",
                (exit_price, exit_time, exit_reason, result, pnl_pct, trade_id),
            )
            await db.commit()

        push_event(
            "trade_closed",
            {
                "trade_id": trade_id,
                "stock": sym,
                "result": result,
                "exit_reason": exit_reason,
                "pnl_pct": pnl_pct,
            },
        )
        closed_ids.append(trade_id)

        total = int(await get_config("total_trades") or "0") + 1
        wins = int(await get_config("total_wins") or "0")
        if result in ("WIN_T1", "WIN_T2"):
            wins += 1
        await set_config("total_trades", str(total))
        await set_config("total_wins", str(wins))

        if total % 10 == 0:
            asyncio.create_task(run_learning_cycle(total))

    for tid in closed_ids:
        t = _active_trades.pop(tid, None)
        if t:
            _active_symbol_lock.discard(t.get("stock", ""))  # RULE 3: free the symbol


# ── RULE 4: Force-close at 3:15 PM IST with mandatory fallback chain ────

async def _force_close_intraday_trades() -> int:
    """Close any ACTIVE intraday trade still open at 3:15 PM IST. Never let
    a zombie trade survive past market close — it corrupts win-rate stats.

    RULE 2: Kite-only price chain. yfinance is NOT permitted as a live
    price source. Order: Kite live -> Kite cache -> hard fallback to
    entry price (loud CRITICAL log + FORCE_CLOSED_NO_PRICE result).
    """
    intraday = [t for t in _active_trades.values() if t.get("horizon") == "intraday"]
    if not intraday:
        return 0

    try:
        from data.kite_client import kite as _kite  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        print(f"[force-close] kite_client import failed: {e}")
        _kite = None  # type: ignore

    closed_count = 0
    loop = asyncio.get_event_loop()

    for trade in list(intraday):
        sym = trade["stock"]
        exit_price: Optional[float] = None
        price_source = "unknown"

        # 1. Kite live quote
        if _kite is not None:
            try:
                p = await loop.run_in_executor(None, _kite.get_live_price, sym)
                if p and p > 0:
                    exit_price = float(p); price_source = "kite_live"
            except Exception as e:  # noqa: BLE001
                print(f"[force-close] kite_live failed for {sym}: {e}")

        # 2. Kite price cache (most recent verified Kite quote)
        if exit_price is None and _kite is not None:
            try:
                cached = _kite.price_cache.get(sym)
                if cached and (time.time() - cached.get("ts", 0)) < 600:
                    exit_price = float(cached["price"]); price_source = "kite_cache"
            except Exception as e:  # noqa: BLE001
                print(f"[force-close] kite_cache read failed for {sym}: {e}")

        # 3. Hard fallback — entry price (loud failure, never silent)
        result = "EXPIRED"
        exit_reason = f"Intraday Expiry ({price_source})"
        if exit_price is None or exit_price <= 0:
            exit_price = float(trade["entry_price"])
            price_source = "fallback_entry_price"
            result = "FORCE_CLOSED_NO_PRICE"
            exit_reason = "Force close — no Kite price available (RULE 2/4)"
            print(f"[force-close] CRITICAL: {sym} closed with no live Kite price")

        entry = float(trade["entry_price"])
        pnl_pct = round((exit_price - entry) / entry * 100.0, 3) if entry else 0.0
        exit_time = datetime.now(IST).isoformat()

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """UPDATE paper_trades SET
                         status='CLOSED', exit_price=?, exit_time=?,
                         exit_reason=?, result=?, pnl_pct=?
                       WHERE trade_id=?""",
                    (exit_price, exit_time, exit_reason, result, pnl_pct, trade["trade_id"]),
                )
                await db.commit()
        except Exception as e:  # noqa: BLE001
            print(f"[force-close] DB write failed for {sym}: {e}")

        push_event("trade_closed", {
            "trade_id": trade["trade_id"], "stock": sym,
            "result": result, "pnl_pct": pnl_pct,
            "price_source": price_source,
        })

        _active_trades.pop(trade["trade_id"], None)
        _active_symbol_lock.discard(sym)
        closed_count += 1

    return closed_count


# ── Adaptive learning every 10 closed trades (Phase 3 — real weight tuning) ──

async def run_learning_cycle(total_trades: int) -> None:
    """Compute factor-level IC against actual outcomes, then UPDATE the
    factor group weights (momentum/trend/volume/volatility) — not just a
    single threshold knob.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT result, pnl_pct, ai_confidence, score_at_entry,
                          indicators_at_entry, stock, exit_reason, horizon
                   FROM paper_trades
                   WHERE status='CLOSED'
                   ORDER BY exit_time DESC LIMIT 20"""
            ) as cursor:
                recent = await cursor.fetchall()

        if len(recent) < 5:
            return

        trades = [dict(r) for r in recent]
        wins   = [t for t in trades if t["result"] in ("WIN_T1", "WIN_T2")]
        losses = [t for t in trades if t["result"] == "LOSS"]
        win_rate = len(wins) / len(trades)
        avg_pnl  = sum(float(t.get("pnl_pct") or 0) for t in trades) / len(trades)

        # ── Factor IC on paper-trade outcomes ─────────────────────────────
        factor_ics: Dict[str, float] = {}
        try:
            from data.orthogonalize import build_orthogonal_features  # noqa: PLC0415
            from scipy import stats  # noqa: PLC0415

            buckets: Dict[str, List[float]] = {
                "momentum": [], "trend": [], "volume": [], "volatility": [],
            }
            outcomes: List[float] = []
            for t in trades:
                try:
                    ind = json.loads(t.get("indicators_at_entry") or "{}")
                except Exception:  # noqa: BLE001
                    continue
                if not ind:
                    continue
                orth = build_orthogonal_features(ind)
                for f in buckets:
                    buckets[f].append(float(orth.get(f"{f}_score", 0.5)))
                outcomes.append(1.0 if t["result"] in ("WIN_T1", "WIN_T2") else 0.0)

            if len(outcomes) >= 5:
                for f, vals in buckets.items():
                    if len(vals) == len(outcomes):
                        try:
                            ic, _ = stats.spearmanr(vals, outcomes)
                            if ic is None or (isinstance(ic, float) and ic != ic):  # NaN check
                                factor_ics[f] = 0.0
                            else:
                                factor_ics[f] = round(float(ic), 4)
                        except Exception:  # noqa: BLE001
                            factor_ics[f] = 0.0
        except Exception as e:  # noqa: BLE001
            print(f"[learning] factor IC computation failed: {e}")

        # ── Generate new factor weights from IC ──────────────────────────
        current_weights = {
            "momentum":   float(await get_config("weight_momentum")   or "0.30"),
            "trend":      float(await get_config("weight_trend")      or "0.25"),
            "volume":     float(await get_config("weight_volume")     or "0.30"),
            "volatility": float(await get_config("weight_volatility") or "0.15"),
        }
        new_weights = dict(current_weights)
        weight_changes: List[Dict[str, Any]] = []

        for factor, ic in factor_ics.items():
            old_w = current_weights.get(factor, 0.25)
            if   ic >  0.10: new_w = min(0.50, old_w * 1.15)   # strong positive — push up
            elif ic >  0.05: new_w = min(0.45, old_w * 1.07)
            elif ic < -0.05: new_w = max(0.05, old_w * 0.85)   # negative — pull down
            else:            new_w = old_w
            new_w = round(new_w, 4)
            new_weights[factor] = new_w
            if abs(new_w - old_w) > 0.005:
                weight_changes.append({
                    "factor": factor, "ic": ic,
                    "old_weight": round(old_w, 4),
                    "new_weight": new_w,
                })

        # Renormalize so they sum to 1.0 (defensive)
        total = sum(new_weights.values()) or 1.0
        new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

        # ── Threshold tuning ─────────────────────────────────────────────
        current_threshold = int(await get_config("confidence_threshold") or "65")
        new_threshold = current_threshold
        if win_rate < 0.40:
            new_threshold = min(current_threshold + 5, 80)
        elif win_rate > 0.65 and avg_pnl > 1.0:
            new_threshold = max(current_threshold - 5, 55)

        # ── AI insight (best-effort) ─────────────────────────────────────
        ai_insight = (
            f"Win rate: {win_rate*100:.0f}%. Avg P&L: {avg_pnl:.2f}%. "
            f"Threshold {current_threshold} → {new_threshold}. "
            f"Factor ICs: {factor_ics}."
        )
        try:
            from ai.llm import active_provider, call_llm_raw  # noqa: PLC0415
            if active_provider() != "none":
                wins_summary   = [{"stock": t["stock"], "pnl": t["pnl_pct"], "exit": t["exit_reason"]} for t in wins[:5]]
                losses_summary = [{"stock": t["stock"], "pnl": t["pnl_pct"], "exit": t["exit_reason"]} for t in losses[:5]]
                prompt = (
                    "Analyse these paper trading results. Be brutally honest.\n\n"
                    f"Wins ({len(wins)}): {json.dumps(wins_summary)}\n"
                    f"Losses ({len(losses)}): {json.dumps(losses_summary)}\n\n"
                    f"Factor IC (Spearman correlation with win/loss outcome):\n{json.dumps(factor_ics)}\n\n"
                    f"Win rate: {win_rate*100:.0f}% | Avg P&L: {avg_pnl:.2f}%\n"
                    f"Weight changes made: {json.dumps(weight_changes)}\n\n"
                    "In EXACTLY 3 bullet points, what patterns distinguish wins from losses? "
                    "Include specific factor names and IC values. Be concrete. "
                    "Respond as JSON: {\"insights\": [\"bullet 1\", \"bullet 2\", \"bullet 3\"]}"
                )
                try:
                    raw = await call_llm_raw(prompt, max_tokens=400, temperature=0.3)
                    data = json.loads(raw) if raw else {}
                    bullets = data.get("insights")
                    if isinstance(bullets, list) and bullets:
                        ai_insight = " | ".join(str(b) for b in bullets[:3])
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

        # ── Persist new weights and threshold ────────────────────────────
        for factor, w in new_weights.items():
            await set_config(f"weight_{factor}", str(w))
        await set_config("confidence_threshold", str(new_threshold))
        await set_config("weights_last_updated", datetime.now(IST).isoformat())

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO learning_insights
                     (insight_date, trades_analyzed, win_rate, avg_pnl,
                      confidence_ic, ai_insight, threshold_before, threshold_after)
                   VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?)""",
                (
                    len(trades), round(win_rate, 3), round(avg_pnl, 3),
                    round(max(factor_ics.values()) if factor_ics else 0.0, 3),
                    ai_insight + (f"\nWeight changes: {json.dumps(weight_changes)}" if weight_changes else ""),
                    current_threshold, new_threshold,
                ),
            )
            await db.commit()

        push_event("weights_updated", {
            "weight_changes": weight_changes,
            "factor_ics": factor_ics,
            "new_threshold": new_threshold,
            "new_weights": new_weights,
            "win_rate": round(win_rate * 100, 1),
        })
        push_event("insight_generated", {
            "insight": ai_insight[:200],
            "win_rate": round(win_rate * 100, 1),
            "threshold_change": f"{current_threshold} → {new_threshold}",
            "weight_changes_count": len(weight_changes),
        })

    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"[learning] Cycle error: {e}")


# ── Main loop (background task) ───────────────────────────────────────

async def engine_loop() -> None:
    """Run forever while _engine_running. Checks every minute."""
    global _engine_running

    print("[engine] Paper trading engine started")
    push_event("engine_started", {"message": "Engine initialized"})

    scan_interval_minutes = 30
    last_scan_slot = -1

    global _last_token_refresh_date
    while _engine_running:
        try:
            now = datetime.now(IST)

            # RULE 8: Kite token refresh at 8:45 AM IST every weekday
            if (now.weekday() < 5 and now.hour == 8 and now.minute == 45
                    and _last_token_refresh_date != now.date()):
                try:
                    from data.kite_client import kite as _kite  # noqa: PLC0415
                    _kite.refresh_token_if_needed()
                except Exception as e:  # noqa: BLE001
                    print(f"[engine] Kite token refresh failed: {e}")
                _last_token_refresh_date = now.date()

            if is_nse_open():
                await set_config("engine_status", "running")
                minutes_since_open = (
                    now - now.replace(hour=9, minute=15, second=0, microsecond=0)
                ).seconds // 60
                current_slot = minutes_since_open // scan_interval_minutes

                if current_slot != last_scan_slot:
                    last_scan_slot = current_slot
                    await morning_scan()

                # RULE 4: force-close intraday at 3:15 PM IST
                if now.hour == FORCE_CLOSE_HOUR and now.minute >= FORCE_CLOSE_MINUTE:
                    await _force_close_intraday_trades()

                await monitor_active_trades()
            else:
                await set_config("engine_status", "market_closed")
                last_scan_slot = -1

            await asyncio.sleep(60)

        except Exception as e:  # noqa: BLE001
            print(f"[engine] Loop error: {e}")
            await asyncio.sleep(60)

    await set_config("engine_status", "idle")
    print("[engine] Engine stopped")


# ── Public control ────────────────────────────────────────────────────

async def start_engine() -> None:
    global _engine_running
    if not _engine_running:
        _engine_running = True
        asyncio.create_task(engine_loop())
        await set_config("engine_running", "true")


async def stop_engine() -> None:
    global _engine_running
    _engine_running = False
    await set_config("engine_running", "false")


async def reload_active_trades() -> int:
    """On server restart, pick up any ACTIVE trades from DB so monitoring resumes.
    Also rebuilds the per-symbol lock set (RULE 3)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM paper_trades WHERE status='ACTIVE'"
        ) as cursor:
            rows = await cursor.fetchall()
    for row in rows:
        trade = dict(row)
        _active_trades[trade["trade_id"]] = trade
        _active_symbol_lock.add(trade.get("stock", ""))
    print(f"[engine] Reloaded {len(rows)} active trades from DB")
    return len(rows)
