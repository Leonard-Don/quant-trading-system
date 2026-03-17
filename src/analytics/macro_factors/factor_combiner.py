"""
宏观因子合成器。
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .base_factor import FactorResult


class FactorCombiner:
    """对多个宏观因子进行加权合成。"""

    def combine(
        self,
        results: Iterable[FactorResult],
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, object]:
        factor_results = list(results)
        if not factor_results:
            return {
                "score": 0.0,
                "signal": 0,
                "confidence": 0.0,
                "factors": [],
            }

        weights = weights or {}
        total_weight = 0.0
        weighted_score = 0.0
        weighted_confidence = 0.0

        for result in factor_results:
            weight = float(weights.get(result.name, 1.0))
            total_weight += weight
            weighted_score += result.value * weight
            weighted_confidence += result.confidence * weight

        score = weighted_score / total_weight if total_weight else 0.0
        confidence = weighted_confidence / total_weight if total_weight else 0.0

        if score > 0.2:
            signal = 1
        elif score < -0.2:
            signal = -1
        else:
            signal = 0

        return {
            "score": round(score, 4),
            "signal": signal,
            "confidence": round(confidence, 4),
            "factors": [result.to_dict() for result in factor_results],
        }
