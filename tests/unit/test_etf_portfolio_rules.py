import pytest

from src.risk.etf_portfolio_rules import EtfRiskRuleConfig, apply_etf_portfolio_risk_rules


ETF_METADATA = {
    "518880": {"bucket": "commodity", "category": "gold"},
    "159985": {"bucket": "commodity", "category": "oil"},
    "513130": {"bucket": "qdii", "category": "overseas", "is_qdii": True},
    "510300": {"bucket": "broad_equity", "category": "domestic_equity"},
    "CASH": {"category": "cash"},
}


def test_reduces_combined_commodity_bucket_to_cap():
    decision = apply_etf_portfolio_risk_rules(
        proposed_weights={
            "518880": 0.45,
            "159985": 0.30,
            "510300": 0.15,
            "CASH": 0.10,
        },
        current_weights={},
        asset_metadata=ETF_METADATA,
    )

    commodity_weight = decision.adjusted_weights["518880"] + decision.adjusted_weights["159985"]

    assert commodity_weight <= 0.55 + 1e-9
    assert decision.adjusted_weights["CASH"] == pytest.approx(0.30)
    assert any("Commodity/resource bucket cap" in reason for reason in decision.reasons)


def test_keeps_cash_at_or_above_floor():
    decision = apply_etf_portfolio_risk_rules(
        proposed_weights={
            "510300": 0.95,
            "CASH": 0.05,
        },
        current_weights={},
        asset_metadata=ETF_METADATA,
        config=EtfRiskRuleConfig(max_single_weight=1.0),
    )

    assert decision.adjusted_weights["CASH"] >= 0.10
    assert decision.adjusted_weights["510300"] <= 0.90
    assert any("Cash floor" in reason for reason in decision.reasons)


def test_premium_veto_prevents_increasing_qdii_and_commodity_etfs():
    decision = apply_etf_portfolio_risk_rules(
        proposed_weights={
            "513130": 0.20,
            "159985": 0.25,
            "510300": 0.45,
            "CASH": 0.10,
        },
        current_weights={
            "513130": 0.08,
            "159985": 0.05,
            "510300": 0.77,
            "CASH": 0.10,
        },
        asset_metadata=ETF_METADATA,
        premium_percentages={
            "513130": 0.03,
            "159985": 0.06,
        },
    )

    assert decision.adjusted_weights["513130"] == pytest.approx(0.08)
    assert decision.adjusted_weights["159985"] == pytest.approx(0.05)
    assert any("Premium veto for 513130" in reason for reason in decision.reasons)
    assert any("Premium veto for 159985" in reason for reason in decision.reasons)


def test_drawdown_above_eight_percent_reduces_gross_exposure():
    decision = apply_etf_portfolio_risk_rules(
        proposed_weights={
            "510300": 0.50,
            "518880": 0.20,
            "513130": 0.20,
            "CASH": 0.10,
        },
        current_weights={},
        asset_metadata=ETF_METADATA,
        portfolio_drawdown=0.09,
    )

    gross_exposure = (
        decision.adjusted_weights["510300"]
        + decision.adjusted_weights["518880"]
        + decision.adjusted_weights["513130"]
    )

    assert gross_exposure < 0.90
    assert decision.adjusted_weights["CASH"] > 0.10
    assert any("Drawdown cut" in reason for reason in decision.reasons)
