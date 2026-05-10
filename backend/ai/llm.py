"""LLM provider — DeepSeek-R1 (primary), Llama 3.3 70B (fallback), Gemini, Claude.

Per-call fallback chain (each level tried in order, exception caught):
  1. Groq: deepseek-r1-distill-llama-70b   ← PRIMARY (reasoning model)
  2. Groq: llama-3.3-70b-versatile          ← FALLBACK 1
  3. Gemini: gemini-2.0-flash               ← FALLBACK 2
  4. Anthropic Claude                       ← FALLBACK 3 (paid, optional)

DeepSeek-R1 outputs <think>...</think> chain-of-thought BEFORE the JSON.
`parse_ai_response()` strips that block first, then extracts the JSON body.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# Primary + fallback model IDs (env-overridable)
GROQ_PRIMARY_MODEL  = os.getenv("GROQ_PRIMARY_MODEL",  "deepseek-r1-distill-llama-70b")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL        = os.getenv("GEMINI_MODEL",        "gemini-2.0-flash")
CLAUDE_MODEL        = os.getenv("CLAUDE_MODEL",        "claude-sonnet-4-20250514")

SYSTEM_PROMPT = (
    "You are a senior quantitative analyst at a Two Sigma-style hedge fund, "
    "specialising in Indian equity markets (NSE/BSE). You have 15 years of "
    "experience in systematic trading, technical analysis, and risk management.\n\n"
    "Your analysis is:\n"
    "- DATA-DRIVEN: Every claim is backed by a specific indicator value\n"
    "- UNEMOTIONAL: No hype. If signals are mixed, say so honestly\n"
    "- RISK-FIRST: Always quantify the downside before the upside\n"
    "- ACTIONABLE: Give precise entry zones, targets, and stop losses in INR\n"
    "- REGIME-AWARE: ALWAYS read the MARKET REGIME CONTEXT before reasoning about a stock\n\n"
    "You always respond in valid JSON only. No prose outside the JSON structure."
)


# ── Prompt builder (regime-aware) ──────────────────────────────────────

def build_prompt(
    symbol: str,
    name: str,
    price: float,
    indicators: Dict[str, Any],
    mode: str,
    market_context: Optional[Dict[str, Any]] = None,
) -> str:
    market_context = market_context or {}
    regime       = market_context.get("regime_note", "Market context unavailable.")
    vix          = market_context.get("india_vix", "N/A")
    nifty_trend  = market_context.get("nifty_trend", "unknown")
    market_bias  = market_context.get("market_bias", "neutral")
    intraday_safe = market_context.get("vix_intraday_safe", True)

    return f"""
Analyse {symbol} ({name}) for {mode} trading.

━━━ MARKET REGIME CONTEXT (read this first — it overrides everything) ━━━
{regime}
Nifty bias: {market_bias.upper()} | India VIX: {vix} | Intraday safe: {"YES" if intraday_safe else "NO — HIGH RISK"}
Nifty trend: {nifty_trend.upper()}

━━━ STOCK: {symbol} | Price: ₹{price:.2f} ━━━

MOMENTUM SIGNALS:
- RSI (14): {indicators.get('rsi', 0):.1f}
- MACD: {indicators.get('macd', 0):.2f} | Signal: {indicators.get('macd_signal', 0):.2f} | Histogram: {indicators.get('macd_histogram', 0):.2f} | Crossover: {indicators.get('macd_crossover', 'N/A')}
- Stochastic RSI: {indicators.get('stoch_rsi', 0):.1f}

TREND SIGNALS:
- EMA 9: {indicators.get('ema_9', 0):.0f} | EMA 20: {indicators.get('ema_20', 0):.0f} | EMA 50: {indicators.get('ema_50', 0):.0f} | EMA 200: {indicators.get('ema_200', 0):.0f}
- Price vs EMAs: {indicators.get('price_vs_ema9','N/A')} EMA9 | {indicators.get('price_vs_ema20','N/A')} EMA20 | {indicators.get('price_vs_ema50','N/A')} EMA50 | {indicators.get('price_vs_ema200','N/A')} EMA200
- ADX: {indicators.get('adx', 0):.1f} ({indicators.get('trend_strength', 'N/A')} trend)
- Supertrend: {indicators.get('supertrend', 'N/A')}

VOLATILITY SIGNALS:
- Bollinger Bands: Upper {indicators.get('bb_upper', 0):.0f} | Mid {indicators.get('bb_middle', 0):.0f} | Lower {indicators.get('bb_lower', 0):.0f}
- BB Position: {indicators.get('bb_position_pct', 0):.0f}% | Squeeze: {indicators.get('bb_squeeze', False)}
- ATR: {indicators.get('atr', 0):.1f} ({indicators.get('atr_pct', 0):.2f}% of price)

VOLUME & INSTITUTIONAL SIGNALS:
- Volume vs 20-day avg: {indicators.get('volume_vs_avg20', 0):.2f}x
- OBV trend: {indicators.get('obv_trend', 'N/A')}
- VWAP: {indicators.get('vwap', 0):.0f} | Price {indicators.get('price_vs_vwap', 'N/A')} VWAP

━━━ INSTRUCTIONS ━━━
1. Read the MARKET REGIME CONTEXT first. If VIX > 20, flag intraday as high risk.
2. If price is below EMA200, the structural trend is bearish — say so explicitly in risks.
3. If signals conflict (e.g. bullish RSI but bearish MACD), explain which you trust more and why.
4. Entry, target, and stop-loss must be calculated from the ATR value above — not guessed.
   - Stop loss = price - (1.5 × ATR) for longs
   - Target 1 = price + (2 × ATR) | Target 2 = price + (3.5 × ATR)
   - R:R = (target - entry) / (entry - stop_loss)
5. Respond ONLY with the JSON below. No prose outside it.

{{
  "bias": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence": 0-100,
  "conviction": "HIGH" or "MEDIUM" or "LOW",
  "regime_impact": "one sentence on how today's market regime affects this setup",
  "intraday": {{
    "entry_low": number,
    "entry_high": number,
    "target_1": number,
    "target_2": number,
    "stop_loss": number,
    "rr_ratio_t1": number,
    "rr_ratio_t2": number,
    "exit_by": "2:30 PM" or "3:00 PM" or "avoid today"
  }},
  "shortterm": {{
    "trigger": "exact price level or event that confirms the trade",
    "target": number,
    "stop_loss": number,
    "horizon_days": number
  }},
  "key_reasons": ["reason 1", "reason 2", "reason 3"],
  "key_risks": ["risk 1", "risk 2"],
  "signal_conflict": "describe any conflicting signals and how you resolved them, or null if none",
  "signal_summary": {{
    "trend": "BULLISH" or "BEARISH" or "NEUTRAL",
    "momentum": "BULLISH" or "BEARISH" or "NEUTRAL",
    "volume": "CONFIRMING" or "DIVERGING" or "NEUTRAL",
    "volatility": "LOW" or "MEDIUM" or "HIGH"
  }},
  "one_line": "single crisp sentence under 15 words"
}}
"""


# Backwards-compat alias (older callers may still import the underscored name)
_build_user_prompt = build_prompt


# ── Response parsing (DeepSeek-R1-aware) ───────────────────────────────

_THINK_RE       = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_JSON_RE  = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_FENCE_PLAIN_RE = re.compile(r"```\s*(.*?)\s*```", re.DOTALL)
_RAW_JSON_RE    = re.compile(r"\{[\s\S]*\}")


def parse_ai_response(raw_text: str) -> Dict[str, Any]:
    """
    Parse an AI response into a JSON dict.

    Handles:
    - DeepSeek-R1's <think>...</think> chain-of-thought block (stripped first)
    - ```json ... ``` fenced code blocks
    - Bare ``` ... ``` fenced blocks
    - Raw JSON with surrounding prose (extracts the outermost {...})
    """
    if not raw_text:
        raise ValueError("Empty AI response")

    # 1. Strip DeepSeek-R1 thinking block(s)
    cleaned = _THINK_RE.sub("", raw_text).strip()

    # 2. Try ```json ... ``` fence
    m = _FENCE_JSON_RE.search(cleaned)
    if m:
        return json.loads(m.group(1))

    # 3. Try bare ``` ... ``` fence
    m = _FENCE_PLAIN_RE.search(cleaned)
    if m:
        candidate = m.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass  # fall through to raw extraction

    # 4. Try parsing the whole cleaned text directly
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 5. Last resort: regex out the outermost {...}
    m = _RAW_JSON_RE.search(cleaned)
    if not m:
        raise ValueError(f"No JSON found in response: {cleaned[:200]}")
    return json.loads(m.group(0))


# Keep the old internal name available so nothing else in the repo breaks.
_extract_json = parse_ai_response


# ── Provider key gating ────────────────────────────────────────────────

def _looks_real(key: str | None) -> bool:
    """Reject empty values and placeholder text from .env templates."""
    if not key:
        return False
    k = key.strip().strip('"').strip("'")
    if len(k) < 20:
        return False
    if "PASTE" in k.upper() or "YOUR_KEY" in k.upper() or "EXAMPLE" in k.upper():
        return False
    return True


def _has_groq() -> bool:
    return _looks_real(os.getenv("GROQ_API_KEY"))


def _has_gemini() -> bool:
    return _looks_real(os.getenv("GEMINI_API_KEY"))


def _has_claude() -> bool:
    return _looks_real(os.getenv("ANTHROPIC_API_KEY"))


def active_provider() -> str:
    """Returns the *primary* provider that will be tried first."""
    if _has_groq():    return "groq"
    if _has_gemini():  return "gemini"
    if _has_claude():  return "claude"
    return "none"


def active_model() -> str:
    """Returns the model id of the primary attempt (for /api/health)."""
    if _has_groq():    return GROQ_PRIMARY_MODEL
    if _has_gemini():  return GEMINI_MODEL
    if _has_claude():  return CLAUDE_MODEL
    return "none"


# ── Provider call wrappers ─────────────────────────────────────────────

def _groq_call(prompt: str, model: str, *, json_mode: bool = True) -> str:
    """Call Groq with a specific model. DeepSeek-R1 returns plain text with
    <think> tags, so we deliberately skip response_format for it."""
    from groq import Groq  # type: ignore
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 4096 if "deepseek" in model.lower() else 2048,
    }
    # DeepSeek-R1 outputs <think>...</think> wrapping the JSON, which breaks
    # strict JSON-mode. Llama-3.3 handles JSON mode cleanly.
    if json_mode and "deepseek" not in model.lower():
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _gemini_call(prompt: str) -> str:
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.4,
            max_output_tokens=2048,
            response_mime_type="application/json",
        ),
    )
    return resp.text or ""


def _claude_call(prompt: str) -> str:
    from anthropic import Anthropic  # type: ignore
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


# ── Public entry point ────────────────────────────────────────────────

class _Attempt:
    __slots__ = ("name", "model", "fn")
    def __init__(self, name: str, model: str, fn: Callable[[], str]) -> None:
        self.name = name; self.model = model; self.fn = fn


def _build_attempt_chain(prompt: str) -> List[_Attempt]:
    chain: List[_Attempt] = []
    if _has_groq():
        chain.append(_Attempt("groq", GROQ_PRIMARY_MODEL,
                              lambda: _groq_call(prompt, GROQ_PRIMARY_MODEL)))
        chain.append(_Attempt("groq", GROQ_FALLBACK_MODEL,
                              lambda: _groq_call(prompt, GROQ_FALLBACK_MODEL)))
    if _has_gemini():
        chain.append(_Attempt("gemini", GEMINI_MODEL, lambda: _gemini_call(prompt)))
    if _has_claude():
        chain.append(_Attempt("claude", CLAUDE_MODEL, lambda: _claude_call(prompt)))
    return chain


def get_recommendation(
    symbol: str,
    name: str,
    price: float,
    indicators: Dict[str, Any],
    mode: str,
    market_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if active_provider() == "none":
        raise RuntimeError(
            "No AI provider configured. Set GROQ_API_KEY (free at https://console.groq.com), "
            "GEMINI_API_KEY (free at https://aistudio.google.com/apikey), "
            "or ANTHROPIC_API_KEY in backend/.env"
        )

    prompt = build_prompt(symbol, name, price, indicators, mode, market_context)
    chain = _build_attempt_chain(prompt)

    last_err: Optional[Exception] = None
    for attempt in chain:
        try:
            raw = attempt.fn()
            parsed = parse_ai_response(raw)
            return {
                "symbol": symbol,
                "name": name,
                "mode": mode,
                "price_at_analysis": price,
                "provider": attempt.name,
                "model": attempt.model,
                "analysis": parsed,
                "market_context": market_context or {},
            }
        except Exception as e:  # noqa: BLE001
            log.warning("AI attempt failed (%s / %s): %s", attempt.name, attempt.model, e)
            last_err = e
            continue

    raise RuntimeError(f"All AI providers failed. Last error: {last_err}")


# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — AI as decision engine, not decoration.
# Async raw-call helper, weight-update analysis, and orthogonal-aware
# trade rationale with rule-based fallback.
# ════════════════════════════════════════════════════════════════════════


async def call_llm_raw(
    prompt: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.4,
    system: Optional[str] = None,
) -> str:
    """Async raw-text LLM call.

    Routes through the same Groq/Gemini/Claude fallback chain as
    `get_recommendation`. Returns whatever text the model produced —
    callers that need JSON should wrap with `parse_ai_response()`.
    """
    if active_provider() == "none":
        raise RuntimeError("No AI provider configured")

    sys_prompt = system or SYSTEM_PROMPT
    loop = asyncio.get_event_loop()
    last_err: Optional[Exception] = None

    def _groq(model: str) -> str:
        from groq import Groq  # type: ignore
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # DeepSeek-R1 emits <think>...</think>; never force JSON mode on it.
        if "deepseek" not in model.lower():
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def _gemini() -> str:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            ),
        )
        return resp.text or ""

    def _claude() -> str:
        from anthropic import Anthropic  # type: ignore
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=sys_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")

    attempts: List[tuple[str, str, Callable[[], str]]] = []
    if _has_groq():
        attempts.append(("groq", GROQ_PRIMARY_MODEL,  lambda: _groq(GROQ_PRIMARY_MODEL)))
        attempts.append(("groq", GROQ_FALLBACK_MODEL, lambda: _groq(GROQ_FALLBACK_MODEL)))
    if _has_gemini():
        attempts.append(("gemini", GEMINI_MODEL, _gemini))
    if _has_claude():
        attempts.append(("claude", CLAUDE_MODEL, _claude))

    for name, model, fn in attempts:
        try:
            return await loop.run_in_executor(None, fn)
        except Exception as e:  # noqa: BLE001
            log.warning("call_llm_raw failed (%s/%s): %s", name, model, e)
            last_err = e
            continue

    raise RuntimeError(f"All AI providers failed in call_llm_raw. Last error: {last_err}")


def _format_wfa(wfa: Dict[str, Any]) -> str:
    """Compact text for the AI weight-update prompt."""
    summary = wfa.get("walk_forward_summary", {})
    if not summary:
        return "No WFA data available."
    lines: List[str] = []
    for horizon, data in summary.items():
        if not isinstance(data, dict):
            continue
        lines.append(
            f"  {horizon}: avg_net_return={data.get('avg_net_return_pct', 0):.4f}%, "
            f"win_rate={data.get('avg_win_rate', 0):.1f}%, "
            f"sharpe_net={data.get('avg_sharpe_net', 0):.3f}, "
            f"has_edge={data.get('has_edge', False)}"
        )
    return "\n".join(lines) if lines else "No WFA data available."


async def generate_weight_update_from_backtest(backtest_results: Dict[str, Any]) -> Dict[str, Any]:
    """Read the full backtest analysis and have the AI propose concrete actions.

    Output shape:
      verdict, new_factor_weights, signals_to_retire, signals_to_amplify,
      regime_adjustments, optimal_score_threshold, optimal_holding_period_days,
      new_hypothesis_to_test, position_sizing_rule.
    """
    wfa     = backtest_results.get("walk_forward_analysis", {})
    ic_data = backtest_results.get("signal_ic", {})
    weights = backtest_results.get("optimal_weights", {})

    # Pick the horizon with the strongest OOS edge
    best_horizon, best_edge = "5d", -999.0
    for h in ("1d", "5d", "20d"):
        d = wfa.get("walk_forward_summary", {}).get(h, {})
        if isinstance(d, dict):
            edge = float(d.get("avg_net_return_pct", -999) or -999)
            if edge > best_edge:
                best_edge, best_horizon = edge, h

    ic_summary: List[str] = []
    for ind in (ic_data.get("indicators") or [])[:10]:
        ic_summary.append(f"{ind['indicator']}: IC={ind['ic']:.4f} ({ind['strength']})")

    weight_recs: List[str] = []
    for w in (weights.get("weights") or []):
        weight_recs.append(
            f"{w['indicator']}: current={w['current_weight']}, "
            f"suggested={w['suggested_weight']}, direction={w['direction']}"
        )

    prompt = f"""You are the quantitative research director at a Two Sigma-style fund.
You have just received the results of a 2-year backtest on 100 Indian NSE stocks.
Your job: analyse the results and output CONCRETE, ACTIONABLE changes to the trading system.

═══ BACKTEST RESULTS ═══

WALK-FORWARD ANALYSIS (Out-of-Sample, net of transaction costs):
{_format_wfa(wfa)}

SIGNAL INFORMATION COEFFICIENTS (IC > 0.05 = meaningful edge):
{chr(10).join(ic_summary) if ic_summary else 'No IC data available.'}

RIDGE REGRESSION WEIGHT SUGGESTIONS:
{chr(10).join(weight_recs) if weight_recs else 'No weight data.'}

BEST PERFORMING HORIZON: {best_horizon} (avg net return: {best_edge:.3f}%)

═══ YOUR ANALYSIS TASK ═══

Respond ONLY with this exact JSON structure. Be specific and data-driven.
Do NOT be diplomatic — if a signal has no edge, say retire it.

{{
  "verdict": {{
    "system_has_edge": true,
    "confidence_in_edge": "HIGH",
    "primary_evidence": "one sentence citing the strongest data point",
    "biggest_weakness": "one sentence on the most critical flaw"
  }},
  "new_factor_weights": {{
    "momentum_group": 0.25,
    "trend_group": 0.25,
    "volume_group": 0.30,
    "volatility_group": 0.20,
    "rationale": "one sentence explaining the rebalancing"
  }},
  "signals_to_retire": [
    {{"signal": "name", "reason": "IC < 0.01 or specific reason"}}
  ],
  "signals_to_amplify": [
    {{"signal": "name", "new_weight_multiplier": 1.5, "reason": "IC=X.XX"}}
  ],
  "regime_adjustments": {{
    "BULL_TRENDING":  {{"momentum_weight_boost": 0.05, "volume_weight_boost": 0.0}},
    "BULL_VOLATILE":  {{"momentum_weight_boost": 0.0,  "volume_weight_boost": 0.05}},
    "SIDEWAYS":       {{"momentum_weight_boost": 0.0,  "volume_weight_boost": 0.0}},
    "BEAR_VOLATILE":  {{"momentum_weight_boost": -0.10, "volume_weight_boost": 0.0}},
    "BEAR_CRISIS":    {{"momentum_weight_boost": -0.15, "volume_weight_boost": 0.0}}
  }},
  "optimal_score_threshold": 65,
  "optimal_holding_period_days": 5,
  "new_hypothesis_to_test": "one specific testable alpha hypothesis for Phase 4",
  "position_sizing_rule": "Kelly fraction guidance based on win rate and avg R:R"
}}"""

    try:
        raw = await call_llm_raw(prompt, max_tokens=1500, temperature=0.1)
        parsed = parse_ai_response(raw)
        parsed["_generated_at"] = datetime.now().isoformat()
        parsed["_based_on_signals"] = len(ic_data.get("indicators", []) or [])
        # Normalize the four-group factor weights to sum to 1.0
        nfw = parsed.get("new_factor_weights")
        if isinstance(nfw, dict):
            keys = ("momentum_group", "trend_group", "volume_group", "volatility_group")
            total = sum(float(nfw.get(k, 0) or 0) for k in keys)
            if total > 0:
                for k in keys:
                    nfw[k] = round(float(nfw.get(k, 0) or 0) / total, 4)
        return parsed
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _rule_based_fallback(
    symbol: str,
    orth: Dict[str, float],
    regime: Dict[str, Any],
    t1: float, t2: float, sl: float, rr_t1: float, rr_t2: float,
) -> Dict[str, Any]:
    """Used when the LLM is fully unavailable. Conservative, deterministic."""
    momentum = float(orth.get("momentum_score", 0.5))
    trend    = float(orth.get("trend_score", 0.5))
    volume   = float(orth.get("volume_score", 0.5))
    regime_name = regime.get("regime", "SIDEWAYS")
    avg = (momentum + trend + volume) / 3.0

    if regime_name in ("BEAR_CRISIS", "BEAR_VOLATILE"):
        bias, confidence = "BEARISH", 40
    elif avg > 0.65:
        bias, confidence = "BULLISH", int(avg * 80)
    elif avg < 0.35:
        bias, confidence = "BEARISH", int((1 - avg) * 70)
    else:
        bias, confidence = "NEUTRAL", 35

    return {
        "bias": bias,
        "confidence": confidence,
        "conviction": "LOW",
        "regime_override": f"Regime: {regime_name} — rule-based fallback in effect",
        "dominant_factor": "momentum" if momentum >= trend else "trend",
        "signal_conflict": None,
        "intraday": {
            "target_1": t1, "target_2": t2, "stop_loss": sl,
            "rr_ratio_t1": rr_t1, "rr_ratio_t2": rr_t2,
            "position_size_pct": 10,
        },
        "key_reasons": [
            f"Momentum factor: {momentum:.2f}",
            f"Trend factor: {trend:.2f}",
            f"Volume factor: {volume:.2f}",
        ],
        "key_risks": ["LLM unavailable — rule-based fallback used. Treat with low conviction."],
        "signal_summary": {
            "trend":      "BULLISH" if trend  > 0.55 else "BEARISH" if trend  < 0.4 else "NEUTRAL",
            "momentum":   "BULLISH" if momentum > 0.55 else "BEARISH" if momentum < 0.4 else "NEUTRAL",
            "volume":     "CONFIRMING" if volume > 0.55 else "DIVERGING" if volume < 0.4 else "NEUTRAL",
            "volatility": "MEDIUM",
        },
        "one_line": f"{bias} via rule-based fallback. Confidence {confidence}%.",
    }


async def generate_ai_trade_rationale(
    symbol: str,
    indicators: Dict[str, Any],
    regime: Dict[str, Any],
    backtest_weight_recs: Optional[Dict[str, Any]],
    mode: str,
    price: float,
    name: str = "",
) -> Dict[str, Any]:
    """Phase 3 trade rationale — orthogonal-feature aware, regime-gated, ATR-derived levels.

    Falls back to a deterministic rule-based output if the LLM chain fails entirely.
    """
    from data.orthogonalize import build_orthogonal_features  # local import to avoid circulars

    orth = build_orthogonal_features(indicators)
    atr     = float(indicators.get("atr", price * 0.015) or price * 0.015)
    atr_pct = float(indicators.get("atr_pct", 1.5) or 1.5)

    entry = price
    sl    = round(price - 1.5 * atr, 2)
    t1    = round(price + 2.0 * atr, 2)
    t2    = round(price + 3.5 * atr, 2)
    rr_t1 = round((t1 - entry) / (entry - sl), 2) if entry > sl else 0.0
    rr_t2 = round((t2 - entry) / (entry - sl), 2) if entry > sl else 0.0

    regime_name  = regime.get("regime", "UNKNOWN")
    regime_note  = regime.get("regime_note", "Market context unavailable")
    intraday_ok  = regime.get("intraday_ok", True)
    adjustments  = regime.get("signal_adjustments", []) or []

    weight_context = ""
    if backtest_weight_recs and backtest_weight_recs.get("available"):
        top = (backtest_weight_recs.get("recommendations") or [])[:3]
        if top:
            weight_context = "BACKTEST-LEARNED PRIORITIES: " + "; ".join(
                f"{r['indicator']} ({r['action']})" for r in top
            )

    prompt = f"""You are a senior quantitative analyst. Analyse {symbol} {('(' + name + ') ') if name else ''}for {mode} trading.

═══ MARKET REGIME (READ FIRST — OVERRIDES EVERYTHING) ═══
Regime: {regime_name}
{regime_note}
Adjustments: {('; '.join(adjustments)) if adjustments else 'None'}
Intraday suitable: {"YES" if intraday_ok else "NO — HIGH RISK"}

═══ STOCK: {symbol} | ₹{price:.2f} ═══

ORTHOGONAL FACTOR SCORES (uncorrelated — these are the real signals):
  Momentum Factor:   {orth['momentum_score']:.3f}/1.0  (RSI+MACD+StochRSI combined, de-duplicated)
  Trend Factor:      {orth['trend_score']:.3f}/1.0  (EMA stack+ADX+Supertrend combined)
  Volume Factor:     {orth['volume_score']:.3f}/1.0  (Volume ratio+OBV+VWAP combined)
  Volatility Factor: {orth['volatility_score']:.3f}/1.0  (BB squeeze+ATR setup)

RAW INDICATORS (for context only):
  RSI: {indicators.get('rsi','N/A')} | MACD: {indicators.get('macd_crossover','N/A')} | ADX: {indicators.get('adx','N/A')}
  EMA200: price {indicators.get('price_vs_ema200','N/A')} | Volume: {indicators.get('volume_vs_avg20','N/A')}x avg
  BB Squeeze: {indicators.get('bb_squeeze', False)} | ATR: {atr:.1f} ({atr_pct:.2f}% of price)

ATR-DERIVED PRICE LEVELS (use these — do not recalculate):
  Entry: ₹{entry:.2f}
  Stop Loss: ₹{sl:.2f} (1.5 × ATR below entry)
  Target 1: ₹{t1:.2f} (2.0 × ATR above — R:R {rr_t1:.1f}:1)
  Target 2: ₹{t2:.2f} (3.5 × ATR above — R:R {rr_t2:.1f}:1)

{weight_context}

INSTRUCTIONS:
1. If regime is BEAR_CRISIS or BEAR_VOLATILE: bias must be BEARISH or NEUTRAL. Never BULLISH.
2. If price is below EMA200: cap confidence at 55 maximum.
3. If momentum_score and trend_score conflict (one > 0.7, other < 0.3): explain the conflict.
4. Use the ATR-derived levels above. Round to nearest 0.5.
5. Respond ONLY with JSON. No prose outside the object.

{{
  "bias": "BULLISH/BEARISH/NEUTRAL",
  "confidence": 0,
  "conviction": "HIGH/MEDIUM/LOW",
  "regime_override": "how the regime modified this recommendation",
  "dominant_factor": "which orthogonal factor drove the bias",
  "signal_conflict": null,
  "intraday": {{
    "entry_low": {round(entry * 0.998, 2)},
    "entry_high": {round(entry * 1.002, 2)},
    "target_1": {t1},
    "target_2": {t2},
    "stop_loss": {sl},
    "rr_ratio_t1": {rr_t1},
    "rr_ratio_t2": {rr_t2},
    "exit_by": "2:30 PM/3:00 PM/avoid today",
    "position_size_pct": 10
  }},
  "shortterm": {{
    "trigger": "exact price level or event",
    "target": {t2},
    "stop_loss": {round(sl * 0.99, 2)},
    "horizon_days": 5
  }},
  "key_reasons": ["reason with specific value", "reason 2", "reason 3"],
  "key_risks": ["risk with specific value", "risk 2"],
  "signal_summary": {{
    "trend": "BULLISH/BEARISH/NEUTRAL",
    "momentum": "BULLISH/BEARISH/NEUTRAL",
    "volume": "CONFIRMING/DIVERGING/NEUTRAL",
    "volatility": "LOW/MEDIUM/HIGH"
  }},
  "one_line": "under 15 words"
}}"""

    try:
        raw = await call_llm_raw(prompt, max_tokens=1200, temperature=0.1)
        parsed = parse_ai_response(raw)
        parsed["_orthogonal_factors"] = orth
        parsed["_regime"] = regime_name
        return parsed
    except Exception as e:  # noqa: BLE001
        log.warning("generate_ai_trade_rationale fell back to rule-based: %s", e)
        result = _rule_based_fallback(symbol, orth, regime, t1, t2, sl, rr_t1, rr_t2)
        result["_orthogonal_factors"] = orth
        result["_regime"] = regime_name
        result["_fallback"] = True
        return result
