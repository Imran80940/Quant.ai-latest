"""Kite Connect client for live market data.

STRICT DATA SOURCE SEPARATION (RULE 2):
  • Kite     -> live quotes / paper-trade execution ONLY
  • yfinance -> historical / backtest ONLY
  • These two sources are NEVER mixed inside this client.
    There is NO yfinance fallback for live prices here. If Kite is
    unavailable, callers must skip the trade and log loudly.

Symbol mapping is the source of truth (RULE 1). The explicit
SYMBOL_MAP below is built from data/universe.py rows using the
per-stock `display_symbol` attribute. There is no string-slicing
or inferred conversion of yfinance symbols. If a yfinance symbol
is not present in SYMBOL_MAP, it CANNOT be live-traded.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pytz

IST = pytz.timezone("Asia/Kolkata")
log = logging.getLogger("kite_client")


def _is_nse_open() -> bool:
    """NSE cash session: Mon-Fri, 09:15-15:30 IST."""
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    open_t = now.replace(hour=9, minute=15, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= now <= close_t


# ── EXPLICIT SYMBOL MAP — yfinance ↔ Kite tradingsymbol ───────────────
# Each entry pairs a yfinance ticker (e.g. "RELIANCE.NS") with its
# explicit Kite NSE tradingsymbol from the universe row's
# `display_symbol` field. No string slicing, no hacks.

def _build_symbol_map() -> Dict[str, str]:
    explicit: Dict[str, str] = {}
    try:
        from .universe import NSE_UNIVERSE  # type: ignore
    except Exception as e:  # noqa: BLE001
        log.error("symbol_map: failed to import NSE_UNIVERSE: %s", e)
        return explicit

    for row in NSE_UNIVERSE:
        yf_sym = row.get("symbol")
        kite_sym = row.get("display_symbol")
        if not yf_sym or not kite_sym:
            log.error("symbol_map: universe row missing symbol/display_symbol: %s", row)
            continue
        if yf_sym in explicit and explicit[yf_sym] != kite_sym:
            log.error(
                "symbol_map: duplicate yf_symbol %s (existing=%s, new=%s)",
                yf_sym, explicit[yf_sym], kite_sym,
            )
            continue
        explicit[yf_sym] = kite_sym
    return explicit


SYMBOL_MAP: Dict[str, str] = _build_symbol_map()
REVERSE_MAP: Dict[str, str] = {v: k for k, v in SYMBOL_MAP.items()}

# Quote-freshness threshold. Any quote older than this is considered
# stale and rejected by validate_live_symbol().
QUOTE_FRESHNESS_SECONDS = 60


class KiteClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("KITE_API_KEY", "")
        self.api_secret = os.getenv("KITE_API_SECRET", "")
        self.access_token = os.getenv("KITE_ACCESS_TOKEN", "")
        self.kite = None  # KiteConnect instance, lazy-loaded
        self._last_token_date: Optional[date] = None
        self._available = False
        self._price_cache: Dict[str, Dict[str, float]] = {}
        self._cache_ttl = 30  # seconds
        self._initialize()

    def _initialize(self) -> None:
        if not (self.api_key and self.access_token):
            log.warning("Kite credentials missing — live trading path disabled.")
            self._available = False
            return
        try:
            from kiteconnect import KiteConnect  # type: ignore
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            self._last_token_date = date.today()
            self._available = True
            log.info("Kite client initialized.")
        except Exception as e:  # noqa: BLE001
            log.error("Kite init failed: %s", e)
            self._available = False

    # ── Symbol lookup helpers (RULE 1 — explicit map only) ─────────
    def in_map(self, yf_symbol: str) -> bool:
        return yf_symbol in SYMBOL_MAP

    def to_kite_symbol(self, yf_symbol: str) -> Optional[str]:
        return SYMBOL_MAP.get(yf_symbol)

    def to_yf_symbol(self, kite_symbol: str) -> Optional[str]:
        return REVERSE_MAP.get(kite_symbol)

    def validate_symbol(self, yf_symbol: str) -> bool:
        """Thin map-only check (kept for backwards compatibility).
        For trade decisions use validate_live_symbol() instead."""
        if yf_symbol not in SYMBOL_MAP:
            log.error("[unmapped_symbol] %s not in SYMBOL_MAP", yf_symbol)
            return False
        return True

    # ── RULE 1 + RULE 2 + RULE 8: full live-symbol validation ──────
    def validate_live_symbol(self, yf_symbol: str) -> Tuple[bool, str]:
        """Validate that a symbol can be live-traded RIGHT NOW.

        Checks (in strict order):
          1. symbol exists in the explicit SYMBOL_MAP
          2. Kite client is available (creds + init succeeded)
          3. a Kite quote can be fetched
          4. the quote's last_price is > 0
          5. NSE market session check:
             - if CLOSED -> return (False, "market_closed"); never "stale_quote"
             - if OPEN   -> require quote age <= QUOTE_FRESHNESS_SECONDS

        Returns (ok, reason). On failure the reason is logged and the
        caller MUST skip the trade — there is no silent fallback.
        """
        if yf_symbol not in SYMBOL_MAP:
            log.error("[validate_live_symbol] unmapped_symbol: %s", yf_symbol)
            return False, "unmapped_symbol"

        if not self._available or self.kite is None:
            log.error("[validate_live_symbol] kite_unavailable: %s", yf_symbol)
            return False, "kite_unavailable"

        instrument = f"NSE:{SYMBOL_MAP[yf_symbol]}"
        try:
            quote = self.kite.quote([instrument])  # type: ignore
        except Exception as e:  # noqa: BLE001
            log.error("[validate_live_symbol] kite_quote_error %s: %s", yf_symbol, e)
            return False, "kite_quote_error"

        q = (quote or {}).get(instrument)
        if not q:
            log.error("[validate_live_symbol] missing_quote: %s", yf_symbol)
            return False, "missing_quote"

        try:
            price = float(q.get("last_price", 0))
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            log.error("[validate_live_symbol] invalid_price (%s): %s", price, yf_symbol)
            return False, "invalid_price"

        # Market-session gate — when NSE is closed, quotes are
        # legitimately stale (last trade was hours/days ago). Surface
        # that as "market_closed" rather than "stale_quote" so the
        # caller can distinguish "wait for the bell" from "feed broke".
        market_open = _is_nse_open()
        if not market_open:
            log.warning("[validate_live_symbol] market_closed: %s", yf_symbol)
            return False, "market_closed"

        # Market is open — enforce the strict freshness window.
        ltt = q.get("last_trade_time") or q.get("timestamp")
        if ltt is not None:
            try:
                if hasattr(ltt, "tzinfo"):
                    last = ltt
                    if last.tzinfo is None:
                        last = IST.localize(last)
                else:
                    s = str(ltt).strip()
                    last = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    if last.tzinfo is None:
                        last = IST.localize(last)
                age = (datetime.now(IST) - last).total_seconds()
                if age > QUOTE_FRESHNESS_SECONDS:
                    log.error(
                        "[validate_live_symbol] stale_quote %s age=%.1fs (>%ds)",
                        yf_symbol, age, QUOTE_FRESHNESS_SECONDS,
                    )
                    return False, "stale_quote"
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "[validate_live_symbol] timestamp_parse_failed %s: %s — accepting price",
                    yf_symbol, e,
                )

        # Cache the fresh price so monitoring loops don't double-fetch.
        self._price_cache[yf_symbol] = {"price": price, "ts": time.time()}
        return True, "ok"

    # ── RULE 8: token refresh ──────────────────────────────────────
    def refresh_token_if_needed(self) -> None:
        today = date.today()
        if self._last_token_date != today:
            log.warning("Kite token may be expired (new day) — re-initializing.")
            self.access_token = os.getenv("KITE_ACCESS_TOKEN", "")
            self._initialize()
            if not self._available:
                log.critical("KITE TOKEN REFRESH FAILED — live trading disabled.")

    # ── live price (Kite ONLY — no yfinance fallback per RULE 2) ───
    def get_live_price(self, yf_symbol: str) -> Optional[float]:
        if yf_symbol not in SYMBOL_MAP:
            log.error("[get_live_price] unmapped_symbol: %s", yf_symbol)
            return None
        if not self._available or self.kite is None:
            log.error("[get_live_price] kite_unavailable: %s", yf_symbol)
            return None

        cached = self._price_cache.get(yf_symbol)
        if cached and (time.time() - cached["ts"]) < self._cache_ttl:
            return cached["price"]

        instrument = f"NSE:{SYMBOL_MAP[yf_symbol]}"
        try:
            quote = self.kite.quote([instrument])  # type: ignore
        except Exception as e:  # noqa: BLE001
            log.error("[get_live_price] kite_quote_error %s: %s", yf_symbol, e)
            return None

        q = (quote or {}).get(instrument)
        if not q:
            log.error("[get_live_price] missing_quote: %s", yf_symbol)
            return None

        try:
            price = float(q.get("last_price", 0))
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            log.error("[get_live_price] invalid_price (%s): %s", price, yf_symbol)
            return None

        self._price_cache[yf_symbol] = {"price": price, "ts": time.time()}
        return price

    def get_batch_prices(self, yf_symbols: List[str]) -> Dict[str, float]:
        """Kite-only batch fetch. Symbols missing from the map / quote /
        with invalid price are dropped — never silently filled from yfinance."""
        results: Dict[str, float] = {}
        if not self._available or self.kite is None:
            log.error("[get_batch_prices] kite_unavailable — returning empty (%d symbols requested)", len(yf_symbols))
            return results

        mapped: Dict[str, str] = {}
        for s in yf_symbols:
            if s in SYMBOL_MAP:
                mapped[s] = SYMBOL_MAP[s]
            else:
                log.error("[get_batch_prices] unmapped_symbol: %s", s)

        if not mapped:
            return results

        try:
            instruments = [f"NSE:{v}" for v in mapped.values()]
            quotes = self.kite.quote(instruments)  # type: ignore
        except Exception as e:  # noqa: BLE001
            log.error("[get_batch_prices] kite_quote_error: %s", e)
            return results

        for yf_sym, kite_sym in mapped.items():
            key = f"NSE:{kite_sym}"
            q = (quotes or {}).get(key)
            if not q:
                log.error("[get_batch_prices] missing_quote: %s", yf_sym)
                continue
            try:
                price = float(q.get("last_price", 0))
            except (TypeError, ValueError):
                price = 0.0
            if price <= 0:
                log.error("[get_batch_prices] invalid_price (%s): %s", price, yf_sym)
                continue
            results[yf_sym] = price
            self._price_cache[yf_sym] = {"price": price, "ts": time.time()}
        return results

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def price_cache(self) -> Dict[str, Dict[str, float]]:
        """Read-only-ish access for the force-close fallback chain."""
        return self._price_cache


# Module-level singleton
kite = KiteClient()


# Convenience module-level wrapper (used by paper trading per RULE 1)
def validate_live_symbol(yf_symbol: str) -> Tuple[bool, str]:
    return kite.validate_live_symbol(yf_symbol)
