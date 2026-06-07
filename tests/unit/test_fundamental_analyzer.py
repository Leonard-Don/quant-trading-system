"""Unit tests for src.analytics.fundamental_analyzer.

The scoring helpers (_assess_valuation / _assess_financial_health /
_assess_growth / _generate_summary) are pure functions of a metrics dict, so
they need no I/O. The public ``analyze`` method is exercised with a fake
provider injected through the DataManager — no network.
"""

from unittest.mock import MagicMock

import pytest

from src.analytics.fundamental_analyzer import FundamentalAnalyzer


def _make_analyzer_with_fundamentals(payload):
    """Build an analyzer whose yahoo provider returns ``payload``."""
    provider = MagicMock()
    provider.get_fundamental_data.return_value = payload

    data_manager = MagicMock()
    data_manager.provider_factory.get_provider.return_value = provider

    return FundamentalAnalyzer(data_manager=data_manager)


class TestAssessValuation:
    def test_low_pe_and_peg_is_undervalued(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_valuation(
            {"pe_ratio": 10, "peg_ratio": 0.5, "price_to_book": 1.0}
        )
        # base 50 + 10 (pe<15) + 15 (peg<1) = 75 -> undervalued
        assert out["score"] == 75
        assert out["status"] == "undervalued"
        assert out["pe"] == 10 and out["peg"] == 0.5 and out["pb"] == 1.0

    def test_high_pe_and_peg_drags_score_down(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_valuation({"pe_ratio": 35, "peg_ratio": 3})
        # 50 - 10 (pe>30) - 10 (peg>2) = 30 -> fair_value boundary (score<30 is
        # overvalued; 30 is not < 30)
        assert out["score"] == 30
        assert out["status"] == "fair_value"

    def test_extreme_pe_uses_most_severe_penalty(self):
        # Regression: the ``pe > 50`` branch used to be unreachable because it
        # sat after ``pe > 30``.  A PE of 80 must now take the -20 penalty, not
        # the -10 one that a PE of 31 would take.
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_valuation({"pe_ratio": 80})
        # base 50 - 20 (pe>50) = 30
        assert out["score"] == 30
        # And it must be strictly worse than a merely-high PE of 31.
        moderate = analyzer._assess_valuation({"pe_ratio": 31})
        assert moderate["score"] == 40  # 50 - 10 (pe>30)
        assert out["score"] < moderate["score"]

    def test_missing_metrics_default_neutral(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_valuation({})
        assert out["score"] == 50
        assert out["status"] == "fair_value"


class TestAssessFinancialHealth:
    def test_strong_balance_sheet_is_healthy(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_financial_health(
            {"current_ratio": 2.0, "debt_to_equity": 30, "profit_margin": 0.2}
        )
        # 50 + 10 + 10 + 10 = 80 -> healthy
        assert out["score"] == 80
        assert out["status"] == "healthy"

    def test_weak_balance_sheet(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_financial_health(
            {"current_ratio": 0.8, "debt_to_equity": 150, "profit_margin": -0.05}
        )
        # 50 - 10 - 10 - 10 = 20 -> weak
        assert out["score"] == 20
        assert out["status"] == "weak"

    def test_neutral_defaults_stable(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_financial_health({})
        assert out["status"] == "stable"


class TestAssessGrowth:
    def test_high_growth(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_growth(
            {"revenue_growth": 0.3, "earnings_growth": 0.25}
        )
        # 50 + 15 + 15 = 80 -> high_growth
        assert out["score"] == 80
        assert out["status"] == "high_growth"

    def test_negative_growth_penalized(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_growth(
            {"revenue_growth": -0.1, "earnings_growth": -0.2}
        )
        # 50 - 10 - 10 = 30 -> moderate boundary (slow_growth is score<30)
        assert out["score"] == 30
        assert out["status"] == "moderate"

    def test_moderate_growth(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        out = analyzer._assess_growth(
            {"revenue_growth": 0.12, "earnings_growth": 0.11}
        )
        # 50 + 5 + 5 = 60 -> moderate
        assert out["score"] == 60
        assert out["status"] == "moderate"


class TestGenerateSummary:
    def test_combines_status_phrases(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        summary = analyzer._generate_summary(
            {"status": "undervalued"},
            {"status": "healthy"},
            {"status": "high_growth"},
        )
        assert "估值偏低" in summary
        assert "财务健康" in summary
        assert "高增长" in summary

    def test_empty_when_all_neutral(self):
        analyzer = FundamentalAnalyzer(data_manager=MagicMock())
        summary = analyzer._generate_summary(
            {"status": "fair_value"},
            {"status": "stable"},
            {"status": "moderate"},
        )
        assert summary == "基本面平稳"


class TestAnalyze:
    def test_returns_full_structure_for_good_data(self):
        analyzer = _make_analyzer_with_fundamentals(
            {
                "pe_ratio": 12,
                "peg_ratio": 0.8,
                "current_ratio": 2.0,
                "debt_to_equity": 30,
                "profit_margin": 0.2,
                "revenue_growth": 0.3,
                "earnings_growth": 0.25,
            }
        )
        result = analyzer.analyze("AAPL")
        assert set(result) == {
            "metrics",
            "valuation",
            "financial_health",
            "growth",
            "summary",
        }
        assert result["valuation"]["status"] == "undervalued"
        assert result["financial_health"]["status"] == "healthy"
        assert result["growth"]["status"] == "high_growth"

    def test_provider_error_returns_empty_result(self):
        analyzer = _make_analyzer_with_fundamentals({"error": "rate limited"})
        result = analyzer.analyze("AAPL")
        assert result["valuation"]["status"] == "unknown"
        assert result["summary"] == "暂无基本面数据"

    def test_provider_exception_returns_empty_result(self):
        provider = MagicMock()
        provider.get_fundamental_data.side_effect = RuntimeError("boom")
        data_manager = MagicMock()
        data_manager.provider_factory.get_provider.return_value = provider
        analyzer = FundamentalAnalyzer(data_manager=data_manager)

        result = analyzer.analyze("AAPL")
        assert result["summary"] == "暂无基本面数据"
        assert result["metrics"] == {}


def test_empty_result_shape():
    analyzer = FundamentalAnalyzer(data_manager=MagicMock())
    empty = analyzer._get_empty_result()
    assert empty["valuation"]["score"] == 50
    assert empty["financial_health"]["score"] == 50
    assert empty["growth"]["score"] == 50
