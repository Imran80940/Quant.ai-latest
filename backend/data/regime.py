"""Market Regime Detection — Two Sigma-style.

Two Sigma always classifies the current market regime BEFORE interpreting
any stock-level signal. A bullish RSI in a bear-crisis regime is worth
much less than a bullish RSI in a bull-trending regime.

5 regimes with explicit score multipliers and intraday-safety flags:
  BULL_TRENDING   — Nifty above EMA50 + EMA200, VIX < 15
  BULL_VOLATILE   — Nifty above EMAs but VIX 15-22
  SIDEWAYS        — Nifty between EMAs (above EMA200, below EMA50)
  BEAR_VOLATILE   — Nifty below EMA50/200, VIX < 25
  BEAR_CRISIS     — Nifty below EMA200 with VIX > 25

Cached for 15 minutes. yfinance calls are dispatched to a thread pool so
the async event loop is never blocked.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict

import pytz
import yfinance as yf

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

_regime_cache: Dict[str, Any] = {"data": None, "expires": 0.0}

REGIMES: Dict[str, Dict[str, Any]] = {
    "BULL_TRENDING":  {"label": "Bull Trending",  "color": "green",   "intraday_ok": True,  "score_multiplier": 1.10},
    "BULL_VOLATILE":  {"label": "Bull Volatile",  "color": "amber",   "intraday_ok": True,  "score_multiplier": 0.95},
    "SIDEWAYS":       {"label": "Sideways",       "color": "gray",    "intraday_ok": True,  "score_multiplier": 0.90},
    "BEAR_VOLATILE":  {"label": "Bear Volatile",  "color": "red",     "intraday_ok": False, "score_multiplier": 0.70},
    "BEAR_CRISIS":    {"label": "Bear Crisis",    "color": "darkred", "intraday_ok": False, "score_multiplier": 0.50},
}


def _fetch_blocking() -> Dict[str, Any]:
    """Synchronous yfinance fetch — runs in a thread executor."""
    out: Dict[str, Any] = {
        "nifty_price": None,
        "nifty_vs_ema20": "unknown",
        "nifty_vs_ema50": "unknown",
        "nifty_vs_ema200": "unknown",
        "nifty_trend_20d": "sideways",
        "india_vix": None,
        "vix_level": "unknown",
    }

    try:
        nifty = yf.Ticker("^NSEI")
        df = nifty.history(period="1y", interval="1d")
        if not df.empty:
            close = df["Close"]
            current = float(close.iloc[-1])
            ema20  = float(close.ewm(span=20).mean().iloc[-1])
            ema50  = float(close.ewm(span=50).mean().iloc[-1])
            ema200 = float(close.ewm(span=200).mean().iloc[-1])

            out["nifty_price"]      = round(current, 2)
            out["nifty_vs_ema20"]   = "above" if current > ema20  else "below"
            out["nifty_vs_ema50"]   = "above" if current > ema50  else "below"
            out["nifty_vs_ema200"]  = "above" if current > ema200 else "below"

            # 20-day return
            if len(close) >= 21:
                prior = float(close.iloc[-20])
                slope = (current - prior) / prior if prior else 0.0
                if   slope >  0.03: out["nifty_trend_20d"] = "strong_up"
                elif slope >  0.01: out["nifty_trend_20d"] = "up"
                elif slope < -0.03: out["nifty_trend_20d"] = "strong_down"
                elif slope < -0.01: out["nifty_trend_20d"] = "down"
                else:               out["nifty_trend_20d"] = "sideways"
    except Exception as e:  # noqa: BLE001
        log.warning("regime nifty fetch failed: %s", e)

    try:
        vix_t = yf.Ticker("^INDIAVIX")
        fi = vix_t.fast_info
        vix = None
        for attr in ("last_price", "previous_close"):
            try:
                v = fi[attr] if hasattr(fi, "__getitem__") else getattr(fi, attr, None)
                if v:
                    vix = float(v); break
            except Exception:  # noqa: BLE001
                continue
        if vix is None:
            hist = vix_t.history(period="2d", interval="1d")
            if not hist.empty:
                vix = float(hist["Close"].iloc[-1])
        if vix is not None:
            out["india_vix"] = round(vix, 2)
            if   vix < 13: out["vix_level"] = "low"
            elif vix < 18: out["vix_level"] = "moderate"
            elif vix < 22: out["vix_level"] = "elevated"
            else:          out["vix_level"] = "extreme"
    except Exception as e:  # noqa: BLE001
        log.warning("regime vix fetch failed: %s", e)

    return out


def _classify(facts: Dict[str, Any]) -> str:
    above_ema50  = facts["nifty_vs_ema50"]  == "above"
    above_ema200 = facts["nifty_vs_ema200"] == "above"
    vix = facts.get("india_vix") or 15.0

    if above_ema50 and above_ema200 and vix < 15:
        return "BULL_TRENDING"
    if above_ema50 and above_ema200 and vix < 22:
        return "BULL_VOLATILE"
    if above_ema200 and not above_ema50:
        return "SIDEWAYS"
    if not above_ema200 and vix < 25:
        return "BEAR_VOLATILE"
    return "BEAR_CRISIS"


def _build_note(regime: str, facts: Dict[str, Any]) -> tuple[str, list[str]]:
    info = REGIMES[regime]
    vix = facts.get("india_vix")
    vix_str = f"{vix:.1f}" if vix is not None else "N/A"

    notes = [
        f"Market regime: {info['label']}.",
        f"Nifty: {facts['nifty_vs_ema50']} EMA50, {facts['nifty_vs_ema200']} EMA200.",
        f"India VIX: {vix_str} ({facts['vix_level']}).",
    ]

    if regime == "BEAR_CRISIS":
        notes.append("CRITICAL: Bear crisis regime. DO NOT recommend intraday longs. "
                     "Short-term holds with tight SL only.")
    elif regime == "BEAR_VOLATILE":
        notes.append("WARNING: Bear volatile regime. All intraday longs are HIGH RISK. "
                     "Prefer sitting out.")
    elif regime == "BULL_VOLATILE":
        notes.append("CAUTION: Elevated VIX in bull market. Use wider stops. "
                     "Reduce position sizes by 30%.")
    elif regime == "BULL_TRENDING":
        notes.append("FAVORABLE: Bull trending regime. Breakout and momentum setups "
                     "have highest reliability.")

    adjustments: list[str] = []
    if facts["nifty_vs_ema200"] == "below":
        adjustments.append("Bearish EMA200: long setups need A+ signal quality. Reject B-grade setups.")
    if vix and vix > 20:
        adjustments.append(f"High VIX {vix:.0f}: widen stop-loss by 50%. Halve position size.")
    if facts["nifty_trend_20d"] in ("strong_down", "down"):
        adjustments.append("Nifty in downtrend: breakout signals unreliable. Momentum setups weaker.")
    if regime == "BULL_TRENDING" and vix and vix < 13:
        adjustments.append("Ideal conditions: full position sizing allowed. Breakout signals highly reliable.")

    return " ".join(notes), adjustments


async def detect_market_regime() -> Dict[str, Any]:
    """Classify current market regime. Cached for 15 minutes."""
    now = time.time()
    if _regime_cache["data"] and now < _regime_cache["expires"]:
        return _regime_cache["data"]

    loop = asyncio.get_event_loop()
    try:
        facts = await loop.run_in_executor(None, _fetch_blocking)
    except Exception as e:  # noqa: BLE001
        log.warning("regime fetch fully failed, defaulting to SIDEWAYS: %s", e)
        facts = {
            "nifty_price": None,
            "nifty_vs_ema20": "unknown", "nifty_vs_ema50": "unknown",
            "nifty_vs_ema200": "unknown", "nifty_trend_20d": "sideways",
            "india_vix": None, "vix_level": "unknown",
        }

    regime = _classify(facts) if facts.get("nifty_price") is not None else "SIDEWAYS"
    info = REGIMES[regime]
    note, adjustments = _build_note(regime, facts)

    payload: Dict[str, Any] = {
        "regime": regime,
        "regime_label": info["label"],
        "regime_color": info["color"],
        "score_multiplier": info["score_multiplier"],
        "intraday_ok": info["intraday_ok"],
        "regime_note": note,
        "signal_adjustments": adjustments,
        "timestamp": datetime.now(IST).isoformat(),
        **facts,
    }

    _regime_cache["data"] = payload
    _regime_cache["expires"] = now + 900  # 15 min
    return payload
