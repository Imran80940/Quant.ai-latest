"""Position Sizing — Kelly Criterion adapted for systematic trading.

Two Sigma uses mean-variance optimization across the full portfolio.
We approximate that with fractional (half) Kelly based on paper-trading
realised stats, scaled by AI confidence and the current market regime.

Hard caps: 2% min, 15% max per position. Half Kelly always — never full.
"""
from __future__ import annotations

from typing import Any, Dict


def kelly_fraction(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> float:
    """Kelly Criterion: f* = (bp - q) / b   where b = avg_win/avg_loss.

    Returns HALF-Kelly clamped to [0.02, 0.20]. Half-Kelly halves variance
    in exchange for a small reduction in long-run growth.
    """
    if avg_loss_pct == 0 or avg_win_pct == 0:
        return 0.05  # 5% default when no data

    b = abs(avg_win_pct) / abs(avg_loss_pct)
    p = win_rate
    q = 1.0 - p

    full_kelly = (b * p - q) / b if b > 0 else 0.0
    half_kelly = full_kelly * 0.5

    return max(0.02, min(0.20, half_kelly))


async def compute_position_size(
    symbol: str,
    confidence: int,
    regime: Dict[str, Any],
    paper_trade_stats: Dict[str, Any],
    portfolio_value: float = 100_000.0,
) -> Dict[str, Any]:
    """Compute capital allocation for a candidate trade.

    Composition:
      base   = half-Kelly from paper-trade win rate + avg win/loss
      conf   = scaled by AI confidence (40% conf -> 0.3x, 80% conf -> 1.0x)
      regime = scaled by regime multiplier (BEAR_CRISIS shrinks size)
      cap    = clamp to [2%, 15%]
    """
    win_rate = float(paper_trade_stats.get("win_rate", 50.0)) / 100.0
    avg_win  = float(paper_trade_stats.get("avg_win_pct",  1.5))
    avg_loss = abs(float(paper_trade_stats.get("avg_loss_pct", -1.0)))

    kelly = kelly_fraction(win_rate, avg_win, avg_loss)

    # Confidence scaling: 40 → 0.0, 80 → 1.0
    conf_scale = max(0.3, min(1.0, (confidence - 40) / 40.0))

    # Regime scaling: 0.50 multiplier → 0.0, 1.10 multiplier → 1.0
    regime_mult = float(regime.get("score_multiplier", 0.9))
    regime_scale = max(0.2, min(1.0, (regime_mult - 0.5) / 0.6))

    final_pct = kelly * conf_scale * regime_scale
    final_pct = max(0.02, min(0.15, final_pct))

    position_value = portfolio_value * final_pct

    return {
        "symbol": symbol,
        "position_size_pct": round(final_pct * 100, 1),
        "position_value_inr": round(position_value, 0),
        "kelly_base_pct": round(kelly * 100, 1),
        "confidence_scaling": round(conf_scale, 2),
        "regime_scaling": round(regime_scale, 2),
        "max_concurrent_positions": 5,
        "max_same_sector": 2,
        "reasoning": (
            f"Kelly {kelly*100:.1f}% × conf {conf_scale:.2f} × regime {regime_scale:.2f}"
        ),
    }
