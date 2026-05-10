"""Backtesting Engine — validates whether Phase 1 scoring has predictive power.

Processes 100 stocks × ~2 years of daily data → ~20,000 signal records.
Every indicator is recomputed on a rolling window slice that contains ONLY
data up to and including the signal date — no future data leaks in.

All ML uses TimeSeriesSplit so the suggested weights are honest.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import aiosqlite
import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

from .database import DB_PATH

# ── Dedicated thread pool for backtest CPU/IO work ───────────────────
# Isolated from FastAPI's default executor (which serves /api/price,
# /api/chart, /api/indicators sync handlers). 2 workers is enough for
# a yfinance-bound pipeline and guarantees the user-facing endpoints
# always have spare threads — the site stays responsive while the
# backtest runs.
_BACKTEST_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="backtest")

# Optional psutil for RSS memory in failure logs
try:
    import psutil  # type: ignore
    _PROC = psutil.Process(os.getpid())
except Exception:  # noqa: BLE001
    _PROC = None  # type: ignore


def _rss_mb() -> Optional[float]:
    if _PROC is None:
        return None
    try:
        return round(_PROC.memory_info().rss / (1024 * 1024), 2)
    except Exception:  # noqa: BLE001
        return None


# ── Research Infrastructure: checkpoint + failure helpers ─────────────

async def _init_progress_rows(run_id: str, symbols: List[str]) -> int:
    """Insert pending rows for every symbol. Returns number of NEW rows
    actually inserted (i.e. 0 if the run was already initialized)."""
    inserted = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for sym in symbols:
            cur = await db.execute(
                "INSERT OR IGNORE INTO backtest_progress (run_id, symbol, status) VALUES (?, ?, 'pending')",
                (run_id, sym),
            )
            inserted += cur.rowcount or 0
        await db.commit()
    return inserted


async def _get_completed_stocks(run_id: str) -> Set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT symbol FROM backtest_progress WHERE run_id = ? AND status = 'completed'",
            (run_id,),
        ) as cur:
            return {row[0] for row in await cur.fetchall()}


async def _mark_progress(
    run_id: str, symbol: str, status: str,
    signal_count: int = 0, error: Optional[str] = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        if status == "running":
            await db.execute(
                """UPDATE backtest_progress
                     SET status='running', started_at=?, error=NULL
                   WHERE run_id=? AND symbol=?""",
                (now, run_id, symbol),
            )
        elif status == "completed":
            await db.execute(
                """UPDATE backtest_progress
                     SET status='completed', completed_at=?, signal_count=?, error=NULL
                   WHERE run_id=? AND symbol=?""",
                (now, int(signal_count), run_id, symbol),
            )
        elif status == "failed":
            await db.execute(
                """UPDATE backtest_progress
                     SET status='failed', completed_at=?, signal_count=?, error=?
                   WHERE run_id=? AND symbol=?""",
                (now, int(signal_count), (error or "")[:2000], run_id, symbol),
            )
        else:
            await db.execute(
                "UPDATE backtest_progress SET status=? WHERE run_id=? AND symbol=?",
                (status, run_id, symbol),
            )
        await db.commit()


async def _log_failure(run_id: str, symbol: str, stage: str, exc: BaseException) -> None:
    tb = traceback.format_exc() or f"{type(exc).__name__}: {exc}"
    mem = _rss_mb()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO backtest_failures
                     (run_id, symbol, stage, traceback, memory_mb, created_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (run_id, symbol, stage, tb[:8000], mem),
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[failure_log] write failed for {symbol}/{stage}: {e}")


# ── Research Infrastructure: post-run validation suite ────────────────

async def _validate_run(run_id: str, expected_stock_count: int) -> Dict[str, Any]:
    """Run integrity checks. Stores a report and may flip run status to 'invalid'."""
    checks: Dict[str, Any] = {}
    passed = True

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # completed stock count from checkpoint table
        async with db.execute(
            "SELECT COUNT(*) FROM backtest_progress WHERE run_id=? AND status='completed'",
            (run_id,),
        ) as cur:
            done = (await cur.fetchone())[0]
        checks["expected_stock_count"] = expected_stock_count
        checks["completed_stock_count"] = done
        checks["meets_stock_count"] = done > 0

        # signal counts (over the whole table — matches what this run wrote, since
        # run_full_backtest clears prior signals on a fresh run)
        async with db.execute("SELECT COUNT(*) FROM backtest_signals") as cur:
            sig_count = (await cur.fetchone())[0]
        checks["signal_count"] = sig_count
        checks["signal_count_gt_zero"] = sig_count > 0

        async with db.execute(
            "SELECT stock, date, COUNT(*) c FROM backtest_signals GROUP BY stock, date HAVING c > 1 LIMIT 5"
        ) as cur:
            dups = await cur.fetchall()
        checks["duplicate_stock_date_count"] = len(dups)
        checks["duplicate_samples"] = [dict(r) for r in dups]

        async with db.execute(
            """SELECT COUNT(*) FROM backtest_signals
                 WHERE forward_return_1d IS NULL
                    OR forward_return_5d IS NULL
                    OR forward_return_20d IS NULL"""
        ) as cur:
            null_fwd = (await cur.fetchone())[0]
        checks["null_forward_returns"] = null_fwd

        async with db.execute(
            """SELECT COUNT(*) FROM backtest_signals
                 WHERE rsi IS NULL OR adx IS NULL OR macd_hist IS NULL
                    OR volume_ratio IS NULL OR close_price IS NULL"""
        ) as cur:
            null_ind = (await cur.fetchone())[0]
        checks["nan_or_null_indicators"] = null_ind

        today_str = datetime.now().strftime("%Y-%m-%d")
        async with db.execute(
            "SELECT COUNT(*) FROM backtest_signals WHERE date > ?",
            (today_str,),
        ) as cur:
            future = (await cur.fetchone())[0]
        checks["future_dated_signals"] = future

        passed = bool(
            checks["meets_stock_count"]
            and checks["signal_count_gt_zero"]
            and checks["duplicate_stock_date_count"] == 0
            and checks["null_forward_returns"] == 0
            and checks["nan_or_null_indicators"] == 0
            and checks["future_dated_signals"] == 0
        )

        await db.execute(
            """INSERT INTO backtest_validation_reports
                 (run_id, passed, checks_json, created_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (run_id, 1 if passed else 0, json.dumps(checks)),
        )
        if not passed:
            await db.execute(
                "UPDATE backtest_runs SET status='invalid' WHERE run_id_external = ?",
                (run_id,),
            )
        await db.commit()

    return {"run_id": run_id, "passed": passed, "checks": checks}

# ── Disk cache for downloaded stock history ───────────────────────────
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL_HOURS = 24
CACHE_MAX_AGE_HOURS = 24  # alias used by Phase 4

# ── In-memory progress tracking ───────────────────────────────────────
_progress: Dict[str, Dict[str, Any]] = {}
# Set of run_ids currently being processed inside this Python process.
# Prevents the same run from being launched twice (e.g. the auto-resume
# task firing while a manual resume is also in flight).
_RUNNING_RUNS: Set[str] = set()


def get_progress(run_id: str) -> Dict[str, Any]:
    return _progress.get(
        run_id,
        {
            "status": "not_found",
            "stocks_done": 0,
            "stocks_total": 0,
            "current_stock": "",
            "percent_complete": 0,
        },
    )


# ── Data fetching with disk cache ─────────────────────────────────────

def fetch_stock_history(symbol: str) -> Optional[pd.DataFrame]:
    """Backwards-compat shim — Phase 4 uses ``fetch_stock_history_max`` instead."""
    return fetch_stock_history_max(symbol)


def fetch_stock_history_max(symbol: str) -> Optional[pd.DataFrame]:
    """Fetch MAXIMUM available history (up to ~10 years) for a symbol.

    Cached to parquet on disk (24-hour TTL). Strict data-quality filtering:
    drops zero/negative prices and outliers >10x off the 20-day rolling median.
    Returns ``None`` if fewer than 252 trading days survive cleaning.
    """
    safe_name = symbol.replace(".", "_").replace("&", "_AND_")
    cache_file = os.path.join(CACHE_DIR, f"{safe_name}.parquet")

    if os.path.exists(cache_file):
        age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
        if age_hours < CACHE_MAX_AGE_HOURS:
            try:
                df = pd.read_parquet(cache_file)
                if len(df) > 252:
                    return df
            except Exception:  # noqa: BLE001
                pass  # fall through and re-download

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="max", interval="1d", auto_adjust=True, actions=False)
    except Exception as e:  # noqa: BLE001
        print(f"[fetch_max] {symbol}: {e}")
        return None

    if df is None or df.empty or len(df) < 252:
        return None

    df.index = pd.to_datetime(df.index).tz_localize(None)
    cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    df = df[cols].copy()

    # Quality filter: bad ticks
    df = df[(df["Close"] > 0) & (df["Open"] > 0)]
    if len(df) > 20:
        rolling_med = df["Close"].rolling(20, min_periods=5).median().replace(0, np.nan)
        ratio = df["Close"] / rolling_med
        df = df[(ratio > 0.1) & (ratio < 10)]

    if len(df) < 252:
        return None

    try:
        df.to_parquet(cache_file)
    except Exception as e:  # noqa: BLE001
        print(f"[fetch_max] cache write failed for {symbol}: {e}")

    print(f"[cache] {symbol}: {df.index[0].date()} → {df.index[-1].date()} "
          f"({len(df)} days, {len(df)/252:.1f}yr)")
    return df


# ── Point-in-time indicator pipeline ──────────────────────────────────

def compute_indicators_for_slice(df_slice: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Compute every indicator using ONLY data up to the current bar.

    Returns None if there's insufficient history or any computation fails.
    """
    if len(df_slice) < 30:
        return None

    try:
        close = df_slice["Close"]
        high = df_slice["High"]
        low = df_slice["Low"]
        volume = df_slice["Volume"]
        current_price = float(close.iloc[-1])

        # ── RSI (Wilder's smoothing) ──
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi_val = float((100 - (100 / (1 + rs))).iloc[-1])
        if not np.isfinite(rsi_val):
            rsi_val = 50.0

        # ── MACD (12, 26, 9) ──
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line
        macd_hist = float(hist.iloc[-1])
        # Crossover within last 3 bars: latest > 0 AND any of last 3 was <= 0
        macd_cross = int(
            len(hist) >= 3
            and macd_hist > 0
            and (hist.iloc[-2] <= 0 or hist.iloc[-3] <= 0)
        )

        # ── EMAs ──
        ema9 = float(close.ewm(span=9, adjust=False).mean().iloc[-1])
        ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
        ema_above_count = int(sum([
            current_price > ema9,
            current_price > ema20,
            current_price > ema50,
            current_price > ema200,
        ]))

        # ── ADX (14) ──
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = tr.ewm(span=14, adjust=False).mean()

        plus_dm = high.diff().clip(lower=0)
        minus_dm = (-low.diff()).clip(lower=0)
        plus_di = 100 * plus_dm.ewm(span=14, adjust=False).mean() / atr14.replace(0, np.nan)
        minus_di = 100 * minus_dm.ewm(span=14, adjust=False).mean() / atr14.replace(0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx_val = float(dx.ewm(span=14, adjust=False).mean().iloc[-1])
        if not np.isfinite(adx_val):
            adx_val = 0.0

        # ── Bollinger Bands (20, 2σ) + squeeze ──
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_width = (bb_upper - bb_lower) / bb_mid

        recent_widths = bb_width.dropna().tail(60)
        bb_squeeze = int(
            len(recent_widths) > 20
            and float(bb_width.iloc[-1]) < float(np.percentile(recent_widths, 20))
        )

        # ── Volume ──
        vol_avg20 = float(volume.rolling(20).mean().iloc[-1])
        volume_ratio = float(volume.iloc[-1] / vol_avg20) if vol_avg20 > 0 else 1.0

        # ── OBV trend ──
        sign = (close.diff() > 0).astype(int) - (close.diff() < 0).astype(int)
        obv = (volume * sign).cumsum()
        obv_slope = float(obv.tail(20).diff().mean())
        obv_trend = "rising" if obv_slope > 0 else "falling"

        # ── VWAP (rolling 20-bar volume-weighted avg) ──
        typical = (high + low + close) / 3
        rolling_pv = (typical * volume).rolling(20).sum()
        rolling_v = volume.rolling(20).sum()
        vwap = float(rolling_pv.iloc[-1] / rolling_v.iloc[-1]) if rolling_v.iloc[-1] > 0 else current_price
        vwap_above = int(current_price > vwap)

        # ── Supertrend (simplified — band cross check) ──
        atr_now = float(atr14.iloc[-1]) if np.isfinite(atr14.iloc[-1]) else 0.0
        midpoint = (float(high.iloc[-1]) + float(low.iloc[-1])) / 2
        lower_band = midpoint - 3 * atr_now
        supertrend_bullish = int(current_price > lower_band)

        return {
            "rsi": rsi_val,
            "macd_hist": macd_hist,
            "macd_cross": macd_cross,
            "adx": adx_val,
            "bb_squeeze": bb_squeeze,
            "ema_above_count": ema_above_count,
            "obv_trend": obv_trend,
            "volume_ratio": volume_ratio,
            "supertrend_bullish": supertrend_bullish,
            "vwap_above": vwap_above,
        }
    except Exception:  # noqa: BLE001
        return None


# ── Scoring (mirrors Phase 1 score_stock logic for backtest data) ─────

def score_from_indicators(ind: Dict[str, Any], mode: str = "intraday") -> int:
    """Replicate Phase 1 scoring using historical indicator dict.

    The historical indicator dict has slightly different keys than the
    live one (e.g. macd_cross int vs macd_crossover string), so this
    function bridges the two.
    """
    score = 0

    rsi = ind.get("rsi", 50)
    if 40 <= rsi <= 65:
        score += 8
    elif rsi > 75:
        score -= 5

    if ind.get("macd_cross"):
        score += 10
    if ind.get("macd_hist", 0) > 0:
        score += 5

    ema_count = int(ind.get("ema_above_count", 0))
    score += [0, 4, 10, 18, 24][min(ema_count, 4)]

    adx = ind.get("adx", 0)
    if adx > 25:
        score += 5
    elif adx < 15:
        score -= 3

    vol_ratio = ind.get("volume_ratio", 1.0)
    if vol_ratio > 1.5:
        score += 12
    elif vol_ratio > 1.2:
        score += 7
    elif vol_ratio < 0.7:
        score -= 5

    if ind.get("obv_trend") == "rising":
        score += 8
    if ind.get("supertrend_bullish"):
        score += 5
    if ind.get("vwap_above"):
        score += 8
    if ind.get("bb_squeeze"):
        score += 5

    return max(0, min(100, score))


# ── Main backtest runner (background task) ────────────────────────────

def _process_stock_blocking(symbol: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
    """All per-stock indicator + signal computation in ONE synchronous call.

    Designed to be dispatched to a thread executor so the event loop stays
    free while ~2,000 pandas slice operations run for each stock.
    Returns a list of signal-dict rows ready for batch insert.
    """
    signals: List[Dict[str, Any]] = []
    dates = df.index.tolist()
    closes = df["Close"].values
    warmup = 60

    for day_idx in range(warmup, len(dates) - 21):
        slice_df = df.iloc[: day_idx + 1]
        ind = compute_indicators_for_slice(slice_df)
        if ind is None:
            continue

        score = score_from_indicators(ind)
        close_d = float(closes[day_idx])
        if close_d <= 0:
            continue

        fwd_1d  = (float(closes[day_idx + 1])  - close_d) / close_d if day_idx + 1  < len(closes) and closes[day_idx + 1]  > 0 else None
        fwd_5d  = (float(closes[day_idx + 5])  - close_d) / close_d if day_idx + 5  < len(closes) and closes[day_idx + 5]  > 0 else None
        fwd_20d = (float(closes[day_idx + 20]) - close_d) / close_d if day_idx + 20 < len(closes) and closes[day_idx + 20] > 0 else None

        if fwd_1d is None or fwd_5d is None or fwd_20d is None:
            continue
        if abs(fwd_1d) > 0.50 or abs(fwd_5d) > 1.0 or abs(fwd_20d) > 2.0:
            continue

        signals.append({
            "stock": symbol,
            "date": dates[day_idx].strftime("%Y-%m-%d"),
            "score": score,
            "rsi": ind["rsi"],
            "macd_hist": ind["macd_hist"],
            "macd_cross": ind["macd_cross"],
            "adx": ind["adx"],
            "bb_squeeze": ind["bb_squeeze"],
            "ema_above_count": ind["ema_above_count"],
            "obv_trend": ind["obv_trend"],
            "volume_ratio": ind["volume_ratio"],
            "supertrend_bullish": ind["supertrend_bullish"],
            "vwap_above": ind["vwap_above"],
            "close_price": close_d,
            "forward_return_1d": fwd_1d,
            "forward_return_5d": fwd_5d,
            "forward_return_20d": fwd_20d,
        })

    return signals


async def run_full_backtest(run_id: str, symbols: List[str], resume: bool = False) -> None:
    """Phase 4 backtest:
      * Fetches MAX available history (8-10y typical) per stock.
      * 60-bar warmup so EMA200 has enough history.
      * All 3 horizons (1d / 5d / 20d) required to record a signal.
      * Forward-return sanity caps reject |1d|>50%, |5d|>100%, |20d|>200%
        — catches data corruption from delistings / unadjusted splits.
      * Reports max_years_data and skip count back via ``_progress``.

    Checkpointing: every symbol is tracked in ``backtest_progress``. If a
    previous attempt for the same ``run_id`` already completed any symbol
    those are skipped automatically (resume-safe).
    """
    # Guard: refuse to launch the same run_id twice concurrently. This
    # closes the duplicate-signal hole that filled the DB with millions
    # of redundant rows the previous time the user kicked off the
    # backtest while another copy was still running.
    if run_id in _RUNNING_RUNS:
        print(f"[backtest] run_id={run_id} already running in this process — skipping duplicate launch")
        return
    _RUNNING_RUNS.add(run_id)

    try:
        await _run_full_backtest_body(run_id, symbols, resume)
    finally:
        _RUNNING_RUNS.discard(run_id)


async def _run_full_backtest_body(run_id: str, symbols: List[str], resume: bool) -> None:
    start_time = time.time()
    total = len(symbols)
    processed = 0
    skipped = 0
    all_signals_count = 0
    max_years = 0.0
    quality_report: List[Dict[str, Any]] = []

    # Initialize / refresh checkpoint table
    new_rows = await _init_progress_rows(run_id, symbols)
    completed_already = await _get_completed_stocks(run_id)
    is_fresh_run = new_rows == total and not completed_already

    _progress[run_id] = {
        "status": "running",
        "stocks_done": len(completed_already),
        "stocks_total": total,
        "current_stock": "Starting...",
        "percent_complete": int(len(completed_already) / total * 100) if total else 0,
        "total_signals": 0,
        "skipped": 0,
        "max_years_data": 0.0,
        "resumed": bool(completed_already) or resume,
    }

    async with aiosqlite.connect(DB_PATH) as db:
        if is_fresh_run:
            await db.execute(
                """INSERT INTO backtest_runs (run_date, stocks_processed, total_signals, status, run_id_external)
                   VALUES (datetime('now'), 0, 0, 'running', ?)""",
                (run_id,),
            )
            await db.execute("DELETE FROM backtest_signals")
        else:
            # Resume: ensure a run row exists for this run_id; otherwise
            # mark it running again (do NOT touch existing signals).
            cur = await db.execute(
                "SELECT id FROM backtest_runs WHERE run_id_external = ? ORDER BY id DESC LIMIT 1",
                (run_id,),
            )
            row = await cur.fetchone()
            if row is None:
                await db.execute(
                    """INSERT INTO backtest_runs (run_date, stocks_processed, total_signals, status, run_id_external)
                       VALUES (datetime('now'), 0, 0, 'running', ?)""",
                    (run_id,),
                )
            else:
                await db.execute(
                    "UPDATE backtest_runs SET status='running' WHERE run_id_external = ?",
                    (run_id,),
                )
            # Also wipe any partial signals for stocks we are about to retry
            to_retry = [s for s in symbols if s not in completed_already]
            if to_retry:
                placeholders = ",".join(["?"] * len(to_retry))
                await db.execute(
                    f"DELETE FROM backtest_signals WHERE stock IN ({placeholders})",
                    to_retry,
                )
        await db.commit()

    loop = asyncio.get_event_loop()
    earliest_date = ""
    latest_date   = ""

    for i, symbol in enumerate(symbols):
        # Skip stocks already completed in a prior attempt
        if symbol in completed_already:
            continue
        _progress[run_id].update({
            "current_stock": symbol,
            "stocks_done": i,
            "percent_complete": int(i / total * 100),
            "total_signals": all_signals_count,
            "skipped": skipped,
            "max_years_data": round(max_years, 1),
        })

        await _mark_progress(run_id, symbol, "running")
        stage = "download"
        try:
            df = await loop.run_in_executor(_BACKTEST_EXECUTOR, fetch_stock_history_max, symbol)

            if df is None or len(df) < 252:
                skipped += 1
                quality_report.append({"symbol": symbol, "valid": False, "reason": "no_data_or_short"})
                await _mark_progress(run_id, symbol, "failed", 0, "no_data_or_short")
                continue

            years = len(df) / 252.0
            if years > max_years:
                max_years = years
            quality_report.append({
                "symbol": symbol, "valid": True,
                "years": round(years, 1),
                "start": str(df.index[0].date()),
                "days":  int(len(df)),
            })

            # CRITICAL: per-stock indicator+signal computation runs in a thread.
            stage = "indicator_computation"
            signals_for_stock: List[Dict[str, Any]] = await loop.run_in_executor(
                _BACKTEST_EXECUTOR, _process_stock_blocking, symbol, df
            )

            # Cancellation check — RULE 9 — between stocks (next stock won't start)
            if _progress.get(run_id, {}).get("status") == "cancelled":
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("DELETE FROM backtest_signals")
                    await db.execute(
                        "UPDATE backtest_runs SET status='cancelled' WHERE status='running'"
                    )
                    await db.commit()
                _progress[run_id]["current_stock"] = "Cancelled"
                _progress[run_id]["percent_complete"] = int(i / total * 100)
                print(f"[backtest] Cancelled at {i}/{total}")
                return

            if signals_for_stock:
                stage = "db_insert"
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.executemany(
                        """INSERT INTO backtest_signals
                           (stock, date, score, rsi, macd_hist, macd_cross, adx,
                            bb_squeeze, ema_above_count, obv_trend, volume_ratio,
                            supertrend_bullish, vwap_above, close_price,
                            forward_return_1d, forward_return_5d, forward_return_20d)
                           VALUES (:stock, :date, :score, :rsi, :macd_hist, :macd_cross,
                                   :adx, :bb_squeeze, :ema_above_count, :obv_trend,
                                   :volume_ratio, :supertrend_bullish, :vwap_above,
                                   :close_price, :forward_return_1d, :forward_return_5d,
                                   :forward_return_20d)""",
                        signals_for_stock,
                    )
                    await db.commit()
                all_signals_count += len(signals_for_stock)
                processed += 1

                # Track date range across all signals
                first_date = signals_for_stock[0]["date"]
                last_date  = signals_for_stock[-1]["date"]
                if not earliest_date or first_date < earliest_date:
                    earliest_date = first_date
                if not latest_date or last_date > latest_date:
                    latest_date = last_date

            await _mark_progress(run_id, symbol, "completed", len(signals_for_stock))

        except Exception as e:  # noqa: BLE001
            print(f"[backtest] {symbol}: ERROR ({stage}) — {e}")
            await _log_failure(run_id, symbol, stage, e)
            await _mark_progress(run_id, symbol, "failed", 0, f"{stage}: {e}")
            skipped += 1
            continue

        # Rate-limit yfinance — do not lower this
        await asyncio.sleep(0.8)

    duration = time.time() - start_time

    async with aiosqlite.connect(DB_PATH) as db:
        # Prefer the row keyed by run_id_external; fall back to the legacy
        # status='running' update for runs created before that column existed.
        cur = await db.execute(
            "SELECT id FROM backtest_runs WHERE run_id_external = ? LIMIT 1",
            (run_id,),
        )
        row = await cur.fetchone()
        if row is not None:
            await db.execute(
                """UPDATE backtest_runs SET
                     stocks_processed = ?,
                     total_signals    = ?,
                     status           = 'complete',
                     duration_seconds = ?,
                     date_range_start = ?,
                     date_range_end   = ?
                   WHERE run_id_external = ?""",
                (processed, all_signals_count, duration, earliest_date, latest_date, run_id),
            )
        else:
            await db.execute(
                """UPDATE backtest_runs SET
                     stocks_processed = ?,
                     total_signals    = ?,
                     status           = 'complete',
                     duration_seconds = ?,
                     date_range_start = ?,
                     date_range_end   = ?
                   WHERE status = 'running'""",
                (processed, all_signals_count, duration, earliest_date, latest_date),
            )
        await db.commit()

    # Run integrity validation. May flip status to 'invalid'.
    try:
        validation = await _validate_run(run_id, total)
        _progress[run_id]["validation_passed"] = validation["passed"]
    except Exception as e:  # noqa: BLE001
        await _log_failure(run_id, "<run>", "validation", e)
        _progress[run_id]["validation_passed"] = False

    _progress[run_id].update({
        "status": "complete",
        "stocks_done": total,
        "percent_complete": 100,
        "current_stock": "Complete",
        "total_signals": all_signals_count,
        "processed": processed,
        "skipped": skipped,
        "duration_minutes": round(duration / 60.0, 1),
        "max_years_data": round(max_years, 1),
        "quality_report": quality_report[:20],
    })

    print(f"[backtest] DONE: {processed} stocks, {all_signals_count:,} signals, "
          f"{duration/60.0:.1f}min, max {max_years:.1f}yr history")


# ── Analysis: score buckets ───────────────────────────────────────────

def _score_bucket_blocking(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"error": "No backtest data. Run backtest first."}
    df = pd.DataFrame(rows)
    buckets = [
        ("0-30",  (df["score"] >= 0) & (df["score"] < 30)),
        ("30-50", (df["score"] >= 30) & (df["score"] < 50)),
        ("50-60", (df["score"] >= 50) & (df["score"] < 60)),
        ("60-70", (df["score"] >= 60) & (df["score"] < 70)),
        ("70-80", (df["score"] >= 70) & (df["score"] < 80)),
        ("80+",   (df["score"] >= 80)),
    ]
    results: List[Dict[str, Any]] = []
    for label, mask in buckets:
        subset = df[mask]
        if len(subset) < 5:
            continue
        for horizon in (1, 5, 20):
            col = f"forward_return_{horizon}d"
            returns = subset[col].dropna()
            if len(returns) < 5:
                continue
            avg_ret = float(returns.mean()); std_ret = float(returns.std())
            win_rate = float((returns > 0).mean())
            sharpe = float(avg_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
            results.append({
                "bucket": label, "horizon_days": horizon,
                "avg_return_pct": round(avg_ret * 100, 3),
                "win_rate": round(win_rate * 100, 1),
                "sharpe": round(sharpe, 2), "count": int(len(returns)),
            })
    return {"buckets": results}


async def score_bucket_analysis() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT score, forward_return_1d, forward_return_5d, forward_return_20d
               FROM backtest_signals WHERE forward_return_1d IS NOT NULL"""
        ) as cursor:
            rows = await cursor.fetchall()
    rows_list = [dict(r) for r in rows]
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _score_bucket_blocking, rows_list)


# ── Analysis: per-indicator IC (Spearman) ─────────────────────────────

def _signal_ic_blocking(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"error": "No data"}
    df = pd.DataFrame(rows)
    target = df["forward_return_5d"]

    indicators = {
        "RSI": "rsi",
        "MACD Histogram": "macd_hist",
        "MACD Crossover": "macd_cross",
        "ADX": "adx",
        "BB Squeeze": "bb_squeeze",
        "EMA Stack Count": "ema_above_count",
        "Volume Ratio": "volume_ratio",
        "Supertrend Bullish": "supertrend_bullish",
        "VWAP Above": "vwap_above",
        "Composite Score": "score",
    }

    results: List[Dict[str, Any]] = []
    for name, col in indicators.items():
        series = df[col].dropna()
        common_idx = series.index.intersection(target.dropna().index)
        if len(common_idx) < 50:
            continue
        ic, pvalue = stats.spearmanr(series[common_idx], target[common_idx])
        if not np.isfinite(ic):
            continue
        ic_abs = abs(float(ic))
        if ic_abs > 0.10:
            strength = "Strong Alpha"
        elif ic_abs > 0.05:
            strength = "Meaningful Alpha"
        elif ic_abs > 0.02:
            strength = "Weak Alpha"
        else:
            strength = "No Edge"
        results.append(
            {
                "indicator": name,
                "ic": round(float(ic), 4),
                "ic_abs": round(ic_abs, 4),
                "p_value": round(float(pvalue), 4),
                "significant": bool(pvalue < 0.05),
                "strength": strength,
                "n_observations": int(len(common_idx)),
            }
        )

    results.sort(key=lambda x: x["ic_abs"], reverse=True)
    return {"indicators": results}


async def signal_ic_analysis() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT rsi, macd_hist, macd_cross, adx, bb_squeeze,
                      ema_above_count, volume_ratio, supertrend_bullish,
                      vwap_above, score, forward_return_5d
               FROM backtest_signals WHERE forward_return_5d IS NOT NULL"""
        ) as cursor:
            rows = await cursor.fetchall()
    rows_list = [dict(r) for r in rows]
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _signal_ic_blocking, rows_list)


# ── Analysis: optimal weights via TimeSeriesSplit + RidgeCV ───────────

def _optimal_weights_blocking(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Heavy sklearn work — designed to run in a thread executor."""
    from sklearn.linear_model import RidgeCV
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score
    from sklearn.preprocessing import StandardScaler

    if len(rows) < 200:
        return {"error": "Insufficient data for regression (need ≥ 200 signals)"}

    df = pd.DataFrame(rows).dropna()
    feature_cols = [
        "rsi", "macd_hist", "macd_cross", "adx", "bb_squeeze",
        "ema_above_count", "volume_ratio", "supertrend_bullish", "vwap_above",
    ]
    X = df[feature_cols].values
    y = df["forward_return_5d"].values

    tscv = TimeSeriesSplit(n_splits=5)
    X_scaled = StandardScaler().fit_transform(X)

    alphas = [0.01, 0.1, 1.0, 10.0, 100.0]
    ridge = RidgeCV(alphas=alphas, cv=tscv)
    ridge.fit(X_scaled, y)

    coefs = ridge.coef_
    coef_abs = np.abs(coefs)
    normalized = coef_abs / coef_abs.sum() * 100 if coef_abs.sum() > 0 else np.zeros_like(coef_abs)

    current_weights = {
        "rsi": 8, "macd_hist": 5, "macd_cross": 10, "adx": 5,
        "bb_squeeze": 5, "ema_above_count": 24, "volume_ratio": 12,
        "supertrend_bullish": 5, "vwap_above": 8,
    }

    results = []
    for i, col in enumerate(feature_cols):
        suggested = round(float(normalized[i]), 1)
        current = current_weights.get(col, 0)
        diff = suggested - current
        results.append({
            "indicator": col.replace("_", " ").title(),
            "current_weight": current,
            "suggested_weight": suggested,
            "raw_coefficient": round(float(coefs[i]), 6),
            "direction": "positive" if coefs[i] > 0 else "negative",
            "change": round(diff, 1),
            "change_direction": "increase" if diff > 2 else ("decrease" if diff < -2 else "maintain"),
        })

    r2_scores = cross_val_score(ridge, X_scaled, y, cv=tscv, scoring="r2")
    return {
        "weights": sorted(results, key=lambda x: x["suggested_weight"], reverse=True),
        "r2_score": round(float(r2_scores.mean()), 4),
        "best_alpha": round(float(ridge.alpha_), 3),
        "note": "Ridge Regression with TimeSeriesSplit CV",
    }


async def optimal_weights() -> Dict[str, Any]:
    """Pull data from DB, then run sklearn in a thread (no event-loop blocking)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT rsi, macd_hist, macd_cross, adx, bb_squeeze,
                      ema_above_count, volume_ratio, supertrend_bullish,
                      vwap_above, forward_return_5d
               FROM backtest_signals
               WHERE forward_return_5d IS NOT NULL
               ORDER BY date ASC"""
        ) as cursor:
            rows = await cursor.fetchall()

    rows_dict = [dict(r) for r in rows]
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _optimal_weights_blocking, rows_dict)


# ── Analysis: strategy performance vs Nifty ───────────────────────────

async def strategy_performance() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT score, date, stock, forward_return_5d, close_price
               FROM backtest_signals
               WHERE forward_return_5d IS NOT NULL
               ORDER BY date ASC"""
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        return {"error": "No data"}

    df = pd.DataFrame([dict(r) for r in rows])

    # Cached Nifty benchmark — keeps the page snappy
    bench = await _nifty_benchmarks_cached()
    nifty_return = bench.get("total_2y", 0.0)

    thresholds = [50, 60, 70, 80]
    results: Dict[str, Any] = {}

    for threshold in thresholds:
        qualifying = df[df["score"] >= threshold]

        if len(qualifying) < 10:
            results[str(threshold)] = {"error": "Insufficient trades"}
            continue

        returns = qualifying["forward_return_5d"].values
        avg_return = float(np.mean(returns))
        std_return = float(np.std(returns))
        win_rate = float((returns > 0).mean() * 100)
        sharpe = float(avg_return / std_return * np.sqrt(252 / 5)) if std_return > 0 else 0.0

        daily = qualifying.groupby("date")["forward_return_5d"].mean()
        cumulative = float(((1 + daily).cumprod().iloc[-1] - 1) * 100)

        cum_series = (1 + daily).cumprod()
        rolling_max = cum_series.cummax()
        drawdown = (cum_series - rolling_max) / rolling_max
        max_dd = float(drawdown.min() * 100) if not drawdown.empty else 0.0

        results[str(threshold)] = {
            "threshold": threshold,
            "total_trades": int(len(qualifying)),
            "unique_stocks": int(qualifying["stock"].nunique()),
            "avg_return_pct": round(avg_return * 100, 3),
            "win_rate": round(win_rate, 1),
            "sharpe_ratio": round(sharpe, 2),
            "cumulative_return_pct": round(cumulative, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "best_trade_pct": round(float(np.max(returns)) * 100, 2),
            "worst_trade_pct": round(float(np.min(returns)) * 100, 2),
            "beats_nifty": cumulative > nifty_return,
            "alpha_vs_nifty": round(cumulative - nifty_return, 2),
            "daily_returns": [
                {"date": str(d), "return": round(float(r) * 100, 3)}
                for d, r in daily.items()
            ][:200],
        }

    return {
        "thresholds": results,
        "nifty_2y_return_pct": round(nifty_return, 2),
        "benchmark": "Nifty 50 (^NSEI)",
    }


# ── Lightweight summary card ──────────────────────────────────────────

async def get_backtest_summary() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM backtest_signals") as cursor:
            row = await cursor.fetchone()
            total_signals = row[0] if row else 0

        async with db.execute(
            """SELECT run_date, duration_seconds FROM backtest_runs
               WHERE status='complete' ORDER BY id DESC LIMIT 1"""
        ) as cursor:
            run_row = await cursor.fetchone()

    if total_signals == 0:
        return {"has_data": False, "message": "No backtest data. Click 'Run Full Backtest'."}

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT AVG(forward_return_5d), COUNT(*),
                      AVG(CASE WHEN forward_return_5d > 0 THEN 1.0 ELSE 0.0 END)
               FROM backtest_signals WHERE score >= 70"""
        ) as cursor:
            row = await cursor.fetchone()
            avg_ret_70 = float(row[0] or 0) * 100
            count_70 = row[1] or 0
            win_rate_70 = float(row[2] or 0) * 100

    return {
        "has_data": True,
        "total_signals": int(total_signals),
        "last_run_date": run_row[0] if run_row else "Unknown",
        "duration_seconds": float(run_row[1]) if run_row and run_row[1] else 0.0,
        "score_70_avg_5d_return": round(avg_ret_70, 3),
        "score_70_win_rate": round(win_rate_70, 1),
        "score_70_count": int(count_70),
        "score_70_has_edge": bool(avg_ret_70 > 0.2),
    }


# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — Transaction costs, Walk-Forward Analysis, all-horizon perf,
# and AI weight recommendations.
# ════════════════════════════════════════════════════════════════════════

# Indian retail cost model (round-trip, conservative):
#   Brokerage + STT + GST + exchange + SEBI + stamp duty + slippage
TRANSACTION_COSTS = {
    "intraday":  0.0008,   # 0.08% round-trip
    "shortterm": 0.0015,   # 0.15% round-trip (delivery taxes higher)
    "default":   0.0010,
}
SLIPPAGE = {
    "large_cap": 0.0005,   # liquid Nifty 50 names
    "mid_cap":   0.0015,   # midcap stocks
}

# 1-hour cache for Nifty benchmark — avoids the slow yfinance fetch on every
# /api/backtest/results call.
_NIFTY_BENCH_CACHE: Dict[str, Any] = {"data": None, "expires": 0.0}


async def _nifty_benchmarks_cached() -> Dict[str, float]:
    """Return per-period Nifty avg returns. Cached 1h to keep the page snappy."""
    now = time.time()
    if _NIFTY_BENCH_CACHE["data"] and now < _NIFTY_BENCH_CACHE["expires"]:
        return _NIFTY_BENCH_CACHE["data"]

    def _blocking() -> Dict[str, float]:
        out = {"1d": 0.04, "5d": 0.18, "20d": 0.70, "total_2y": 0.0}
        try:
            hist = yf.Ticker("^NSEI").history(period="2y", interval="1d")
            if not hist.empty:
                closes = hist["Close"]
                out["1d"]  = float((closes.diff() / closes.shift()).mean() * 100)
                out["5d"]  = float(((closes.shift(-5)  - closes) / closes).mean() * 100)
                out["20d"] = float(((closes.shift(-20) - closes) / closes).mean() * 100)
                out["total_2y"] = float((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100)
        except Exception:  # noqa: BLE001
            pass
        return out

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _blocking)
    _NIFTY_BENCH_CACHE["data"] = data
    _NIFTY_BENCH_CACHE["expires"] = now + 3600  # 1 hour
    return data


def apply_transaction_costs(gross_return: float, mode: str = "intraday") -> float:
    """Subtract realistic Indian retail round-trip cost + slippage."""
    cost = TRANSACTION_COSTS.get(mode, TRANSACTION_COSTS["default"])
    slip = SLIPPAGE["large_cap"]  # default to large-cap; midcap names are sparse in our universe
    return gross_return - cost - slip


# ── Walk-Forward Analysis ───────────────────────────────────────────────

async def walk_forward_analysis(symbols: List[str] | None = None) -> Dict[str, Any]:
    """Walk-Forward Analysis on stored backtest_signals.

    Train: 12 months → Purge: 10 trading days → Test: 3 months. Slide forward.
    The threshold is selected on TRAIN data (in-sample), then applied to TEST
    data (genuinely unseen). Net of transaction costs. Reports avg metrics
    across all out-of-sample windows for 1d / 5d / 20d horizons.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT date, stock, score, forward_return_1d, forward_return_5d,
                      forward_return_20d, volume_ratio
               FROM backtest_signals
               WHERE forward_return_5d IS NOT NULL
               ORDER BY date ASC"""
        ) as cursor:
            rows = await cursor.fetchall()

    if len(rows) < 500:
        return {"error": f"Insufficient data for WFA (need ≥500, have {len(rows)})."}

    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    dates = pd.Series(df["date"].unique())
    n_dates = len(dates)

    train_days = 12 * 21    # ~12 months
    test_days  = 3 * 21     # ~3 months
    purge_days = 10         # gap between train and test

    oos_results: List[Dict[str, Any]] = []
    window_results: List[Dict[str, Any]] = []

    start_idx = 0
    while start_idx + train_days + purge_days + test_days <= n_dates:
        train_end_idx  = start_idx + train_days
        test_start_idx = train_end_idx + purge_days
        test_end_idx   = test_start_idx + test_days

        train_dates = dates.iloc[start_idx:train_end_idx]
        test_dates  = dates.iloc[test_start_idx:test_end_idx]

        train_df = df[df["date"].isin(train_dates)]
        test_df  = df[df["date"].isin(test_dates)]
        if len(test_df) < 50:
            start_idx += test_days
            continue

        # Pick optimal threshold on TRAIN ONLY (no leakage)
        best_threshold = 60
        best_train_sharpe = -999.0
        for thr in (50, 55, 60, 65, 70, 75, 80):
            qual = train_df[train_df["score"] >= thr]
            if len(qual) < 20:
                continue
            r = qual["forward_return_5d"].dropna().values
            if len(r) < 5:
                continue
            avg = float(np.mean(r)); std = float(np.std(r))
            sh = (avg / std * np.sqrt(252.0 / 5.0)) if std > 0 else 0.0
            if sh > best_train_sharpe:
                best_train_sharpe = sh
                best_threshold = thr

        test_qual = test_df[test_df["score"] >= best_threshold]
        if len(test_qual) < 10:
            start_idx += test_days
            continue

        for horizon_col, horizon_days in [
            ("forward_return_1d",  1),
            ("forward_return_5d",  5),
            ("forward_return_20d", 20),
        ]:
            gross = test_qual[horizon_col].dropna().values
            if len(gross) < 5:
                continue
            mode_for_cost = "intraday" if horizon_days == 1 else "shortterm"
            net = np.array([apply_transaction_costs(float(r), mode_for_cost) for r in gross])

            avg = float(np.mean(net)); std = float(np.std(net))
            wr = float((net > 0).mean())
            sharpe = (avg / std * np.sqrt(252.0 / horizon_days)) if std > 0 else 0.0

            oos_results.append({
                "window_start": str(test_dates.iloc[0])[:10],
                "window_end":   str(test_dates.iloc[-1])[:10],
                "horizon_days": horizon_days,
                "threshold_used": best_threshold,
                "avg_net_return_pct":   round(avg * 100, 4),
                "avg_gross_return_pct": round(float(np.mean(gross)) * 100, 4),
                "transaction_cost_pct": round((float(np.mean(gross)) - avg) * 100, 4),
                "win_rate":  round(wr * 100, 1),
                "sharpe_net": round(float(sharpe), 3),
                "n_trades":  int(len(net)),
            })

        window_results.append({
            "period": f"{str(test_dates.iloc[0])[:10]} to {str(test_dates.iloc[-1])[:10]}",
            "optimal_threshold": best_threshold,
            "train_sharpe": round(best_train_sharpe, 3),
        })

        start_idx += test_days

    if not oos_results:
        return {"error": "Not enough data for WFA windows."}

    oos_df = pd.DataFrame(oos_results)
    summary_by_horizon: Dict[str, Any] = {}
    for h in (1, 5, 20):
        subset = oos_df[oos_df["horizon_days"] == h]
        if subset.empty:
            continue
        avg_net = float(subset["avg_net_return_pct"].mean())
        summary_by_horizon[f"{h}d"] = {
            "avg_net_return_pct":      round(avg_net, 4),
            "avg_gross_return_pct":    round(float(subset["avg_gross_return_pct"].mean()), 4),
            "avg_transaction_cost_pct": round(float(subset["transaction_cost_pct"].mean()), 4),
            "avg_win_rate":   round(float(subset["win_rate"].mean()), 1),
            "avg_sharpe_net": round(float(subset["sharpe_net"].mean()), 3),
            "total_oos_trades": int(subset["n_trades"].sum()),
            "n_windows":  int(len(subset)),
            "has_edge":   bool(avg_net > 0.05),
        }

    return {
        "walk_forward_summary": summary_by_horizon,
        "window_details": window_results,
        "oos_period_results": oos_results[-30:],
        "methodology": "Walk-Forward Analysis: 12mo train, 10-day purge, 3mo OOS test. Net of NSE costs.",
        "cost_model": "0.08% intraday, 0.15% delivery round-trip (STT + brokerage + GST + slippage)",
    }


# ── Strategy performance for ALL horizons (1d/5d/20d), net of costs ──────

async def strategy_performance_all_horizons() -> Dict[str, Any]:
    """For each (horizon, threshold) report gross + net + Sharpe + alpha vs Nifty."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT score, date, stock,
                      forward_return_1d, forward_return_5d, forward_return_20d
               FROM backtest_signals
               WHERE forward_return_20d IS NOT NULL
               ORDER BY date ASC"""
        ) as cursor:
            rows = await cursor.fetchall()
    if not rows:
        return {"error": "No data. Run backtest first."}
    df = pd.DataFrame([dict(r) for r in rows])

    # Cached Nifty benchmarks — fetched once per hour, not on every call
    bench = await _nifty_benchmarks_cached()
    nifty_benchmarks = {k: v for k, v in bench.items() if k in ("1d", "5d", "20d")}

    results: Dict[str, Dict[str, Any]] = {}
    for horizon_col, horizon_days, mode_for_cost in [
        ("forward_return_1d",  1,  "intraday"),
        ("forward_return_5d",  5,  "shortterm"),
        ("forward_return_20d", 20, "shortterm"),
    ]:
        hkey = f"{horizon_days}d"
        nifty_avg = nifty_benchmarks.get(hkey, 0.0)
        results[hkey] = {}

        for thr in (50, 60, 70, 80):
            qual = df[df["score"] >= thr]
            if len(qual) < 10:
                continue
            gross = qual[horizon_col].dropna().values
            net = np.array([apply_transaction_costs(float(r), mode_for_cost) for r in gross])
            if len(net) < 5:
                continue

            avg_g = float(np.mean(gross)) * 100
            avg_n = float(np.mean(net))   * 100
            std_n = float(np.std(net))    * 100
            wr = float((net > 0).mean()) * 100
            sharpe = (np.mean(net) / np.std(net) * np.sqrt(252.0 / horizon_days)) if np.std(net) > 0 else 0.0

            daily_g = qual.groupby("date")[horizon_col].mean()
            daily_n = daily_g.apply(lambda r: apply_transaction_costs(float(r), mode_for_cost))
            cum_n = float(((1 + daily_n).cumprod().iloc[-1] - 1) * 100)

            cum_series = (1 + daily_n).cumprod()
            roll_max = cum_series.cummax()
            max_dd = float(((cum_series - roll_max) / roll_max).min() * 100) if not cum_series.empty else 0.0

            alpha = avg_n - nifty_avg

            results[hkey][str(thr)] = {
                "threshold": thr,
                "horizon_days": horizon_days,
                "n_trades": int(len(net)),
                "avg_gross_return_pct": round(avg_g, 4),
                "avg_net_return_pct":   round(avg_n, 4),
                "transaction_cost_pct": round(avg_g - avg_n, 4),
                "win_rate_pct":         round(wr, 1),
                "sharpe_ratio_net":     round(float(sharpe), 3),
                "cumulative_net_pct":   round(cum_n, 2),
                "max_drawdown_pct":     round(max_dd, 2),
                "nifty_avg_return_pct": round(nifty_avg, 4),
                "alpha_vs_nifty":       round(alpha, 4),
                "beats_nifty":          bool(alpha > 0),
                "has_real_edge":        bool(sharpe > 0.5 and wr > 52 and alpha > 0),
            }

    return {
        "by_horizon": results,
        "nifty_benchmarks": nifty_benchmarks,
        "cost_model": TRANSACTION_COSTS,
        "slippage_model": SLIPPAGE,
    }


# ── AI weight recommendations from Ridge + IC ────────────────────────────

def generate_weight_recommendations(weights_data: Dict[str, Any], ic_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compose human-readable recommendations + machine-applicable weights."""
    if "error" in weights_data or "error" in ic_data:
        return {"available": False}

    recs: List[Dict[str, Any]] = []
    new_weights: Dict[str, float] = {}

    ic_lookup = {i["indicator"].lower().replace(" ", "_"): i["ic"]
                 for i in ic_data.get("indicators", [])}

    for w in weights_data.get("weights", []):
        ind_key = w["indicator"].lower().replace(" ", "_")
        change = w.get("change", 0)
        ic_val = ic_lookup.get(ind_key, 0.0)
        new_weights[ind_key] = w["suggested_weight"]
        if abs(change) > 5:
            direction = "INCREASE" if change > 0 else "DECREASE"
            recs.append({
                "indicator": w["indicator"],
                "action": direction,
                "from": w["current_weight"],
                "to": w["suggested_weight"],
                "ic": round(float(ic_val), 4),
                "reason": f"Ridge regression suggests {direction.lower()}. IC={ic_val:.3f}.",
            })

    return {
        "available": True,
        "recommendations": recs,
        "new_weights_for_screener": new_weights,
        "apply_instruction": "POST /api/backtest/apply-weights with {'new_weights_for_screener': {...}} to adopt",
    }


_FULL_RESULTS_CACHE: Dict[str, Any] = {"data": None, "expires": 0.0, "computing": False}
_DATA_QUALITY_CACHE: Dict[str, Any] = {"data": None, "expires": 0.0}


def invalidate_results_cache() -> None:
    """Clear both result caches — call this after a fresh backtest run."""
    _FULL_RESULTS_CACHE["data"] = None
    _FULL_RESULTS_CACHE["expires"] = 0.0
    _DATA_QUALITY_CACHE["data"] = None
    _DATA_QUALITY_CACHE["expires"] = 0.0


async def _ensure_indexes() -> None:
    """Add SQL indexes once — speeds GROUP BY and date-range queries."""
    async with aiosqlite.connect(DB_PATH) as db:
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_signals_score      ON backtest_signals(score)",
            "CREATE INDEX IF NOT EXISTS idx_signals_date       ON backtest_signals(date)",
            "CREATE INDEX IF NOT EXISTS idx_signals_stock      ON backtest_signals(stock)",
            "CREATE INDEX IF NOT EXISTS idx_signals_ret5d      ON backtest_signals(forward_return_5d)",
        ):
            try:
                await db.execute(sql)
            except Exception:  # noqa: BLE001
                pass
        await db.commit()


async def _compute_full_results() -> Dict[str, Any]:
    """The expensive computation — run sequentially so we don't slam the
    SQLite DB with 6 concurrent scans on a 50K+ row table."""
    summary  = await get_backtest_summary()
    buckets  = await score_bucket_analysis()
    ic       = await signal_ic_analysis()
    weights  = await optimal_weights()
    perf     = await strategy_performance()
    perf_all = await strategy_performance_all_horizons()
    wfa      = await walk_forward_analysis()
    weight_recs = generate_weight_recommendations(weights, ic)
    return {
        "summary": summary,
        "score_buckets": buckets,
        "signal_ic": ic,
        "optimal_weights": weights,
        "strategy_performance": perf,
        "strategy_performance_all_horizons": perf_all,
        "walk_forward_analysis": wfa,
        "weight_recommendations": weight_recs,
    }


async def get_full_backtest_results() -> Dict[str, Any]:
    """Cached results — 1 HOUR TTL, since analyses don't change unless a new
    backtest is run (which calls ``invalidate_results_cache``).

    First call: compute synchronously (one-time cost).
    All subsequent calls: served from cache instantly.
    """
    now = time.time()
    cached = _FULL_RESULTS_CACHE["data"]

    # Fresh cache hit
    if cached and now < _FULL_RESULTS_CACHE["expires"]:
        return cached

    # If a stale cache exists AND another request is computing, return stale
    # immediately so the user never waits more than once.
    if cached and _FULL_RESULTS_CACHE.get("computing"):
        return cached

    _FULL_RESULTS_CACHE["computing"] = True
    try:
        await _ensure_indexes()
        payload = await _compute_full_results()
        _FULL_RESULTS_CACHE["data"] = payload
        _FULL_RESULTS_CACHE["expires"] = now + 3600.0   # 1-hour TTL
        return payload
    finally:
        _FULL_RESULTS_CACHE["computing"] = False


# ════════════════════════════════════════════════════════════════════════
# RESEARCH INFRASTRUCTURE — RESUME + REGIME-SEGMENTED ANALYSIS
# ════════════════════════════════════════════════════════════════════════

async def find_active_run() -> Optional[Dict[str, Any]]:
    """Find a run that has pending/failed/running stocks the user can resume.

    Returns the most recent such run with its progress counts. Used by:
    - the frontend, on /backtest mount, to reconnect to in-flight runs
    - the backend, on startup, to auto-resume after a process restart or
      laptop sleep that killed the in-memory task.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT bp.run_id,
                      SUM(CASE WHEN bp.status='completed' THEN 1 ELSE 0 END) AS completed,
                      SUM(CASE WHEN bp.status='pending'   THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN bp.status='failed'    THEN 1 ELSE 0 END) AS failed,
                      SUM(CASE WHEN bp.status='running'   THEN 1 ELSE 0 END) AS running,
                      COUNT(*) AS total,
                      MAX(bp.started_at) AS last_activity
                 FROM backtest_progress bp
                GROUP BY bp.run_id
                ORDER BY last_activity DESC NULLS LAST"""
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    for r in rows:
        if (r["pending"] or 0) > 0 or (r["failed"] or 0) > 0 or (r["running"] or 0) > 0:
            return r
    return None


async def resume_backtest(run_id: str) -> Dict[str, Any]:
    """Resume a backtest by re-processing only its pending/failed stocks.
    Completed stocks are left untouched — no duplicate signals."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT symbol FROM backtest_progress WHERE run_id=? ORDER BY symbol",
            (run_id,),
        ) as cur:
            all_syms = [r[0] for r in await cur.fetchall()]
        async with db.execute(
            "SELECT symbol FROM backtest_progress WHERE run_id=? AND status='completed'",
            (run_id,),
        ) as cur:
            done_syms = [r[0] for r in await cur.fetchall()]

    if not all_syms:
        return {"status": "unknown_run_id", "run_id": run_id}

    pending = [s for s in all_syms if s not in set(done_syms)]
    if not pending:
        return {
            "status": "already_complete",
            "run_id": run_id,
            "completed": len(done_syms),
            "pending": 0,
        }

    asyncio.create_task(run_full_backtest(run_id, all_syms, resume=True))
    return {
        "status": "resumed",
        "run_id": run_id,
        "completed": len(done_syms),
        "pending": len(pending),
        "total": len(all_syms),
    }


# ── Historical regime classification (read-only; mirrors data/regime.py) ──

_REGIME_HIST_CACHE: Dict[str, pd.DataFrame] = {}


def _build_regime_history_blocking() -> Optional[pd.DataFrame]:
    """Pull max-history Nifty + India VIX, derive per-day regime."""
    try:
        nifty = yf.Ticker("^NSEI").history(period="max", interval="1d", auto_adjust=False)
    except Exception as e:  # noqa: BLE001
        print(f"[regime_hist] nifty fetch failed: {e}")
        return None
    if nifty is None or nifty.empty:
        return None
    nifty.index = pd.to_datetime(nifty.index).tz_localize(None)
    close = nifty["Close"].astype(float)
    df = pd.DataFrame(index=nifty.index)
    df["close"]  = close
    df["ema50"]  = close.ewm(span=50,  adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    # India VIX (only exists from ~2008). Forward-fill, default 15.
    try:
        vix = yf.Ticker("^INDIAVIX").history(period="max", interval="1d", auto_adjust=False)
        if vix is not None and not vix.empty:
            vix.index = pd.to_datetime(vix.index).tz_localize(None)
            df["vix"] = vix["Close"].reindex(df.index).ffill()
    except Exception as e:  # noqa: BLE001
        print(f"[regime_hist] vix fetch failed: {e}")
    if "vix" not in df.columns:
        df["vix"] = 15.0
    df["vix"] = df["vix"].fillna(15.0)

    def classify(row: pd.Series) -> str:
        above_50  = row["close"] > row["ema50"]
        above_200 = row["close"] > row["ema200"]
        v = float(row["vix"])
        if above_50 and above_200 and v < 15:  return "BULL_TRENDING"
        if above_50 and above_200 and v < 22:  return "BULL_VOLATILE"
        if above_200 and not above_50:         return "SIDEWAYS"
        if not above_200 and v < 25:           return "BEAR_VOLATILE"
        return "BEAR_CRISIS"

    df["regime"] = df.apply(classify, axis=1)
    return df[["regime"]]


async def _get_regime_history() -> Optional[pd.DataFrame]:
    if "df" in _REGIME_HIST_CACHE:
        return _REGIME_HIST_CACHE["df"]
    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, _build_regime_history_blocking)
    if df is not None:
        _REGIME_HIST_CACHE["df"] = df
    return df


REGIMES_LIST = ["BULL_TRENDING", "BULL_VOLATILE", "SIDEWAYS", "BEAR_VOLATILE", "BEAR_CRISIS"]


async def regime_segmented_analysis(run_id: Optional[str] = None) -> Dict[str, Any]:
    """For each regime × horizon × threshold compute trade-level metrics
    using the SAME cost model as ``strategy_performance_all_horizons``.

    ``run_id`` is accepted for API symmetry but signals are not tagged
    with a run_id in the schema; the analysis runs over current signals.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT score, date, stock,
                      forward_return_1d, forward_return_5d, forward_return_20d
               FROM backtest_signals
               WHERE forward_return_20d IS NOT NULL
               ORDER BY date ASC"""
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        return {"run_id": run_id, "error": "No backtest data. Run backtest first."}

    sig = pd.DataFrame([dict(r) for r in rows])
    sig["date"] = pd.to_datetime(sig["date"]).dt.tz_localize(None).dt.normalize()

    regime_df = await _get_regime_history()
    if regime_df is None or regime_df.empty:
        return {"run_id": run_id, "error": "Regime history unavailable (Nifty fetch failed)."}

    sig = sig.merge(regime_df, left_on="date", right_index=True, how="left")
    sig["regime"] = sig["regime"].fillna("SIDEWAYS")

    horizon_specs = [
        ("forward_return_1d",  1,  "intraday"),
        ("forward_return_5d",  5,  "shortterm"),
        ("forward_return_20d", 20, "shortterm"),
    ]
    thresholds = (50, 60, 70, 80)

    out: Dict[str, Any] = {}
    for regime in REGIMES_LIST:
        sub_r = sig[sig["regime"] == regime]
        if sub_r.empty:
            out[regime] = {"signal_count": 0}
            continue
        regime_block: Dict[str, Any] = {"signal_count": int(len(sub_r))}
        for col, hdays, mode_for_cost in horizon_specs:
            hkey = f"{hdays}d"
            regime_block[hkey] = {}
            for thr in thresholds:
                qual = sub_r[sub_r["score"] >= thr]
                if len(qual) < 5:
                    continue
                gross = qual[col].dropna().values
                if len(gross) < 5:
                    continue
                net = np.array([apply_transaction_costs(float(r), mode_for_cost) for r in gross])

                avg_g = float(np.mean(gross)) * 100
                avg_n = float(np.mean(net))   * 100
                std_n = float(np.std(net))    * 100
                wr    = float((net > 0).mean()) * 100
                sharpe = (
                    float(np.mean(net) / np.std(net) * np.sqrt(252.0 / hdays))
                    if np.std(net) > 0 else 0.0
                )

                # cumulative + drawdown using daily mean compounding
                qual_sorted = qual.sort_values("date")
                daily_g = qual_sorted.groupby("date")[col].mean()
                daily_n = daily_g.apply(lambda r: apply_transaction_costs(float(r), mode_for_cost))
                cum_series = (1 + daily_n).cumprod()
                cum_n = float((cum_series.iloc[-1] - 1) * 100) if not cum_series.empty else 0.0
                roll_max = cum_series.cummax()
                max_dd = float(((cum_series - roll_max) / roll_max).min() * 100) if not cum_series.empty else 0.0

                regime_block[hkey][str(thr)] = {
                    "threshold": thr,
                    "horizon_days": hdays,
                    "trade_count": int(len(net)),
                    "avg_return_pct":   round(avg_n, 4),
                    "avg_gross_pct":    round(avg_g, 4),
                    "win_rate_pct":     round(wr, 1),
                    "sharpe_net":       round(sharpe, 3),
                    "net_return_pct":   round(avg_n, 4),
                    "cumulative_net_pct": round(cum_n, 2),
                    "max_drawdown_pct": round(max_dd, 2),
                }
        out[regime] = regime_block

    return {
        "run_id": run_id,
        "by_regime": out,
        "regimes": REGIMES_LIST,
        "horizons": ["1d", "5d", "20d"],
        "cost_model": TRANSACTION_COSTS,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
