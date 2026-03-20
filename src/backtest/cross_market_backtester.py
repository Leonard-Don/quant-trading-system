"""Cross-market backtesting engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.backtest.metrics import (
    calculate_annualized_return,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_var,
    calculate_volatility,
)
from src.data.data_manager import DataManager
from src.trading.cross_market import (
    AssetSide,
    AssetUniverse,
    CrossMarketStrategy,
    HedgePortfolioBuilder,
    SpreadZScoreStrategy,
)


class CrossMarketBacktester:
    """Backtest long-short cross-market baskets on daily data."""

    STRATEGIES = {
        "spread_zscore": SpreadZScoreStrategy,
    }

    def __init__(
        self,
        data_manager: Optional[DataManager] = None,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.001,
    ):
        self.data_manager = data_manager or DataManager()
        self.initial_capital = float(initial_capital)
        self.commission = float(commission)
        self.slippage = float(slippage)

    def run(
        self,
        assets: List[Dict[str, object]],
        strategy_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        construction_mode: str = "equal_weight",
        min_history_days: int = 60,
        min_overlap_ratio: float = 0.7,
    ) -> Dict[str, Any]:
        if strategy_name not in self.STRATEGIES:
            raise ValueError(f"Unsupported cross-market strategy: {strategy_name}")
        if construction_mode not in {"equal_weight", "ols_hedge"}:
            raise ValueError(f"Unsupported construction_mode: {construction_mode}")
        if min_history_days < 10:
            raise ValueError("min_history_days must be at least 10")
        if not 0 < float(min_overlap_ratio) <= 1:
            raise ValueError("min_overlap_ratio must be between 0 and 1")

        universe = AssetUniverse(assets)
        alignment = self._build_price_matrix(
            universe=universe,
            start_date=start_date,
            end_date=end_date,
            min_history_days=min_history_days,
            min_overlap_ratio=min_overlap_ratio,
        )
        price_matrix = alignment["aligned_price_matrix"]

        strategy: CrossMarketStrategy = self.STRATEGIES[strategy_name]()
        signal_frame = strategy.generate_cross_signals(
            price_matrix=price_matrix,
            asset_specs=universe.get_assets(),
            parameters={
                **(parameters or {}),
                "construction_mode": construction_mode,
            },
        )
        results = self._build_results(
            universe=universe,
            price_matrix=price_matrix,
            signal_frame=signal_frame,
            data_alignment=alignment,
            construction_mode=construction_mode,
        )
        results["strategy"] = strategy_name
        results["parameters"] = parameters or {}
        results["asset_specs"] = universe.as_dicts()
        results["asset_universe"] = universe.summary()
        results["price_matrix_summary"] = {
            "asset_count": len(price_matrix.columns),
            "row_count": len(price_matrix),
            "symbols": list(price_matrix.columns),
            "start_date": price_matrix.index[0].strftime("%Y-%m-%d"),
            "end_date": price_matrix.index[-1].strftime("%Y-%m-%d"),
        }
        return results

    def _build_price_matrix(
        self,
        universe: AssetUniverse,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        min_history_days: int,
        min_overlap_ratio: float,
    ) -> Dict[str, Any]:
        series_map: Dict[str, pd.Series] = {}
        symbol_alignment: List[Dict[str, Any]] = []
        for asset in universe.get_assets():
            data = self.data_manager.get_historical_data(
                symbol=asset.symbol,
                start_date=start_date,
                end_date=end_date,
                interval="1d",
            )
            if data.empty or "close" not in data.columns:
                raise ValueError(f"No daily close data found for {asset.symbol}")
            series = self._normalize_daily_close(data["close"], asset.symbol)
            if series.empty:
                raise ValueError(f"No normalized daily close data found for {asset.symbol}")
            series_map[asset.symbol] = series
            symbol_alignment.append(
                {
                    "symbol": asset.symbol,
                    "raw_rows": int(len(data)),
                    "valid_rows": int(len(series)),
                    "first_date": series.index[0].strftime("%Y-%m-%d") if len(series) else None,
                    "last_date": series.index[-1].strftime("%Y-%m-%d") if len(series) else None,
                }
            )

        outer_matrix = pd.concat(series_map.values(), axis=1, join="outer").sort_index()
        outer_matrix = outer_matrix[~outer_matrix.index.duplicated(keep="last")]

        if outer_matrix.empty:
            raise ValueError("No cross-market price history found")

        tradable_mask = outer_matrix.notna().all(axis=1)
        aligned_price_matrix = outer_matrix.loc[tradable_mask].copy()
        tradable_count = int(tradable_mask.sum())
        union_count = int(len(outer_matrix))
        tradable_day_ratio = tradable_count / union_count if union_count else 0.0
        dropped_dates_count = int(union_count - tradable_count)

        if aligned_price_matrix.empty:
            raise ValueError("No aligned cross-market price history found after tradable-day filtering")
        if tradable_count < min_history_days:
            raise ValueError(
                f"Tradable overlap history too short: {tradable_count} days, need at least {min_history_days}"
            )
        if tradable_day_ratio < min_overlap_ratio:
            raise ValueError(
                f"Tradable overlap ratio {tradable_day_ratio:.2f} below threshold {min_overlap_ratio:.2f}"
            )

        for item in symbol_alignment:
            item["coverage_ratio"] = round(
                item["valid_rows"] / union_count if union_count else 0.0,
                4,
            )

        return {
            "raw_price_matrix": outer_matrix,
            "aligned_price_matrix": aligned_price_matrix,
            "tradable_mask": tradable_mask.astype(bool),
            "data_alignment": {
                "per_symbol": symbol_alignment,
                "union_row_count": union_count,
                "aligned_row_count": tradable_count,
                "tradable_day_ratio": round(tradable_day_ratio, 4),
                "dropped_dates_count": dropped_dates_count,
            },
        }

    def _build_results(
        self,
        universe: AssetUniverse,
        price_matrix: pd.DataFrame,
        signal_frame: pd.DataFrame,
        data_alignment: Dict[str, Any],
        construction_mode: str,
    ) -> Dict[str, Any]:
        returns = price_matrix.pct_change().fillna(0.0)
        hedge_portfolio = HedgePortfolioBuilder(universe.get_assets())
        long_assets = hedge_portfolio.long_leg.assets
        short_assets = hedge_portfolio.short_leg.assets
        leg_returns = hedge_portfolio.build_leg_returns(returns)
        long_leg_returns = leg_returns["long"]
        short_leg_returns = leg_returns["short"]
        spread_return = long_leg_returns - short_leg_returns

        positions = signal_frame["position"].shift(1).fillna(0.0)
        turnover = signal_frame["position"].diff().abs().fillna(signal_frame["position"].abs())
        transaction_cost = turnover * (self.commission + self.slippage)
        portfolio_returns = positions * spread_return - transaction_cost

        portfolio = pd.DataFrame(index=price_matrix.index)
        portfolio["long_leg_return"] = long_leg_returns
        portfolio["short_leg_return"] = short_leg_returns
        portfolio["spread_return"] = spread_return
        portfolio["position"] = positions
        portfolio["transaction_cost"] = transaction_cost
        portfolio["returns"] = portfolio_returns
        portfolio["total"] = self.initial_capital * (1 + portfolio_returns).cumprod()
        portfolio["cash"] = portfolio["total"]
        portfolio["exposure"] = portfolio["position"].abs() * portfolio["total"]

        trades = self._build_trades(signal_frame, portfolio)
        total_return = (portfolio["total"].iloc[-1] - self.initial_capital) / self.initial_capital
        daily_returns = portfolio["returns"].dropna()
        closed_holds = [
            float(trade["holding_period_days"])
            for trade in trades
            if trade["type"].startswith("CLOSE") and trade.get("holding_period_days") is not None
        ]
        avg_holding_period = float(np.mean(closed_holds)) if closed_holds else 0.0

        leg_performance = {
            "long": {
                "assets": [asset.to_dict() for asset in long_assets],
                "cumulative_return": float((1 + long_leg_returns).cumprod().iloc[-1] - 1),
            },
            "short": {
                "assets": [asset.to_dict() for asset in short_assets],
                "cumulative_return": float((1 + short_leg_returns).cumprod().iloc[-1] - 1),
            },
            "spread": {
                "cumulative_return": float((1 + spread_return).cumprod().iloc[-1] - 1),
            },
        }
        asset_contributions = hedge_portfolio.build_asset_contributions(returns)
        hedge_summary = hedge_portfolio.summarize_exposures(signal_frame.get("hedge_ratio"))

        spread_series = signal_frame.copy()
        spread_series["date"] = spread_series.index.strftime("%Y-%m-%d")

        correlation_matrix = returns[price_matrix.columns].corr().fillna(0.0)

        execution_diagnostics = {
            "construction_mode": construction_mode,
            "turnover": float(turnover.sum()),
            "cost_drag": float(transaction_cost.sum()),
            "avg_holding_period": round(avg_holding_period, 2),
        }

        results = {
            "initial_capital": self.initial_capital,
            "final_value": float(portfolio["total"].iloc[-1]),
            "total_return": float(total_return),
            "annualized_return": float(calculate_annualized_return(total_return, len(portfolio))),
            "sharpe_ratio": float(calculate_sharpe_ratio(daily_returns)) if len(daily_returns) > 1 else 0.0,
            "max_drawdown": float(calculate_max_drawdown(portfolio["total"])),
            "volatility": float(calculate_volatility(daily_returns)) if len(daily_returns) > 1 else 0.0,
            "var_95": float(calculate_var(daily_returns)) if len(daily_returns) > 0 else 0.0,
            "num_trades": len(trades),
            "portfolio": _portfolio_to_records(portfolio),
            "portfolio_curve": _portfolio_curve(portfolio),
            "trades": trades,
            "spread_series": _dataframe_to_records(
                spread_series[
                    ["date", "long_leg", "short_leg", "hedge_ratio", "spread", "z_score", "signal", "position"]
                ]
            ),
            "leg_performance": leg_performance,
            "correlation_matrix": {
                "columns": list(correlation_matrix.columns),
                "rows": [
                    {
                        "symbol": index,
                        **{column: float(value) for column, value in row.items()},
                    }
                    for index, row in correlation_matrix.iterrows()
                ],
            },
            "data_alignment": data_alignment["data_alignment"],
            "execution_diagnostics": execution_diagnostics,
            "hedge_portfolio": hedge_summary,
            "asset_contributions": asset_contributions,
        }
        if construction_mode == "ols_hedge":
            results["hedge_ratio_series"] = _dataframe_to_records(
                spread_series[["date", "hedge_ratio"]]
            )
        return results

    def _build_trades(self, signal_frame: pd.DataFrame, portfolio: pd.DataFrame) -> List[Dict[str, Any]]:
        trades: List[Dict[str, Any]] = []
        previous_position = 0
        entry_value: Optional[float] = None
        entry_date: Optional[str] = None
        entry_timestamp: Optional[pd.Timestamp] = None

        for idx, row in signal_frame.iterrows():
            current_position = int(row["position"])
            date_str = idx.strftime("%Y-%m-%d")
            if current_position == previous_position:
                continue

            if previous_position != 0:
                exit_value = float(portfolio.loc[idx, "total"])
                trades.append(
                    {
                        "date": date_str,
                        "type": "CLOSE_LONG_SPREAD" if previous_position == 1 else "CLOSE_SHORT_SPREAD",
                        "position": 0,
                        "spread": float(row["spread"]),
                        "z_score": float(row["z_score"]),
                        "pnl": float(exit_value - (entry_value or exit_value)),
                        "entry_date": entry_date,
                        "holding_period_days": int((idx - entry_timestamp).days) if entry_timestamp is not None else None,
                    }
                )
                entry_value = None
                entry_date = None
                entry_timestamp = None

            if current_position != 0:
                entry_value = float(portfolio.loc[idx, "total"])
                entry_date = date_str
                entry_timestamp = idx
                trades.append(
                    {
                        "date": date_str,
                        "type": "OPEN_LONG_SPREAD" if current_position == 1 else "OPEN_SHORT_SPREAD",
                        "position": current_position,
                        "spread": float(row["spread"]),
                        "z_score": float(row["z_score"]),
                        "pnl": 0.0,
                        "entry_date": date_str,
                        "holding_period_days": None,
                    }
                )

            previous_position = current_position

        return trades

    @staticmethod
    def _normalize_daily_close(close_series: pd.Series, symbol: str) -> pd.Series:
        series = close_series.copy()
        series.index = pd.to_datetime(series.index, utc=True).tz_localize(None).normalize()
        series = series[~series.index.duplicated(keep="last")]
        series = series.sort_index().dropna().astype(float)
        series.name = symbol
        return series


def _portfolio_to_records(portfolio: pd.DataFrame) -> List[Dict[str, Any]]:
    records = []
    for idx, row in portfolio.iterrows():
        records.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "total": float(row["total"]),
                "returns": float(row["returns"]),
                "cash": float(row["cash"]),
                "exposure": float(row["exposure"]),
                "position": float(row["position"]),
            }
        )
    return records


def _portfolio_curve(portfolio: pd.DataFrame) -> List[Dict[str, Any]]:
    return [
        {
            "date": idx.strftime("%Y-%m-%d"),
            "total": float(row["total"]),
            "returns": float(row["returns"]),
        }
        for idx, row in portfolio.iterrows()
    ]


def _dataframe_to_records(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for _, row in frame.iterrows():
        records.append(
            {
                key: (float(value) if key != "date" else value)
                for key, value in row.to_dict().items()
            }
        )
    return records
