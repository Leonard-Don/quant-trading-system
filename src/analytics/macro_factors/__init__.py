"""宏观错误定价因子库。"""

from .base_factor import FactorResult, MacroFactor
from .baseload_mismatch import BaseloadMismatchFactor
from .bureaucratic_friction import BureaucraticFrictionFactor
from .credit_spread_stress import CreditSpreadStressFactor
from .factor_combiner import FactorCombiner
from .factor_registry import FactorRegistry, build_default_registry
from .fx_mismatch import FXMismatchFactor
from .history import MacroHistoryStore
from .people_fragility import PeopleFragilityFactor
from .policy_execution_disorder import PolicyExecutionDisorderFactor
from .rate_curve_pressure import RateCurvePressureFactor
from .tech_dilution import TechDilutionFactor

__all__ = [
    "FactorResult",
    "MacroFactor",
    "BaseloadMismatchFactor",
    "BureaucraticFrictionFactor",
    "CreditSpreadStressFactor",
    "FactorCombiner",
    "FactorRegistry",
    "FXMismatchFactor",
    "MacroHistoryStore",
    "PeopleFragilityFactor",
    "PolicyExecutionDisorderFactor",
    "RateCurvePressureFactor",
    "TechDilutionFactor",
    "build_default_registry",
]
