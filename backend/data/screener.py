"""Stock screener — Two Sigma-style multi-factor scoring.

For each stock in `NSE_UNIVERSE` we fetch 6 months of daily OHLCV,
compute the indicator suite, score it under the chosen mode, and
return the top 10. Scans run in parallel with a semaphore-bounded
thread pool to respect Yahoo's rate limits.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .indicators import compute_indicators
from .market import fetch_daily_6mo, fetch_price
from .orthogonalize import build_orthogonal_features, compute_composite_score
from .universe import (
    NSE_UNIVERSE,
    get_all_symbols,
    get_by_cap,
    get_meta,
    get_symbol_metadata,
)

log = logging.getLogger(__name__)

# Phase 4: cap-size modes alongside the existing 5 setup modes.
MODES = {"intraday", "shortterm", "momentum", "breakout", "value", "smallcap", "midcap"}

# Simple in-process cache: mode -> (timestamp, result)
_CACHE: Dict[str, tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL_SEC = 180  # 3 minutes


# ── Live (learned-or-default) factor weights ──────────────────────────
# Priority: paper-trade-learned > backtest-derived > hardcoded mode defaults.

_DEFAULT_MODE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "intraday":  {"momentum": 0.30, "trend": 0.25, "volume": 0.30, "volatility": 0.15},
    "shortterm": {"momentum": 0.25, "trend": 0.35, "volume": 0.25, "volatility": 0.15},
    "momentum":  {"momentum": 0.45, "trend": 0.25, "volume": 0.20, "volatility": 0.10},
    "breakout":  {"momentum": 0.15, "trend": 0.25, "volume": 0.35, "volatility": 0.25},
    "value":     {"momentum": 0.10, "trend": 0.40, "volume": 0.15, "volatility": 0.35},
}


async def get_live_weights(mode: str = "intraday") -> Dict[str, Any]:
    """Return the factor weights the screener should use for `mode`.

    Returns ``{"weights": {momentum, trend, volume, volatility}, "source": str}``.
    Keeping the numeric weights in their own subdict prevents accidental
    `sum(values)` over a string field downstream.
    """
    try:
        from backtest.database import get_config  # type: ignore  # noqa: PLC0415
        m = float(await get_config("weight_momentum")   or "0")
        t = float(await get_config("weight_trend")      or "0")
        v = float(await get_config("weight_volume")     or "0")
        vol = float(await get_config("weight_volatility") or "0")
        if m + t + v + vol > 0.1:
            return {
                "weights": {"momentum": m, "trend": t, "volume": v, "volatility": vol},
                "source":  "learned",
            }
    except Exception as e:  # noqa: BLE001
        log.debug("get_live_weights fell back to defaults: %s", e)
    return {
        "weights": dict(_DEFAULT_MODE_WEIGHTS.get(mode, _DEFAULT_MODE_WEIGHTS["intraday"])),
        "source":  "default",
    }


def _grade(score: int) -> str:
    if score >= 80: return "A+"
    if score >= 70: return "A"
    if score >= 60: return "B+"
    if score >= 50: return "B"
    return "C"


def score_stock(indicators: Dict[str, Any], price_data: Dict[str, Any], mode: str) -> Dict[str, Any]:
    score = 0
    reasons: List[str] = []
    risks: List[str] = []

    rsi = indicators["rsi"]
    macd_cross = indicators["macd_crossover"]
    macd_hist = indicators["macd_histogram"]
    stoch = indicators["stoch_rsi"]
    adx = indicators["adx"]
    vol_mult = indicators["volume_vs_avg20"]
    obv = indicators["obv_trend"]
    bb_squeeze = indicators["bb_squeeze"]
    bb_pos = indicators["bb_position_pct"]
    atr_pct = indicators["atr_pct"]
    st = indicators["supertrend"]
    vs_vwap = indicators["price_vs_vwap"]

    # ── MOMENTUM (0-25) ──
    if 40 < rsi < 65:
        score += 8; reasons.append("RSI in bullish zone")
    if macd_cross == "bullish":
        score += 10; reasons.append("MACD bullish crossover")
    if stoch > 50:
        score += 7; reasons.append("Stochastic RSI bullish")

    # ── TREND (0-25) ──
    if indicators["price_vs_ema20"] == "above": score += 6
    if indicators["price_vs_ema50"] == "above":
        score += 8; reasons.append("Price above EMA50")
    if indicators["price_vs_ema200"] == "above":
        score += 6; reasons.append("Long-term uptrend intact")
    if adx > 25:
        score += 5; reasons.append(f"ADX {adx:.0f} — strong trend")

    # ── VOLUME (0-20) ──
    if vol_mult > 1.5:
        score += 12; reasons.append(f"Volume {vol_mult:.1f}x above average")
    elif vol_mult > 1.2:
        score += 7
    if obv == "rising":
        score += 8; reasons.append("OBV rising — accumulation")

    # ── VOLATILITY SETUP (0-15) ──
    if bb_squeeze:
        score += 10; reasons.append("Bollinger Band squeeze — breakout imminent")
    if atr_pct < 2.5:
        score += 5

    # ── VWAP (0-15, intraday only) ──
    if mode == "intraday":
        if vs_vwap == "above":
            score += 10; reasons.append("Price above VWAP — institutional bias bullish")
        if st == "bullish":
            score += 5

    # ── MODE-SPECIFIC NUDGES ──
    if mode == "breakout":
        if bb_squeeze and vol_mult > 1.2:
            score += 8; reasons.append("Squeeze + volume — classic breakout setup")
        if bb_pos > 80:
            score += 4; reasons.append("Pressing upper Bollinger band")
    elif mode == "momentum":
        if rsi > 60 and macd_hist > 0:
            score += 6; reasons.append("Momentum extending")
        if st == "bullish":
            score += 4
    elif mode == "shortterm":
        if indicators["price_vs_ema50"] == "above" and obv == "rising":
            score += 6
    elif mode == "value":
        # Value mode: prefer mean-reversion candidates near lower band
        # with healthy long-term trend (above EMA200).
        if bb_pos < 30 and indicators["price_vs_ema200"] == "above":
            score += 12; reasons.append("Mean reversion: near BB lower band, LT trend intact")
        if rsi < 40:
            score += 6; reasons.append(f"RSI {rsi:.0f} — oversold opportunity")

    # ── RISKS ──
    if rsi > 75:
        risks.append(f"RSI {rsi:.0f} — overbought, pullback risk")
    if rsi < 25:
        risks.append(f"RSI {rsi:.0f} — oversold, downtrend")
    if adx < 15:
        risks.append("ADX weak — no clear trend")
    if vol_mult < 0.5:
        risks.append("Low volume — weak conviction")
    if atr_pct > 4.0:
        risks.append(f"High ATR {atr_pct:.1f}% — volatile, wide stop needed")
    if indicators["price_vs_ema200"] == "below" and mode != "value":
        risks.append("Trading below 200 EMA — long-term downtrend")

    return {
        "score": min(int(score), 100),
        "reasons": reasons,
        "risks": risks,
    }


# ── Async fetch + score wrapper ────────────────────────────────────────

async def _score_one(
    symbol: str,
    mode: str,
    sem: asyncio.Semaphore,
    weights: Dict[str, Any],
    regime_mult: float,
) -> Optional[Dict[str, Any]]:
    """Fetch price + indicators for one symbol and return its scored card.

    Phase 3 scoring path:
      1. Compute the existing rule-based score for reasons/risks (still useful).
      2. Compute the orthogonal composite score using learned weights.
      3. Apply the market-regime multiplier — this is the score the UI shows.
    """
    async with sem:
        loop = asyncio.get_event_loop()
        try:
            price_data = await loop.run_in_executor(None, fetch_price, symbol)
            df = await loop.run_in_executor(None, fetch_daily_6mo, symbol)
            indicators = await loop.run_in_executor(None, compute_indicators, df)
        except Exception as e:  # noqa: BLE001
            log.info("screener skipped %s: %s", symbol, e)
            return None

        # Rule-based pass: gives us reasons + risks for the UI.
        scored = score_stock(indicators, price_data, mode)

        # Orthogonal pass: the actual displayed score.
        orth = build_orthogonal_features(indicators)
        # `weights` is the {"weights": {...}, "source": ...} envelope; pass the inner dict only.
        weights_inner = weights.get("weights") if isinstance(weights.get("weights"), dict) else weights
        orth_score = compute_composite_score(orth, weights_inner, mode)
        gated_score = round(min(100.0, max(0.0, orth_score * regime_mult)), 1)

        meta = get_symbol_metadata(symbol)
        return {
            "symbol": symbol,
            "display_symbol": meta.get("display_symbol", symbol.replace(".NS", "")),
            "name": price_data.get("name") or meta.get("name", symbol),
            "sector": price_data.get("sector") or meta.get("sector", "Unknown"),
            "cap": meta.get("cap", "unknown"),
            "price": price_data["price"],
            "change_pct": price_data["change_pct"],
            "score": gated_score,
            "raw_score": orth_score,            # before regime multiplier
            "rule_score": scored["score"],      # legacy — kept for transparency
            "grade": _grade(int(gated_score)),
            "reasons": scored["reasons"],
            "risks": scored["risks"],
            "indicators": indicators,
            "orthogonal": orth,
        }


async def run_screener(mode: str, top_n: int = 10) -> Dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}. Valid modes: {sorted(MODES)}")

    cached = _CACHE.get(mode)
    if cached and (time.time() - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    # Live weights (learned > default)
    weights = await get_live_weights(mode)

    # Market regime — fetch ONCE per scan, apply multiplier to every score
    regime: Dict[str, Any] = {}
    regime_mult = 1.0
    try:
        from .regime import detect_market_regime  # type: ignore  # noqa: PLC0415
        regime = await detect_market_regime()
        regime_mult = float(regime.get("score_multiplier", 1.0))
    except Exception as e:  # noqa: BLE001
        log.warning("screener regime detection failed: %s", e)

    sem = asyncio.Semaphore(10)
    # Cap-size modes filter the universe before scoring; setup modes scan large+mid only
    # (small-cap names are illiquid and inflate scan time without adding alpha).
    if mode == "smallcap":
        symbols = [s["symbol"] for s in get_by_cap("small")]
        scoring_mode = "shortterm"
    elif mode == "midcap":
        symbols = [s["symbol"] for s in get_by_cap("mid")]
        scoring_mode = "shortterm"
    else:
        large = [s["symbol"] for s in get_by_cap("large")]
        mid   = [s["symbol"] for s in get_by_cap("mid")]
        symbols = large + mid
        scoring_mode = mode

    tasks = [_score_one(sym, scoring_mode, sem, weights, regime_mult) for sym in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    cards = [r for r in results if r is not None]
    cards.sort(key=lambda c: c["score"], reverse=True)
    top = cards[:top_n]

    payload = {
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanned": len(symbols),
        "succeeded": len(cards),
        "stocks": top,
        "weights": weights,             # phase 3 — show what's driving the score
        "regime": regime,               # phase 3 — show today's regime in the response
    }
    _CACHE[mode] = (time.time(), payload)
    return payload
