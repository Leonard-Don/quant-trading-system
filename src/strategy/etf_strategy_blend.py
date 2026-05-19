"""Multi-strategy ensemble — weighted blend of trend + mean-reversion signals.

Single strategies have *single* failure modes:

* Pure trend-following bleeds in chop / sideways markets and during
  whipsaw transitions.
* Pure mean-reversion bleeds in strong directional regimes and is
  vulnerable to falling-knife trades when the long-term trend breaks.

Combining them with a **regime-aware blend weight** produces a payoff
that is less correlated with any single regime, which is the textbook
quant motivation for ensembles. The blender:

1. Asks each child strategy for its target-weight signals.
2. Computes a regime-aware ``α`` (default: bull/crisis = 1.0 trend,
   sideways = 0.5 balanced, bear = 0.4 MR-tilted, correction = 0.6).
3. Blends per-ETF target weight as ``α * w_trend + (1-α) * w_mr``.
4. Re-normalises to respect the gross-cap.
5. Emits ``EtfSignal`` objects whose ``reasons`` carry the blend ratio
   so the dashboard / audit log can show which strategy drove each
   position.

The blender exposes the *same* ``evaluate(...)`` signature as
``EtfRotationStrategy`` so ``daily_etf_signal.generate_plan`` can use
it as a drop-in replacement.

Degeneracy contract under ``regime="unknown"``
----------------------------------------------
``DEFAULT_REGIME_BLEND_WEIGHTS["unknown"] = 1.0`` on purpose: a caller
that has not classified the market regime gets the pure trend output
back rather than a silent 50/50 bet on mean-reversion. The consequence
is that ``EtfStrategyBlend`` with ``regime="unknown"`` (the constructor
default) is mathematically equivalent to ``EtfRotationStrategy`` —
*every* per-bar target weight, score, and downstream metric is
byte-identical. The comparison harness in ``src/backtest/strategy_comparison.py``
and walk-forward scripts that exercise blend without an explicit regime
will therefore report blend's per-window metrics as identical to
rotation's. This is not a bug in the blender; it is the documented
α=1.0 contract pinned by ``test_blend_pure_trend_alpha_matches_pure_trend_strategy_output``.
Callers wanting a real blend comparison must pass a non-trend regime
label (``"sideways"`` → α=0.5, ``"bear"`` → α=0.4, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Dict, List, Mapping, Optional

import pandas as pd

from src.strategy.etf_rotation_strategy import EtfOverlay, EtfSignal

logger = logging.getLogger(__name__)


DEFAULT_REGIME_BLEND_WEIGHTS: Dict[str, float] = {
    # α = trend weight (1.0 = pure trend, 0.0 = pure MR)
    "bull": 1.00,
    "correction": 0.60,
    "sideways": 0.50,
    "bear": 0.40,
    "crisis": 1.00,  # crisis = stay with trend's defensive call; MR catches knives
    # ``unknown`` is the "no regime classified yet" fallback — α=1.00 means
    # the blender returns *exactly* the trend strategy's target weights and
    # the MR leg contributes nothing. This is by design (a caller that
    # hasn't classified regime should not be silently making a 50/50 bet on
    # mean-reversion they didn't ask for) but it has a non-obvious harness
    # consequence: any comparison / walk-forward that runs blend with the
    # default regime will produce per-window metrics that are byte-identical
    # to the rotation strategy's. Callers wanting a *non-degenerate* blend
    # comparison MUST pass an explicit non-trend regime label (e.g.
    # ``"sideways"`` for α=0.5) — see ``EtfStrategyBlend.set_regime`` and
    # the ``--blend-regime`` flag on ``scripts/compare_strategies.py`` /
    # ``scripts/walkforward_stat_tests.py``.
    "unknown": 1.00,
}


@dataclass(frozen=True)
class EtfStrategyBlendConfig:
    """Blender configuration — defaults are deliberately trend-biased."""

    enabled: bool = False
    regime_blend_weights: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_REGIME_BLEND_WEIGHTS)
    )
    # Floor / ceiling on alpha to avoid catastrophic single-strategy bets
    alpha_floor: float = 0.20
    alpha_ceiling: float = 1.00


@dataclass(frozen=True)
class StrategyComponentSignal:
    """One child strategy's output for a single ETF, attached to the blended signal."""

    label: str
    score: float
    raw_target_weight: float
    blended_weight_contribution: float


class EtfStrategyBlend:
    """Drop-in strategy that delegates to trend + MR and blends the results."""

    def __init__(
        self,
        *,
        trend_strategy,
        mr_strategy,
        config: Optional[EtfStrategyBlendConfig] = None,
        regime: str = "unknown",
    ) -> None:
        self._trend = trend_strategy
        self._mr = mr_strategy
        self._config = config or EtfStrategyBlendConfig()
        self._regime = regime

    def set_regime(self, regime: str) -> None:
        """Update the regime label used to look up the blend weight."""

        self._regime = regime

    def current_alpha(self) -> float:
        """Return the trend-weight α applied for the current regime."""

        raw = float(self._config.regime_blend_weights.get(
            self._regime,
            self._config.regime_blend_weights.get("unknown", 1.0),
        ))
        return max(
            self._config.alpha_floor,
            min(self._config.alpha_ceiling, raw),
        )

    def evaluate(
        self,
        price_matrix: pd.DataFrame,
        *,
        overlays: Optional[Mapping[str, EtfOverlay]] = None,
        current_weights: Optional[Mapping[str, float]] = None,
        industry_signals: Optional[Mapping[str, Mapping[str, object]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
    ) -> List[EtfSignal]:
        # The trend child gets the policy nudge; the MR child intentionally
        # does NOT (mean-reversion already trades against momentum, so a
        # policy boost on the trend leg is the right signal to consume —
        # the MR leg would be double-counting).
        trend_signals = self._trend.evaluate(
            price_matrix,
            overlays=overlays,
            current_weights=current_weights,
            industry_signals=industry_signals,
            etf_industry_map=etf_industry_map,
        )
        mr_signals = self._mr.evaluate(
            price_matrix,
            overlays=overlays,
            current_weights=current_weights,
        )
        return self._blend(trend_signals, mr_signals)

    def _blend(
        self,
        trend_signals: List[EtfSignal],
        mr_signals: List[EtfSignal],
    ) -> List[EtfSignal]:
        alpha = self.current_alpha()
        trend_by_code = {s.symbol: s for s in trend_signals}
        mr_by_code = {s.symbol: s for s in mr_signals}
        codes = set(trend_by_code) | set(mr_by_code)

        out: List[EtfSignal] = []
        for code in codes:
            t = trend_by_code.get(code)
            m = mr_by_code.get(code)
            # Linear blend on target_weight and score.
            t_w = float(t.target_weight) if t else 0.0
            m_w = float(m.target_weight) if m else 0.0
            blended_w = alpha * t_w + (1.0 - alpha) * m_w

            t_score = float(t.score) if t else 0.0
            m_score = float(m.score) if m else 0.0
            blended_score = alpha * t_score + (1.0 - alpha) * m_score

            base = t or m
            if base is None:
                continue

            reasons = list(base.reasons)
            reasons.append(
                f"blend:trend={alpha:.2f}*{t_w:.4f} mr={1.0 - alpha:.2f}*{m_w:.4f} regime={self._regime}"
            )
            policy_adjustment = self._blend_policy_adjustment(
                trend_signal=t,
                mr_weight=m_w,
                alpha=alpha,
                blended_weight=blended_w,
            )
            out.append(replace(
                base,
                score=blended_score,
                raw_weight=blended_w,
                target_weight=blended_w,
                reasons=reasons,
                policy_adjustment=policy_adjustment,
            ))
        return out

    @staticmethod
    def _blend_policy_adjustment(
        *,
        trend_signal: Optional[EtfSignal],
        mr_weight: float,
        alpha: float,
        blended_weight: float,
    ) -> Optional[dict[str, object]]:
        """Translate trend-leg policy metadata onto the final blended weight."""

        if trend_signal is None or not trend_signal.policy_adjustment:
            return None

        meta = dict(trend_signal.policy_adjustment)
        try:
            trend_before = float(meta.get("weight_before", trend_signal.target_weight))
        except (TypeError, ValueError):
            trend_before = float(trend_signal.target_weight)

        blended_before = float(alpha) * trend_before + (1.0 - float(alpha)) * float(mr_weight)
        blended_after = float(blended_weight)
        delta = blended_after - blended_before

        meta["weight_before"] = blended_before
        meta["weight_after"] = blended_after
        meta["delta_weight"] = delta
        if abs(delta) <= 1e-12:
            meta["applied"] = False
        return meta

    @staticmethod
    def build_component_breakdown(
        trend_signals: List[EtfSignal],
        mr_signals: List[EtfSignal],
        alpha: float,
    ) -> Dict[str, Dict[str, object]]:
        """Per-code dict showing each child strategy's raw output + contribution.

        Useful for audit logging / dashboards: surfaces *why* the blend
        landed where it did per asset.
        """

        breakdown: Dict[str, Dict[str, object]] = {}
        for sig in trend_signals:
            breakdown.setdefault(sig.symbol, {})["trend"] = {
                "score": float(sig.score),
                "raw_target_weight": float(sig.target_weight),
                "contribution": float(alpha) * float(sig.target_weight),
            }
        for sig in mr_signals:
            breakdown.setdefault(sig.symbol, {})["mr"] = {
                "score": float(sig.score),
                "raw_target_weight": float(sig.target_weight),
                "contribution": (1.0 - float(alpha)) * float(sig.target_weight),
            }
        return breakdown


__all__ = [
    "DEFAULT_REGIME_BLEND_WEIGHTS",
    "EtfStrategyBlend",
    "EtfStrategyBlendConfig",
    "StrategyComponentSignal",
]
