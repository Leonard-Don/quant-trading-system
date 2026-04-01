"""
Position Sizing Module

Provides pluggable position sizing strategies that determine *how much* to
allocate to each trade, independent of signal direction.

Supported strategies:
    - FixedFraction: constant fraction of equity per trade
    - KellyCriterion: optimal growth sizing based on win rate and payoff
    - VolatilityTarget: scale position so portfolio vol matches a target
    - EqualRisk: equalize risk contribution across positions (for multi-asset)

Usage:
    sizer = VolatilityTargetSizer(target_vol=0.15, lookback=20)
    shares = sizer.calculate(context)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SizingContext:
    """Information available to the position sizer at trade entry.

    Simple Python types so the sizer is engine-agnostic.
    """
    current_equity: float = 0.0
    current_price: float = 0.0
    signal_strength: float = 1.0      # 0–1 scale from strategy (1 = full conviction)

    # Historical info (optional, used by adaptive sizers)
    recent_returns: List[float] = field(default_factory=list)
    recent_win_rate: float = 0.5
    recent_avg_win: float = 0.0
    recent_avg_loss: float = 0.0

    # Risk manager advisory
    risk_scale_factor: float = 1.0    # from RiskManager volatility scaling

    # Constraints
    commission: float = 0.001
    slippage: float = 0.001
    min_shares: int = 1
    allow_fractional: bool = False    # True for crypto / forex


@dataclass
class SizingResult:
    """Output of a position sizing calculation."""
    shares: float = 0.0
    position_value: float = 0.0
    fraction_of_equity: float = 0.0
    method: str = ""
    details: str = ""


class BasePositionSizer(ABC):
    """Abstract base class for position sizers."""

    @abstractmethod
    def calculate(self, ctx: SizingContext) -> SizingResult:
        """Calculate the number of shares/units to buy.

        Args:
            ctx: Current sizing context.

        Returns:
            SizingResult with the recommended position size.
        """
        ...

    def _clamp_shares(self, raw_shares: float, ctx: SizingContext) -> float:
        """Apply minimum / fractional constraints."""
        if raw_shares <= 0:
            return 0.0
        if ctx.allow_fractional:
            return max(raw_shares, 0.0)
        return max(float(int(raw_shares)), float(ctx.min_shares))

    def _max_affordable_shares(self, ctx: SizingContext) -> float:
        """Max shares affordable after transaction costs."""
        cost_mult = (1 + ctx.slippage) * (1 + ctx.commission)
        if ctx.current_price * cost_mult <= 0:
            return 0.0
        return ctx.current_equity / (ctx.current_price * cost_mult)


class FixedFractionSizer(BasePositionSizer):
    """Allocate a fixed fraction of equity to each trade.

    This is the simplest possible sizer — equivalent to the ``position_size``
    parameter of the original ``Backtester.run()`` method.
    """

    def __init__(self, fraction: float = 1.0):
        """
        Args:
            fraction: Fraction of equity to allocate (0.0–1.0).
        """
        if not 0.0 < fraction <= 1.0:
            raise ValueError(f"fraction must be in (0, 1], got {fraction}")
        self.fraction = fraction

    def calculate(self, ctx: SizingContext) -> SizingResult:
        available = ctx.current_equity * self.fraction * ctx.risk_scale_factor * ctx.signal_strength
        cost_mult = (1 + ctx.slippage) * (1 + ctx.commission)
        if ctx.current_price * cost_mult <= 0:
            return SizingResult(method="fixed_fraction")

        raw_shares = available / (ctx.current_price * cost_mult)
        shares = self._clamp_shares(raw_shares, ctx)
        value = shares * ctx.current_price

        return SizingResult(
            shares=shares,
            position_value=value,
            fraction_of_equity=value / ctx.current_equity if ctx.current_equity > 0 else 0.0,
            method="fixed_fraction",
            details=f"fraction={self.fraction:.2%}, signal={ctx.signal_strength:.2f}",
        )


class KellyCriterionSizer(BasePositionSizer):
    """Kelly Criterion position sizing.

    Full Kelly: ``f* = (p * b - q) / b``
    where ``p`` = win rate, ``b`` = avg_win / avg_loss, ``q`` = 1 - p.

    In practice, fractional Kelly (e.g. half-Kelly) is used to reduce variance.
    """

    def __init__(
        self,
        kelly_fraction: float = 0.5,
        max_position_pct: float = 0.25,
        min_trades_required: int = 10,
    ):
        """
        Args:
            kelly_fraction: Fraction of full Kelly to use (0.5 = half-Kelly).
            max_position_pct: Maximum position as fraction of equity.
            min_trades_required: Minimum completed trades before using Kelly
                                 (falls back to fixed fraction otherwise).
        """
        self.kelly_fraction = kelly_fraction
        self.max_position_pct = max_position_pct
        self.min_trades_required = min_trades_required

    def calculate(self, ctx: SizingContext) -> SizingResult:
        # Fall back to conservative sizing if insufficient trade history
        if (
            ctx.recent_avg_loss == 0
            or ctx.recent_avg_win == 0
            or len(ctx.recent_returns) < self.min_trades_required
        ):
            fallback = FixedFractionSizer(fraction=min(self.max_position_pct, 0.10))
            result = fallback.calculate(ctx)
            result.method = "kelly_fallback"
            result.details = f"insufficient history ({len(ctx.recent_returns)} trades)"
            return result

        p = ctx.recent_win_rate
        q = 1 - p
        b = abs(ctx.recent_avg_win / ctx.recent_avg_loss)

        full_kelly = (p * b - q) / b if b > 0 else 0.0
        kelly_pct = full_kelly * self.kelly_fraction * ctx.risk_scale_factor

        # Clamp to [0, max_position_pct]
        kelly_pct = float(np.clip(kelly_pct, 0.0, self.max_position_pct))

        if kelly_pct <= 0:
            return SizingResult(
                method="kelly",
                details=f"Kelly suggests 0% (p={p:.2f}, b={b:.2f})",
            )

        available = ctx.current_equity * kelly_pct * ctx.signal_strength
        cost_mult = (1 + ctx.slippage) * (1 + ctx.commission)
        if ctx.current_price * cost_mult <= 0:
            return SizingResult(method="kelly")

        raw_shares = available / (ctx.current_price * cost_mult)
        shares = self._clamp_shares(raw_shares, ctx)
        value = shares * ctx.current_price

        return SizingResult(
            shares=shares,
            position_value=value,
            fraction_of_equity=value / ctx.current_equity if ctx.current_equity > 0 else 0.0,
            method="kelly",
            details=(
                f"full_kelly={full_kelly:.2%}, "
                f"applied={kelly_pct:.2%} "
                f"(×{self.kelly_fraction} fraction, "
                f"p={p:.2f}, b={b:.2f})"
            ),
        )


class VolatilityTargetSizer(BasePositionSizer):
    """Scale position so expected portfolio volatility matches a target.

    ``position_fraction = target_vol / (realized_vol * sqrt(252))``
    """

    def __init__(
        self,
        target_vol: float = 0.15,
        lookback: int = 20,
        max_leverage: float = 1.5,
    ):
        """
        Args:
            target_vol: Annualized volatility target.
            lookback: Number of bars to estimate realized volatility.
            max_leverage: Maximum allowed leverage.
        """
        self.target_vol = target_vol
        self.lookback = lookback
        self.max_leverage = max_leverage

    def calculate(self, ctx: SizingContext) -> SizingResult:
        if len(ctx.recent_returns) < self.lookback:
            fallback = FixedFractionSizer(fraction=1.0)
            result = fallback.calculate(ctx)
            result.method = "vol_target_fallback"
            result.details = f"insufficient data ({len(ctx.recent_returns)} < {self.lookback})"
            return result

        recent = np.array(ctx.recent_returns[-self.lookback:])
        realized_vol = float(np.std(recent, ddof=1)) * np.sqrt(252)

        if realized_vol <= 1e-10:
            fraction = self.max_leverage
        else:
            fraction = self.target_vol / realized_vol

        fraction = float(np.clip(fraction, 0.0, self.max_leverage))
        fraction *= ctx.risk_scale_factor * ctx.signal_strength

        available = ctx.current_equity * fraction
        cost_mult = (1 + ctx.slippage) * (1 + ctx.commission)
        if ctx.current_price * cost_mult <= 0:
            return SizingResult(method="vol_target")

        raw_shares = available / (ctx.current_price * cost_mult)
        shares = self._clamp_shares(raw_shares, ctx)
        value = shares * ctx.current_price

        return SizingResult(
            shares=shares,
            position_value=value,
            fraction_of_equity=value / ctx.current_equity if ctx.current_equity > 0 else 0.0,
            method="vol_target",
            details=(
                f"realized_vol={realized_vol:.2%}, "
                f"target_vol={self.target_vol:.2%}, "
                f"fraction={fraction:.2%}"
            ),
        )


class EqualRiskSizer(BasePositionSizer):
    """Size positions so each contributes equal risk to the portfolio.

    ``weight_i = (1 / vol_i) / sum(1 / vol_j for j in assets)``

    For single-asset use, this simplifies to volatility-inverse sizing
    capped at total equity.
    """

    def __init__(
        self,
        lookback: int = 20,
        max_position_pct: float = 1.0,
    ):
        self.lookback = lookback
        self.max_position_pct = max_position_pct

    def calculate(self, ctx: SizingContext) -> SizingResult:
        if len(ctx.recent_returns) < self.lookback:
            fallback = FixedFractionSizer(fraction=min(self.max_position_pct, 0.5))
            result = fallback.calculate(ctx)
            result.method = "equal_risk_fallback"
            return result

        recent = np.array(ctx.recent_returns[-self.lookback:])
        vol = float(np.std(recent, ddof=1))

        if vol <= 1e-10:
            fraction = self.max_position_pct
        else:
            # Inverse-vol weighting normalized to [0, max_position_pct]
            inv_vol = 1.0 / vol
            # Scale factor: target ~5% daily risk budget
            fraction = min(0.01 / vol, self.max_position_pct)

        fraction *= ctx.risk_scale_factor * ctx.signal_strength
        fraction = float(np.clip(fraction, 0.0, self.max_position_pct))

        available = ctx.current_equity * fraction
        cost_mult = (1 + ctx.slippage) * (1 + ctx.commission)
        if ctx.current_price * cost_mult <= 0:
            return SizingResult(method="equal_risk")

        raw_shares = available / (ctx.current_price * cost_mult)
        shares = self._clamp_shares(raw_shares, ctx)
        value = shares * ctx.current_price

        return SizingResult(
            shares=shares,
            position_value=value,
            fraction_of_equity=value / ctx.current_equity if ctx.current_equity > 0 else 0.0,
            method="equal_risk",
            details=f"daily_vol={vol:.4f}, fraction={fraction:.2%}",
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
SIZER_REGISTRY = {
    "fixed_fraction": FixedFractionSizer,
    "kelly": KellyCriterionSizer,
    "vol_target": VolatilityTargetSizer,
    "equal_risk": EqualRiskSizer,
}


def create_position_sizer(method: str = "fixed_fraction", **kwargs) -> BasePositionSizer:
    """Factory function to create a position sizer by name.

    Args:
        method: One of 'fixed_fraction', 'kelly', 'vol_target', 'equal_risk'.
        **kwargs: Arguments forwarded to the sizer constructor.

    Returns:
        An instance of :class:`BasePositionSizer`.
    """
    cls = SIZER_REGISTRY.get(method)
    if cls is None:
        raise ValueError(
            f"Unknown position sizer '{method}'. "
            f"Available: {list(SIZER_REGISTRY.keys())}"
        )
    return cls(**kwargs)
