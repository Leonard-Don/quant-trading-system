"""Unit tests for src.analytics.comprehensive_scorer.

The scoring/recommendation helpers consume plain dicts (the outputs of the
sub-analyzers), so they are tested directly with hand-built inputs — no network,
no sub-analyzer execution. The public ``comprehensive_analysis`` is exercised
only on its insufficient-data short-circuit, which returns before touching any
analyzer.
"""

import pandas as pd
import pytest

from src.analytics.comprehensive_scorer import ComprehensiveScorer


@pytest.fixture
def scorer():
    return ComprehensiveScorer()


class TestTrendScore:
    def test_strong_bullish_with_strength_and_signal(self, scorer):
        result = {
            "trend": "strong_bullish",
            "trend_strength": 80,
            "signal_strength": {"signal": "strong_buy"},
        }
        # 50 + 30 + 10 + 10 = 100 (capped)
        assert scorer._calculate_trend_score(result) == 100

    def test_strong_bearish_floors_at_zero(self, scorer):
        result = {
            "trend": "strong_bearish",
            "trend_strength": 10,
            "signal_strength": {"signal": "strong_sell"},
        }
        # 50 - 30 - 10 - 10 = 0
        assert scorer._calculate_trend_score(result) == 0

    def test_neutral_defaults_to_base(self, scorer):
        # Empty input: trend="neutral" (no adjustment), strength default 50
        # (neither >50 nor <50), signal default "neutral" => stays at base 50.
        assert scorer._calculate_trend_score({}) == 50

    def test_mild_bullish(self, scorer):
        result = {"trend": "bullish", "trend_strength": 60}
        # 50 + 20 + 5 = 75
        assert scorer._calculate_trend_score(result) == 75


class TestVolumeScore:
    def test_bullish_inflow_accumulation(self, scorer):
        result = {
            "obv_analysis": {"obv_trend": "bullish"},
            "money_flow": {"status": "strong_inflow"},
            "accumulation_distribution": {"ad_trend": "accumulation"},
        }
        # 50 + 20 + 15 + 10 = 95
        assert scorer._calculate_volume_score(result) == 95

    def test_bearish_outflow_distribution(self, scorer):
        result = {
            "obv_analysis": {"obv_trend": "bearish"},
            "money_flow": {"status": "strong_outflow"},
            "accumulation_distribution": {"ad_trend": "distribution"},
        }
        # 50 - 20 - 15 - 10 = 5
        assert scorer._calculate_volume_score(result) == 5

    def test_divergences_adjust_score(self, scorer):
        result = {
            "divergence": {
                "divergences": [
                    {"signal": "bullish"},
                    {"signal": "bearish"},
                ]
            }
        }
        # 50 + 5 - 5 = 50
        assert scorer._calculate_volume_score(result) == 50


class TestSentimentScore:
    def test_uses_fear_greed_index(self, scorer):
        assert scorer._calculate_sentiment_score({"fear_greed_index": 65}) == 65

    def test_very_high_risk_caps_score(self, scorer):
        result = {"fear_greed_index": 80, "risk_level": "very_high"}
        assert scorer._calculate_sentiment_score(result) == 30

    def test_panic_selling_reduces_score(self, scorer):
        result = {
            "fear_greed_index": 40,
            "extreme_sentiment": {
                "has_extreme_sentiment": True,
                "signals": [{"type": "panic_selling"}],
            },
        }
        assert scorer._calculate_sentiment_score(result) == 30


class TestTechnicalScore:
    def test_multi_timeframe_consistency_bonus(self, scorer):
        result = {
            "score": 60,
            "multi_timeframe": {
                "1d": {"trend": "上涨"},
                "1w": {"trend": "上涨"},
                "1m": {"trend": "上涨"},
            },
        }
        # all up => +10 -> 70
        assert scorer._calculate_technical_score(result) == 70

    def test_all_down_penalty(self, scorer):
        result = {
            "score": 60,
            "multi_timeframe": {
                "1d": {"trend": "下跌"},
                "1w": {"trend": "下跌"},
            },
        }
        # consistency_ratio == 0 => -10 -> 50
        assert scorer._calculate_technical_score(result) == 50

    def test_no_multi_timeframe_returns_base_score(self, scorer):
        assert scorer._calculate_technical_score({"score": 55}) == 55


class TestFundamentalScore:
    def test_averages_three_dimensions(self, scorer):
        result = {
            "valuation": {"score": 60},
            "financial_health": {"score": 90},
            "growth": {"score": 30},
        }
        assert scorer._calculate_fundamental_score(result) == pytest.approx(60.0)

    def test_missing_dimensions_default_to_50(self, scorer):
        assert scorer._calculate_fundamental_score({}) == pytest.approx(50.0)


class TestRecommendation:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (80, "强烈买入"),
            (65, "买入"),
            (50, "持有"),
            (35, "卖出"),
            (10, "强烈卖出"),
        ],
    )
    def test_recommendation_thresholds(self, scorer, score, expected):
        assert scorer._generate_recommendation(score, {}, {}, {}) == expected


class TestConfidence:
    def test_high_strength_and_signals_give_high_confidence(self, scorer):
        trend = {
            "trend_strength": 80,
            "signal_strength": {"buy_strength": 80, "sell_strength": 0},
        }
        volume = {"price_volume_correlation": {"correlation": 0.6}}
        # 3 (strength) + 3 (signal) + 2 (corr) = 8 -> very_high
        assert scorer._assess_confidence(trend, volume, {}) == "very_high"

    def test_weak_inputs_give_low_confidence(self, scorer):
        assert scorer._assess_confidence({}, {}, {}) == "low"


class TestKeySignals:
    def test_strong_trend_and_rsi_overbought(self, scorer):
        trend = {"trend": "strong_bullish", "indicators": {"rsi": 75}}
        signals = scorer._summarize_key_signals(trend, {}, {})
        types = {s["type"] for s in signals}
        assert "趋势" in types
        assert "技术" in types

    def test_volume_pattern_emitted(self, scorer):
        volume = {
            "volume_patterns": {
                "patterns": [{"description": "放量上涨"}]
            }
        }
        signals = scorer._summarize_key_signals({}, volume, {})
        assert any(s["signal"] == "放量上涨" for s in signals)


class TestRiskWarnings:
    def test_high_risk_and_extreme_sentiment(self, scorer):
        sentiment = {
            "risk_level": "very_high",
            "extreme_sentiment": {"has_extreme_sentiment": True},
        }
        warnings = scorer._generate_risk_warnings({}, {}, sentiment)
        assert any("风险等级" in w for w in warnings)
        assert any("极端情绪" in w for w in warnings)

    def test_divergence_and_high_volatility(self, scorer):
        trend = {"volatility": {"level": "high"}, "trend_strength": 20}
        volume = {
            "divergence": {"divergences": [{"description": "顶背离"}]}
        }
        warnings = scorer._generate_risk_warnings(trend, volume, {})
        assert any("顶背离" in w for w in warnings)
        assert any("波动率" in w for w in warnings)
        assert any("趋势强度" in w for w in warnings)

    def test_no_warnings_for_calm_market(self, scorer):
        assert scorer._generate_risk_warnings({}, {}, {}) == []


class TestScoreExplanation:
    def test_produces_five_dimensions(self, scorer):
        explanations = scorer._generate_score_explanation(
            70, 60, 55, 50, 65,
            {"trend": "strong_bullish", "trend_strength": 80,
             "indicators": {"rsi": 75, "macd": {"histogram": 1}}},
            {"money_flow": {"status": "strong_inflow"}},
            {"fear_greed_index": 55, "overall_sentiment": "greed"},
        )
        dims = [e["dimension"] for e in explanations]
        assert dims == ["趋势面", "资金面", "情绪面", "技术面", "基本面"]
        # RSI>70 and MACD histogram>0 => both reasons present in technical dim.
        tech = next(e for e in explanations if e["dimension"] == "技术面")
        assert "RSI超买" in tech["reason"]
        assert "MACD金叉" in tech["reason"]

    def test_handles_non_numeric_rsi_gracefully(self, scorer):
        explanations = scorer._generate_score_explanation(
            50, 50, 50, 50, 50,
            {"indicators": {"rsi": "n/a"}},
            {},
            {},
        )
        # Should not raise; technical dimension still present.
        assert any(e["dimension"] == "技术面" for e in explanations)


class TestRecommendationReasons:
    def test_bullish_and_buy_signals(self, scorer):
        trend = {
            "trend": "strong_bullish",
            "signal_strength": {"buy_strength": 70, "sell_strength": 0},
        }
        reasons = scorer._generate_recommendation_reasons(trend, {}, {})
        assert any("上升通道" in r for r in reasons)
        assert any("买入信号" in r for r in reasons)

    def test_fear_sentiment_reason(self, scorer):
        sentiment = {"overall_sentiment": "extreme_fear"}
        reasons = scorer._generate_recommendation_reasons({}, {}, sentiment)
        assert any("超跌反弹" in r for r in reasons)


class TestComprehensiveAnalysisShortCircuit:
    def test_insufficient_data_returns_watch_recommendation(self, scorer):
        df = pd.DataFrame({"close": [1, 2, 3]})  # < 50 rows
        result = scorer.comprehensive_analysis(df, symbol="TEST")
        assert result["overall_score"] == 50
        assert result["recommendation"] == "观望"
        assert result["confidence"] == "low"
        assert "error" in result

    def test_empty_dataframe_short_circuits(self, scorer):
        result = scorer.comprehensive_analysis(pd.DataFrame(), symbol="TEST")
        assert result["recommendation"] == "观望"
        assert "error" in result
