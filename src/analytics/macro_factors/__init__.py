"""宏观错误定价因子库。"""

from .base_factor import FactorResult, MacroFactor
from .baseload_mismatch import BaseloadMismatchFactor
from .bureaucratic_friction import BureaucraticFrictionFactor
from .factor_combiner import FactorCombiner
from .factor_registry import FactorRegistry, build_default_registry
from .history import MacroHistoryStore
from .tech_dilution import TechDilutionFactor

__all__ = [
    "FactorResult",
    "MacroFactor",
    "BaseloadMismatchFactor",
    "BureaucraticFrictionFactor",
    "FactorCombiner",
    "FactorRegistry",
    "MacroHistoryStore",
    "TechDilutionFactor",
    "build_default_registry",
]
