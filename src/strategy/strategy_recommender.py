"""Map a :class:`MarketRegime` to a concrete strategy recommendation.

Companion module to :mod:`src.strategy.market_regime_classifier`. The
classifier already knows the canonical regime → strategy mapping (the
:data:`market_regime_classifier._RECOMMENDATION_TABLE`), but consumers
often want a stable, typed return value separate from the classifier's
output dataclass. This module:

* Exposes :class:`StrategyRecommendation` — a small dataclass the
  backend / CLI / frontend can pass around without re-importing the
  classifier internals.
* Exposes :func:`recommend_strategy` — the public API the dashboard
  tile / CLI calls. Idempotent on the same :class:`MarketRegime`.
* Lets a caller layer extra overrides on top of the canonical map
  (e.g. force ``min_score_to_hold`` higher when the operator is
  paranoid about a specific window) without mutating the canonical
  table — :func:`recommend_strategy` always returns a fresh
  dataclass.

Bear in mind: this module is intentionally *value-only*. It does not
load or apply any config; the caller is responsible for actually
swapping the running strategy. That keeps the recommender pure +
testable without spinning up the rotation service.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional

from .market_regime_classifier import (
    _RECOMMENDATION_TABLE,
    MarketRegime,
)


@dataclass(frozen=True)
class StrategyRecommendation:
    """A single strategy recommendation with overrides + rationale."""

    strategy_name: str
    config_overrides: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    alternatives: list[str] = field(default_factory=list)
    regime_name: Optional[str] = None
    confidence: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "config_overrides": dict(self.config_overrides),
            "rationale": self.rationale,
            "alternatives": list(self.alternatives),
            "regime_name": self.regime_name,
            "confidence": (
                float(self.confidence) if self.confidence is not None else None
            ),
        }


def recommend_strategy(
    regime: MarketRegime,
    *,
    extra_overrides: Optional[Mapping[str, Any]] = None,
) -> StrategyRecommendation:
    """Map a :class:`MarketRegime` to a :class:`StrategyRecommendation`.

    Args:
        regime: The classifier's output.
        extra_overrides: Optional caller-supplied config overrides
            layered on top of the canonical map (later keys win).
            Useful when the operator wants to override a specific
            parameter without forking the recommender.

    Returns:
        A fresh :class:`StrategyRecommendation`. The function never
        mutates its inputs and never raises — an unknown regime name
        falls back to the ``unknown`` row of the canonical table.
    """

    if regime is None:
        # Defensive: a None regime should never happen in practice but
        # we want the API to be total. Return a no-op recommendation.
        return StrategyRecommendation(
            strategy_name="unchanged",
            config_overrides={},
            rationale=(
                "No regime supplied; cannot recommend a strategy. "
                "Pass a MarketRegime from MarketRegimeClassifier.classify()."
            ),
            alternatives=[],
            regime_name=None,
            confidence=None,
        )

    entry = _RECOMMENDATION_TABLE.get(
        regime.regime_name, _RECOMMENDATION_TABLE["unknown"]
    )
    overrides = dict(entry["config_overrides"])
    if extra_overrides:
        overrides.update(dict(extra_overrides))
    return StrategyRecommendation(
        strategy_name=str(entry["strategy_name"]),
        config_overrides=overrides,
        rationale=str(entry["rationale"]),
        alternatives=list(entry["alternatives"]),
        regime_name=regime.regime_name,
        confidence=float(regime.confidence) if regime.confidence is not None else None,
    )


__all__ = [
    "StrategyRecommendation",
    "recommend_strategy",
]
