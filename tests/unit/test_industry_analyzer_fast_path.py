
import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.analytics.industry_analyzer import IndustryAnalyzer

class TestIndustryAnalyzerFastPath:
    
    @pytest.fixture
    def mock_provider(self):
        provider = Mock()
        
        # Mock money flow data (Fast Path source)
        provider.get_industry_money_flow.return_value = pd.DataFrame([
            {
                "industry_name": "Tech",
                "change_pct": 5.0,
                "flow_strength": 0.8,
                "main_net_inflow": 1000000,
                "volume": 10000,
                "amount": 500000,
                "turnover_rate": 3.0,
            },
            {
                "industry_name": "Finance",
                "change_pct": -2.0,
                "flow_strength": -0.3,
                "main_net_inflow": -500000,
                "volume": 8000,
                "amount": 400000,
                "turnover_rate": 8.0,
            }
        ])
        provider.get_industry_classification.return_value = pd.DataFrame([
            {"industry_name": "Tech", "industry_code": "801001"},
            {"industry_name": "Finance", "industry_code": "801002"},
        ])

        def _mock_industry_index(code, start_date=None, end_date=None):
            if code == "801001":
                closes = [100, 101, 102, 103, 104]
            else:
                closes = [100, 104, 98, 105, 97]
            dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
            return pd.DataFrame({"close": closes}, index=dates)

        provider.get_industry_index.side_effect = _mock_industry_index
        
        return provider

    @pytest.fixture
    def analyzer(self, mock_provider):
        return IndustryAnalyzer(mock_provider)

    def test_calculate_industry_momentum_uses_fast_path(self, analyzer, mock_provider):
        """Test that momentum calculation uses fast path and avoids N+1 queries"""
        
        # Call calculate_industry_momentum
        df = analyzer.calculate_industry_momentum()
        
        # Verify result is not empty
        assert not df.empty
        assert len(df) == 2
        assert "momentum_score" in df.columns
        assert "weighted_change" in df.columns
        assert "industry_volatility" in df.columns
        
        # Verify values match aggregated data
        tech_row = df[df["industry_name"] == "Tech"].iloc[0]
        assert tech_row["weighted_change"] == 5.0
        assert tech_row["total_market_cap"] > 0 # Should be estimated
        assert tech_row["industry_volatility"] > 0
        
        # CRITICAL: Verify get_stock_list_by_industry was NOT called
        mock_provider.get_stock_list_by_industry.assert_not_called()
        
        # Verify get_industry_money_flow WAS called
        mock_provider.get_industry_money_flow.assert_called_with(days=20)

    def test_calculate_industry_historical_volatility_from_index_history(self, analyzer):
        """Historical volatility should be derived from industry index close series when available."""
        result = analyzer.calculate_industry_historical_volatility(lookback=4)

        assert not result.empty
        by_name = {row["industry_name"]: row["industry_volatility"] for row in result.to_dict(orient="records")}
        assert "Tech" in by_name
        assert "Finance" in by_name
        assert by_name["Finance"] > by_name["Tech"]

    def test_fast_path_prefers_historical_volatility_over_proxy(self, analyzer):
        """Fast path should use real historical volatility when index history exists."""
        df = analyzer.calculate_industry_momentum(lookback=4)
        historical_vol = analyzer.calculate_industry_historical_volatility(lookback=4)
        hist_by_name = {row["industry_name"]: row["industry_volatility"] for row in historical_vol.to_dict(orient="records")}

        tech_row = df[df["industry_name"] == "Tech"].iloc[0]
        finance_row = df[df["industry_name"] == "Finance"].iloc[0]

        assert tech_row["industry_volatility"] == pytest.approx(hist_by_name["Tech"], rel=0.001)
        assert finance_row["industry_volatility"] == pytest.approx(hist_by_name["Finance"], rel=0.001)
        assert finance_row["industry_volatility"] > tech_row["industry_volatility"]

    def test_calculate_industry_momentum_fallback(self, analyzer, mock_provider):
        """Test fallback to slow path if fast path fails or returns empty"""
        
        # Setup mock to fail fast path
        mock_provider.get_industry_money_flow.return_value = pd.DataFrame() # Empty
        
        # Mock Sina fallback to also return empty (we're testing slow path fallback)
        analyzer._try_sina_fallback = lambda days: pd.DataFrame()
        
        # Setup mock for slow path
        mock_provider.get_industry_classification.return_value = pd.DataFrame([
            {"industry_name": "Tech", "industry_code": "001"}
        ])
        
        mock_provider.get_stock_list_by_industry.return_value = [
            {"name": "s1", "change_pct": 3.0, "market_cap": 100, "volume": 10}
        ]
        
        # Call
        df = analyzer.calculate_industry_momentum()
        
        # Verify results
        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["industry_name"] == "Tech"
        
        # Verify slow path methods WERE called
        mock_provider.get_industry_classification.assert_called()
        mock_provider.get_stock_list_by_industry.assert_called_with("Tech")

    def test_rank_score_penalizes_high_volatility_when_other_factors_match(self, analyzer):
        """High volatility should be penalized when momentum/flow/volume are otherwise equal."""
        df = pd.DataFrame([
            {
                "industry_name": "Stable",
                "change_pct": 3.0,
                "flow_strength": 0.5,
                "avg_volume": 1000,
                "industry_volatility": 2.0,
            },
            {
                "industry_name": "Volatile",
                "change_pct": 3.0,
                "flow_strength": 0.5,
                "avg_volume": 1000,
                "industry_volatility": 10.0,
            },
        ])

        scores = analyzer._calculate_rank_score_series(df)

        assert scores.iloc[0] > scores.iloc[1]
        assert scores.iloc[0] == pytest.approx(95.0, rel=0.001)
        assert scores.iloc[1] == pytest.approx(20.0, rel=0.001)
