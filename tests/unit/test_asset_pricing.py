"""
资产定价模块单元测试
测试 CAPM、FF3、DCF、可比估值和定价差异分析
"""

import pytest
import numpy as np
import pandas as pd
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
    @patch("src.data.data_manager.DataManager.get_historical_data")
    def test_capm_analysis(self, mock_get_data, mock_ff):
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

        engine = AssetPricingEngine()
        result = engine.analyze("TEST", "1y")

        # 验证结构
        assert "capm" in result
        assert "fama_french" in result
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
    @patch("src.data.data_manager.DataManager.get_historical_data")
    def test_ff3_factor_loadings(self, mock_get_data, mock_ff):
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

        engine = AssetPricingEngine()
        result = engine.analyze("TEST", "1y")
        ff3 = result["fama_french"]

        assert "error" not in ff3, f"FF3 出错: {ff3.get('error')}"
        assert "factor_loadings" in ff3
        loadings = ff3["factor_loadings"]
        assert "market" in loadings
        assert "size" in loadings
        assert "value" in loadings
        assert "r_squared" in ff3

    @patch("src.data.data_manager.DataManager.get_historical_data")
    def test_insufficient_data(self, mock_get_data):
        """测试数据不足时的处理"""
        from src.analytics.asset_pricing import AssetPricingEngine

        mock_get_data.return_value = pd.DataFrame()

        engine = AssetPricingEngine()
        result = engine.analyze("INVALID", "1y")

        assert "capm" in result
        assert "error" in result["capm"]


class TestValuationModel:
    """测试内在价值估值模型"""

    def _mock_fundamentals(self):
        return {
            "symbol": "TEST",
            "company_name": "Test Corp",
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 1e12,
            "pe_ratio": 25,
            "forward_pe": 22,
            "peg_ratio": 1.5,
            "price_to_book": 8,
            "dividend_yield": 0.005,
            "profit_margin": 0.25,
            "operating_margin": 0.30,
            "roe": 0.35,
            "roa": 0.15,
            "revenue_growth": 0.12,
            "earnings_growth": 0.15,
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
        assert "implications" in result
        assert "summary" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
