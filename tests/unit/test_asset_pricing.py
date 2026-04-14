"""
资产定价模块单元测试
测试 CAPM、FF3、DCF、可比估值和定价差异分析
"""

import pytest
import numpy as np
import pandas as pd
import warnings
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


class TestAssetPricingEngine:
    """测试多因子资产定价引擎"""

    def _make_mock_returns(self, days=200, trend=0.0005):
        """生成模拟收益序列"""
        np.random.seed(42)
        dates = pd.date_range(start="2024-01-01", periods=days)
        returns = np.random.normal(trend, 0.02, days)
        return pd.Series(returns, index=dates)

    def _make_mock_ff_factors(self, days=200):
        """生成模拟 FF 因子数据"""
        np.random.seed(42)
        dates = pd.date_range(start="2024-01-01", periods=days)
        return pd.DataFrame({
            "Mkt-RF": np.random.normal(0.0003, 0.01, days),
            "SMB": np.random.normal(0.0001, 0.005, days),
            "HML": np.random.normal(0.0001, 0.005, days),
            "RF": np.full(days, 0.0002)
        }, index=dates)

    @patch("src.analytics.asset_pricing._fetch_ff_factors")
    @patch("src.analytics.asset_pricing._fetch_ff5_factors")
    @patch("src.data.data_manager.DataManager.get_historical_data")
    def test_capm_analysis(self, mock_get_data, mock_ff5, mock_ff):
        """测试 CAPM 分析结果结构和合理性"""
        from src.analytics.asset_pricing import AssetPricingEngine

        # 构造模拟数据
        days = 200
        dates = pd.date_range(start="2024-01-01", periods=days)
        close_prices = 100 + np.cumsum(np.random.normal(0.1, 1, days))
        mock_data = pd.DataFrame({
            "open": close_prices * 0.99,
            "high": close_prices * 1.01,
            "low": close_prices * 0.98,
            "close": close_prices,
            "volume": np.random.randint(1000000, 5000000, days)
        }, index=dates)
        mock_get_data.return_value = mock_data
        mock_ff.return_value = self._make_mock_ff_factors(days)
        ff5 = self._make_mock_ff_factors(days)
        ff5["RMW"] = np.random.normal(0.0001, 0.004, days)
        ff5["CMA"] = np.random.normal(0.0001, 0.004, days)
        mock_ff5.return_value = ff5

        engine = AssetPricingEngine()
        result = engine.analyze("TEST", "1y")

        # 验证结构
        assert "capm" in result
        assert "fama_french" in result
        assert "fama_french_five_factor" in result
        assert "attribution" in result
        assert "summary" in result

        # 验证 CAPM 字段
        capm = result["capm"]
        assert "error" not in capm, f"CAPM 出错: {capm.get('error')}"
        assert "alpha_annual" in capm
        assert "beta" in capm
        assert "r_squared" in capm
        assert 0 <= capm["r_squared"] <= 1
        assert "interpretation" in capm

    @patch("src.analytics.asset_pricing._fetch_ff_factors")
    @patch("src.analytics.asset_pricing._fetch_ff5_factors")
    @patch("src.data.data_manager.DataManager.get_historical_data")
    def test_ff3_factor_loadings(self, mock_get_data, mock_ff5, mock_ff):
        """测试 FF3 因子暴露度结果"""
        from src.analytics.asset_pricing import AssetPricingEngine

        days = 200
        dates = pd.date_range(start="2024-01-01", periods=days)
        close_prices = 100 + np.cumsum(np.random.normal(0.1, 1, days))
        mock_data = pd.DataFrame({
            "open": close_prices * 0.99,
            "high": close_prices * 1.01,
            "low": close_prices * 0.98,
            "close": close_prices,
            "volume": np.random.randint(1000000, 5000000, days)
        }, index=dates)
        mock_get_data.return_value = mock_data
        mock_ff.return_value = self._make_mock_ff_factors(days)
        ff5 = self._make_mock_ff_factors(days)
        ff5["RMW"] = np.random.normal(0.0001, 0.004, days)
        ff5["CMA"] = np.random.normal(0.0001, 0.004, days)
        mock_ff5.return_value = ff5

        engine = AssetPricingEngine()
        result = engine.analyze("TEST", "1y")
        ff3 = result["fama_french"]
        ff5_result = result["fama_french_five_factor"]

        assert "error" not in ff3, f"FF3 出错: {ff3.get('error')}"
        assert "factor_loadings" in ff3
        loadings = ff3["factor_loadings"]
        assert "market" in loadings
        assert "size" in loadings
        assert "value" in loadings
        assert "r_squared" in ff3
        assert "error" not in ff5_result, f"FF5 出错: {ff5_result.get('error')}"
        assert "profitability" in ff5_result["factor_loadings"]
        assert "investment" in ff5_result["factor_loadings"]

    @patch("src.analytics.asset_pricing._fetch_ff_factors")
    @patch("src.analytics.asset_pricing._fetch_ff5_factors")
    @patch("src.data.data_manager.DataManager.get_historical_data")
    def test_aligns_tz_aware_prices_with_tz_naive_factors(self, mock_get_data, mock_ff5, mock_ff):
        """测试时区感知价格索引与无时区因子索引可以安全对齐"""
        from src.analytics.asset_pricing import AssetPricingEngine

        days = 200
        aware_dates = pd.date_range(start="2024-01-01", periods=days, tz="America/New_York")
        naive_dates = pd.date_range(start="2024-01-01", periods=days)
        close_prices = 100 + np.cumsum(np.random.normal(0.1, 1, days))

        mock_get_data.return_value = pd.DataFrame({
            "open": close_prices * 0.99,
            "high": close_prices * 1.01,
            "low": close_prices * 0.98,
            "close": close_prices,
            "volume": np.random.randint(1000000, 5000000, days)
        }, index=aware_dates)
        mock_ff.return_value = pd.DataFrame({
            "Mkt-RF": np.random.normal(0.0003, 0.01, days),
            "SMB": np.random.normal(0.0001, 0.005, days),
            "HML": np.random.normal(0.0001, 0.005, days),
            "RF": np.full(days, 0.0002)
        }, index=naive_dates)
        mock_ff5.return_value = pd.DataFrame({
            "Mkt-RF": np.random.normal(0.0003, 0.01, days),
            "SMB": np.random.normal(0.0001, 0.005, days),
            "HML": np.random.normal(0.0001, 0.005, days),
            "RMW": np.random.normal(0.0001, 0.004, days),
            "CMA": np.random.normal(0.0001, 0.004, days),
            "RF": np.full(days, 0.0002)
        }, index=naive_dates)

        engine = AssetPricingEngine()
        result = engine.analyze("TEST", "1y")

        assert "error" not in result["capm"], result["capm"].get("error")
        assert "error" not in result["fama_french"], result["fama_french"].get("error")
        assert "error" not in result["fama_french_five_factor"], result["fama_french_five_factor"].get("error")

    @patch("src.analytics.asset_pricing._fetch_ff_factors")
    @patch("src.analytics.asset_pricing._fetch_ff5_factors")
    @patch("src.data.data_manager.DataManager.get_historical_data")
    def test_factor_analysis_avoids_runtime_warnings(self, mock_get_data, mock_ff5, mock_ff):
        """测试因子分析主路径不会触发 runtime warning 噪音"""
        from src.analytics.asset_pricing import AssetPricingEngine

        days = 200
        dates = pd.date_range(start="2024-01-01", periods=days)
        close_prices = 100 + np.cumsum(np.random.normal(0.1, 1, days))
        mock_get_data.return_value = pd.DataFrame({
            "open": close_prices * 0.99,
            "high": close_prices * 1.01,
            "low": close_prices * 0.98,
            "close": close_prices,
            "volume": np.random.randint(1000000, 5000000, days)
        }, index=dates)
        mock_ff.return_value = self._make_mock_ff_factors(days)
        ff5 = self._make_mock_ff_factors(days)
        ff5["RMW"] = np.random.normal(0.0001, 0.004, days)
        ff5["CMA"] = np.random.normal(0.0001, 0.004, days)
        mock_ff5.return_value = ff5

        engine = AssetPricingEngine()
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            result = engine.analyze("TEST", "1y")

        runtime_warnings = [item for item in captured if issubclass(item.category, RuntimeWarning)]
        assert not runtime_warnings, [str(item.message) for item in runtime_warnings]
        assert "error" not in result["capm"], result["capm"].get("error")

    @patch("src.data.data_manager.DataManager.get_historical_data")
    def test_insufficient_data(self, mock_get_data):
        """测试数据不足时的处理"""
        from src.analytics.asset_pricing import AssetPricingEngine

        mock_get_data.return_value = pd.DataFrame()

        engine = AssetPricingEngine()
        result = engine.analyze("INVALID", "1y")

        assert "capm" in result
        assert "error" in result["capm"]

    def test_factor_attribution_uses_dynamic_realized_premia(self):
        """测试因子归因优先使用当前窗口的动态年化因子溢价"""
        from src.analytics.asset_pricing import AssetPricingEngine

        engine = AssetPricingEngine()
        ff_factors = pd.DataFrame({
            "Mkt-RF": np.full(60, 0.0005),
            "SMB": np.full(60, 0.0002),
            "HML": np.full(60, -0.0001),
            "RF": np.full(60, 0.0001),
        }, index=pd.date_range(start="2024-01-01", periods=60))
        ff_factors.attrs["source"] = {
            "type": "kenneth_french_library",
            "label": "Kenneth French Data Library",
            "is_proxy": False,
            "warning": "",
        }

        result = engine._factor_attribution(
            {"alpha_annual": 0.03},
            {"factor_loadings": {"market": 1.2, "size": 0.5, "value": -0.4}, "alpha_annual": 0.03},
            ff_factors,
        )

        assumptions = result["premium_assumptions"]
        assert assumptions["source"] == "rolling_realized_window"
        assert assumptions["window_days"] == 60
        assert assumptions["market"] == pytest.approx(0.126, rel=1e-3)
        assert assumptions["size"] == pytest.approx(0.0504, rel=1e-3)
        assert assumptions["value"] == pytest.approx(-0.0252, rel=1e-3)
        assert result["components"]["market"]["value"] == pytest.approx(1.2 * 0.126, rel=1e-3)
        assert result["components"]["size"]["value"] == pytest.approx(0.5 * 0.0504, rel=1e-3)
        assert result["components"]["value"]["value"] == pytest.approx(-0.4 * -0.0252, rel=2e-3)


class TestValuationModel:
    """测试内在价值估值模型"""

    def _mock_fundamentals(self):
        return {
            "symbol": "TEST",
            "company_name": "Test Corp",
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 1e12,
            "enterprise_value": 1.15e12,
            "pe_ratio": 25,
            "forward_pe": 22,
            "peg_ratio": 1.5,
            "price_to_book": 8,
            "price_to_sales": 6.2,
            "enterprise_to_ebitda": 18.5,
            "enterprise_to_revenue": 7.4,
            "dividend_yield": 0.005,
            "profit_margin": 0.25,
            "operating_margin": 0.30,
            "roe": 0.35,
            "roa": 0.15,
            "revenue_growth": 0.12,
            "earnings_growth": 0.15,
            "revenue": 1.55e11,
            "debt_to_equity": 60,
            "current_ratio": 1.8,
            "beta": 1.1,
            "52w_high": 200,
            "52w_low": 150,
            "target_price": 190,
        }

    @patch("src.data.data_manager.DataManager.get_latest_price")
    @patch("src.data.data_manager.DataManager.get_fundamental_data")
    def test_valuation_structure(self, mock_fund, mock_price):
        """测试估值结果的完整结构"""
        from src.analytics.valuation_model import ValuationModel

        mock_fund.return_value = self._mock_fundamentals()
        mock_price.return_value = {"price": 180, "symbol": "TEST"}

        model = ValuationModel()
        result = model.analyze("TEST")

        assert "dcf" in result
        assert "monte_carlo" in result
        assert "comparable" in result
        assert "fair_value" in result
        assert "valuation_status" in result
        assert "summary" in result

    @patch("src.data.data_manager.DataManager.get_latest_price")
    @patch("src.data.data_manager.DataManager.get_fundamental_data")
    def test_dcf_valuation(self, mock_fund, mock_price):
        """测试 DCF 估值结果合理性"""
        from src.analytics.valuation_model import ValuationModel

        mock_fund.return_value = self._mock_fundamentals()
        mock_price.return_value = {"price": 180, "symbol": "TEST"}

        model = ValuationModel()
        result = model.analyze("TEST")

        dcf = result["dcf"]
        if "error" not in dcf:
            assert dcf["intrinsic_value"] > 0
            assert "assumptions" in dcf
            assert dcf["assumptions"]["wacc"] > 0
            assert dcf["assumptions"]["wacc"] < 0.30  # WACC 不应超过 30%
            assert len(dcf["scenarios"]) == 3
            assert [item["label"] for item in dcf["scenarios"]] == ["悲观", "基准", "乐观"]
            bear_case = next(item for item in dcf["scenarios"] if item["name"] == "bear")
            base_case = next(item for item in dcf["scenarios"] if item["name"] == "base")
            bull_case = next(item for item in dcf["scenarios"] if item["name"] == "bull")
            assert bear_case["intrinsic_value"] < base_case["intrinsic_value"] < bull_case["intrinsic_value"]
            assert base_case["intrinsic_value"] == dcf["intrinsic_value"]
            assert result["monte_carlo"]["sample_count"] > 0
            assert result["monte_carlo"]["p10"] <= result["monte_carlo"]["p50"] <= result["monte_carlo"]["p90"]

    def test_composite_valuation_uses_scenario_and_multiple_dispersion_for_range(self):
        """测试综合估值区间优先使用情景与倍数分布，而不是固定 ±15%"""
        from src.analytics.valuation_model import ValuationModel

        model = ValuationModel()
        fair_value = model._composite_valuation(
            {
                "intrinsic_value": 100,
                "scenarios": [
                    {"name": "bear", "intrinsic_value": 86},
                    {"name": "base", "intrinsic_value": 100},
                    {"name": "bull", "intrinsic_value": 121},
                ],
            },
            {
                "fair_value": 108,
                "methods": [
                    {"method": "P/E 倍数法", "fair_value": 102},
                    {"method": "P/B 倍数法", "fair_value": 114},
                ],
            },
        )

        assert fair_value["mid"] == 104.0
        assert fair_value["low"] == 86.0
        assert fair_value["high"] == 121.0
        assert fair_value["range_basis"] == "dcf_scenarios_and_multiples"

    @patch("src.data.data_manager.DataManager.get_latest_price")
    @patch("src.data.data_manager.DataManager.get_fundamental_data")
    def test_comparable_valuation(self, mock_fund, mock_price):
        """测试可比估值法"""
        from src.analytics.valuation_model import ValuationModel

        mock_fund.return_value = self._mock_fundamentals()
        mock_price.return_value = {"price": 180, "symbol": "TEST"}

        model = ValuationModel()
        result = model.analyze("TEST")

        comp = result["comparable"]
        if "error" not in comp:
            assert comp["fair_value"] > 0
            assert len(comp["methods"]) > 0
            method_names = {item["method"] for item in comp["methods"]}
            assert "EV/Revenue 倍数法" in method_names
            assert "PEG 倍数法" in method_names

    @patch("src.data.data_manager.DataManager.get_latest_price")
    @patch("src.data.data_manager.DataManager.get_fundamental_data")
    def test_comparable_valuation_prefers_dynamic_peer_benchmarks(self, mock_fund, mock_price):
        """测试同行样本足够时优先使用动态同行中位数，而不是静态行业模板"""
        from src.analytics.valuation_model import ValuationModel

        base = self._mock_fundamentals()
        peer_values = {
            "AAPL": {"pe_ratio": 26, "peg_ratio": 1.7, "price_to_book": 7.2, "price_to_sales": 6.8, "enterprise_to_ebitda": 18, "enterprise_to_revenue": 7.1},
            "MSFT": {"pe_ratio": 31, "peg_ratio": 1.9, "price_to_book": 9.1, "price_to_sales": 11.4, "enterprise_to_ebitda": 22, "enterprise_to_revenue": 11.8},
            "NVDA": {"pe_ratio": 35, "peg_ratio": 2.1, "price_to_book": 15.0, "price_to_sales": 18.0, "enterprise_to_ebitda": 28, "enterprise_to_revenue": 19.5},
            "AMZN": {"pe_ratio": 29, "peg_ratio": 1.6, "price_to_book": 6.0, "price_to_sales": 4.1, "enterprise_to_ebitda": 19, "enterprise_to_revenue": 4.4},
        }

        def build_fundamental(symbol):
            if symbol == "TEST":
                return base
            if symbol in peer_values:
                return {
                    **base,
                    "symbol": symbol,
                    "company_name": symbol,
                    "industry": "Software",
                    **peer_values[symbol],
                }
            return {"symbol": symbol, "error": "not used"}

        mock_fund.side_effect = build_fundamental
        mock_price.return_value = {"price": 180, "symbol": "TEST"}

        model = ValuationModel()
        result = model.analyze("TEST")
        comp = result["comparable"]

        assert comp["benchmark_source"] == "dynamic_peer_median"
        assert comp["benchmark_peer_count"] >= 3
        assert "AAPL" in comp["benchmark_peer_symbols"]
        assert comp["sector_benchmark"]["pe"] == 30.0
        assert any("同行中位数" in warning for warning in comp["warnings"])

    @patch("src.data.data_manager.DataManager.get_historical_data")
    @patch("src.data.data_manager.DataManager.get_latest_price")
    @patch("src.data.data_manager.DataManager.get_fundamental_data")
    def test_valuation_falls_back_to_recent_close_when_latest_price_unavailable(self, mock_fund, mock_price, mock_hist):
        """测试最新价失败时回退到最近收盘价，而不是 52 周高点"""
        from src.analytics.valuation_model import ValuationModel

        fundamentals = self._mock_fundamentals()
        fundamentals["52w_high"] = 200
        mock_fund.return_value = fundamentals
        mock_price.return_value = {"symbol": "TEST", "error": "latest unavailable"}
        mock_hist.return_value = pd.DataFrame({
            "close": [118.5, 121.2, 123.45],
        }, index=pd.date_range(start="2024-01-01", periods=3))

        model = ValuationModel()
        result = model.analyze("TEST")

        assert result["current_price"] == 123.45
        assert result["current_price"] != 200
        assert result["current_price_source"] == "historical_close"

    @patch("src.data.data_manager.DataManager.get_fundamental_data")
    def test_missing_data_handling(self, mock_fund):
        """测试缺失数据的处理"""
        from src.analytics.valuation_model import ValuationModel

        mock_fund.return_value = {"symbol": "FAIL", "error": "Data not found"}

        model = ValuationModel()
        result = model.analyze("FAIL")

        assert "valuation_status" in result
        assert result["valuation_status"]["status"] == "unknown"


class TestPricingGapAnalyzer:
    """测试定价差异分析器"""

    @patch("src.analytics.asset_pricing._fetch_ff_factors")
    @patch("src.data.data_manager.DataManager.get_latest_price")
    @patch("src.data.data_manager.DataManager.get_fundamental_data")
    @patch("src.data.data_manager.DataManager.get_historical_data")
    def test_gap_analysis_structure(self, mock_hist, mock_fund, mock_price, mock_ff):
        """测试定价差异分析结果结构"""
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        np.random.seed(42)
        days = 200
        dates = pd.date_range(start="2024-01-01", periods=days)
        close = 100 + np.cumsum(np.random.normal(0.1, 1, days))
        mock_hist.return_value = pd.DataFrame({
            "open": close * 0.99, "high": close * 1.01,
            "low": close * 0.98, "close": close,
            "volume": np.random.randint(1e6, 5e6, days)
        }, index=dates)

        mock_fund.return_value = {
            "symbol": "TEST", "company_name": "Test", "sector": "Technology",
            "industry": "SW", "market_cap": 1e12, "pe_ratio": 25,
            "forward_pe": 22, "price_to_book": 8, "beta": 1.1,
            "revenue_growth": 0.12, "profit_margin": 0.25,
            "debt_to_equity": 60, "current_ratio": 1.8,
            "52w_high": 200, "52w_low": 150, "peg_ratio": 1.5,
            "dividend_yield": 0, "operating_margin": 0.3,
            "roe": 0.35, "roa": 0.15, "earnings_growth": 0.15,
            "quick_ratio": 1.5, "analyst_rating": "buy", "target_price": 190,
        }
        mock_price.return_value = {"price": 180, "symbol": "TEST"}

        ff_data = pd.DataFrame({
            "Mkt-RF": np.random.normal(0.0003, 0.01, days),
            "SMB": np.random.normal(0.0001, 0.005, days),
            "HML": np.random.normal(0.0001, 0.005, days),
            "RF": np.full(days, 0.0002)
        }, index=dates)
        mock_ff.return_value = ff_data

        analyzer = PricingGapAnalyzer()
        result = analyzer.analyze("TEST", "1y")

        assert "factor_model" in result
        assert "valuation" in result
        assert "gap_analysis" in result
        assert "deviation_drivers" in result
        assert "people_layer" in result
        assert "implications" in result
        assert "summary" in result

    def test_people_layer_combines_executives_insiders_and_hiring(self):
        """测试人的维度会聚合高管画像、内部人交易和招聘稀释度"""
        from src.data.alternative.people import PeopleSignalAnalyzer

        analyzer = PeopleSignalAnalyzer()
        result = analyzer.analyze("BABA", "阿里巴巴", "Technology")

        assert result["symbol"] == "BABA"
        assert result["risk_level"] in {"medium", "high"}
        assert result["executive_profile"]["leadership_style"] == "commercial_finance_led"
        assert result["insider_flow"]["net_action"] in {"neutral", "mixed", "selling", "buying"}
        assert "dilution_ratio" in result["hiring_signal"]
        assert result["summary"]

    def test_implications_include_people_layer_risk_context(self):
        """测试人的维度会进入最终投资含义"""
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        factor = {
            "data_points": 120,
            "capm": {"alpha_pct": -4.5, "data_points": 120},
            "fama_french": {"alpha_pct": -3.2, "data_points": 120},
        }
        valuation = {
            "current_price_source": "live",
            "fair_value": {"mid": 100},
            "dcf": {"intrinsic_value": 90},
            "comparable": {"fair_value": 94},
            "valuation_status": {"status": "overvalued"},
        }
        gap = {
            "gap_pct": 26.0,
            "severity": "high",
            "direction": "溢价(高估)",
        }
        people_layer = {
            "risk_level": "high",
            "stance": "fragile",
            "summary": "人的维度偏脆弱",
            "notes": ["内部人交易偏减持，说明管理层对当前定价的安全边际未给出强背书。"],
        }

        implications = analyzer._derive_implications(gap, factor, valuation, people_layer)

        assert implications["people_risk"] == "high"
        assert implications["people_summary"] == "人的维度偏脆弱"
        assert any("人的维度显示组织与治理脆弱度偏高" in item for item in implications["insights"])

    def test_people_governance_overlay_builds_discount_and_source_mode_context(self):
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        overlay = analyzer._build_people_governance_overlay(
            symbol="BABA",
            gap={"gap_pct": 24.0},
            valuation={"valuation_status": {"status": "overvalued"}},
            factor={
                "capm": {"alpha_pct": -4.1},
                "fama_french": {"alpha_pct": -2.4},
            },
            people_layer={
                "stance": "fragile",
                "risk_level": "high",
                "confidence": 0.78,
                "people_fragility_score": 0.74,
                "people_quality_score": 0.31,
                "executive_profile": {"leadership_balance": "商业/财务主导"},
                "insider_flow": {"label": "内部人减持偏谨慎", "conviction_score": -0.22},
                "hiring_signal": {"dilution_ratio": 1.71, "alert_message": "技术组织被商业目标稀释"},
            },
            alt_context={
                "people_signal": {"avg_fragility_score": 0.69},
                "people_watch_entry": {"people_fragility_score": 0.77},
                "policy_execution": {
                    "score": 0.66,
                    "confidence": 0.73,
                    "summary": "部门级政策执行混乱继续升温",
                    "top_departments": [
                        {
                            "department": "ndrc",
                            "department_label": "发改委",
                            "execution_status": "lagging",
                            "lag_days": 14,
                            "full_text_ratio": 0.41,
                            "reason": "方向反复 2 次，长官意志偏高",
                        }
                    ],
                },
                "source_mode_summary": {"label": "fallback-heavy", "coverage": 8},
            },
        )

        assert overlay["label"] in {"治理折价", "严重治理折价"}
        assert overlay["governance_discount_pct"] > 5
        assert overlay["confidence"] >= 0.7
        assert overlay["source_mode_summary"]["label"] == "fallback-heavy"
        assert overlay["executive_evidence"]["leadership_balance"] == "商业/财务主导"
        assert overlay["hiring_evidence"]["dilution_ratio"] == 1.71
        assert overlay["policy_execution_context"]["label"] == "chaotic"
        assert overlay["policy_execution_context"]["top_department"] == "发改委"

    def test_screening_score_penalizes_value_ideas_with_high_governance_discount(self):
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        neutral_score = analyzer._screening_score(
            gap_pct=-28.0,
            confidence_score=0.72,
            primary_view="低估",
            alignment_status="aligned",
            people_governance_overlay={"governance_discount_pct": 0.0, "confidence": 0.0},
        )
        fragile_score = analyzer._screening_score(
            gap_pct=-28.0,
            confidence_score=0.72,
            primary_view="低估",
            alignment_status="aligned",
            people_governance_overlay={"governance_discount_pct": 12.0, "confidence": 0.78},
        )

        assert fragile_score < neutral_score

    def test_structural_decay_escalates_when_people_and_market_signals_break_together(self):
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        factor = {
            "capm": {"alpha_pct": -6.2, "data_points": 180},
            "fama_french": {"alpha_pct": -4.1, "data_points": 180},
        }
        valuation = {
            "symbol": "TEST",
            "current_price_source": "live",
            "fair_value": {"mid": 100},
            "dcf": {"intrinsic_value": 90},
            "comparable": {"fair_value": 96},
            "valuation_status": {"status": "overvalued"},
        }
        gap = {
            "current_price": 128,
            "fair_value_mid": 100,
            "gap_pct": 28.0,
            "severity": "high",
            "direction": "溢价(高估)",
        }
        people_layer = {
            "risk_level": "high",
            "stance": "fragile",
            "people_fragility_score": 0.76,
            "people_quality_score": 0.34,
            "summary": "人的维度偏脆弱",
            "hiring_signal": {"dilution_ratio": 1.72},
            "insider_flow": {"conviction_score": -0.24},
        }

        implications = analyzer._derive_implications(gap, factor, valuation, people_layer)

        assert implications["structural_decay"]["score"] >= 0.72
        assert implications["structural_decay"]["action"] == "structural_short"
        assert implications["structural_decay"]["dominant_failure_label"] in {"组织与治理稀释", "竞争与执行失速"}
        assert implications["macro_mispricing_thesis"]["thesis_type"] == "relative_short"
        assert implications["macro_mispricing_thesis"]["primary_leg"]["symbol"] == "TEST"
        assert implications["macro_mispricing_thesis"]["primary_leg"]["side"] == "short"
        assert implications["macro_mispricing_thesis"]["hedge_leg"]["symbol"] == "SPY"
        assert len(implications["macro_mispricing_thesis"]["trade_legs"]) >= 2
        assert implications["macro_mispricing_thesis"]["trade_legs"][0]["role"] == "core_expression"
        assert any(leg["role"] == "stress_hedge" for leg in implications["macro_mispricing_thesis"]["trade_legs"])
        assert any("结构性衰败" in item for item in implications["insights"])

    def test_implications_confidence_high_with_full_model_coverage(self):
        """测试数据完整时给出高置信度"""
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        factor = {
            "data_points": 220,
            "capm": {"alpha_pct": -2.1, "data_points": 212},
            "fama_french": {"alpha_pct": -1.8, "data_points": 212},
        }
        valuation = {
            "current_price_source": "live",
            "fair_value": {"mid": 100},
            "dcf": {"intrinsic_value": 96},
            "comparable": {"fair_value": 104},
            "valuation_status": {"status": "fairly_valued"},
        }
        gap = {
            "gap_pct": 12.0,
            "severity": "moderate",
            "direction": "溢价(高估)",
        }

        implications = analyzer._derive_implications(gap, factor, valuation)

        assert implications["confidence"] == "high"
        assert implications["confidence_score"] >= 0.72
        assert implications["confidence_reasons"] == []
        assert any(item["key"] == "gap_anchor" for item in implications["confidence_breakdown"])
        assert implications["trade_setup"]["target_price"] == 100.0
        assert implications["factor_alignment"]["status"] == "neutral"
        assert implications["factor_alignment"]["label"] == "待确认"

    def test_implications_confidence_low_with_partial_models_and_fallback_price(self):
        """测试模型缺失且价格回退时降低置信度"""
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        factor = {
            "data_points": 45,
            "capm": {"error": "对齐后数据不足30天"},
            "fama_french": {"error": "对齐后数据不足30天"},
        }
        valuation = {
            "current_price_source": "historical_close",
            "fair_value": {"mid": 100},
            "dcf": {"error": "缺少关键财务数据", "intrinsic_value": None},
            "comparable": {"fair_value": 138},
            "valuation_status": {"status": "overvalued"},
        }
        gap = {
            "gap_pct": 38.0,
            "severity": "extreme",
            "direction": "溢价(高估)",
        }

        implications = analyzer._derive_implications(gap, factor, valuation)

        assert implications["confidence"] == "low"
        assert implications["confidence_score"] < 0.45
        assert any("CAPM" in reason for reason in implications["confidence_reasons"])
        assert implications["trade_setup"]["stance"] == "关注回归风险"

    def test_implications_confidence_penalizes_factor_valuation_conflict(self):
        """测试二级因子方向与估值结论冲突时降低置信度"""
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        factor = {
            "data_points": 140,
            "capm": {"alpha_pct": 6.4, "data_points": 140},
            "fama_french": {"alpha_pct": 5.2, "data_points": 140},
        }
        valuation = {
            "current_price_source": "live",
            "fair_value": {"mid": 100},
            "dcf": {"intrinsic_value": 92},
            "comparable": {"fair_value": 112},
            "valuation_status": {"status": "overvalued"},
        }
        gap = {
            "gap_pct": 20.0,
            "severity": "high",
            "direction": "溢价(高估)",
        }

        implications = analyzer._derive_implications(gap, factor, valuation)

        assert implications["confidence"] == "medium"
        assert implications["confidence_score"] < 0.72
        assert "二级因子表现与估值结论方向不一致" in implications["confidence_reasons"]
        assert any(item["key"] == "factor_alignment" and item["delta"] < 0 for item in implications["confidence_breakdown"])
        assert implications["factor_alignment"]["status"] == "conflict"
        assert implications["factor_alignment"]["label"] == "冲突"

    def test_deviation_drivers_are_ranked_by_signal_strength(self):
        """测试主驱动按影响强度排序，而不是按拼接顺序返回"""
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        factor = {
            "capm": {
                "alpha_pct": 6.0,
                "beta": 1.35,
            },
            "fama_french": {
                "factor_loadings": {
                    "size": 0.35,
                    "value": -0.32,
                }
            },
        }
        valuation = {
            "comparable": {
                "methods": [
                    {
                        "method": "P/B 倍数法",
                        "current_multiple": 4.8,
                        "benchmark_multiple": 2.4,
                    }
                ]
            }
        }

        drivers = analyzer._analyze_deviation_drivers(factor, valuation)

        assert drivers["primary_driver"]["factor"] == "P/B 倍数法溢价"
        assert drivers["drivers"][0]["factor"] == "P/B 倍数法溢价"
        assert drivers["drivers"][1]["factor"] == "Alpha 超额收益"
        assert drivers["primary_driver"]["signal_strength"] > drivers["drivers"][1]["signal_strength"]
        assert drivers["primary_driver"]["ranking_reason"] == "相对行业基准的估值溢价最显著，说明倍数扩张是当前定价偏差的主要来源"

    def test_screening_ranks_symbols_by_gap_confidence_and_alignment(self):
        """测试批量筛选会按机会分排序并跳过失败标的"""
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        fake_results = {
            "AAPL": {
                "symbol": "AAPL",
                "valuation": {"company_name": "Apple", "current_price_source": "live"},
                "gap_analysis": {"current_price": 180, "fair_value_mid": 120, "gap_pct": 50.0, "direction": "溢价(高估)", "severity": "extreme", "severity_label": "极端偏离"},
                "deviation_drivers": {"primary_driver": {"factor": "P/E 倍数法溢价", "ranking_reason": "倍数扩张最显著"}},
                "implications": {"primary_view": "高估", "confidence": "high", "confidence_score": 0.9, "factor_alignment": {"status": "aligned", "label": "同向", "summary": "同向"}},
                "summary": "AAPL ranked first",
            },
            "MSFT": {
                "symbol": "MSFT",
                "valuation": {"company_name": "Microsoft", "current_price_source": "live"},
                "gap_analysis": {"current_price": 300, "fair_value_mid": 250, "gap_pct": 20.0, "direction": "溢价(高估)", "severity": "high", "severity_label": "显著偏离"},
                "deviation_drivers": {"primary_driver": {"factor": "Alpha 超额收益", "ranking_reason": "超额收益最显著"}},
                "implications": {"primary_view": "高估", "confidence": "medium", "confidence_score": 0.55, "factor_alignment": {"status": "conflict", "label": "冲突", "summary": "冲突"}},
                "summary": "MSFT ranked second",
            },
            "FAIL": {
                "symbol": "FAIL",
                "error": "analysis failed",
            },
        }

        with patch.object(PricingGapAnalyzer, "analyze", side_effect=lambda symbol, period: fake_results[symbol]):
            result = analyzer.screen(["AAPL", "MSFT", "AAPL", "FAIL"], period="1y", limit=5)

        assert result["total_input"] == 3
        assert result["analyzed_count"] == 2
        assert result["result_count"] == 2
        assert result["results"][0]["symbol"] == "AAPL"
        assert result["results"][0]["rank"] == 1
        assert result["results"][0]["screening_score"] > result["results"][1]["screening_score"]
        assert result["results"][1]["symbol"] == "MSFT"
        assert result["failures"] == [{"symbol": "FAIL", "error": "analysis failed"}]

    def test_peer_comparison_prefers_same_industry_and_similar_size(self):
        """测试同行对比优先选同细分行业且体量更接近的标的"""
        from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

        analyzer = PricingGapAnalyzer()
        fundamentals_map = {
            "AAPL": {
                "symbol": "AAPL",
                "company_name": "Apple",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "market_cap": 3000,
                "pe_ratio": 28,
                "price_to_sales": 7.5,
            },
            "MSFT": {
                "symbol": "MSFT",
                "company_name": "Microsoft",
                "sector": "Technology",
                "industry": "Software",
                "market_cap": 3100,
                "pe_ratio": 34,
                "price_to_sales": 12.0,
            },
            "SONY": {
                "symbol": "SONY",
                "company_name": "Sony",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "market_cap": 120,
                "pe_ratio": 19,
                "price_to_sales": 1.8,
            },
            "DELL": {
                "symbol": "DELL",
                "company_name": "Dell",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "market_cap": 90,
                "pe_ratio": 17,
                "price_to_sales": 0.9,
            },
            "XOM": {
                "symbol": "XOM",
                "company_name": "Exxon Mobil",
                "sector": "Energy",
                "industry": "Oil & Gas",
                "market_cap": 420,
                "pe_ratio": 13,
                "price_to_sales": 1.3,
            },
        }
        valuation_map = {
            symbol: {
                "current_price": 100 + index * 10,
                "fair_value": {"mid": 110 + index * 10},
            }
            for index, symbol in enumerate(fundamentals_map.keys())
        }

        analyzer.valuation_model.data_manager.get_fundamental_data = MagicMock(side_effect=lambda symbol: fundamentals_map.get(symbol, {"error": "missing"}))
        analyzer.valuation_model.analyze = MagicMock(side_effect=lambda symbol: valuation_map[symbol])

        result = analyzer.build_peer_comparison("AAPL", ["MSFT", "SONY", "DELL", "XOM"], limit=3)

        assert result["target"]["symbol"] == "AAPL"
        assert result["peers"][0]["symbol"] in {"SONY", "DELL"}
        assert all(item["symbol"] != "XOM" for item in result["peers"])
        assert result["summary"]["same_industry_count"] >= 2
        assert result["candidate_count"] == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
