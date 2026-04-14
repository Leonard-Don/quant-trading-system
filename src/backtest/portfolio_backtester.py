"""Multi-asset portfolio backtester built on target-weight execution."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from .base_backtester import BaseBacktester
from .execution_engine import PortfolioExecutionConfig, PortfolioExecutionEngine
from .impact_model import normalize_market_impact_model, summarize_execution_costs
from .signal_adapter import SignalAdapter


class PortfolioBacktester(BaseBacktester):
    """Backtest multi-asset target-weight strategies."""

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.001,
        *,
        allow_fractional_shares: bool = False,
        max_gross_exposure: float = 1.0,
        min_trade_value: float = 0.0,
        min_rebalance_weight_delta: float = 0.0,
        max_turnover_per_rebalance: Optional[float] = None,
        fixed_commission: float = 0.0,
        min_commission: float = 0.0,
        market_impact_bps: float = 0.0,
        market_impact_model: str = "constant",
        impact_reference_notional: float = 100000.0,
        impact_coefficient: float = 1.0,
        permanent_impact_bps: float = 0.0,
    ):
        super().__init__(
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
        )
        self.execution_config = PortfolioExecutionConfig(
            allow_fractional_shares=allow_fractional_shares,
            max_gross_exposure=max_gross_exposure,
            min_trade_value=min_trade_value,
            min_rebalance_weight_delta=min_rebalance_weight_delta,
            max_turnover_per_rebalance=max_turnover_per_rebalance,
            fixed_commission=fixed_commission,
            min_commission=min_commission,
            market_impact_bps=market_impact_bps,
            market_impact_model=normalize_market_impact_model(market_impact_model),
            impact_reference_notional=impact_reference_notional,
            impact_coefficient=impact_coefficient,
            permanent_impact_bps=permanent_impact_bps,
        )

    def run(self, strategy: Any, data: Any, **kwargs: Any) -> Dict[str, Any]:
        price_matrix = self._prepare_price_matrix(data)
        if price_matrix.empty:
            return {}

        raw_signals = strategy.generate_signals(price_matrix)
        target_weights = SignalAdapter.normalize_target_weights(
            raw_signals,
            index=price_matrix.index,
            columns=price_matrix.columns,
            max_gross_exposure=self.execution_config.max_gross_exposure,
        )

        engine = PortfolioExecutionEngine(
            initial_capital=self.initial_capital,
            commission=self.commission,
            slippage=self.slippage,
            config=self.execution_config,
        )
        execution = engine.execute(price_data=price_matrix, target_weights=target_weights)

        portfolio_history = execution["portfolio_history"]
        if portfolio_history.empty:
            return {}

        metrics = self.calculate_common_metrics(portfolio_history["total"])
        metrics.update(
            {
                "initial_capital": self.initial_capital,
                "final_value": float(portfolio_history["total"].iloc[-1]),
                "num_trades": len(execution["trades"]),
                "portfolio_history": portfolio_history.reset_index().to_dict("records"),
                "positions_history": execution["positions"].reset_index().to_dict("records"),
                "trades": execution["trades"],
                "assets": list(price_matrix.columns),
                "execution_costs": summarize_execution_costs(execution["trades"]),
                "execution_diagnostics": {
                    "market_impact_bps": self.execution_config.market_impact_bps,
                    "market_impact_model": self.execution_config.market_impact_model,
                    "impact_reference_notional": self.execution_config.impact_reference_notional,
                    "impact_coefficient": self.execution_config.impact_coefficient,
                    "permanent_impact_bps": self.execution_config.permanent_impact_bps,
                    "fixed_commission": self.execution_config.fixed_commission,
                    "min_commission": self.execution_config.min_commission,
                },
            }
        )
        self.results = metrics
        return metrics

    @staticmethod
    def _prepare_price_matrix(data: Any) -> pd.DataFrame:
        if isinstance(data, pd.DataFrame):
            frame = data.copy()
        elif isinstance(data, dict):
            series_map = {}
            for asset, frame in data.items():
                if isinstance(frame, pd.DataFrame):
                    close_col = "close" if "close" in frame.columns else "Close"
                    series_map[asset] = pd.to_numeric(frame[close_col], errors="coerce")
                else:
                    series_map[asset] = pd.to_numeric(pd.Series(frame), errors="coerce")
            frame = pd.DataFrame(series_map)
        else:
            raise ValueError("PortfolioBacktester data must be a DataFrame or dict of DataFrames")

        frame = frame.apply(pd.to_numeric, errors="coerce").dropna(how="all")
        frame = frame.ffill().dropna()
        return frame
