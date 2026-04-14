from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.backtest.cross_market_backtester import CrossMarketBacktester
from src.trading.cross_market import AssetSide, AssetUniverse, SpreadZScoreStrategy, CointegrationReversionStrategy


def _price_frame(values, start="2024-01-01"):
    dates = pd.date_range(start=start, periods=len(values), freq="D")
    prices = pd.Series(values, index=dates)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": 1_000_000,
        }
    )


class DummyDataManager:
    def __init__(self, frames):
        self.frames = frames

    def get_historical_data(self, symbol, start_date=None, end_date=None, interval="1d", period=None):
        return self.frames.get(symbol, pd.DataFrame()).copy()

    def get_cross_market_historical_data(
        self,
        symbol,
        asset_class,
        start_date=None,
        end_date=None,
        interval="1d",
    ):
        return {
            "data": self.frames.get(symbol, pd.DataFrame()).copy(),
            "provider": f"mock_{str(asset_class).lower()}",
            "asset_class": asset_class,
            "symbol": symbol,
        }


def test_asset_universe_normalizes_weights_by_side():
    universe = AssetUniverse(
        [
            {"symbol": "xlu", "asset_class": "ETF", "side": "long"},
            {"symbol": "duk", "asset_class": "US_STOCK", "side": "long"},
            {"symbol": "qqq", "asset_class": "ETF", "side": "short", "weight": 3},
            {"symbol": "arkk", "asset_class": "ETF", "side": "short", "weight": 1},
        ]
    )

    long_assets = universe.get_assets(AssetSide.LONG)
    short_assets = universe.get_assets(AssetSide.SHORT)

    assert [asset.symbol for asset in long_assets] == ["XLU", "DUK"]
    assert round(sum(asset.weight for asset in long_assets), 6) == 1.0
    assert round(sum(asset.weight for asset in short_assets), 6) == 1.0
    assert short_assets[0].weight == 0.75
    assert short_assets[1].weight == 0.25
    summary = universe.summary()
    assert summary["asset_count"] == 4
    assert summary["by_side"]["long"] == 2
    assert summary["by_asset_class"]["ETF"] == 3
    assert summary["execution_channels"]["cash_equity"] == 4
    assert long_assets[0].market == "USA"
    assert long_assets[0].preferred_provider == "us_stock"


def test_asset_universe_requires_both_sides():
    with pytest.raises(ValueError, match="both long and short"):
        AssetUniverse(
            [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "DUK", "asset_class": "US_STOCK", "side": "long"},
            ]
        )


def test_spread_zscore_strategy_opens_and_closes_positions():
    dates = pd.date_range("2024-01-01", periods=12, freq="D")
    price_matrix = pd.DataFrame(
        {
            "XLU": [100, 100, 100, 100, 100, 130, 135, 100, 100, 100, 100, 100],
            "QQQ": [100] * 12,
        },
        index=dates,
    )
    universe = AssetUniverse(
        [
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ]
    )

    strategy = SpreadZScoreStrategy()
    signals = strategy.generate_cross_signals(
        price_matrix=price_matrix,
        asset_specs=universe.get_assets(),
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
    )

    assert "z_score" in signals.columns
    assert (signals["signal"] == -1).any()
    assert (signals["position"] == -1).any()
    assert signals["position"].iloc[-1] == 0


def test_cointegration_reversion_strategy_adds_cointegration_gate():
    dates = pd.date_range("2024-01-01", periods=18, freq="D")
    base = pd.Series(np.linspace(100, 110, len(dates)), index=dates)
    price_matrix = pd.DataFrame(
        {
            "XLU": base,
            "QQQ": base * 0.98 + 1.5,
        },
        index=dates,
    )
    universe = AssetUniverse(
        [
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ]
    )

    strategy = CointegrationReversionStrategy()
    signals = strategy.generate_cross_signals(
        price_matrix=price_matrix,
        asset_specs=universe.get_assets(),
        parameters={"lookback": 10, "entry_threshold": 1.0, "exit_threshold": 0.3, "p_value_threshold": 0.5, "refit_interval": 3},
    )

    assert "cointegration_p_value" in signals.columns
    assert "cointegrated" in signals.columns


def test_cross_market_backtester_returns_expected_sections():
    frames = {
        "XLU": _price_frame([100, 101, 102, 104, 108, 115, 118, 112, 109, 105, 103, 101]),
        "QQQ": _price_frame([100, 100, 99, 98, 97, 96, 95, 97, 99, 101, 102, 103]),
    }
    backtester = CrossMarketBacktester(
        data_manager=DummyDataManager(frames),
        initial_capital=100000,
        commission=0.0005,
        slippage=0.0005,
    )

    results = backtester.run(
        assets=[
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ],
        template_context={
            "template_id": "utilities_vs_growth",
            "template_name": "US utilities vs NASDAQ growth",
            "allocation_mode": "macro_bias",
            "bias_summary": "多头增配 XLU，空头增配 QQQ",
            "bias_strength_raw": 11.8,
            "bias_strength": 6.5,
            "bias_scale": 0.55,
            "bias_quality_label": "compressed",
            "bias_quality_reason": "正文抓取脆弱源 ndrc，宏观偏置已收缩",
            "base_recommendation_score": 3.1,
            "recommendation_score": 2.65,
            "base_recommendation_tier": "优先部署",
            "recommendation_tier": "重点跟踪",
            "ranking_penalty": 0.45,
            "ranking_penalty_reason": "核心腿 XLU 已进入压缩焦点，模板排序自动降级",
            "input_reliability_label": "fragile",
            "input_reliability_score": 0.41,
            "input_reliability_lead": "当前输入可靠度偏脆弱，主要风险来自时效偏旧与来源退化。",
            "input_reliability_posture": "输入需谨慎使用",
            "input_reliability_reason": "effective confidence 0.41 · freshness aging · 风险 时效偏旧、来源退化",
            "input_reliability_action_hint": "建议先复核当前宏观输入可靠度，再决定是否继续沿用当前模板强度。",
            "department_chaos_label": "chaotic",
            "department_chaos_score": 0.68,
            "department_chaos_top_department": "发改委",
            "department_chaos_reason": "方向反复 3 次，长官意志 0.84",
            "department_chaos_risk_budget_scale": 0.82,
            "policy_execution_label": "chaotic",
            "policy_execution_score": 0.66,
            "policy_execution_top_department": "发改委",
            "policy_execution_reason": "正文覆盖退化，执行滞后正在抬升组合防御需求",
            "policy_execution_risk_budget_scale": 0.84,
            "people_fragility_label": "fragile",
            "people_fragility_score": 0.79,
            "people_fragility_focus": "阿里巴巴",
            "people_fragility_reason": "技术权威继续被非技术 KPI 稀释",
            "people_fragility_risk_budget_scale": 0.88,
            "source_mode_label": "fallback-heavy",
            "source_mode_dominant": "proxy",
            "source_mode_reason": "当前来源治理偏回退，建议压缩偏置强度。",
            "source_mode_risk_budget_scale": 0.72,
            "structural_decay_radar_label": "decay_alert",
            "structural_decay_radar_display_label": "结构衰败警报",
            "structural_decay_radar_score": 0.74,
            "structural_decay_radar_action_hint": "人的维度、治理与执行证据已经共振。",
            "structural_decay_radar_risk_budget_scale": 0.78,
            "structural_decay_radar_top_signals": [{"key": "people", "label": "人的维度", "score": 0.82}],
            "execution_posture": "防御优先 / 对冲增强",
            "base_assets": [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.45},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 0.55},
            ],
            "raw_bias_assets": [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.518},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 0.482},
            ],
        },
        strategy_name="spread_zscore",
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
        min_history_days=10,
    )

    assert "price_matrix_summary" in results
    assert "spread_series" in results
    assert "leg_performance" in results
    assert "correlation_matrix" in results
    assert "data_alignment" in results
    assert "execution_diagnostics" in results
    assert "asset_universe" in results
    assert "hedge_portfolio" in results
    assert "asset_contributions" in results
    assert "cointegration_diagnostics" in results
    assert "execution_plan" in results
    assert results["price_matrix_summary"]["asset_count"] == 2
    assert len(results["portfolio_curve"]) == 12
    assert results["asset_universe"]["by_side"]["long"] == 1
    assert "XLU" in results["asset_contributions"]
    assert results["hedge_portfolio"]["gross_exposure"] > 0
    assert results["hedge_portfolio"]["beta_neutrality"]["level"] in {"balanced", "watch", "stretched", "unknown"}
    assert results["data_alignment"]["per_symbol"][0]["provider"].startswith("mock_")
    assert results["data_alignment"]["per_symbol"][0]["venue"]
    assert results["data_alignment"]["calendar_diagnostics"]["level"] in {"aligned", "watch", "stretched"}
    assert results["execution_plan"]["route_count"] == 2
    assert results["execution_diagnostics"]["route_count"] == 2
    assert results["execution_plan"]["initial_capital"] == 100000
    assert all(route["target_notional"] > 0 for route in results["execution_plan"]["routes"])
    assert round(sum(route["capital_fraction"] for route in results["execution_plan"]["routes"]), 6) == 1.0
    assert results["execution_diagnostics"]["batch_count"] == len(results["execution_plan"]["batches"])
    assert results["execution_diagnostics"]["provider_count"] == len(results["execution_plan"]["by_provider"])
    assert results["execution_diagnostics"]["concentration_level"] in {"balanced", "moderate", "high"}
    assert results["execution_plan"]["provider_allocation"][0]["target_notional"] > 0
    assert results["execution_plan"]["largest_batch"]["target_notional"] > 0
    assert results["execution_plan"]["routes"][0]["rounded_quantity"] >= 1
    assert results["execution_plan"]["routes"][0]["reference_price"] > 0
    assert results["execution_plan"]["routes"][0]["avg_daily_notional"] > 0
    assert results["execution_plan"]["routes"][0]["adv_usage"] > 0
    assert results["execution_plan"]["routes"][0]["liquidity_band"] in {"comfortable", "watch", "stretched", "unknown"}
    assert results["execution_plan"]["routes"][0]["margin_requirement"] > 0
    assert results["execution_plan"]["routes"][0]["margin_rate"] > 0
    assert results["execution_plan"]["sizing_summary"]["lot_efficiency"] > 0
    assert results["execution_plan"]["liquidity_summary"]["max_adv_usage"] > 0
    assert results["execution_plan"]["margin_summary"]["utilization"] > 0
    assert results["execution_plan"]["margin_summary"]["gross_leverage"] > 0
    assert results["execution_diagnostics"]["liquidity_level"] in {"comfortable", "watch", "stretched", "unknown"}
    assert results["execution_diagnostics"]["margin_level"] in {"manageable", "elevated", "aggressive"}
    assert results["execution_diagnostics"]["beta_level"] in {"balanced", "watch", "stretched", "unknown"}
    assert results["execution_diagnostics"]["calendar_level"] in {"aligned", "watch", "stretched"}
    assert results["execution_diagnostics"]["cointegration_level"] in {"strong", "watch", "weak", "unknown"}
    assert results["execution_diagnostics"]["suggested_rebalance"] in {"weekly", "biweekly", "monthly"}
    assert results["cointegration_diagnostics"]["pair_count"] >= 1
    assert results["cointegration_diagnostics"]["best_pair"]["p_value"] >= 0
    assert len(results["execution_plan"]["execution_stress"]["scenarios"]) == 4
    assert results["execution_plan"]["execution_stress"]["worst_case"]["largest_batch_notional"] > 0
    assert "liquidity_level" in results["execution_plan"]["execution_stress"]["worst_case"]
    assert "margin_level" in results["execution_plan"]["execution_stress"]["worst_case"]
    assert results["execution_diagnostics"]["stress_test_flag"] in {"balanced", "moderate", "high"}
    assert results["allocation_overlay"]["allocation_mode"] == "macro_bias"
    assert results["allocation_overlay"]["bias_strength_raw"] == 11.8
    assert results["allocation_overlay"]["bias_strength"] == 6.5
    assert results["allocation_overlay"]["bias_scale"] == 0.55
    assert results["allocation_overlay"]["bias_quality_label"] == "compressed"
    assert results["allocation_overlay"]["bias_compression_effect"] > 0
    assert results["allocation_overlay"]["compression_summary"]["label"] == "compressed"
    assert results["allocation_overlay"]["compression_summary"]["compression_ratio"] > 0
    assert results["allocation_overlay"]["selection_quality"]["label"] == "auto_downgraded"
    assert results["allocation_overlay"]["selection_quality"]["base_recommendation_score"] == 3.1
    assert results["allocation_overlay"]["selection_quality"]["effective_recommendation_score"] == 2.65
    assert results["allocation_overlay"]["selection_quality"]["ranking_penalty"] == 0.45
    assert "核心腿" in results["allocation_overlay"]["selection_quality"]["reason"]
    assert results["allocation_overlay"]["selection_quality"]["input_reliability_posture"] == "输入需谨慎使用"
    assert "复核" in results["allocation_overlay"]["selection_quality"]["input_reliability_action_hint"]
    assert results["allocation_overlay"]["input_reliability"]["label"] == "fragile"
    assert results["allocation_overlay"]["input_reliability"]["score"] == 0.41
    assert results["allocation_overlay"]["input_reliability"]["posture"] == "输入需谨慎使用"
    assert "复核" in results["allocation_overlay"]["input_reliability"]["action_hint"]
    assert results["allocation_overlay"]["department_chaos"]["label"] == "chaotic"
    assert results["allocation_overlay"]["department_chaos"]["score"] == 0.68
    assert results["allocation_overlay"]["department_chaos"]["top_department"] == "发改委"
    assert results["allocation_overlay"]["department_chaos"]["risk_budget_scale"] == 0.82
    assert results["allocation_overlay"]["department_chaos"]["active"] is True
    assert results["allocation_overlay"]["policy_execution"]["label"] == "chaotic"
    assert results["allocation_overlay"]["policy_execution"]["top_department"] == "发改委"
    assert results["allocation_overlay"]["policy_execution"]["risk_budget_scale"] == 0.84
    assert results["allocation_overlay"]["policy_execution"]["active"] is True
    assert results["allocation_overlay"]["people_fragility"]["label"] == "fragile"
    assert results["allocation_overlay"]["people_fragility"]["score"] == 0.79
    assert results["allocation_overlay"]["people_fragility"]["focus"] == "阿里巴巴"
    assert results["allocation_overlay"]["people_fragility"]["risk_budget_scale"] == 0.88
    assert results["allocation_overlay"]["people_fragility"]["active"] is True
    assert results["allocation_overlay"]["source_mode_summary"]["label"] == "fallback-heavy"
    assert results["allocation_overlay"]["source_mode_summary"]["dominant"] == "proxy"
    assert results["allocation_overlay"]["source_mode_summary"]["risk_budget_scale"] == 0.72
    assert results["allocation_overlay"]["source_mode_summary"]["active"] is True
    assert results["allocation_overlay"]["structural_decay_radar"]["label"] == "decay_alert"
    assert results["allocation_overlay"]["structural_decay_radar"]["score"] == 0.74
    assert results["allocation_overlay"]["structural_decay_radar"]["risk_budget_scale"] == 0.78
    assert results["allocation_overlay"]["structural_decay_radar"]["active"] is True
    assert results["allocation_overlay"]["execution_posture"] == "防御优先 / 对冲增强"
    assert results["allocation_overlay"]["compressed_asset_count"] >= 1
    assert results["allocation_overlay"]["rows"][0]["raw_bias_weight"] >= 0
    assert "compression_delta" in results["allocation_overlay"]["rows"][0]
    assert results["allocation_overlay"]["rows"][0]["effective_weight"] >= 0
    assert results["allocation_overlay"]["max_delta_weight"] >= 0
    assert results["constraint_overlay"]["applied"] is False
    assert results["data_alignment"]["per_symbol"][0]["avg_daily_notional"] > 0
    assert results["refit_summary"]["refit_interval"] == 1


def test_cross_market_backtester_supports_cointegration_reversion_with_refit():
    frames = {
        "XLU": _price_frame([100, 101, 102, 104, 106, 108, 109, 111, 112, 113, 114, 115, 116, 117, 118, 119]),
        "QQQ": _price_frame([99, 100, 101, 103, 105, 107, 108, 110, 111, 112, 113, 114, 115, 116, 117, 118]),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    results = backtester.run(
        assets=[
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ],
        strategy_name="cointegration_reversion",
        parameters={
            "lookback": 10,
            "entry_threshold": 1.0,
            "exit_threshold": 0.2,
            "p_value_threshold": 0.5,
            "refit_interval": 4,
        },
        construction_mode="ols_hedge",
        min_history_days=10,
    )

    assert results["strategy"] == "cointegration_reversion"
    assert results["refit_summary"]["refit_interval"] == 4
    assert results["refit_summary"]["dynamic_hedge"] is True
    assert results["cointegration_diagnostics"]["available"] is True


def test_cross_market_backtester_uses_tradable_mask():
    frames = {
        "XLU": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111]),
        "QQQ": _price_frame([100, 99, 98, 97, 96, 95, 94, 93, 92, 91], start="2024-01-03"),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    results = backtester.run(
        assets=[
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ],
        strategy_name="spread_zscore",
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
        min_history_days=10,
        min_overlap_ratio=0.7,
    )

    assert results["data_alignment"]["dropped_dates_count"] == 2
    assert results["data_alignment"]["aligned_row_count"] == 10


def test_cross_market_backtester_applies_weight_constraints():
    frames = {
        "XLU": _price_frame([100, 101, 102, 104, 108, 115, 118, 112, 109, 105, 103, 101]),
        "DUK": _price_frame([100, 100, 101, 102, 103, 104, 105, 106, 106, 107, 108, 109]),
        "QQQ": _price_frame([100, 100, 99, 98, 97, 96, 95, 97, 99, 101, 102, 103]),
        "ARKK": _price_frame([100, 99, 98, 97, 95, 94, 93, 92, 91, 90, 89, 88]),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    results = backtester.run(
        assets=[
            {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.85},
            {"symbol": "DUK", "asset_class": "US_STOCK", "side": "long", "weight": 0.15},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 0.8},
            {"symbol": "ARKK", "asset_class": "ETF", "side": "short", "weight": 0.2},
        ],
        strategy_name="spread_zscore",
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
        min_history_days=10,
        allocation_constraints={"max_single_weight": 0.6, "min_single_weight": 0.2},
    )

    assert results["constraint_overlay"]["applied"] is True
    assert results["constraint_overlay"]["binding_count"] >= 1
    assert results["constraint_overlay"]["max_delta_weight"] > 0
    assert any(row["binding"] == "max" for row in results["constraint_overlay"]["rows"])
    assert results["execution_diagnostics"]["constraint_binding_count"] == results["constraint_overlay"]["binding_count"]


def test_cross_market_backtester_rejects_infeasible_constraints():
    frames = {
        "XLU": _price_frame([100, 101, 102, 104, 108, 115, 118, 112, 109, 105, 103, 101]),
        "QQQ": _price_frame([100, 100, 99, 98, 97, 96, 95, 97, 99, 101, 102, 103]),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    with pytest.raises(ValueError, match="infeasible"):
        backtester.run(
            assets=[
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
            ],
            strategy_name="spread_zscore",
            parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
            min_history_days=10,
            allocation_constraints={"max_single_weight": 0.4},
        )


def test_cross_market_backtester_rejects_short_history():
    frames = {
        "XLU": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
        "QQQ": _price_frame([100, 99, 98, 97, 96, 95, 94, 93, 92, 91]),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    with pytest.raises(ValueError, match="need at least 20"):
        backtester.run(
            assets=[
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
            ],
            strategy_name="spread_zscore",
            parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
            min_history_days=20,
        )


def test_cross_market_backtester_returns_hedge_ratio_series_for_ols_mode():
    frames = {
        "XLU": _price_frame([100, 101, 102, 103, 104, 106, 108, 110, 111, 112, 113, 114, 115, 116]),
        "QQQ": _price_frame([100, 100, 101, 101, 102, 103, 104, 104, 105, 106, 107, 108, 109, 110]),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    results = backtester.run(
        assets=[
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ],
        strategy_name="spread_zscore",
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
        construction_mode="ols_hedge",
        min_history_days=10,
    )

    assert "hedge_ratio_series" in results
    assert len(results["hedge_ratio_series"]) == results["price_matrix_summary"]["row_count"]
    assert results["execution_diagnostics"]["construction_mode"] == "ols_hedge"
    assert results["hedge_portfolio"]["hedge_ratio"]["average"] > 0


def test_cross_market_backtester_uses_asset_class_aware_fetch_metadata():
    frames = {
        "HG=F": _price_frame([100, 102, 103, 101, 105, 110, 108, 107, 109, 111, 114, 116]),
        "SOXX": _price_frame([100, 99, 101, 103, 102, 101, 100, 98, 97, 96, 95, 94]),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    results = backtester.run(
        assets=[
            {"symbol": "HG=F", "asset_class": "COMMODITY_FUTURES", "side": "long"},
            {"symbol": "SOXX", "asset_class": "ETF", "side": "short"},
        ],
        strategy_name="spread_zscore",
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
        min_history_days=10,
    )

    symbol_rows = {item["symbol"]: item for item in results["data_alignment"]["per_symbol"]}
    assert symbol_rows["HG=F"]["asset_class"] == "COMMODITY_FUTURES"
    assert symbol_rows["HG=F"]["provider"] == "mock_commodity_futures"
    assert symbol_rows["SOXX"]["provider"] == "mock_etf"
    assert results["execution_plan"]["batches"][0]["preferred_provider"] in {"commodity", "us_stock"}
    assert any(batch["target_notional"] > 0 for batch in results["execution_plan"]["batches"])
    assert results["execution_plan"]["venue_allocation"][0]["target_notional"] > 0
    assert all(route["capacity_band"] in {"light", "moderate", "heavy"} for route in results["execution_plan"]["routes"])
