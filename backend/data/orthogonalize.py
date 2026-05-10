"""Factor Orthogonalization — removes correlation between indicators
so the scoring model doesn't double / triple count the same underlying signal.

Two Sigma approach: collapse correlated raw indicators into one *factor group*
score per group (momentum / trend / volume / volatility), then score on the
group composites — not the raw individual signals.

The four factor scores are designed to be approximately uncorrelated by
construction (they measure different drivers of price action).
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict

import numpy as np

# Persisted weights file (used by future PCA fits — not required for v1).
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pca_model.pkl")

# Reference groups — kept for documentation / future PCA work.
MOMENTUM_FACTORS   = ["rsi", "macd_histogram", "stoch_rsi", "macd_crossover"]
TREND_FACTORS      = ["ema_above_count", "adx", "supertrend", "price_vs_ema200"]
VOLUME_FACTORS     = ["volume_vs_avg20", "obv_trend", "price_vs_vwap"]
VOLATILITY_FACTORS = ["bb_squeeze", "atr_pct"]


def _ema_above_count(indicators: Dict[str, Any]) -> int:
    """How many of the four EMAs the price sits above (0..4)."""
    return sum(
        1 if indicators.get(k) == "above" else 0
        for k in ("price_vs_ema9", "price_vs_ema20", "price_vs_ema50", "price_vs_ema200")
    )


def build_orthogonal_features(indicators: Dict[str, Any]) -> Dict[str, float]:
    """Convert raw indicator values into 4 orthogonal factor scores in [0, 1].

    Each group score is a *weighted average* of its raw signals (not a sum), so
    it does not double-count the same underlying driver. Returned alongside the
    individual normalized sub-scores for transparency.
    """
    # ── MOMENTUM GROUP ──────────────────────────────────────────────────
    rsi        = float(indicators.get("rsi", 50) or 50)
    macd_hist  = float(indicators.get("macd_histogram", indicators.get("macd_hist", 0)) or 0)
    stoch_rsi  = float(indicators.get("stoch_rsi", 50) or 50)
    macd_cross = 1.0 if indicators.get("macd_crossover") == "bullish" else 0.0

    # RSI: 30 → 0, 70 → 1 (linear in the meaningful zone)
    rsi_score = max(0.0, min(1.0, (rsi - 30) / 40))
    # MACD histogram: sigmoid centered on 0
    try:
        macd_score = 1.0 / (1.0 + math.exp(-macd_hist * 0.1))
    except OverflowError:
        macd_score = 0.5
    stoch_score = max(0.0, min(1.0, stoch_rsi / 100.0))

    momentum_score = (
        rsi_score   * 0.35
        + macd_score  * 0.30
        + stoch_score * 0.20
        + macd_cross  * 0.15
    )

    # ── TREND GROUP ─────────────────────────────────────────────────────
    ema_count   = _ema_above_count(indicators)
    adx         = float(indicators.get("adx", 0) or 0)
    supertrend  = 1.0 if indicators.get("supertrend") == "bullish" else 0.0
    vs_ema200   = 1.0 if indicators.get("price_vs_ema200") == "above" else 0.0

    ema_score = ema_count / 4.0
    adx_score = max(0.0, min(1.0, (adx - 15) / 35))  # 15 → 0, 50 → 1

    trend_score = (
        ema_score   * 0.40
        + adx_score   * 0.25
        + supertrend  * 0.20
        + vs_ema200   * 0.15
    )

    # ── VOLUME GROUP ────────────────────────────────────────────────────
    vol_ratio  = float(indicators.get("volume_vs_avg20", indicators.get("volume_ratio", 1.0)) or 1.0)
    obv        = indicators.get("obv_trend", "flat")
    vwap_above = 1.0 if indicators.get("price_vs_vwap") == "above" else 0.0

    vol_score = max(0.0, min(1.0, (vol_ratio - 0.5) / 2.0))  # 0.5x → 0, 2.5x → 1
    obv_score = 1.0 if obv == "rising" else 0.0 if obv == "falling" else 0.5

    volume_score = (
        vol_score  * 0.50
        + obv_score  * 0.30
        + vwap_above * 0.20
    )

    # ── VOLATILITY SETUP GROUP ──────────────────────────────────────────
    bb_squeeze = 1.0 if indicators.get("bb_squeeze") else 0.0
    atr_pct    = float(indicators.get("atr_pct", 2.0) or 2.0)
    bb_pos     = float(indicators.get("bb_position_pct", 50) or 50) / 100.0

    # Low ATR is favourable: 0.5% → 1.0, 5.5% → 0.0
    atr_score = max(0.0, min(1.0, 1.0 - (atr_pct - 0.5) / 5.0))

    volatility_score = (
        bb_squeeze * 0.45
        + atr_score  * 0.35
        + bb_pos     * 0.20
    )

    return {
        "momentum_score":   round(float(momentum_score), 4),
        "trend_score":      round(float(trend_score), 4),
        "volume_score":     round(float(volume_score), 4),
        "volatility_score": round(float(volatility_score), 4),
        # Originals for transparency
        "raw_rsi": rsi,
        "raw_adx": adx,
        "raw_volume_ratio": vol_ratio,
        "raw_ema_above_count": ema_count,
    }


def compute_composite_score(
    orth_factors: Dict[str, float],
    weights: Dict[str, float] | None,
    mode: str = "intraday",
) -> float:
    """Compute a 0-100 composite score from orthogonal factors using learned weights.

    `weights` shape: ``{"momentum": 0.30, "trend": 0.25, "volume": 0.30, "volatility": 0.15}``
    If absent, falls back to mode-specific hard-coded defaults.
    """
    default_weights = {
        "intraday":  {"momentum": 0.30, "trend": 0.25, "volume": 0.30, "volatility": 0.15},
        "shortterm": {"momentum": 0.25, "trend": 0.35, "volume": 0.25, "volatility": 0.15},
        "momentum":  {"momentum": 0.45, "trend": 0.25, "volume": 0.20, "volatility": 0.10},
        "breakout":  {"momentum": 0.15, "trend": 0.25, "volume": 0.35, "volatility": 0.25},
        "value":     {"momentum": 0.10, "trend": 0.40, "volume": 0.15, "volatility": 0.35},
    }
    # Defensive: filter to the four numeric factor keys only. The caller may
    # have stuffed metadata like {"source": "learned"} into the dict.
    valid_keys = ("momentum", "trend", "volume", "volatility")
    if weights:
        clean = {
            k: float(v) for k, v in weights.items()
            if k in valid_keys and isinstance(v, (int, float))
        }
    else:
        clean = {}
    w = clean if (clean and sum(clean.values()) > 0.1) else default_weights.get(mode, default_weights["intraday"])

    # Normalize so weights sum to 1.0 (defensive — even when learned weights drift)
    total = sum(w.values()) or 1.0
    w = {k: v / total for k, v in w.items()}

    raw = (
        orth_factors["momentum_score"]   * w.get("momentum",   0.25)
        + orth_factors["trend_score"]      * w.get("trend",      0.25)
        + orth_factors["volume_score"]     * w.get("volume",     0.25)
        + orth_factors["volatility_score"] * w.get("volatility", 0.25)
    )
    return round(min(100.0, raw * 100.0), 1)
