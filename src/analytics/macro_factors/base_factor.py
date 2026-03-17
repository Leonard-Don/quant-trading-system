"""
宏观因子基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class FactorResult:
    """标准化因子输出。"""

    name: str
    value: float
    z_score: float
    signal: int
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": round(float(self.value), 4),
            "z_score": round(float(self.z_score), 4),
            "signal": int(self.signal),
            "confidence": round(float(self.confidence), 4),
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class MacroFactor(ABC):
    """宏观因子抽象基类。"""

    name: str = "macro_factor"
    default_threshold: float = 0.25

    def __init__(self, threshold: Optional[float] = None):
        self.threshold = threshold if threshold is not None else self.default_threshold

    @abstractmethod
    def compute(self, data_context: Dict[str, Any]) -> FactorResult:
        """从上下文中计算因子。"""

    def _build_result(
        self,
        value: float,
        history: Optional[List[float]] = None,
        confidence: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FactorResult:
        z_score = self._compute_z_score(value, history or [])
        signal = self._to_signal(value)
        return FactorResult(
            name=self.name,
            value=value,
            z_score=z_score,
            signal=signal,
            confidence=confidence,
            metadata=metadata or {},
        )

    def _to_signal(self, value: float) -> int:
        if value >= self.threshold:
            return 1
        if value <= -self.threshold:
            return -1
        return 0

    @staticmethod
    def _compute_z_score(value: float, history: List[float]) -> float:
        valid_history = [float(item) for item in history if item is not None]
        if len(valid_history) < 2:
            return 0.0
        mean = float(np.mean(valid_history))
        std = float(np.std(valid_history))
        if std == 0:
            return 0.0
        return (float(value) - mean) / std
