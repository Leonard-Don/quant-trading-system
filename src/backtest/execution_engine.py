"""Reusable execution engines for single and multi-asset backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from .impact_model import (
    estimate_market_impact_rate,
    normalize_market_impact_model,
)


@dataclass
class PortfolioExecutionConfig:
    allow_fractional_shares: bool = False
    max_gross_exposure: float = 1.0
    min_trade_value: float = 0.0
    min_rebalance_weight_delta: float = 0.0
    max_turnover_per_rebalance: Optional[float] = None
    fixed_commission: float = 0.0
    min_commission: float = 0.0
    market_impact_bps: float = 0.0
    market_impact_model: str = "constant"
    impact_reference_notional: float = 100000.0
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0
    execution_lag: int = 1
    # Per-symbol A-share friction profiles: {symbol: {stamp_duty_rate,
    # transfer_fee_rate, enforce_t_plus_1, price_limit_pct}} — the same shape
    # ashare_cost_profile()/resolve_ashare_frictions() produce. Empty (default)
    # keeps every path byte-identical. Mixed portfolios charge only flagged
    # legs. Note: T+1 needs no engine logic here — the engine sells before it
    # buys within a bar and an asset is on exactly one side per bar (delta sign),
    # so a same-bar buy-then-sell of one asset is structurally impossible.
    ashare_frictions: dict[str, dict[str, Any]] = field(default_factory=dict)


class PortfolioExecutionEngine:
    """Execute target portfolio weights across multiple assets.

    Supports long and short targets by interpreting negative weights as short
    exposure. The execution model is intentionally simple and daily-bar based:
    positions are rebalanced to the target weights for each timestamp.
    """

    def __init__(
        self,
        *,
        initial_capital: float,
        commission: float,
        slippage: float,
        config: Optional[PortfolioExecutionConfig] = None,
    ):
        self.initial_capital = float(initial_capital)
        self.commission = float(commission)
        self.slippage = float(slippage)
        self.config = config or PortfolioExecutionConfig()
        self.config.market_impact_model = normalize_market_impact_model(self.config.market_impact_model)

    def execute(self, *, price_data: pd.DataFrame, target_weights: pd.DataFrame) -> dict[str, Any]:
        prices = price_data.astype(float).copy()
        weights = target_weights.reindex(index=prices.index, columns=prices.columns).fillna(0.0)
        weights = self._apply_execution_lag(weights)
        market_context = self._build_market_context(prices)
        prev_closes = prices.shift(1)  # per-symbol price-limit bands need t-1 closes

        positions = pd.Series(0.0, index=prices.columns, dtype=float)
        cash = float(self.initial_capital)
        trades: list[dict[str, Any]] = []
        history: list[dict[str, Any]] = []
        position_history: list[dict[str, Any]] = []

        for timestamp, price_row in prices.iterrows():
            valid_prices = price_row.replace([np.inf, -np.inf], np.nan).dropna()
            if valid_prices.empty:
                continue

            current_prices = valid_prices.reindex(prices.columns)
            current_equity = self._portfolio_value(cash, positions, current_prices)
            desired_weights = weights.loc[timestamp].reindex(prices.columns).fillna(0.0)
            current_weights = self._current_weights(current_equity, positions, current_prices)

            gross = float(desired_weights.abs().sum())
            if gross > self.config.max_gross_exposure > 0:
                desired_weights = desired_weights * (self.config.max_gross_exposure / gross)

            if self.config.min_rebalance_weight_delta > 0:
                weight_gap = (desired_weights - current_weights).abs()
                desired_weights = desired_weights.where(
                    weight_gap >= self.config.min_rebalance_weight_delta,
                    current_weights,
                )

            desired_shares = self._desired_shares(current_equity, desired_weights, current_prices)
            delta_shares = desired_shares - positions
            if self.config.max_turnover_per_rebalance is not None and current_equity > 0:
                turnover_value = float(np.nansum((delta_shares.abs() * current_prices).fillna(0.0)))
                max_turnover_value = float(max(self.config.max_turnover_per_rebalance, 0.0) * current_equity)
                if turnover_value > max_turnover_value > 0:
                    delta_shares = delta_shares * (max_turnover_value / turnover_value)

            # Sell / increase shorts first to release cash.
            for asset, delta in delta_shares.items():
                price = current_prices.get(asset)
                if pd.isna(price) or delta >= 0:
                    continue
                band = self._price_limit_band(asset, prev_closes.loc[timestamp].get(asset))
                if band is not None and float(price) <= band[0]:
                    continue  # limit-down: sells don't fill (跌停无法卖出)
                shares_to_sell = min(abs(delta), abs(positions[asset]) if positions[asset] > 0 else abs(delta))
                shares_to_sell = self._normalize_shares(shares_to_sell)
                if shares_to_sell <= 0 or (shares_to_sell * price) < self.config.min_trade_value:
                    continue

                execution_cost = self._execution_cost_profile(
                    price=price,
                    shares=shares_to_sell,
                    timestamp=timestamp,
                    asset=asset,
                    market_context=market_context,
                )
                proceeds = shares_to_sell * price * (1 - float(execution_cost["total_slippage_rate"]))
                commission_cost = self._commission_cost(proceeds)
                stamp_duty_cost, transfer_fee_cost = self._ashare_costs(
                    asset, shares_to_sell * price, "SELL"
                )
                cash += proceeds - commission_cost - stamp_duty_cost - transfer_fee_cost
                positions[asset] -= shares_to_sell
                trades.append(
                    {
                        "date": timestamp,
                        "asset": asset,
                        "type": "SELL",
                        "shares": float(shares_to_sell),
                        "price": float(price),
                        "value": float(
                            proceeds - commission_cost - stamp_duty_cost - transfer_fee_cost
                        ),
                        "stamp_duty_cost": float(stamp_duty_cost),
                        "transfer_fee_cost": float(transfer_fee_cost),
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

            # Buy / cover second.
            for asset, delta in delta_shares.items():
                price = current_prices.get(asset)
                if pd.isna(price) or delta <= 0:
                    continue
                band = self._price_limit_band(asset, prev_closes.loc[timestamp].get(asset))
                if band is not None and float(price) >= band[1]:
                    continue  # limit-up: buys don't fill (涨停无法买入)
                shares_to_buy = self._normalize_shares(delta)
                if shares_to_buy <= 0 or (shares_to_buy * price) < self.config.min_trade_value:
                    continue

                transfer_fee_rate = float(
                    self._friction_profile(asset).get("transfer_fee_rate") or 0.0
                )
                execution_cost = self._execution_cost_profile(
                    price=price,
                    shares=shares_to_buy,
                    timestamp=timestamp,
                    asset=asset,
                    market_context=market_context,
                )
                gross_cost = shares_to_buy * price * (1 + float(execution_cost["total_slippage_rate"]))
                commission_cost = self._commission_cost(gross_cost)
                _, transfer_fee_cost = self._ashare_costs(asset, shares_to_buy * price, "BUY")
                total_cost = gross_cost + commission_cost + transfer_fee_cost

                if total_cost > cash and price > 0:
                    affordable = cash / (
                        price
                        * (1 + float(execution_cost["total_slippage_rate"]))
                        * (1 + self.commission + transfer_fee_rate)
                    )
                    shares_to_buy = self._normalize_shares(affordable)
                    execution_cost = self._execution_cost_profile(
                        price=price,
                        shares=shares_to_buy,
                        timestamp=timestamp,
                        asset=asset,
                        market_context=market_context,
                    )
                    gross_cost = shares_to_buy * price * (1 + float(execution_cost["total_slippage_rate"]))
                    commission_cost = self._commission_cost(gross_cost)
                    _, transfer_fee_cost = self._ashare_costs(asset, shares_to_buy * price, "BUY")
                    total_cost = gross_cost + commission_cost + transfer_fee_cost

                if shares_to_buy <= 0 or total_cost > cash:
                    continue

                cash -= total_cost
                positions[asset] += shares_to_buy
                trades.append(
                    {
                        "date": timestamp,
                        "asset": asset,
                        "type": "BUY",
                        "shares": float(shares_to_buy),
                        "price": float(price),
                        "value": float(total_cost),
                        "stamp_duty_cost": 0.0,
                        "transfer_fee_cost": float(transfer_fee_cost),
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

            portfolio_value = self._portfolio_value(cash, positions, current_prices)
            gross_exposure = float(
                np.nansum(np.abs((positions * current_prices).fillna(0.0)))
            )
            net_exposure = float(
                np.nansum((positions * current_prices).fillna(0.0))
            )

            history.append(
                {
                    "date": timestamp,
                    "cash": float(cash),
                    "total": float(portfolio_value),
                    "gross_exposure": gross_exposure,
                    "net_exposure": net_exposure,
                }
            )
            position_history.append(
                {
                    "date": timestamp,
                    **{asset: float(value) for asset, value in positions.items()},
                }
            )

        history_df = pd.DataFrame(history).set_index("date") if history else pd.DataFrame()
        if not history_df.empty:
            history_df["returns"] = history_df["total"].pct_change().fillna(0.0)

        positions_df = pd.DataFrame(position_history).set_index("date") if position_history else pd.DataFrame()
        return {
            "portfolio_history": history_df,
            "positions": positions_df,
            "trades": trades,
        }

    def _configured_execution_lag(self) -> int:
        return max(int(self.config.execution_lag or 0), 0)

    def _apply_execution_lag(self, weights: pd.DataFrame) -> pd.DataFrame:
        """Defer target weights by ``execution_lag`` bars.

        A target derived from bar ``t`` is filled at bar ``t + lag``'s price,
        matching the single-asset ``SingleAssetExecutionEngine`` default and
        preventing same-bar look-ahead on the portfolio path.
        """
        lag = self._configured_execution_lag()
        if lag <= 0:
            return weights
        return weights.shift(lag).fillna(0.0)

    def _desired_shares(
        self,
        equity: float,
        target_weights: pd.Series,
        prices: pd.Series,
    ) -> pd.Series:
        desired_values = target_weights * equity
        desired_shares = desired_values.divide(prices.replace(0, np.nan)).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        return desired_shares.apply(self._normalize_shares)

    def _normalize_shares(self, shares: float) -> float:
        if not np.isfinite(shares):
            return 0.0
        if self.config.allow_fractional_shares:
            return float(shares)
        return float(np.trunc(shares))

    def _build_market_context(self, prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
        returns = prices.pct_change().replace([np.inf, -np.inf], np.nan)
        fallback_volatility = returns.std().replace([np.inf, -np.inf], np.nan).fillna(0.02).clip(lower=0.005)
        rolling_volatility = returns.rolling(20, min_periods=2).std()
        rolling_volatility = rolling_volatility.ffill().fillna(fallback_volatility)
        reference_notional = max(float(self.config.impact_reference_notional or 100000.0), 1.0)
        avg_daily_notional = pd.DataFrame(
            reference_notional,
            index=prices.index,
            columns=prices.columns,
            dtype=float,
        )
        return {
            "volatility": rolling_volatility,
            "avg_daily_notional": avg_daily_notional,
        }

    def _execution_cost_profile(
        self,
        *,
        price: float,
        shares: float,
        timestamp: Any,
        asset: str,
        market_context: dict[str, pd.DataFrame],
    ) -> dict[str, float | str]:
        impact = estimate_market_impact_rate(
            abs(float(price or 0.0) * float(shares or 0.0)),
            market_impact_bps=self.config.market_impact_bps,
            model=self.config.market_impact_model,
            avg_daily_notional=float(market_context["avg_daily_notional"].loc[timestamp, asset]),
            volatility=float(market_context["volatility"].loc[timestamp, asset]),
            impact_coefficient=self.config.impact_coefficient,
            permanent_impact_bps=self.config.permanent_impact_bps,
            reference_notional=self.config.impact_reference_notional,
        )
        trade_notional = abs(float(price or 0.0) * float(shares or 0.0))
        total_slippage_rate = float(self.slippage) + float(impact["impact_rate"])
        return {
            **impact,
            "trade_notional": trade_notional,
            "total_slippage_rate": total_slippage_rate,
            "estimated_market_impact_cost": trade_notional * float(impact["impact_rate"]),
            "estimated_total_slippage_cost": trade_notional * total_slippage_rate,
        }

    def _friction_profile(self, asset: str) -> dict[str, Any]:
        return self.config.ashare_frictions.get(asset) or {}

    def _ashare_costs(self, asset: str, notional: float, side: str) -> tuple[float, float]:
        """(stamp_duty_cost, transfer_fee_cost) for a flagged symbol.

        Parity with the single-asset engine (backtester.py::_ashare_costs):
        stamp duty on the SELL side only, transfer fee on both sides, both on
        the RAW shares×price notional. Unflagged symbols cost (0.0, 0.0).
        """
        profile = self._friction_profile(asset)
        if not profile:
            return 0.0, 0.0
        raw = abs(float(notional or 0.0))
        if not np.isfinite(raw) or raw <= 0:
            return 0.0, 0.0
        stamp = raw * float(profile.get("stamp_duty_rate") or 0.0) if side == "SELL" else 0.0
        transfer = raw * float(profile.get("transfer_fee_rate") or 0.0)
        return float(stamp), float(transfer)

    def _price_limit_band(self, asset: str, prev_close: Any) -> Optional[tuple[float, float]]:
        """(lower, upper) daily price band from the prior close, or ``None``.

        Mirrors the single-asset ``_price_limit_band``: no band on the first
        bar (NaN prev close) or for symbols without a ``price_limit_pct``.
        """
        profile = self._friction_profile(asset)
        pct = profile.get("price_limit_pct")
        if pct is None or float(pct) <= 0:
            return None
        try:
            prev = float(prev_close)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(prev) or prev <= 0:
            return None
        pct = float(pct)
        return (round(prev * (1 - pct), 2), round(prev * (1 + pct), 2))

    def _commission_cost(self, notional: float) -> float:
        if not np.isfinite(notional) or notional <= 0:
            return 0.0
        commission_cost = (float(notional) * self.commission) + float(self.config.fixed_commission or 0.0)
        return float(max(commission_cost, float(self.config.min_commission or 0.0)))

    @staticmethod
    def _current_weights(equity: float, positions: pd.Series, prices: pd.Series) -> pd.Series:
        if equity <= 0:
            return pd.Series(0.0, index=prices.index, dtype=float)
        current_values = (positions * prices).fillna(0.0)
        return current_values / equity

    @staticmethod
    def _portfolio_value(cash: float, positions: pd.Series, prices: pd.Series) -> float:
        exposure = float(np.nansum((positions * prices).fillna(0.0)))
        return float(cash + exposure)
