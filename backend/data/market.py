"""Yahoo Finance market data fetcher.

Returns price snapshots, OHLCV history, and index levels.
All numeric values are coerced to plain Python floats / ints so they
serialize cleanly to JSON.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from .universe import get_meta

log = logging.getLogger(__name__)


# ── helpers ────────────────────────────────────────────────────────────

def _safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None:
            return default
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    f = _safe_float(v, None)
    return int(f) if f is not None else default


# ── range / interval mapping ───────────────────────────────────────────

VALID_RANGES = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"}
VALID_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo"}


def normalize_range_interval(rng: str, interval: str) -> tuple[str, str]:
    rng = rng if rng in VALID_RANGES else "6mo"
    interval = interval if interval in VALID_INTERVALS else "1d"
    return rng, interval


# ── price snapshot ─────────────────────────────────────────────────────

def fetch_price(symbol: str) -> Dict[str, Any]:
    """Fetch a one-shot price snapshot for `symbol`.

    Combines fast_info (cheap, near-real-time) with info (heavier,
    more fundamentals). If both fail, raises ValueError so the caller
    can return HTTP 503.
    """
    ticker = yf.Ticker(symbol)
    meta = get_meta(symbol)

    fast: Dict[str, Any] = {}
    try:
        fi = ticker.fast_info
        # fast_info is dict-like in newer yfinance; tolerate older attribute style
        for key in ("last_price", "previous_close", "open", "day_high", "day_low",
                    "last_volume", "year_high", "year_low", "market_cap"):
            try:
                fast[key] = fi[key] if hasattr(fi, "__getitem__") else getattr(fi, key, None)
            except (KeyError, AttributeError):
                fast[key] = None
    except Exception as e:  # noqa: BLE001
        log.warning("fast_info failed for %s: %s", symbol, e)

    info: Dict[str, Any] = {}
    try:
        info = ticker.info or {}
    except Exception as e:  # noqa: BLE001
        log.warning("info failed for %s: %s", symbol, e)

    price = _safe_float(fast.get("last_price")) or _safe_float(info.get("currentPrice")) \
        or _safe_float(info.get("regularMarketPrice"))
    prev_close = _safe_float(fast.get("previous_close")) or _safe_float(info.get("previousClose")) \
        or _safe_float(info.get("regularMarketPreviousClose"))

    if price is None and prev_close is None:
        # final fallback: 1d history
        try:
            hist = ticker.history(period="2d", interval="1d")
            if not hist.empty:
                price = _safe_float(hist["Close"].iloc[-1])
                if len(hist) >= 2:
                    prev_close = _safe_float(hist["Close"].iloc[-2])
        except Exception:  # noqa: BLE001
            pass

    if price is None:
        raise ValueError(f"No price data available for {symbol}")

    change = (price - prev_close) if prev_close is not None else 0.0
    change_pct = (change / prev_close * 100.0) if prev_close else 0.0

    return {
        "symbol": symbol,
        "display_symbol": meta["display_symbol"],
        "name": info.get("longName") or info.get("shortName") or meta["name"],
        "sector": info.get("sector") or meta["sector"],
        "exchange": "NSE" if symbol.endswith(".NS") else ("BSE" if symbol.endswith(".BO") else "—"),
        "price": round(price, 2),
        "previous_close": round(prev_close, 2) if prev_close else None,
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "open": _safe_float(fast.get("open")) or _safe_float(info.get("open")),
        "high": _safe_float(fast.get("day_high")) or _safe_float(info.get("dayHigh")),
        "low": _safe_float(fast.get("day_low")) or _safe_float(info.get("dayLow")),
        "volume": _safe_int(fast.get("last_volume")) or _safe_int(info.get("volume")),
        "week52_high": _safe_float(fast.get("year_high")) or _safe_float(info.get("fiftyTwoWeekHigh")),
        "week52_low":  _safe_float(fast.get("year_low"))  or _safe_float(info.get("fiftyTwoWeekLow")),
        "market_cap": _safe_int(fast.get("market_cap")) or _safe_int(info.get("marketCap")),
        "pe_ratio":  _safe_float(info.get("trailingPE")),
        "forward_pe": _safe_float(info.get("forwardPE")),
        "beta":      _safe_float(info.get("beta")),
        "dividend_yield": _safe_float(info.get("dividendYield")),
    }


# ── OHLCV history for chart ────────────────────────────────────────────

def fetch_history(symbol: str, rng: str, interval: str) -> List[Dict[str, Any]]:
    rng, interval = normalize_range_interval(rng, interval)
    ticker = yf.Ticker(symbol)
    df: pd.DataFrame = ticker.history(period=rng, interval=interval, auto_adjust=False)
    if df.empty:
        return []

    # Reset index; the index is a tz-aware Timestamp called 'Datetime' or 'Date'
    df = df.reset_index()
    ts_col = "Datetime" if "Datetime" in df.columns else "Date"

    out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        ts = row[ts_col]
        try:
            unix = int(pd.Timestamp(ts).timestamp())
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "time":   unix,
            "open":   _safe_float(row.get("Open"), 0.0),
            "high":   _safe_float(row.get("High"), 0.0),
            "low":    _safe_float(row.get("Low"), 0.0),
            "close":  _safe_float(row.get("Close"), 0.0),
            "volume": _safe_int(row.get("Volume"), 0),
        })
    return out


# ── index levels (Nifty / Bank Nifty / VIX) ────────────────────────────

INDEX_SYMBOLS = {
    "nifty":     {"symbol": "^NSEI",     "label": "NIFTY 50"},
    "banknifty": {"symbol": "^NSEBANK",  "label": "BANK NIFTY"},
    "vix":       {"symbol": "^INDIAVIX", "label": "INDIA VIX"},
}


_INDICES_CACHE: Dict[str, Any] = {"data": None, "expires": 0.0}


def fetch_indices() -> Dict[str, Dict[str, Any]]:
    import time as _t
    now = _t.time()
    if _INDICES_CACHE["data"] and now < _INDICES_CACHE["expires"]:
        return _INDICES_CACHE["data"]

    out: Dict[str, Dict[str, Any]] = {}
    for key, meta in INDEX_SYMBOLS.items():
        try:
            t = yf.Ticker(meta["symbol"])
            fi = t.fast_info
            price = _safe_float(fi["last_price"] if hasattr(fi, "__getitem__") else getattr(fi, "last_price", None))
            prev  = _safe_float(fi["previous_close"] if hasattr(fi, "__getitem__") else getattr(fi, "previous_close", None))
            if price is None or prev is None:
                hist = t.history(period="2d", interval="1d")
                if not hist.empty:
                    price = price if price is not None else _safe_float(hist["Close"].iloc[-1])
                    if len(hist) >= 2 and prev is None:
                        prev = _safe_float(hist["Close"].iloc[-2])
            if price is None:
                out[key] = {"label": meta["label"], "symbol": meta["symbol"], "error": "unavailable"}
                continue
            change = (price - prev) if prev is not None else 0.0
            change_pct = (change / prev * 100.0) if prev else 0.0
            out[key] = {
                "label": meta["label"],
                "symbol": meta["symbol"],
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            }
        except Exception as e:  # noqa: BLE001
            log.warning("index fetch failed for %s: %s", meta["symbol"], e)
            out[key] = {"label": meta["label"], "symbol": meta["symbol"], "error": str(e)}
    _INDICES_CACHE["data"] = out
    _INDICES_CACHE["expires"] = now + 60.0   # 60s TTL — kills the lag
    return out


# ── 6-month daily history (used by indicator pipeline) ─────────────────

def fetch_daily_6mo(symbol: str) -> pd.DataFrame:
    """Return the raw daily DataFrame used for indicator calculations."""
    return yf.Ticker(symbol).history(period="6mo", interval="1d", auto_adjust=False)


# ── Maximum-available history (used by Phase 4 backtest) ───────────────

def fetch_max_history(symbol: str) -> Optional[pd.DataFrame]:
    """Fetch up-to-10-years of daily OHLCV via yfinance ``period="max"``.

    Strict data-quality gates:
      * remove rows with non-positive Open/Close (bad ticks)
      * remove rows where Close differs from 20-day rolling median by > 10x
        (catches unadjusted splits or corrupt prints)
      * require at least 252 trading days (~1 year) — anything less returns None

    Returned DataFrame is timezone-naive with columns ``Open, High, Low, Close, Volume``.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="max", interval="1d", auto_adjust=True,
                            back_adjust=False, actions=False)
    except Exception as e:  # noqa: BLE001
        log.warning("fetch_max_history %s: %s", symbol, e)
        return None

    if df is None or df.empty:
        return None

    df.index = pd.to_datetime(df.index).tz_localize(None)
    cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    df = df[cols].copy()

    # Strip bad ticks
    df = df[(df["Close"] > 0) & (df["Open"] > 0)]
    if len(df) > 20:
        import numpy as np  # local import to avoid hard top-level dep on caller
        rolling_med = df["Close"].rolling(20, min_periods=5).median().replace(0, np.nan)
        ratio = df["Close"] / rolling_med
        df = df[(ratio > 0.1) & (ratio < 10)]

    df = df.sort_index()
    if len(df) < 252:
        return None
    return df


def validate_ohlcv_quality(df: Optional[pd.DataFrame], symbol: str) -> Dict[str, Any]:
    """Run quality checks on a daily OHLCV frame. Used before backtest inclusion."""
    if df is None or df.empty:
        return {"symbol": symbol, "valid": False, "reason": "empty"}

    report: Dict[str, Any] = {
        "symbol": symbol,
        "valid": True,
        "total_days": int(len(df)),
        "years_of_data": round(len(df) / 252.0, 1),
        "start_date": str(df.index[0].date()),
        "end_date":   str(df.index[-1].date()),
        "missing_days_pct": 0.0,
        "zero_volume_days": 0,
        "warnings": [],
    }

    # zero-volume days
    if "Volume" in df.columns:
        zv = int((df["Volume"] == 0).sum())
        report["zero_volume_days"] = zv
        if zv > len(df) * 0.05:
            report["warnings"].append(f"High zero-volume days: {zv}")

    # extreme single-day moves
    daily_ret = df["Close"].pct_change().abs()
    extreme = int((daily_ret > 0.20).sum())
    if extreme > 5:
        report["warnings"].append(f"Extreme daily moves (>20%): {extreme}")

    if report["years_of_data"] < 3:
        report["valid"] = False
        report["reason"] = f"Only {report['years_of_data']} years of data"

    return report
