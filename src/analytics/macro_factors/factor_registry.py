"""
宏观因子注册中心。
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .base_factor import MacroFactor
from .baseload_mismatch import BaseloadMismatchFactor
from .bureaucratic_friction import BureaucraticFrictionFactor
from .credit_spread_stress import CreditSpreadStressFactor
from .fx_mismatch import FXMismatchFactor
from .people_fragility import PeopleFragilityFactor
from .policy_execution_disorder import PolicyExecutionDisorderFactor
from .rate_curve_pressure import RateCurvePressureFactor
from .tech_dilution import TechDilutionFactor


class FactorRegistry:
    """负责管理和执行因子。"""

    def __init__(self, factors: Optional[Iterable[MacroFactor]] = None):
        self._factors: Dict[str, MacroFactor] = {}
        for factor in factors or []:
            self.register(factor)

    def register(self, factor: MacroFactor) -> None:
        self._factors[factor.name] = factor

    def get(self, name: str) -> MacroFactor:
        return self._factors[name]

    def all(self) -> List[MacroFactor]:
        return list(self._factors.values())

    def compute_all(self, data_context):
        return [factor.compute(data_context) for factor in self.all()]


def build_default_registry() -> FactorRegistry:
    return FactorRegistry(
        [
            BureaucraticFrictionFactor(),
            TechDilutionFactor(),
            PeopleFragilityFactor(),
            PolicyExecutionDisorderFactor(),
            BaseloadMismatchFactor(),
            RateCurvePressureFactor(),
            CreditSpreadStressFactor(),
            FXMismatchFactor(),
        ]
    )
