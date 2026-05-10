"""Technical indicator pipeline.

Takes a 6-month daily OHLCV DataFrame and returns the full indicator
dictionary consumed by the frontend Signal Panel and the Claude prompt.

Built on the `ta` library plus a couple of hand-rolled calculations
(VWAP and a simple Supertrend) to keep dependencies minimal.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, MACD
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator

log = logging.getLogger(__name__)


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _direction(price: float, ref: float) -> str:
    if ref == 0:
        return "neutral"
    return "above" if price >= ref else "below"


def _supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> str:
    """Return the latest Supertrend bias ('bullish' / 'bearish').

    Standard Supertrend: ATR-based bands tracking close. We compute
    only the final state (no need to expose the line for Phase 1).
    """
    high, low, close = df["High"], df["Low"], df["Close"]
    atr = AverageTrueRange(high, low, close, window=period).average_true_range()
    hl2 = (high + low) / 2.0
    upper = (hl2 + mult * atr).values
    lower = (hl2 - mult * atr).values
    c = close.values

    final_upper = np.copy(upper)
    final_lower = np.copy(lower)
    trend = np.ones(len(c))  # 1 = bullish, -1 = bearish

    for i in range(1, len(c)):
        final_upper[i] = upper[i] if (upper[i] < final_upper[i-1] or c[i-1] > final_upper[i-1]) else final_upper[i-1]
        final_lower[i] = lower[i] if (lower[i] > final_lower[i-1] or c[i-1] < final_lower[i-1]) else final_lower[i-1]
        if trend[i-1] == 1:
            trend[i] = -1 if c[i] < final_lower[i] else 1
        else:
            trend[i] = 1 if c[i] > final_upper[i] else -1

    return "bullish" if trend[-1] == 1 else "bearish"


def _vwap_session(df: pd.DataFrame) -> float:
    """Anchored VWAP over the available window (session-anchored is impossible
    on daily bars; using cumulative VWAP as a proxy for the current setup).
    """
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol = df["Volume"].replace(0, np.nan)
    cum_pv = (typical * vol).cumsum()
    cum_v = vol.cumsum()
    vwap = cum_pv / cum_v
    return _f(vwap.iloc[-1])


def compute_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute the full indicator dictionary from daily OHLCV."""
    if df is None or df.empty or len(df) < 30:
        raise ValueError("Insufficient data for indicators (need >= 30 bars)")

    df = df.copy().dropna(subset=["Open", "High", "Low", "Close"])
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    vol   = df["Volume"]

    last_close = _f(close.iloc[-1])

    # ── RSI (14) ──
    rsi = RSIIndicator(close, window=14).rsi()
    rsi_last = _f(rsi.iloc[-1])

    # ── MACD (12, 26, 9) ──
    macd_obj = MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_line   = macd_obj.macd()
    macd_signal = macd_obj.macd_signal()
    macd_hist   = macd_obj.macd_diff()
    m_last  = _f(macd_line.iloc[-1])
    m_sig   = _f(macd_signal.iloc[-1])
    m_hist  = _f(macd_hist.iloc[-1])
    m_hist_prev = _f(macd_hist.iloc[-2]) if len(macd_hist) >= 2 else 0.0
    if m_last > m_sig and m_hist > 0 and m_hist_prev <= 0:
        crossover = "bullish"
    elif m_last < m_sig and m_hist < 0 and m_hist_prev >= 0:
        crossover = "bearish"
    elif m_last > m_sig:
        crossover = "bullish"
    else:
        crossover = "bearish"

    # ── EMAs ──
    def _ema(window: int) -> float:
        if len(close) < window:
            return last_close
        return _f(EMAIndicator(close, window=window).ema_indicator().iloc[-1])

    ema9   = _ema(9)
    ema20  = _ema(20)
    ema50  = _ema(50)
    ema200 = _ema(200) if len(close) >= 200 else _ema(min(len(close), 100))

    # ── Bollinger Bands (20, 2) ──
    bb = BollingerBands(close, window=20, window_dev=2)
    bb_u = _f(bb.bollinger_hband().iloc[-1])
    bb_m = _f(bb.bollinger_mavg().iloc[-1])
    bb_l = _f(bb.bollinger_lband().iloc[-1])
    bb_width = (bb_u - bb_l) / bb_m if bb_m else 0.0
    # squeeze: BB width below the 20th percentile of the last 60 bars
    width_series = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg()
    width_recent = width_series.dropna().tail(60)
    squeeze = bool(len(width_recent) >= 30 and bb_width <= np.nanpercentile(width_recent, 20))
    bb_pos_pct = ((last_close - bb_l) / (bb_u - bb_l) * 100.0) if (bb_u - bb_l) > 0 else 50.0
    bb_pos_pct = float(max(0.0, min(100.0, bb_pos_pct)))

    # ── ADX (14) ──
    adx_obj = ADXIndicator(high, low, close, window=14)
    adx_val = _f(adx_obj.adx().iloc[-1])
    if adx_val >= 25:
        trend_strength = "strong"
    elif adx_val >= 15:
        trend_strength = "moderate"
    else:
        trend_strength = "weak"

    # ── ATR (14) ──
    atr_val = _f(AverageTrueRange(high, low, close, window=14).average_true_range().iloc[-1])
    atr_pct = (atr_val / last_close * 100.0) if last_close else 0.0

    # ── OBV trend ──
    obv = OnBalanceVolumeIndicator(close, vol).on_balance_volume()
    if len(obv) >= 20:
        obv_recent_slope = _f(obv.iloc[-1] - obv.iloc[-20])
        obv_trend = "rising" if obv_recent_slope > 0 else ("falling" if obv_recent_slope < 0 else "flat")
    else:
        obv_trend = "flat"

    # ── Volume vs 20-day average ──
    avg20_vol = _f(vol.tail(20).mean(), 1.0) or 1.0
    vol_vs_avg20 = _f(vol.iloc[-1]) / avg20_vol if avg20_vol else 0.0

    # ── Stochastic RSI (14) ──
    stoch_rsi_obj = StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
    stoch_rsi_val = _f(stoch_rsi_obj.stochrsi().iloc[-1]) * 100.0  # -> 0-100

    # ── Supertrend ──
    try:
        st = _supertrend(df)
    except Exception as e:  # noqa: BLE001
        log.warning("supertrend failed: %s", e)
        st = "neutral"

    # ── VWAP ──
    vwap_val = _vwap_session(df)

    return {
        "rsi": round(rsi_last, 2),
        "macd": round(m_last, 2),
        "macd_signal": round(m_sig, 2),
        "macd_histogram": round(m_hist, 2),
        "macd_crossover": crossover,

        "ema_9":   round(ema9, 2),
        "ema_20":  round(ema20, 2),
        "ema_50":  round(ema50, 2),
        "ema_200": round(ema200, 2),
        "price_vs_ema9":   _direction(last_close, ema9),
        "price_vs_ema20":  _direction(last_close, ema20),
        "price_vs_ema50":  _direction(last_close, ema50),
        "price_vs_ema200": _direction(last_close, ema200),

        "bb_upper": round(bb_u, 2),
        "bb_middle": round(bb_m, 2),
        "bb_lower": round(bb_l, 2),
        "bb_squeeze": squeeze,
        "bb_position_pct": round(bb_pos_pct, 1),

        "adx": round(adx_val, 2),
        "trend_strength": trend_strength,

        "atr": round(atr_val, 2),
        "atr_pct": round(atr_pct, 2),

        "obv_trend": obv_trend,
        "volume_vs_avg20": round(vol_vs_avg20, 2),

        "stoch_rsi": round(stoch_rsi_val, 1),

        "supertrend": st,
        "vwap": round(vwap_val, 2),
        "price_vs_vwap": _direction(last_close, vwap_val),

        "last_close": round(last_close, 2),
    }
