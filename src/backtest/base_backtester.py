"""
Base Backtester Abstract Class

Provides a unified interface for all backtesting engines.  Concrete
backtester classes (single-asset, cross-market, industry rotation) inherit
from this base class and implement the ``run()`` method.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .metrics import (
    calculate_annualized_return,
    calculate_calmar_ratio,
    calculate_cvar,
    calculate_max_drawdown,
    calculate_max_drawdown_duration,
    calculate_omega_ratio,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_var,
    calculate_volatility,
)

logger = logging.getLogger(__name__)


class BaseBacktester(ABC):
    """Abstract base class for all backtest engines.

    Subclasses **must** implement :meth:`run`.  The base class provides:

    * Standard construction parameters (``initial_capital``, ``commission``,
      ``slippage``).
    * :meth:`calculate_common_metrics` — a shared helper that computes
      core risk/return metrics from an equity curve.
    * :attr:`results` — stores the latest run result.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        commission: float = 0.001,
        slippage: float = 0.001,
    ):
        """
        Args:
            initial_capital: Starting capital for the backtest.
            commission: One-way commission rate (e.g. 0.001 = 0.1 %).
            slippage: Slippage rate applied to each fill.
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.results: Dict[str, Any] = {}

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Execute a backtest and return the results dictionary.

        Every concrete subclass must implement this method.  The returned
        dictionary **should** include at minimum::

            {
                "portfolio_history": [...],  # list of dicts with 'date', 'total'
                "trades": [...],             # list of trade records
                "total_return": float,
                "sharpe_ratio": float,
                "max_drawdown": float,
            }
        """
        ...

    def calculate_common_metrics(
        self,
        equity_curve: pd.Series,
        *,
        trading_days_per_year: int = 252,
    ) -> Dict[str, Any]:
        """Compute standard risk/return metrics from an equity curve.

        This is designed to be called by any subclass after the simulation
        loop completes, ensuring consistent metric definitions across all
        backtesting engines.

        Args:
            equity_curve: A ``pd.Series`` of portfolio values indexed by
                date/bar.
            trading_days_per_year: Used for annualization.

        Returns:
            Dictionary of computed metrics.
        """
        if equity_curve.empty or len(equity_curve) < 2:
            return self._empty_metrics()

        values = equity_curve.values.astype(float)
        total_return = calculate_returns(values)
        n_days = len(values)
        annualized_return = calculate_annualized_return(
            total_return, n_days, trading_days_per_year
        )

        returns = pd.Series(values).pct_change().dropna().replace(
            [np.inf, -np.inf], 0.0
        )

        max_drawdown = calculate_max_drawdown(values)
        dd_duration, underwater = calculate_max_drawdown_duration(values)
        sharpe = calculate_sharpe_ratio(returns, periods_per_year=trading_days_per_year)
        sortino = calculate_sortino_ratio(returns, periods_per_year=trading_days_per_year)
        calmar = calculate_calmar_ratio(annualized_return, max_drawdown)
        volatility = calculate_volatility(returns, periods_per_year=trading_days_per_year)
        var_95 = calculate_var(returns)
        cvar_95 = calculate_cvar(returns)
        omega = calculate_omega_ratio(returns)

        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "volatility": volatility,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown": max_drawdown,
            "max_drawdown_duration": dd_duration,
            "max_underwater_period": underwater,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "omega_ratio": omega,
        }

    @staticmethod
    def _empty_metrics() -> Dict[str, Any]:
        """Return a zeroed-out metrics dict for edge cases."""
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "volatility": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_duration": 0,
            "max_underwater_period": 0,
            "var_95": 0.0,
            "cvar_95": 0.0,
            "omega_ratio": 0.0,
        }
