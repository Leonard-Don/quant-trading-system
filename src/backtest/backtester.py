"""
Backtest engine for testing trading strategies
"""

import logging
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from .base_backtester import BaseBacktester
from .impact_model import (
    estimate_market_impact_rate,
    normalize_market_impact_model,
    summarize_execution_costs,
)
from .signal_adapter import SignalAdapter
from .risk_manager import RiskManager, RiskContext, RiskAction
from .position_sizer import (
    BasePositionSizer,
    FixedFractionSizer,
    SizingContext,
)
from .metrics import (
    calculate_annualized_return,
    calculate_sharpe_ratio, 
    calculate_sortino_ratio,
    calculate_max_drawdown,
    calculate_max_drawdown_duration,
    calculate_calmar_ratio,
    calculate_volatility,
    calculate_var,
    calculate_cvar,
    calculate_omega_ratio,
    calculate_recovery_factor,
    calculate_expectancy,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Configuration for the single-asset execution engine."""

    allow_fractional_shares: bool = False
    signal_mode: str = "auto"  # auto | event | target
    fixed_commission: float = 0.0
    min_commission: float = 0.0
    market_impact_bps: float = 0.0
    market_impact_model: str = "constant"
    impact_reference_notional: float = 100000.0
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0


class SingleAssetExecutionEngine:
    """Execute single-asset strategy signals into a portfolio path.

    The engine supports two signal semantics:
    - ``event``: legacy buy/hold/sell events in ``{-1, 0, 1}``
    - ``target``: target long exposure in ``[0, 1]`` per bar
    """

    def __init__(
        self,
        *,
        initial_capital: float,
        commission: float,
        slippage: float,
        config: ExecutionConfig,
    ):
        self.initial_capital = float(initial_capital)
        self.commission = float(commission)
        self.slippage = float(slippage)
        self.config = config
        self.config.market_impact_model = normalize_market_impact_model(self.config.market_impact_model)

    def execute(
        self,
        *,
        data: pd.DataFrame,
        signals: pd.Series,
        sizer: BasePositionSizer,
        risk_mgr: Optional[RiskManager],
        stop_loss_pct: Optional[float],
        take_profit_pct: Optional[float],
        max_holding_days: Optional[int],
    ) -> Dict[str, Any]:
        signal_mode = self._resolve_signal_mode(signals)
        if signal_mode == "target":
            execution = self._execute_target_exposure(
                data=data,
                signals=signals,
                sizer=sizer,
                risk_mgr=risk_mgr,
                max_holding_days=max_holding_days,
            )
        else:
            execution = self._execute_event_signals(
                data=data,
                signals=signals,
                sizer=sizer,
                risk_mgr=risk_mgr,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                max_holding_days=max_holding_days,
            )
        execution["resolved_signal_mode"] = signal_mode
        return execution

    def _resolve_signal_mode(self, signals: pd.Series) -> str:
        if self.config.signal_mode in {"event", "target"}:
            return self.config.signal_mode

        clean = pd.Series(signals).dropna()
        if clean.empty:
            return "event"

        unique_values = set(np.round(clean.astype(float), 8).tolist())
        if unique_values.issubset({-1.0, 0.0, 1.0}):
            return "event"
        return "target"

    def _normalize_shares(self, shares: float) -> float:
        if shares <= 0:
            return 0.0
        if self.config.allow_fractional_shares:
            return float(shares)
        return float(int(shares))

    def _prepare_execution_context(self, data: pd.DataFrame) -> Dict[str, np.ndarray]:
        prices = pd.to_numeric(data["close"], errors="coerce").replace([np.inf, -np.inf], np.nan)
        returns = prices.pct_change().replace([np.inf, -np.inf], np.nan)
        fallback_volatility = float(returns.std()) if returns.dropna().size else 0.02
        fallback_volatility = max(fallback_volatility, 0.005)
        rolling_volatility = (
            returns.rolling(20, min_periods=2).std().fillna(fallback_volatility).to_numpy(dtype=float)
        )

        if "volume" in data.columns:
            volumes = pd.to_numeric(data["volume"], errors="coerce").clip(lower=0)
            dollar_volume = (prices * volumes).replace([np.inf, -np.inf], np.nan)
            fallback_notional = (
                float(dollar_volume.dropna().median())
                if dollar_volume.dropna().size
                else float(self.config.impact_reference_notional or 100000.0)
            )
            fallback_notional = max(fallback_notional, float(self.config.impact_reference_notional or 100000.0), 1.0)
            avg_daily_notional = (
                dollar_volume.rolling(20, min_periods=1).mean().fillna(fallback_notional).to_numpy(dtype=float)
            )
        else:
            fallback_notional = max(float(self.config.impact_reference_notional or 100000.0), 1.0)
            avg_daily_notional = np.full(len(data), fallback_notional, dtype=float)

        return {
            "avg_daily_notional": avg_daily_notional,
            "volatility": rolling_volatility,
        }

    def _execution_cost_profile(
        self,
        *,
        price: float,
        shares: float,
        bar_index: int,
        market_context: Dict[str, np.ndarray],
    ) -> Dict[str, float | str]:
        trade_notional = abs(float(price or 0.0) * float(shares or 0.0))
        impact = estimate_market_impact_rate(
            trade_notional,
            market_impact_bps=self.config.market_impact_bps,
            model=self.config.market_impact_model,
            avg_daily_notional=float(market_context["avg_daily_notional"][bar_index]),
            volatility=float(market_context["volatility"][bar_index]),
            impact_coefficient=self.config.impact_coefficient,
            permanent_impact_bps=self.config.permanent_impact_bps,
            reference_notional=self.config.impact_reference_notional,
        )
        total_slippage_rate = float(self.slippage) + float(impact["impact_rate"])
        return {
            **impact,
            "trade_notional": trade_notional,
            "total_slippage_rate": total_slippage_rate,
            "estimated_market_impact_cost": trade_notional * float(impact["impact_rate"]),
            "estimated_total_slippage_cost": trade_notional * total_slippage_rate,
        }

    def _commission_cost(self, notional: float) -> float:
        if notional <= 0:
            return 0.0
        commission_cost = (notional * self.commission) + float(self.config.fixed_commission or 0.0)
        return float(max(commission_cost, float(self.config.min_commission or 0.0)))

    def _build_portfolio(
        self,
        *,
        data: pd.DataFrame,
        signal_array: np.ndarray,
        price_array: np.ndarray,
        position_array: np.ndarray,
        cash_array: np.ndarray,
        holdings_array: np.ndarray,
        total_array: np.ndarray,
    ) -> pd.DataFrame:
        portfolio = pd.DataFrame(
            {
                "price": price_array,
                "signal": signal_array,
                "position": position_array,
                "cash": cash_array,
                "holdings": holdings_array,
                "total": total_array,
            },
            index=data.index,
        )
        portfolio["returns"] = portfolio["total"].pct_change()
        return portfolio

    def _execute_event_signals(
        self,
        *,
        data: pd.DataFrame,
        signals: pd.Series,
        sizer: BasePositionSizer,
        risk_mgr: Optional[RiskManager],
        stop_loss_pct: Optional[float],
        take_profit_pct: Optional[float],
        max_holding_days: Optional[int],
    ) -> Dict[str, Any]:
        price_array = data["close"].astype(float).to_numpy()
        signal_array = signals.astype(int).to_numpy()
        bar_count = len(price_array)
        position_array = np.zeros(bar_count, dtype=float)
        cash_array = np.zeros(bar_count, dtype=float)
        holdings_array = np.zeros(bar_count, dtype=float)
        total_array = np.zeros(bar_count, dtype=float)

        trades: List[Dict[str, Any]] = []
        trade_pnls: List[float] = []
        current_position = 0.0
        current_cash = self.initial_capital
        avg_cost_basis = 0.0
        current_entry_date = None
        peak_equity = self.initial_capital
        prev_total = self.initial_capital
        market_context = self._prepare_execution_context(data)

        for i, (price, signal) in enumerate(zip(price_array, signal_array)):
            current_equity = current_cash + current_position * price
            daily_ret = (
                (current_equity - prev_total) / prev_total if prev_total > 0 else 0.0
            )
            peak_equity = max(peak_equity, current_equity)

            if risk_mgr is not None:
                risk_ctx = RiskContext(
                    bar_index=i,
                    current_price=price,
                    current_date=data.index[i],
                    position_size=float(current_position),
                    entry_price=avg_cost_basis,
                    entry_date=current_entry_date,
                    current_equity=current_equity,
                    peak_equity=peak_equity,
                    initial_capital=self.initial_capital,
                    daily_return=daily_ret,
                    recent_trade_pnls=trade_pnls.copy(),
                )
                decision = risk_mgr.evaluate(risk_ctx)
                if decision.action == RiskAction.FORCE_EXIT and current_position > 0:
                    signal = -1
                elif decision.action == RiskAction.BLOCK_ENTRY and signal == 1:
                    signal = 0
            else:
                if current_position > 0 and avg_cost_basis > 0:
                    unrealized_return = (price - avg_cost_basis) / avg_cost_basis
                    if stop_loss_pct is not None and unrealized_return <= -stop_loss_pct:
                        signal = -1
                    elif (
                        current_entry_date is not None
                        and max_holding_days is not None
                        and (data.index[i] - current_entry_date).days >= max_holding_days
                    ):
                        signal = -1
                    elif (
                        take_profit_pct is not None
                        and unrealized_return >= take_profit_pct
                    ):
                        signal = -1

            if signal == 1 and current_position == 0:
                sizing_ctx = SizingContext(
                    current_equity=current_equity,
                    current_price=price,
                    signal_strength=1.0,
                    commission=self.commission,
                    slippage=self.slippage,
                    risk_scale_factor=(
                        risk_mgr.get_position_scale() if risk_mgr else 1.0
                    ),
                    allow_fractional=self.config.allow_fractional_shares,
                )
                sizing_result = sizer.calculate(sizing_ctx)
                shares = self._normalize_shares(sizing_result.shares)

                if shares > 0:
                    execution_cost = self._execution_cost_profile(
                        price=price,
                        shares=shares,
                        bar_index=i,
                        market_context=market_context,
                    )
                    gross_cost = shares * price * (1 + float(execution_cost["total_slippage_rate"]))
                    commission_cost = self._commission_cost(gross_cost)
                    total_cost = gross_cost + commission_cost
                    if total_cost <= current_cash:
                        current_cash -= total_cost
                        current_position = shares
                        current_entry_date = data.index[i]
                        avg_cost_basis = total_cost / shares if shares else 0.0
                        trades.append(
                            {
                                "date": data.index[i],
                                "type": "BUY",
                                "price": price,
                                "shares": shares,
                                "cost": total_cost,
                                "pnl": 0.0,
                                "market_impact_rate": execution_cost["impact_rate"],
                                "execution_slippage_rate": execution_cost["total_slippage_rate"],
                                "estimated_market_impact_cost": execution_cost["estimated_market_impact_cost"],
                                "estimated_total_slippage_cost": execution_cost["estimated_total_slippage_cost"],
                                "impact_model": execution_cost["model"],
                                "participation_rate": execution_cost["participation_rate"],
                                "impact_liquidity_proxy": execution_cost["liquidity_proxy"],
                                "impact_volatility_estimate": execution_cost["volatility_estimate"],
                            }
                        )
            elif signal == -1 and current_position > 0:
                execution_cost = self._execution_cost_profile(
                    price=price,
                    shares=current_position,
                    bar_index=i,
                    market_context=market_context,
                )
                gross_revenue = current_position * price * (1 - float(execution_cost["total_slippage_rate"]))
                commission_cost = self._commission_cost(gross_revenue)
                total_revenue = gross_revenue - commission_cost
                total_cost_basis = current_position * avg_cost_basis
                pnl = total_revenue - total_cost_basis
                current_cash += total_revenue
                trade_pnls.append(pnl)
                trades.append(
                    {
                        "date": data.index[i],
                        "type": "SELL",
                        "price": price,
                        "shares": current_position,
                        "revenue": total_revenue,
                        "pnl": pnl,
                        "market_impact_rate": execution_cost["impact_rate"],
                        "execution_slippage_rate": execution_cost["total_slippage_rate"],
                        "estimated_market_impact_cost": execution_cost["estimated_market_impact_cost"],
                        "estimated_total_slippage_cost": execution_cost["estimated_total_slippage_cost"],
                        "impact_model": execution_cost["model"],
                        "participation_rate": execution_cost["participation_rate"],
                        "impact_liquidity_proxy": execution_cost["liquidity_proxy"],
                        "impact_volatility_estimate": execution_cost["volatility_estimate"],
                    }
                )
                current_position = 0.0
                avg_cost_basis = 0.0
                current_entry_date = None

            position_array[i] = float(current_position)
            cash_array[i] = float(current_cash)
            holdings_array[i] = float(current_position * price)
            total_array[i] = float(current_cash + current_position * price)
            prev_total = total_array[i]

        return {
            "portfolio": self._build_portfolio(
                data=data,
                signal_array=signal_array,
                price_array=price_array,
                position_array=position_array,
                cash_array=cash_array,
                holdings_array=holdings_array,
                total_array=total_array,
            ),
            "trades": trades,
        }

    def _execute_target_exposure(
        self,
        *,
        data: pd.DataFrame,
        signals: pd.Series,
        sizer: BasePositionSizer,
        risk_mgr: Optional[RiskManager],
        max_holding_days: Optional[int],
    ) -> Dict[str, Any]:
        price_array = data["close"].astype(float).to_numpy()
        signal_array = signals.astype(float).to_numpy()
        bar_count = len(price_array)
        position_array = np.zeros(bar_count, dtype=float)
        cash_array = np.zeros(bar_count, dtype=float)
        holdings_array = np.zeros(bar_count, dtype=float)
        total_array = np.zeros(bar_count, dtype=float)

        trades: List[Dict[str, Any]] = []
        trade_pnls: List[float] = []
        current_position = 0.0
        current_cash = self.initial_capital
        avg_cost_basis = 0.0
        current_entry_date = None
        peak_equity = self.initial_capital
        prev_total = self.initial_capital
        market_context = self._prepare_execution_context(data)

        for i, (price, raw_signal) in enumerate(zip(price_array, signal_array)):
            current_equity = current_cash + current_position * price
            daily_ret = (
                (current_equity - prev_total) / prev_total if prev_total > 0 else 0.0
            )
            peak_equity = max(peak_equity, current_equity)

            target_exposure = float(np.clip(raw_signal, 0.0, 1.0))
            current_exposure = (
                (current_position * price) / current_equity
                if current_equity > 0 and price > 0
                else 0.0
            )

            if risk_mgr is not None:
                risk_ctx = RiskContext(
                    bar_index=i,
                    current_price=price,
                    current_date=data.index[i],
                    position_size=float(current_position),
                    entry_price=avg_cost_basis,
                    entry_date=current_entry_date,
                    current_equity=current_equity,
                    peak_equity=peak_equity,
                    initial_capital=self.initial_capital,
                    daily_return=daily_ret,
                    recent_trade_pnls=trade_pnls.copy(),
                )
                decision = risk_mgr.evaluate(risk_ctx)
                if decision.action == RiskAction.FORCE_EXIT:
                    target_exposure = 0.0
                elif decision.action == RiskAction.BLOCK_ENTRY:
                    target_exposure = min(target_exposure, current_exposure)

            if (
                max_holding_days is not None
                and current_position > 0
                and current_entry_date is not None
                and (data.index[i] - current_entry_date).days >= max_holding_days
            ):
                target_exposure = 0.0

            sizing_ctx = SizingContext(
                current_equity=current_equity,
                current_price=price,
                signal_strength=target_exposure,
                commission=self.commission,
                slippage=self.slippage,
                risk_scale_factor=(risk_mgr.get_position_scale() if risk_mgr else 1.0),
                allow_fractional=self.config.allow_fractional_shares,
            )
            desired_position = self._normalize_shares(sizer.calculate(sizing_ctx).shares)
            position_delta = desired_position - current_position

            if position_delta > 0:
                shares_to_buy = position_delta
                execution_cost = self._execution_cost_profile(
                    price=price,
                    shares=shares_to_buy,
                    bar_index=i,
                    market_context=market_context,
                )
                gross_cost = shares_to_buy * price * (1 + float(execution_cost["total_slippage_rate"]))
                commission_cost = self._commission_cost(gross_cost)
                total_cost = gross_cost + commission_cost
                if total_cost <= current_cash and shares_to_buy > 0:
                    previous_position = current_position
                    current_cash -= total_cost
                    current_position += shares_to_buy
                    if previous_position <= 0:
                        current_entry_date = data.index[i]
                    previous_cost_basis = previous_position * avg_cost_basis
                    avg_cost_basis = (
                        (previous_cost_basis + total_cost) / current_position
                        if current_position > 0
                        else 0.0
                    )
                    trades.append(
                        {
                            "date": data.index[i],
                            "type": "BUY",
                            "price": price,
                            "shares": shares_to_buy,
                            "cost": total_cost,
                            "pnl": 0.0,
                            "market_impact_rate": execution_cost["impact_rate"],
                            "execution_slippage_rate": execution_cost["total_slippage_rate"],
                            "estimated_market_impact_cost": execution_cost["estimated_market_impact_cost"],
                            "estimated_total_slippage_cost": execution_cost["estimated_total_slippage_cost"],
                            "impact_model": execution_cost["model"],
                            "participation_rate": execution_cost["participation_rate"],
                            "impact_liquidity_proxy": execution_cost["liquidity_proxy"],
                            "impact_volatility_estimate": execution_cost["volatility_estimate"],
                        }
                    )
            elif position_delta < 0 and current_position > 0:
                shares_to_sell = min(abs(position_delta), current_position)
                execution_cost = self._execution_cost_profile(
                    price=price,
                    shares=shares_to_sell,
                    bar_index=i,
                    market_context=market_context,
                )
                gross_revenue = shares_to_sell * price * (1 - float(execution_cost["total_slippage_rate"]))
                commission_cost = self._commission_cost(gross_revenue)
                total_revenue = gross_revenue - commission_cost
                pnl = total_revenue - (shares_to_sell * avg_cost_basis)
                current_cash += total_revenue
                current_position -= shares_to_sell
                trade_pnls.append(pnl)
                trades.append(
                    {
                        "date": data.index[i],
                        "type": "SELL",
                            "price": price,
                            "shares": shares_to_sell,
                            "revenue": total_revenue,
                            "pnl": pnl,
                            "market_impact_rate": execution_cost["impact_rate"],
                            "execution_slippage_rate": execution_cost["total_slippage_rate"],
                            "estimated_market_impact_cost": execution_cost["estimated_market_impact_cost"],
                            "estimated_total_slippage_cost": execution_cost["estimated_total_slippage_cost"],
                            "impact_model": execution_cost["model"],
                            "participation_rate": execution_cost["participation_rate"],
                            "impact_liquidity_proxy": execution_cost["liquidity_proxy"],
                            "impact_volatility_estimate": execution_cost["volatility_estimate"],
                        }
                    )
                if current_position <= 0:
                    current_position = 0.0
                    avg_cost_basis = 0.0
                    current_entry_date = None

            position_array[i] = float(current_position)
            cash_array[i] = float(current_cash)
            holdings_array[i] = float(current_position * price)
            total_array[i] = float(current_cash + current_position * price)
            prev_total = total_array[i]

        return {
            "portfolio": self._build_portfolio(
                data=data,
                signal_array=signal_array,
                price_array=price_array,
                position_array=position_array,
                cash_array=cash_array,
                holdings_array=holdings_array,
                total_array=total_array,
            ),
            "trades": trades,
        }


class Backtester(BaseBacktester):
    """Single-asset event-driven backtesting engine.

    Supports optional *RiskManager* and *PositionSizer* components.  When
    not provided, the engine falls back to the legacy behaviour (fixed
    fraction sizing, simple stop-loss/take-profit).
    """

    def __init__(
        self,
        initial_capital: float = 100000,
        commission: float = 0.001,
        slippage: float = 0.001,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        risk_manager: Optional[RiskManager] = None,
        position_sizer: Optional[BasePositionSizer] = None,
        allow_fractional_shares: bool = False,
        signal_mode: str = "auto",
        fixed_commission: float = 0.0,
        min_commission: float = 0.0,
        market_impact_bps: float = 0.0,
        market_impact_model: str = "constant",
        impact_reference_notional: float = 100000.0,
        impact_coefficient: float = 1.0,
        permanent_impact_bps: float = 0.0,
        max_holding_days: Optional[int] = None,
    ):
        """
        Initialize backtester

        Args:
            initial_capital: Starting capital
            commission: Commission rate (e.g., 0.001 = 0.1%)
            slippage: Slippage rate
            stop_loss_pct: Stop-loss percentage (legacy shortcut; ignored
                           when a *risk_manager* is supplied).
            take_profit_pct: Take-profit percentage (legacy shortcut).
            risk_manager: Optional :class:`RiskManager` for advanced risk
                          control.  When provided, ``stop_loss_pct`` and
                          ``take_profit_pct`` are ignored.
            position_sizer: Optional :class:`BasePositionSizer`.  When
                            ``None``, a :class:`FixedFractionSizer` using
                            the ``position_size`` argument of :meth:`run`
                            is created on each call.
        """
        super().__init__(
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
        )
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.risk_manager = risk_manager
        self.position_sizer = position_sizer
        self.max_holding_days = max_holding_days
        self.execution_config = ExecutionConfig(
            allow_fractional_shares=allow_fractional_shares,
            signal_mode=signal_mode,
            fixed_commission=fixed_commission,
            min_commission=min_commission,
            market_impact_bps=market_impact_bps,
            market_impact_model=normalize_market_impact_model(market_impact_model),
            impact_reference_notional=impact_reference_notional,
            impact_coefficient=impact_coefficient,
            permanent_impact_bps=permanent_impact_bps,
        )

    def run(
        self, strategy: Any, data: pd.DataFrame, position_size: float = 1.0
    ) -> Dict[str, Any]:
        """
        Run backtest

        Args:
            strategy: Strategy object with generate_signals method
            data: DataFrame with OHLCV data
            position_size: Position size as fraction of capital (1.0 = 100%)

        Returns:
            Dictionary with backtest results
        """
        if data.empty:
            logger.error("No data provided for backtest")
            return {}

        data = self._prepare_market_data(data)
        if data.empty:
            logger.error("No valid price data remaining after cleaning")
            return {}

        # Generate and normalize signals
        signals = SignalAdapter.normalize_single_asset(
            strategy.generate_signals(data),
            index=data.index,
            signal_mode=self.execution_config.signal_mode,
        )

        # Prepare sizer (use run-time position_size when no explicit sizer)
        sizer = self.position_sizer or FixedFractionSizer(fraction=position_size)

        # Prepare risk manager
        risk_mgr = self.risk_manager
        if risk_mgr is not None:
            risk_mgr.reset()

        execution = self._execute_signals(
            data=data,
            signals=signals.values,
            sizer=sizer,
            risk_mgr=risk_mgr,
        )

        portfolio = execution["portfolio"]
        trades = execution["trades"]

        # Calculate metrics
        results = self._calculate_metrics(portfolio, trades)
        results["portfolio"] = portfolio
        results["trades"] = trades
        results["execution_costs"] = summarize_execution_costs(trades)
        results["execution_diagnostics"] = {
            "configured_signal_mode": self.execution_config.signal_mode,
            "resolved_signal_mode": execution.get("resolved_signal_mode", self.execution_config.signal_mode),
            "allow_fractional_shares": self.execution_config.allow_fractional_shares,
            "risk_manager": type(risk_mgr).__name__ if risk_mgr is not None else None,
            "position_sizer": type(sizer).__name__ if sizer is not None else None,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_holding_days": self.max_holding_days,
            "fixed_commission": self.execution_config.fixed_commission,
            "min_commission": self.execution_config.min_commission,
            "market_impact_bps": self.execution_config.market_impact_bps,
            "market_impact_model": self.execution_config.market_impact_model,
            "impact_reference_notional": self.execution_config.impact_reference_notional,
            "impact_coefficient": self.execution_config.impact_coefficient,
            "permanent_impact_bps": self.execution_config.permanent_impact_bps,
        }

        self.results = results
        return results

    def _execute_signals(
        self,
        *,
        data: pd.DataFrame,
        signals: pd.Series,
        sizer: BasePositionSizer,
        risk_mgr: Optional[RiskManager],
    ) -> Dict[str, Any]:
        """Run the execution loop against a precomputed signal series."""
        engine = SingleAssetExecutionEngine(
            initial_capital=self.initial_capital,
            commission=self.commission,
            slippage=self.slippage,
            config=self.execution_config,
        )
        return engine.execute(
            data=data,
            signals=signals,
            sizer=sizer,
            risk_mgr=risk_mgr,
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pct=self.take_profit_pct,
            max_holding_days=self.max_holding_days,
        )

    def _prepare_market_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Drop incomplete bars so NaN market data cannot zero out the portfolio."""
        cleaned = data.copy()

        if "close" not in cleaned.columns:
            logger.error("Backtest data is missing required 'close' column")
            return pd.DataFrame()

        numeric_cols = [col for col in ["open", "high", "low", "close", "volume"] if col in cleaned.columns]
        for col in numeric_cols:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")

        before = len(cleaned)
        cleaned = cleaned[np.isfinite(cleaned["close"])]
        cleaned = cleaned[cleaned["close"] > 0]
        dropped = before - len(cleaned)

        if dropped > 0:
            logger.info("Dropped %s incomplete market bars before backtest execution", dropped)

        return cleaned

    def _calculate_metrics(
        self, portfolio: pd.DataFrame, trades: list
    ) -> Dict[str, Any]:
        """Calculate performance metrics"""
        total_return = (
            portfolio["total"].iloc[-1] - self.initial_capital
        ) / self.initial_capital

        # Calculate annualized return
        days = len(portfolio)
        annualized_return = calculate_annualized_return(total_return, days)

        # Get daily returns series
        returns = portfolio["returns"].dropna()

        # Calculate Sharpe ratio
        sharpe_ratio = calculate_sharpe_ratio(returns)

        # Calculate max drawdown
        portfolio_values = portfolio["total"].values
        max_drawdown = calculate_max_drawdown(portfolio_values)

        # Trade statistics
        num_trades = len(trades)
        buy_trades = [t for t in trades if t["type"] == "BUY"]
        sell_trades = [t for t in trades if t["type"] == "SELL"]

        completed_trade_pnls, completed_trade_returns, has_open_position = (
            self._extract_completed_trade_statistics(trades, portfolio)
        )

        winning_trades = [pnl for pnl in completed_trade_pnls if pnl > 0]
        losing_trades = [pnl for pnl in completed_trade_pnls if pnl < 0]

        # Calculate win rate based on completed trades only
        total_completed_trades = len(completed_trade_pnls)
        win_rate = (
            len(winning_trades) / total_completed_trades if total_completed_trades > 0 else 0
        )

        # Calculate profit factor (gross profit / gross loss)
        gross_profit = sum(winning_trades) if winning_trades else 0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 0
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0)
        )

        # Calculate best and worst trades
        best_trade = (
            max(completed_trade_pnls) if completed_trade_pnls else 0
        )
        worst_trade = (
            min(completed_trade_pnls) if completed_trade_pnls else 0
        )

        # Calculate net profit
        net_profit = portfolio["total"].iloc[-1] - self.initial_capital

        # Calculate consecutive wins/losses
        consecutive_wins = 0
        consecutive_losses = 0
        max_consecutive_wins = 0
        max_consecutive_losses = 0

        for trade_pnl in completed_trade_pnls:
            if trade_pnl > 0:
                consecutive_wins += 1
                consecutive_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
            elif trade_pnl < 0:
                consecutive_losses += 1
                consecutive_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            else:
                consecutive_wins = 0
                consecutive_losses = 0

        # Calculate average trade
        avg_trade = (
            sum(completed_trade_pnls) / len(completed_trade_pnls)
            if completed_trade_pnls
            else 0
        )
        expectancy = calculate_expectancy(completed_trade_pnls)

        # Calculate Sortino ratio (downside deviation)
        sortino_ratio = calculate_sortino_ratio(returns)

        # Calculate Calmar ratio (annual return / max drawdown)
        calmar_ratio = calculate_calmar_ratio(annualized_return, max_drawdown)

        # Calculate annualized volatility
        volatility = calculate_volatility(returns)
        
        # Calculate Value at Risk (95% confidence)
        var_95 = calculate_var(returns)

        # Calculate CVaR / Expected Shortfall (95% confidence)
        cvar_95 = calculate_cvar(returns)

        # Calculate Omega Ratio
        omega_ratio = calculate_omega_ratio(returns)

        # Calculate max drawdown duration
        max_dd_duration, max_underwater = calculate_max_drawdown_duration(
            portfolio_values
        )
        recovery_factor = calculate_recovery_factor(net_profit, max_drawdown)
        execution_costs = summarize_execution_costs(trades)

        metrics = {
            "initial_capital": self.initial_capital,
            "final_value": portfolio["total"].iloc[-1],
            "total_return": total_return,
            "annualized_return": annualized_return,
            "volatility": volatility,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "max_drawdown": max_drawdown,
            "max_drawdown_duration": max_dd_duration,
            "max_underwater_period": max_underwater,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "omega_ratio": omega_ratio,
            "num_trades": num_trades,
            "num_buy_trades": len(buy_trades),
            "num_sell_trades": len(sell_trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "net_profit": net_profit,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "avg_trade": avg_trade,
            "expectancy": expectancy,
            "recovery_factor": recovery_factor,
            "max_consecutive_wins": max_consecutive_wins,
            "max_consecutive_losses": max_consecutive_losses,
            "total_completed_trades": total_completed_trades,
            "has_open_position": has_open_position,  # 标记是否有未平仓头寸
            "execution_costs": execution_costs,
        }

        return metrics

    def _extract_completed_trade_statistics(
        self, trades: List[Dict[str, Any]], portfolio: pd.DataFrame
    ) -> tuple[List[float], List[float], bool]:
        """Match BUY and SELL lots so partial rebalances produce correct trade stats."""
        open_lots: List[Dict[str, float]] = []
        completed_trade_pnls: List[float] = []
        completed_trade_returns: List[float] = []

        for trade in trades:
            trade_type = str(trade.get("type", "")).upper()
            shares = float(trade.get("shares", 0) or 0)
            if shares <= 0:
                continue

            if trade_type == "BUY":
                entry_value = float(
                    trade.get("cost")
                    or (float(trade.get("price", 0) or 0) * shares)
                )
                open_lots.append(
                    {
                        "shares": shares,
                        "cost_per_share": entry_value / shares if shares else 0.0,
                    }
                )
                continue

            if trade_type != "SELL":
                logger.warning("发现未知交易类型: %s", trade)
                continue

            revenue_value = float(
                trade.get("revenue")
                or (float(trade.get("price", 0) or 0) * shares)
            )
            exit_price_per_share = revenue_value / shares if shares else 0.0
            remaining = shares

            while remaining > 1e-12 and open_lots:
                lot = open_lots[0]
                matched = min(remaining, lot["shares"])
                entry_value = matched * lot["cost_per_share"]
                exit_value = matched * exit_price_per_share
                pnl = exit_value - entry_value
                completed_trade_pnls.append(float(pnl))
                completed_trade_returns.append(
                    float(pnl / entry_value) if entry_value else 0.0
                )

                lot["shares"] -= matched
                remaining -= matched
                if lot["shares"] <= 1e-12:
                    open_lots.pop(0)

        has_open_position = any(lot["shares"] > 1e-12 for lot in open_lots)
        if has_open_position and not portfolio.empty:
            current_price = float(portfolio["price"].iloc[-1])
            unrealized_pnl = sum(
                lot["shares"] * (current_price - lot["cost_per_share"])
                for lot in open_lots
            )
            logger.info(
                "检测到未平仓头寸: 当前价格=%.2f, 未实现盈亏=%.2f",
                current_price,
                unrealized_pnl,
            )
        return completed_trade_pnls, completed_trade_returns, has_open_position

    def plot_results(self, show: bool = True):
        """Plot backtest results"""
        if not self.results or "portfolio" not in self.results:
            logger.error("No results to plot")
            return

        import matplotlib.pyplot as plt

        portfolio = self.results["portfolio"]

        fig, axes = plt.subplots(3, 1, figsize=(12, 10))

        # Plot portfolio value
        axes[0].plot(portfolio.index, portfolio["total"], label="Portfolio Value")
        axes[0].axhline(
            y=self.initial_capital, color="r", linestyle="--", label="Initial Capital"
        )
        axes[0].set_ylabel("Portfolio Value ($)")
        axes[0].set_title("Portfolio Performance")
        axes[0].legend()
        axes[0].grid(True)

        # Plot price and signals
        axes[1].plot(portfolio.index, portfolio["price"], label="Price", alpha=0.7)

        # Mark buy signals
        buy_signals = portfolio[portfolio["signal"] == 1]
        if not buy_signals.empty:
            axes[1].scatter(
                buy_signals.index,
                buy_signals["price"],
                color="green",
                marker="^",
                s=100,
                label="Buy",
            )

        # Mark sell signals
        sell_signals = portfolio[portfolio["signal"] == -1]
        if not sell_signals.empty:
            axes[1].scatter(
                sell_signals.index,
                sell_signals["price"],
                color="red",
                marker="v",
                s=100,
                label="Sell",
            )

        axes[1].set_ylabel("Price ($)")
        axes[1].set_title("Price and Trading Signals")
        axes[1].legend()
        axes[1].grid(True)

        # Plot returns
        axes[2].plot(
            portfolio.index, portfolio["returns"].cumsum(), label="Cumulative Returns"
        )
        axes[2].set_ylabel("Cumulative Returns")
        axes[2].set_xlabel("Date")
        axes[2].set_title("Cumulative Returns")
        axes[2].legend()
        axes[2].grid(True)

        plt.tight_layout()

        if show:
            plt.show()

        return fig

    def print_summary(self):
        """Print summary of backtest results"""
        if not self.results:
            logger.error("No results to display")
            return

        metrics = self.results

        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print(f"Initial Capital:       ${metrics['initial_capital']:,.2f}")
        print(f"Final Value:           ${metrics['final_value']:,.2f}")
        print(f"Net Profit:            ${metrics['net_profit']:,.2f}")
        print(f"Total Return:          {metrics['total_return']:.2%}")
        print(f"Annualized Return:     {metrics['annualized_return']:.2%}")
        print("-" * 60)
        print("RISK METRICS")
        print("-" * 60)
        print(f"Sharpe Ratio:          {metrics['sharpe_ratio']:.2f}")
        print(f"Sortino Ratio:         {metrics['sortino_ratio']:.2f}")
        print(f"Calmar Ratio:          {metrics['calmar_ratio']:.2f}")
        print(f"Max Drawdown:          {metrics['max_drawdown']:.2%}")
        print(f"Max DD Duration:       {metrics.get('max_drawdown_duration', 0)} bars")
        print(f"Max Underwater:        {metrics.get('max_underwater_period', 0)} bars")
        print(f"Value at Risk (95%):   {metrics['var_95']:.2%}")
        print(f"CVaR / ES (95%):       {metrics.get('cvar_95', 0):.2%}")
        print(f"Omega Ratio:           {metrics.get('omega_ratio', 0):.2f}")
        print("-" * 60)
        print("TRADE STATISTICS")
        print("-" * 60)
        print(f"Total Trades:          {metrics['num_trades']}")
        print(f"Completed Trades:      {metrics['total_completed_trades']}")
        print(f"Win Rate:              {metrics['win_rate']:.2%}")
        print(f"Profit Factor:         {metrics['profit_factor']:.2f}")
        print(f"Average Trade:         ${metrics['avg_trade']:,.2f}")
        print(f"Best Trade:            ${metrics['best_trade']:,.2f}")
        print(f"Worst Trade:           ${metrics['worst_trade']:,.2f}")
        print(f"Max Consecutive Wins:  {metrics['max_consecutive_wins']}")
        print(f"Max Consecutive Losses: {metrics['max_consecutive_losses']}")
        print(f"Gross Profit:          ${metrics['gross_profit']:,.2f}")
        print(f"Gross Loss:            ${metrics['gross_loss']:,.2f}")
        print("=" * 60)
