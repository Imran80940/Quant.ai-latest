"""QUANT.AI — FastAPI backend.

Endpoints:
- GET  /api/price/{symbol}        price snapshot
- GET  /api/chart/{symbol}        OHLCV history
- GET  /api/indicators/{symbol}   full technical indicator pack
- GET  /api/screener              top-10 ranked stocks per mode
- POST /api/recommend             Claude AI recommendation
- GET  /api/indices               Nifty / Bank Nifty / India VIX
- GET  /api/universe              full searchable stock list
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict

import pytz
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("quant-ai")

IST = pytz.timezone("Asia/Kolkata")

from ai.llm import active_provider, get_recommendation  # noqa: E402
from data.indicators import compute_indicators  # noqa: E402
from data.market import fetch_daily_6mo, fetch_history, fetch_indices, fetch_price  # noqa: E402
from data.screener import MODES, run_screener  # noqa: E402
from data.universe import NSE_UNIVERSE  # noqa: E402

# ── Phase 2 imports ────────────────────────────────────────────────────
from backtest.database import DB_PATH, get_config, init_db, set_config  # noqa: E402
from backtest.engine import (  # noqa: E402
    find_active_run,
    get_backtest_summary,
    get_full_backtest_results,
    get_progress,
    optimal_weights,
    regime_segmented_analysis,
    resume_backtest,
    run_full_backtest,
    score_bucket_analysis,
    signal_ic_analysis,
    strategy_performance,
    walk_forward_analysis,
)
from ai.llm import generate_weight_update_from_backtest  # noqa: E402
from data.regime import detect_market_regime  # noqa: E402

app = FastAPI(title="QUANT.AI", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Startup: init DB, reload active paper trades, auto-start engine,
    schedule nightly integrity check at 11 PM IST."""
    await init_db()
    log.info("[startup] Database initialized (WAL mode)")
    try:
        from paper_trading.engine import reload_active_trades, start_engine
        reloaded = await reload_active_trades()
        # Phase 4 spec: budget cap removed; max 8 concurrent positions.
        await set_config("max_concurrent", "8")
        await set_config("trade_horizon",  "intraday+shortterm")
        await start_engine()
        log.info(
            "[startup] Engine auto-started (max 8 positions, intraday+shortterm, RULE-compliant). "
            "Reloaded %d active trades.", reloaded
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[startup] Paper-trading init skipped: %s", e)

    # Nightly integrity check at 23:00 IST
    async def _integrity_loop():
        from backtest.database import run_nightly_integrity_check  # noqa: PLC0415
        while True:
            try:
                now = datetime.now(IST)
                if now.hour == 23 and now.minute < 5:
                    await run_nightly_integrity_check()
                    await asyncio.sleep(3600)
                else:
                    await asyncio.sleep(300)
            except Exception as e:  # noqa: BLE001
                log.warning("[integrity-loop] %s", e)
                await asyncio.sleep(300)

    asyncio.create_task(_integrity_loop())

    # Auto-resume any backtest that was interrupted (laptop sleep, crash, restart).
    # Runs in the background so startup is not delayed.
    async def _auto_resume_backtest():
        try:
            active = await find_active_run()
            if active and active.get("run_id"):
                log.info(
                    "[startup] Resuming interrupted backtest %s "
                    "(completed=%s pending=%s failed=%s)",
                    active["run_id"], active.get("completed"),
                    active.get("pending"), active.get("failed"),
                )
                await resume_backtest(active["run_id"])
        except Exception as e:  # noqa: BLE001
            log.warning("[startup] auto-resume skipped: %s", e)

    asyncio.create_task(_auto_resume_backtest())


# ── Pydantic bodies ────────────────────────────────────────────────────

class RecommendBody(BaseModel):
    symbol: str
    name: str = ""
    mode: str = Field("intraday", pattern="^(intraday|shortterm|momentum|breakout|value)$")
    indicators: Dict[str, Any] | None = None
    price_data: Dict[str, Any] | None = None


# ── Routes ─────────────────────────────────────────────────────────────

@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "name": "QUANT.AI",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "/api/price/{symbol}",
            "/api/chart/{symbol}?range=&interval=",
            "/api/indicators/{symbol}",
            "/api/screener?mode=",
            "/api/recommend (POST)",
            "/api/indices",
            "/api/universe",
        ],
    }


@app.get("/api/health")
def health() -> Dict[str, Any]:
    try:
        from data.kite_client import kite as _kite
        kite_avail = _kite.is_available
    except Exception:  # noqa: BLE001
        kite_avail = False
    return {
        "status": "ok",
        "ai_provider": active_provider(),
        "kite_available": kite_avail,
    }


# ── Global exception handler — never crash with 500 (RULE: graceful) ───
from fastapi import Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled exception on %s: %s", request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=503,
        content={"error": "service_temporarily_unavailable", "detail": str(exc)},
    )


@app.get("/api/universe")
def universe() -> Dict[str, Any]:
    return {"count": len(NSE_UNIVERSE), "stocks": NSE_UNIVERSE}


@app.get("/api/price/{symbol}")
def price(symbol: str) -> Dict[str, Any]:
    try:
        return fetch_price(symbol)
    except ValueError as e:
        raise HTTPException(status_code=503, detail={"error": "data_unavailable", "symbol": symbol, "message": str(e)})
    except Exception as e:  # noqa: BLE001
        log.exception("price failed for %s", symbol)
        raise HTTPException(status_code=503, detail={"error": "data_unavailable", "symbol": symbol, "message": str(e)})


@app.get("/api/chart/{symbol}")
def chart(
    symbol: str,
    range: str = Query("6mo", description="1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y"),
    interval: str = Query("1d", description="1m, 5m, 15m, 30m, 1h, 1d, 1wk"),
) -> Dict[str, Any]:
    try:
        bars = fetch_history(symbol, range, interval)
        if not bars:
            raise HTTPException(status_code=503, detail={"error": "data_unavailable", "symbol": symbol})
        return {"symbol": symbol, "range": range, "interval": interval, "bars": bars}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("chart failed for %s", symbol)
        raise HTTPException(status_code=503, detail={"error": "data_unavailable", "symbol": symbol, "message": str(e)})


@app.get("/api/indicators/{symbol}")
def indicators(symbol: str) -> Dict[str, Any]:
    try:
        df = fetch_daily_6mo(symbol)
        ind = compute_indicators(df)
        return {"symbol": symbol, "indicators": ind}
    except ValueError as e:
        raise HTTPException(status_code=503, detail={"error": "insufficient_data", "symbol": symbol, "message": str(e)})
    except Exception as e:  # noqa: BLE001
        log.exception("indicators failed for %s", symbol)
        raise HTTPException(status_code=503, detail={"error": "data_unavailable", "symbol": symbol, "message": str(e)})


@app.get("/api/screener")
async def screener(
    mode: str = Query("intraday", description="intraday | shortterm | momentum | breakout | value"),
    top: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    if mode not in MODES:
        raise HTTPException(status_code=400, detail={"error": "invalid_mode", "valid_modes": sorted(MODES)})
    try:
        return await run_screener(mode, top_n=top)
    except Exception as e:  # noqa: BLE001
        log.exception("screener failed")
        raise HTTPException(status_code=503, detail={"error": "screener_failed", "message": str(e)})


@app.post("/api/recommend")
def recommend(body: RecommendBody) -> Dict[str, Any]:
    if active_provider() == "none":
        raise HTTPException(status_code=503, detail={
            "error": "ai_unavailable",
            "message": "No AI provider configured. Set GEMINI_API_KEY (free) or ANTHROPIC_API_KEY in backend/.env.",
        })

    indicators_payload = body.indicators
    price_payload = body.price_data
    name = body.name

    # Backfill indicators / price if the caller didn't pass them.
    if indicators_payload is None or price_payload is None:
        try:
            df = fetch_daily_6mo(body.symbol)
            indicators_payload = indicators_payload or compute_indicators(df)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=503, detail={"error": "data_unavailable", "message": str(e)})
        try:
            price_payload = price_payload or fetch_price(body.symbol)
            name = name or price_payload.get("name", "")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=503, detail={"error": "data_unavailable", "message": str(e)})

    price_value = float(price_payload.get("price") or indicators_payload.get("last_close") or 0.0)
    if not name:
        name = price_payload.get("name", body.symbol)

    try:
        return get_recommendation(body.symbol, name, price_value, indicators_payload, body.mode)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail={"error": "ai_unavailable", "message": str(e)})
    except Exception as e:  # noqa: BLE001
        log.exception("claude recommend failed")
        raise HTTPException(status_code=503, detail={"error": "ai_unavailable", "message": str(e)})


@app.get("/api/indices")
def indices() -> Dict[str, Any]:
    return {"indices": fetch_indices()}


# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — BACKTEST ENDPOINTS
# ════════════════════════════════════════════════════════════════════════

@app.post("/api/backtest/run")
async def start_backtest(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Trigger full backtest across the EXPANDED universe (active + distressed).

    Uses ``period="max"`` per stock so we cover up to ~10 years of history.
    Including distressed stocks partially mitigates survivorship bias.

    If a backtest is already in flight this endpoint short-circuits and
    returns the existing run_id instead of launching a duplicate. This
    closes the bug where users got millions of duplicate signal rows by
    re-clicking "Run" before the previous run finished.
    """
    from data.universe import get_backtest_symbols  # local import — fresh on every call

    # Refuse to launch a second concurrent run.
    existing = await find_active_run()
    if existing and existing.get("run_id"):
        return {
            "run_id": existing["run_id"],
            "status": "already_running",
            "stocks_total": existing.get("total"),
            "stocks_done": existing.get("completed"),
            "note": "A backtest is already in flight — reconnect to its progress at /api/backtest/progress/{run_id}",
        }

    symbols = get_backtest_symbols()
    run_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(run_full_backtest, run_id, symbols)
    return {
        "run_id": run_id,
        "status": "started",
        "stocks_total": len(symbols),
        # ~0.8s per stock + cache hits much faster
        "estimated_minutes": round(len(symbols) * 0.8 / 60.0, 0),
        "data_period": "Maximum available (up to 10+ years)",
        "survivorship_bias": "Partially mitigated — distressed stocks included",
        "note": "Watch progress at /api/backtest/progress/{run_id}",
    }


@app.get("/api/universe/stats")
async def universe_stats() -> Dict[str, Any]:
    """Stats about the expanded universe — sectors, cap distribution, distressed."""
    from data.universe import (  # noqa: PLC0415
        DELISTED_OR_DISTRESSED,
        NSE_UNIVERSE as ACTIVE,
        SECTORS,
    )

    sector_counts: Dict[str, int] = {}
    cap_counts = {"large": 0, "mid": 0, "small": 0}
    for s in ACTIVE:
        sec = s.get("sector", "Unknown")
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        cap = s.get("cap", "unknown")
        if cap in cap_counts:
            cap_counts[cap] += 1

    return {
        "total_active_stocks":    len(ACTIVE),
        "total_backtest_stocks":  len(ACTIVE) + len(DELISTED_OR_DISTRESSED),
        "distressed_stocks_included": len(DELISTED_OR_DISTRESSED),
        "sectors": len(SECTORS),
        "by_sector": sector_counts,
        "by_cap":    cap_counts,
        "survivorship_bias_note": (
            f"{len(DELISTED_OR_DISTRESSED)} distressed/delisted stocks included "
            "to partially reduce survivorship bias in backtest"
        ),
    }


_DATA_QUALITY_CACHE_MAIN: Dict[str, Any] = {"data": None, "expires": 0.0}


@app.get("/api/backtest/data-quality")
async def backtest_data_quality() -> Dict[str, Any]:
    """Cached 60s — heavy GROUP BY over the full signals table."""
    import time as _time
    now = _time.time()
    if _DATA_QUALITY_CACHE_MAIN["data"] and now < _DATA_QUALITY_CACHE_MAIN["expires"]:
        return _DATA_QUALITY_CACHE_MAIN["data"]

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT stock,
                      COUNT(*) AS signal_count,
                      MIN(date) AS earliest_date,
                      MAX(date) AS latest_date,
                      ROUND(COUNT(*) / 252.0, 1) AS approx_years
               FROM backtest_signals
               GROUP BY stock
               ORDER BY approx_years DESC"""
        ) as cursor:
            rows = await cursor.fetchall()
    data = [dict(r) for r in rows]
    if not data:
        return {"message": "No backtest data yet. Run backtest first.", "total_stocks_with_data": 0}

    years_dist: Dict[str, int] = {}
    for r in data:
        bucket = str(int(float(r["approx_years"] or 0)))
        years_dist[bucket] = years_dist.get(bucket, 0) + 1

    avg_years = sum(float(r["approx_years"] or 0) for r in data) / len(data)
    payload = {
        "total_stocks_with_data": len(data),
        "avg_years_per_stock": round(avg_years, 1),
        "max_years": max(float(r["approx_years"] or 0) for r in data),
        "min_years": min(float(r["approx_years"] or 0) for r in data),
        "years_distribution": years_dist,
        "stocks_with_5plus_years": len([r for r in data if float(r["approx_years"] or 0) >= 5]),
        "stocks_with_8plus_years": len([r for r in data if float(r["approx_years"] or 0) >= 8]),
        "top_20_longest":  data[:20],
        "bottom_20_shortest": data[-20:],
    }
    _DATA_QUALITY_CACHE_MAIN["data"] = payload
    _DATA_QUALITY_CACHE_MAIN["expires"] = now + 60.0
    return payload


@app.get("/api/backtest/progress/{run_id}")
async def backtest_progress(run_id: str):
    """Server-Sent Events stream for real-time backtest progress."""
    async def event_generator():
        while True:
            progress = get_progress(run_id)
            yield f"data: {json.dumps(progress)}\n\n"
            if progress.get("status") in ("complete", "failed", "not_found"):
                break
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/backtest/results")
async def backtest_results() -> Dict[str, Any]:
    """Phase 3 enhanced bundle.

    Includes legacy keys (`score_buckets`, `signal_ic`, `optimal_weights`,
    `strategy_performance`) PLUS Phase 3 additions (`walk_forward_analysis`,
    `strategy_performance_all_horizons`, `weight_recommendations`).
    """
    try:
        return await get_full_backtest_results()
    except Exception as e:  # noqa: BLE001
        log.exception("backtest_results failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/backtest/summary")
async def backtest_summary() -> Dict[str, Any]:
    return await get_backtest_summary()


# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — INTELLIGENCE LAYER ENDPOINTS
# ════════════════════════════════════════════════════════════════════════

@app.get("/api/backtest/walk-forward")
async def backtest_walk_forward() -> Dict[str, Any]:
    """Walk-Forward Analysis — out-of-sample performance net of NSE costs."""
    return await walk_forward_analysis()


@app.get("/api/backtest/ai-analysis")
async def backtest_ai_analysis() -> Dict[str, Any]:
    """AI as decision engine: read backtest results, propose concrete actions."""
    try:
        results = await get_full_backtest_results()
        analysis = await generate_weight_update_from_backtest(results)
        return {
            "backtest_summary": results.get("summary"),
            "ai_analysis": analysis,
            "generated_at": datetime.now(IST).isoformat(),
        }
    except Exception as e:  # noqa: BLE001
        log.exception("backtest_ai_analysis failed")
        raise HTTPException(status_code=500, detail=str(e))


class ApplyWeightsBody(BaseModel):
    new_weights_for_screener: Dict[str, float] = Field(default_factory=dict)


@app.post("/api/backtest/apply-weights")
async def apply_backtest_weights(body: ApplyWeightsBody) -> Dict[str, Any]:
    """Adopt AI-recommended factor-group weights into the live screener.

    Accepts the four-key shape: ``{"momentum_group", "trend_group",
    "volume_group", "volatility_group"}`` (or the unsuffixed variants).
    Always normalised to sum to 1.0 before persisting.
    """
    raw = body.new_weights_for_screener or {}
    if not raw:
        raise HTTPException(status_code=400, detail="No weights provided")

    # Accept both `momentum_group` and `momentum` style keys.
    norm: Dict[str, float] = {}
    for k, v in raw.items():
        key = k.lower().replace("_group", "").strip()
        if key in ("momentum", "trend", "volume", "volatility"):
            try:
                norm[key] = float(v)
            except (TypeError, ValueError):
                continue

    if not norm:
        raise HTTPException(status_code=400, detail="No recognised weight keys")

    total = sum(norm.values()) or 1.0
    norm = {k: round(v / total, 4) for k, v in norm.items()}

    applied: list[Dict[str, Any]] = []
    for factor, w in norm.items():
        await set_config(f"weight_{factor}", str(w))
        applied.append({"factor": factor, "weight": w})
    await set_config("weights_last_updated", datetime.now(IST).isoformat())

    return {
        "status": "applied",
        "weights": applied,
        "message": "Screener will use these weights on the next scan (cache cleared per-mode after 3 min).",
    }


@app.get("/api/regime")
async def get_regime() -> Dict[str, Any]:
    """Current market regime (cached 15 min). Drives screener score multipliers."""
    return await detect_market_regime()


@app.get("/api/paper-trading/would-trade")
async def would_trade(symbol: str, mode: str = "intraday") -> Dict[str, Any]:
    """RULE 6: Dry-run a paper trade WITHOUT placing it. Use this to test
    behaviour without contaminating the dataset or lowering the threshold.
    """
    from data.kite_client import kite as _kite  # noqa: PLC0415
    from paper_trading.engine import _active_symbol_lock, _active_trades, MAX_CONCURRENT_POSITIONS  # noqa: PLC0415

    out: Dict[str, Any] = {
        "symbol": symbol, "mode": mode,
        "would_trade": False, "reason": "",
        "symbol_in_kite_map": _kite.validate_symbol(symbol),
        "already_active":      symbol in _active_symbol_lock,
        "max_positions_reached": len(_active_trades) >= MAX_CONCURRENT_POSITIONS,
    }
    if not out["symbol_in_kite_map"]:
        out["reason"] = "symbol_not_in_kite_map"; return out
    if out["already_active"]:
        out["reason"] = "already_has_active_trade"; return out
    if out["max_positions_reached"]:
        out["reason"] = "max_positions_reached"; return out
    try:
        threshold = int((await get_config("confidence_threshold")) or "65")
        out["threshold"] = threshold
        df = fetch_daily_6mo(symbol)
        ind = compute_indicators(df)
        price = fetch_price(symbol)
        rec = get_recommendation(symbol, price.get("name", symbol),
                                 float(price.get("price") or 0), ind, mode)
        analysis = rec.get("analysis", {})
        out["confidence"] = int(analysis.get("confidence", 0))
        out["bias"]       = analysis.get("bias", "NEUTRAL")
        out["would_trade"] = (out["bias"] == "BULLISH" and out["confidence"] >= threshold)
        out["reason"]     = "meets_criteria" if out["would_trade"] else \
            f"bias={out['bias']} conf={out['confidence']} < {threshold}"
        out["analysis"]   = analysis
    except Exception as e:  # noqa: BLE001
        out["reason"] = f"error: {e}"
    return out


@app.get("/api/backtest/active")
async def backtest_active() -> Dict[str, Any]:
    """Return the most recent backtest that is still in flight (or has
    pending/failed stocks the user may resume). Lets the frontend reconnect
    its progress stream after navigating away or reloading."""
    try:
        info = await find_active_run()
        if not info:
            return {"active": False}
        progress = get_progress(info["run_id"])
        return {"active": True, "run": info, "progress": progress}
    except Exception as e:  # noqa: BLE001
        log.exception("backtest_active failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/backtest/resume/{run_id}")
async def resume_backtest_endpoint(run_id: str) -> Dict[str, Any]:
    """Resume an interrupted backtest. Re-runs only pending/failed stocks
    from ``backtest_progress``. Completed stocks are never duplicated."""
    try:
        return await resume_backtest(run_id)
    except Exception as e:  # noqa: BLE001
        log.exception("resume_backtest failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/backtest/regime-analysis/{run_id}")
async def backtest_regime_analysis(run_id: str) -> Dict[str, Any]:
    """Per-regime × per-horizon × per-threshold breakdown of backtest signals."""
    try:
        return await regime_segmented_analysis(run_id)
    except Exception as e:  # noqa: BLE001
        log.exception("regime_segmented_analysis failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/backtest/cancel/{run_id}")
async def cancel_backtest(run_id: str) -> Dict[str, Any]:
    """RULE 9: Cancel a running backtest cleanly. Marks the run as cancelled
    so the next status poll sees the change."""
    try:
        from backtest.engine import _progress  # type: ignore
        if run_id in _progress:
            _progress[run_id]["status"] = "cancelled"
            _progress[run_id]["current_stock"] = "Cancelled by user"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE backtest_runs SET status='cancelled' WHERE status='running'"
            )
            await db.commit()
        return {"status": "cancellation_requested", "run_id": run_id}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/debug/run-integrity-check")
async def trigger_integrity_check() -> Dict[str, Any]:
    """Manual trigger for the nightly integrity check (test endpoint)."""
    from backtest.database import run_nightly_integrity_check  # noqa: PLC0415
    issues = await run_nightly_integrity_check()
    return {"issues_found": len(issues), "issues": issues}


@app.get("/api/paper-trading/rejections")
async def paper_trading_rejections(limit: int = 50) -> Dict[str, Any]:
    """RULE 7: Surface rejection data for research."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM scan_rejections ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return {"count": len(rows), "rejections": [dict(r) for r in rows]}


@app.get("/api/paper-trading/live-weights")
async def paper_trading_live_weights() -> Dict[str, Any]:
    """The factor weights currently driving the screener + paper trading."""
    momentum   = float((await get_config("weight_momentum"))   or "0.30")
    trend      = float((await get_config("weight_trend"))      or "0.25")
    volume     = float((await get_config("weight_volume"))     or "0.30")
    volatility = float((await get_config("weight_volatility")) or "0.15")
    threshold  = int((await get_config("confidence_threshold")) or "65")
    last       = (await get_config("weights_last_updated")) or "never"
    learned    = momentum + trend + volume + volatility > 0.1 and last != "never"

    return {
        "momentum":   round(momentum,   4),
        "trend":      round(trend,      4),
        "volume":     round(volume,     4),
        "volatility": round(volatility, 4),
        "sum":        round(momentum + trend + volume + volatility, 4),
        "confidence_threshold": threshold,
        "source":     "paper_trade_learning" if learned else "default",
        "last_updated": last,
    }


# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — PAPER TRADING ENDPOINTS
# ════════════════════════════════════════════════════════════════════════

import aiosqlite  # noqa: E402


@app.get("/api/paper-trading/status")
async def paper_trading_status() -> Dict[str, Any]:
    from paper_trading.engine import (  # noqa: PLC0415
        _active_trades,
        _last_scan_time,
        is_nse_open,
        time_until_next_scan_minutes,
    )

    total_trades = int(await get_config("total_trades") or "0")
    total_wins = int(await get_config("total_wins") or "0")
    win_rate = round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0.0

    today = datetime.now(IST).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE created_date = ?", (today,)
        ) as c:
            row = await c.fetchone()
            today_trades = row[0] if row else 0
        async with db.execute(
            """SELECT AVG(pnl_pct) FROM paper_trades
               WHERE created_date = ? AND status = 'CLOSED'""",
            (today,),
        ) as c:
            row = await c.fetchone()
            today_avg_pnl = round(float(row[0] or 0), 2)

    return {
        "engine_status": (await get_config("engine_status")) or "idle",
        "engine_running": (await get_config("engine_running")) == "true",
        "is_market_open": is_nse_open(),
        "active_trades_count": len(_active_trades),
        "active_trades": list(_active_trades.values()),
        "confidence_threshold": int((await get_config("confidence_threshold")) or "65"),
        "last_scan_time": _last_scan_time.isoformat() if _last_scan_time else None,
        "next_scan_in_minutes": time_until_next_scan_minutes(),
        "total_trades_all_time": total_trades,
        "total_wins": total_wins,
        "overall_win_rate": win_rate,
        "today_trades": today_trades,
        "today_avg_pnl": today_avg_pnl,
        # Phase 4 budget info
        "portfolio_budget_inr": float((await get_config("portfolio_budget_inr")) or "20000"),
        "per_trade_inr":        float((await get_config("per_trade_inr"))        or "5000"),
        "max_concurrent":       int((await get_config("max_concurrent"))         or "4"),
        "trade_horizon":        (await get_config("trade_horizon")) or "intraday",
        "auto_start":           True,
    }


@app.get("/api/paper-trading/trades")
async def get_trades(status: str = "all", limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    where = "" if status == "all" else "WHERE status = ?"
    params: tuple = (limit, offset) if status == "all" else (status.upper(), limit, offset)
    sql = (
        f"SELECT * FROM paper_trades {where} ORDER BY entry_time DESC LIMIT ? OFFSET ?"
    )

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
    return {
        "trades": [dict(r) for r in rows],
        "offset": offset,
        "limit": limit,
        "count": len(rows),
    }


@app.get("/api/paper-trading/active")
async def get_active_trades() -> Dict[str, Any]:
    from paper_trading.engine import _active_trades, fetch_live_prices

    if not _active_trades:
        return {"trades": []}

    symbols = list({t["stock"] for t in _active_trades.values()})
    prices = await fetch_live_prices(symbols)

    out = []
    for trade in _active_trades.values():
        copy = dict(trade)
        current = prices.get(trade["stock"], trade["entry_price"])
        copy["current_price"] = round(float(current), 2)
        copy["live_pnl_pct"] = round(
            (float(current) - float(trade["entry_price"])) / float(trade["entry_price"]) * 100, 3
        )
        out.append(copy)
    return {"trades": out}


@app.get("/api/paper-trading/analytics")
async def paper_trading_analytics() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM paper_trades WHERE status = 'CLOSED' ORDER BY exit_time ASC"
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        return {"message": "No closed trades yet", "total_trades": 0}

    trades = [dict(r) for r in rows]

    def safe_pnl(t: Dict[str, Any]) -> float:
        return float(t.get("pnl_pct") or 0.0)

    def is_win(t: Dict[str, Any]) -> bool:
        return t.get("result") in ("WIN_T1", "WIN_T2")

    by_mode: Dict[str, Any] = {}
    for mode in ("intraday", "shortterm"):
        mode_trades = [t for t in trades if t.get("horizon") == mode]
        if mode_trades:
            by_mode[mode] = {
                "trades": len(mode_trades),
                "win_rate": round(sum(1 for t in mode_trades if is_win(t)) / len(mode_trades) * 100, 1),
                "avg_pnl": round(sum(safe_pnl(t) for t in mode_trades) / len(mode_trades), 2),
            }

    sorted_by_pnl = sorted(trades, key=safe_pnl)

    # Cumulative P&L over time
    cumulative = []
    running = 0.0
    for t in trades:
        running += safe_pnl(t)
        cumulative.append({"date": t.get("exit_time", ""), "cum_pnl": round(running, 3), "stock": t["stock"]})

    # Current streak
    recent = trades[-20:]
    streak = 0
    last_result = None
    for t in reversed(recent):
        r = "win" if is_win(t) else "loss"
        if last_result is None:
            last_result = r
        if r == last_result:
            streak += 1
        else:
            break

    total_pnl = sum(safe_pnl(t) for t in trades)
    win_rate = sum(1 for t in trades if is_win(t)) / len(trades) * 100

    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate, 1),
        "total_pnl_pct": round(total_pnl, 2),
        "avg_pnl_per_trade": round(total_pnl / len(trades), 2),
        "by_mode": by_mode,
        "best_trade": {"stock": sorted_by_pnl[-1]["stock"], "pnl": safe_pnl(sorted_by_pnl[-1])},
        "worst_trade": {"stock": sorted_by_pnl[0]["stock"], "pnl": safe_pnl(sorted_by_pnl[0])},
        "current_streak": streak,
        "streak_type": last_result,
        "cumulative_pnl_series": cumulative,
    }


@app.get("/api/paper-trading/insights")
async def paper_trading_insights() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM learning_insights ORDER BY id DESC LIMIT 10"
        ) as cursor:
            rows = await cursor.fetchall()
    return {
        "insights": [dict(r) for r in rows],
        "current_threshold": int((await get_config("confidence_threshold")) or "65"),
    }


class ControlBody(BaseModel):
    action: str = Field(..., pattern="^(start|stop|reset_threshold)$")


@app.post("/api/paper-trading/control")
async def control_engine(body: ControlBody) -> Dict[str, Any]:
    from paper_trading.engine import start_engine, stop_engine

    if body.action == "start":
        await start_engine()
        return {"status": "started"}
    if body.action == "stop":
        await stop_engine()
        return {"status": "stopped"}
    if body.action == "reset_threshold":
        await set_config("confidence_threshold", "65")
        return {"status": "threshold_reset", "threshold": 65}
    raise HTTPException(status_code=400, detail="Invalid action")


@app.get("/api/paper-trading/stream")
async def paper_trading_stream():
    """SSE stream of live engine events (trades opened/closed, scans, insights)."""
    from paper_trading.engine import _live_events

    async def event_generator():
        last_idx = len(_live_events)
        # Send a heartbeat immediately so the client knows the stream is open
        yield f"data: {json.dumps({'type': 'heartbeat', 'data': {}, 'timestamp': datetime.now(IST).isoformat()})}\n\n"
        while True:
            new_events = _live_events[last_idx:]
            for event in new_events:
                yield f"data: {json.dumps(event)}\n\n"
            last_idx = len(_live_events)
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Static frontend (Railway single-service mode) ─────────────────────────────
# When SERVE_FRONTEND=true the backend also serves the built React app.
# Railway build step copies frontend/dist into backend/static before uvicorn starts.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.environ.get("SERVE_FRONTEND", "false").lower() == "true" and os.path.isdir(_STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(_STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = os.path.join(_STATIC_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return {"error": "Frontend not built"}
