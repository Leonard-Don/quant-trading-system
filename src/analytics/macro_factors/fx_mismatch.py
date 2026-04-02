"""
汇率错配因子。
"""

from __future__ import annotations

from typing import Any, Dict

from .base_factor import MacroFactor


class FXMismatchFactor(MacroFactor):
    """用美元指数和贸易脉冲近似跨市场汇率错配压力。"""

    name = "fx_mismatch"
    default_threshold = 0.15

    def compute(self, data_context: Dict[str, Any]):
        indicators = data_context.get("market_indicators", {}) or {}
        macro_signal = data_context.get("signals", {}).get("macro_hf", {}) or {}
        trade_score = float(macro_signal.get("dimensions", {}).get("trade", {}).get("score", 0.0))
        inventory_score = float(macro_signal.get("dimensions", {}).get("inventory", {}).get("score", 0.0))
        logistics_score = float(macro_signal.get("dimensions", {}).get("logistics", {}).get("score", 0.0))
        dxy_pressure = _normalize_dxy(indicators.get("dxy"))

        mismatch_value = max(
            -1.0,
            min(
                1.0,
                dxy_pressure * 0.55 + max(-trade_score, 0.0) * 0.25 + max(logistics_score, 0.0) * 0.1 + max(inventory_score, 0.0) * 0.1,
            ),
        )
        confidence = min(
            1.0,
            0.42
            + (0.22 if indicators.get("dxy") is not None else 0.0)
            + float(macro_signal.get("confidence", 0.0)) * 0.28,
        )

        history = [0.0, 0.05, 0.09, 0.12]
        return self._build_result(
            value=mismatch_value,
            history=history,
            confidence=confidence,
            metadata={
                "dxy": indicators.get("dxy"),
                "trade_score": round(trade_score, 4),
                "inventory_score": round(inventory_score, 4),
                "logistics_score": round(logistics_score, 4),
            },
        )


def _normalize_dxy(value: Any) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    return max(-1.0, min(1.0, (numeric - 103.0) / 8.0))
