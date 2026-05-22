"""Tests for the externalised ETF rotation strategy config loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.strategy.etf_rotation_config_loader import (
    CONFIG_PATH_ENV,
    DEFAULT_ORDER_PRICING_PARAMS,
    DEFAULT_RISK_RULES,
    DEFAULT_STRATEGY_PARAMS,
    DEFAULT_UNIVERSE,
    StrategyConfig,
    load_strategy_config,
)


def test_load_strategy_config_returns_built_in_defaults_when_no_file(monkeypatch) -> None:
    monkeypatch.delenv(CONFIG_PATH_ENV, raising=False)
    monkeypatch.setattr(
        "src.strategy.etf_rotation_config_loader.DEFAULT_CONFIG_PATH",
        Path("/nonexistent/strategy.json"),
    )

    cfg = load_strategy_config()
    assert isinstance(cfg, StrategyConfig)
    assert cfg.source_path is None
    assert [a["code"] for a in cfg.universe] == [a["code"] for a in DEFAULT_UNIVERSE]
    assert cfg.risk_rules["min_cash_weight"] == DEFAULT_RISK_RULES["min_cash_weight"]
    assert cfg.strategy["scoring_mode"] == DEFAULT_STRATEGY_PARAMS["scoring_mode"]
    assert cfg.order_pricing["tick_size"] == DEFAULT_ORDER_PRICING_PARAMS["tick_size"]
    assert (
        cfg.order_pricing["default_recommendation"]
        == DEFAULT_ORDER_PRICING_PARAMS["default_recommendation"]
    )


def test_load_strategy_config_overrides_only_specified_fields(tmp_path) -> None:
    payload = {
        "_comment": "tweak only one risk rule",
        "risk_rules": {"min_cash_weight": 0.15},
        "strategy": {"scoring_mode": "cross_sectional"},
    }
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps(payload))

    cfg = load_strategy_config(path)
    assert cfg.risk_rules["min_cash_weight"] == 0.15
    # The other risk fields fall back to defaults.
    assert (
        cfg.risk_rules["commodity_resource_bucket_cap"]
        == DEFAULT_RISK_RULES["commodity_resource_bucket_cap"]
    )
    # Universe unchanged.
    assert len(cfg.universe) == len(DEFAULT_UNIVERSE)
    assert cfg.strategy["scoring_mode"] == "cross_sectional"


def test_load_strategy_config_appends_new_universe_entry(tmp_path) -> None:
    payload = {
        "universe": [
            {
                "code": "511260", "name": "10年国债ETF", "exchange": "sh",
                "category": "rates_hedge",
                "max_weight": 0.20, "base_weight": 0.10,
                "risk_metadata": {"bucket": "fixed_income"},
            },
        ]
    }
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps(payload))

    cfg = load_strategy_config(path)
    codes = [a["code"] for a in cfg.universe]
    # Existing 5 ETFs preserved, new sleeve appended.
    assert codes[:5] == [a["code"] for a in DEFAULT_UNIVERSE]
    assert codes[-1] == "511260"
    asset = cfg.asset_lookup()["511260"]
    assert asset["max_weight"] == 0.20


def test_load_strategy_config_overrides_existing_universe_entry(tmp_path) -> None:
    payload = {
        "universe": [
            {"code": "510300", "max_weight": 0.50},
        ]
    }
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps(payload))

    cfg = load_strategy_config(path)
    asset = cfg.asset_lookup()["510300"]
    # max_weight overridden, name/exchange preserved from defaults.
    assert asset["max_weight"] == 0.50
    assert asset["name"] == "沪深300ETF华泰柏瑞"


def test_load_strategy_config_uses_env_var(tmp_path, monkeypatch) -> None:
    path = tmp_path / "from-env.json"
    # Raise both ends of the score ramp together — bumping only
    # min_score_to_hold above the default min_score_full_hold (35) would
    # be an inverted, incoherent ramp.
    path.write_text(json.dumps({
        "strategy": {"min_score_to_hold": 40.0, "min_score_full_hold": 50.0},
    }))
    monkeypatch.setenv(CONFIG_PATH_ENV, str(path))

    cfg = load_strategy_config()
    assert cfg.strategy["min_score_to_hold"] == 40.0
    assert cfg.source_path == path


def test_load_strategy_config_warns_and_falls_back_when_env_path_missing(monkeypatch) -> None:
    monkeypatch.setenv(CONFIG_PATH_ENV, "/path/that/does/not/exist.json")
    monkeypatch.setattr(
        "src.strategy.etf_rotation_config_loader.DEFAULT_CONFIG_PATH",
        Path("/another/nonexistent.json"),
    )

    cfg = load_strategy_config()
    assert cfg.source_path is None
    assert cfg.universe  # built-in defaults preserved


def test_asset_metadata_includes_cash_entry(tmp_path) -> None:
    cfg = load_strategy_config()
    metadata = cfg.asset_metadata()
    assert "CASH" in metadata
    assert metadata["CASH"]["category"] == "cash"
    # Existing universe risk_metadata flows through.
    assert metadata["518680"]["bucket"] == "commodity"


def test_load_strategy_config_recovers_from_malformed_json(tmp_path) -> None:
    bad = tmp_path / "broken.json"
    bad.write_text("{not valid json")
    cfg = load_strategy_config(bad)
    # Defaults preserved; source_path becomes None to signal failure.
    assert cfg.source_path is None
    assert len(cfg.universe) == len(DEFAULT_UNIVERSE)


def test_load_strategy_config_strips_comment_keys(tmp_path) -> None:
    """Top-level ``_comment`` etc. must not be treated as sections."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "_comment": "ignore this",
        "_load_order": "also ignored",
        "strategy": {"gross_cap": 0.85},
    }))

    cfg = load_strategy_config(path)
    assert cfg.strategy["gross_cap"] == 0.85


def test_load_strategy_config_ignores_non_mapping_order_pricing(tmp_path) -> None:
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({"order_pricing": "not-an-object"}))

    cfg = load_strategy_config(path)

    assert cfg.order_pricing == DEFAULT_ORDER_PRICING_PARAMS


def test_load_strategy_config_merges_order_pricing_overrides(tmp_path) -> None:
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "order_pricing": {
            "tick_size": 0.01,
            "default_recommendation": "aggressive",
            "preferred_windows": ["10:15-10:45"],
        },
    }))

    cfg = load_strategy_config(path)

    assert cfg.order_pricing["tick_size"] == 0.01
    assert cfg.order_pricing["default_recommendation"] == "aggressive"
    assert cfg.order_pricing["preferred_windows"] == ["10:15-10:45"]
    # Fields not mentioned by the user still fall back to built-ins.
    assert (
        cfg.order_pricing["batch_breakpoint_shares"]
        == DEFAULT_ORDER_PRICING_PARAMS["batch_breakpoint_shares"]
    )


def test_load_strategy_config_parses_manual_overrides(tmp_path) -> None:
    """Whitelisted keys + price coercion + comment-key stripping."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "manual_overrides": {
            "_comment": "ignored",  # top-level comment key inside the section
            "512400": {
                "invalidation_price": "1.975",  # string coerces to float
                "thesis": "底部+石油抽走流动性",
                "set_at": "2026-05-18",
                "note": "extra context",
                "unsupported_field": "should be dropped",  # silently ignored
            },
            "513130": {
                "invalidation_price": 0.60,
                "thesis": "0.6 技术支撑",
            },
            "518680": {
                # No invalidation_price → still kept because thesis is set.
                "thesis": "$4500 spot 黄金承接",
            },
            "BADCODE": {
                # No valid normalised fields → entry is dropped entirely.
                "invalidation_price": "not-a-number",
                "thesis": "",
            },
        },
    }))

    cfg = load_strategy_config(path)

    assert "_comment" not in cfg.manual_overrides
    assert cfg.manual_overrides["512400"] == {
        "invalidation_price": 1.975,
        "thesis": "底部+石油抽走流动性",
        "set_at": "2026-05-18",
        "note": "extra context",
    }
    assert cfg.manual_overrides["513130"] == {
        "invalidation_price": 0.60,
        "thesis": "0.6 技术支撑",
    }
    assert cfg.manual_overrides["518680"] == {
        "thesis": "$4500 spot 黄金承接",
    }
    assert "BADCODE" not in cfg.manual_overrides


def test_load_strategy_config_manual_overrides_default_empty(tmp_path) -> None:
    """No manual_overrides section → empty dict, never None."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({"strategy": {"rebalance_threshold": 0.20}}))

    cfg = load_strategy_config(path)

    assert cfg.manual_overrides == {}


def test_load_strategy_config_ignores_non_mapping_manual_overrides(tmp_path) -> None:
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({"manual_overrides": "not-an-object"}))

    cfg = load_strategy_config(path)

    assert cfg.manual_overrides == {}


def test_load_strategy_config_rejects_negative_invalidation_price(tmp_path) -> None:
    """Negative/zero prices silently dropped (the entry is still kept if it
    has thesis text — just without the broken price)."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "manual_overrides": {
            "510300": {"invalidation_price": -1.0, "thesis": "test"},
            "159985": {"invalidation_price": 0.0, "thesis": "zero"},
        },
    }))

    cfg = load_strategy_config(path)

    assert cfg.manual_overrides["510300"] == {"thesis": "test"}
    assert cfg.manual_overrides["159985"] == {"thesis": "zero"}


# ---------------------------------------------------------------------------
# Numeric / safety validation at the load chokepoint
#
# A real-money config must fail fast at load time, not deep inside the
# strategy. These cover weights/caps that must be fractions in [0, 1], a
# negative cash floor, non-numeric where numeric is expected, and a
# protective stop-loss accidentally set to a non-negative value (which
# would silently disable the stop).
# ---------------------------------------------------------------------------


def test_load_strategy_config_rejects_max_weight_above_one(tmp_path) -> None:
    """A per-ETF ``max_weight`` of 3.5 is nonsense — fractions are [0, 1]."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "universe": [{"code": "510300", "max_weight": 3.5}],
    }))

    with pytest.raises(ValueError, match="max_weight"):
        load_strategy_config(path)


def test_load_strategy_config_rejects_negative_base_weight(tmp_path) -> None:
    """A negative ``base_weight`` cannot be a valid fraction."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "universe": [{"code": "510300", "base_weight": -0.1}],
    }))

    with pytest.raises(ValueError, match="base_weight"):
        load_strategy_config(path)


def test_load_strategy_config_rejects_negative_min_cash_weight(tmp_path) -> None:
    """A negative cash floor would let the portfolio go fully invested
    while *claiming* to keep a cash buffer — reject it loudly."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "risk_rules": {"min_cash_weight": -0.05},
    }))

    with pytest.raises(ValueError, match="min_cash_weight"):
        load_strategy_config(path)


def test_load_strategy_config_rejects_risk_cap_above_one(tmp_path) -> None:
    """``max_single_weight`` is a fraction — 1.5 is out of range."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "risk_rules": {"max_single_weight": 1.5},
    }))

    with pytest.raises(ValueError, match="max_single_weight"):
        load_strategy_config(path)


def test_load_strategy_config_rejects_string_typed_risk_cap(tmp_path) -> None:
    """A string where a numeric cap is expected must fail fast."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "risk_rules": {"commodity_resource_bucket_cap": "lots"},
    }))

    with pytest.raises(ValueError, match="commodity_resource_bucket_cap"):
        load_strategy_config(path)


def test_load_strategy_config_rejects_positive_stop_loss_threshold(tmp_path) -> None:
    """``stop_loss_threshold`` is the *negative* loss bound. A positive
    value silently disables the protective stop — reject it so the
    operator can't ship a real-money config with no downside stop."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "strategy": {"stop_loss_threshold": 0.15},
    }))

    with pytest.raises(ValueError, match="stop_loss_threshold"):
        load_strategy_config(path)


def test_load_strategy_config_allows_null_stop_loss_threshold(tmp_path) -> None:
    """An explicit ``null`` disables the stop intentionally — that is a
    deliberate, documented choice and must NOT raise."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "strategy": {"stop_loss_threshold": None},
    }))

    cfg = load_strategy_config(path)
    assert cfg.strategy["stop_loss_threshold"] is None


def test_load_strategy_config_rejects_gross_cap_above_one(tmp_path) -> None:
    """``gross_cap`` is a fraction in (0, 1]."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "strategy": {"gross_cap": 1.4},
    }))

    with pytest.raises(ValueError, match="gross_cap"):
        load_strategy_config(path)


def test_load_strategy_config_rejects_score_ramp_inverted(tmp_path) -> None:
    """``min_score_full_hold`` below ``min_score_to_hold`` is incoherent."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "strategy": {"min_score_to_hold": 40.0, "min_score_full_hold": 20.0},
    }))

    with pytest.raises(ValueError, match="min_score"):
        load_strategy_config(path)


def test_load_strategy_config_rejects_negative_warmup_days(tmp_path) -> None:
    """``warmup_days`` must be a positive integer."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "strategy": {"warmup_days": -10},
    }))

    with pytest.raises(ValueError, match="warmup_days"):
        load_strategy_config(path)


def test_load_strategy_config_rejects_negative_premium_veto(tmp_path) -> None:
    """Premium veto thresholds are non-negative fractions."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "risk_rules": {"hard_premium_veto": -0.05},
    }))

    with pytest.raises(ValueError, match="hard_premium_veto"):
        load_strategy_config(path)


def test_load_strategy_config_accepts_valid_full_override(tmp_path) -> None:
    """A complete, well-formed override must load without complaint —
    validation rejects bad values, not legitimate tuning."""

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "universe": [{"code": "510300", "max_weight": 0.45, "base_weight": 0.30}],
        "risk_rules": {
            "max_single_weight": 0.40,
            "min_cash_weight": 0.05,
            "commodity_resource_bucket_cap": 0.60,
            "hard_premium_veto": 0.06,
        },
        "strategy": {
            "gross_cap": 0.95,
            "warmup_days": 90,
            "min_score_to_hold": 20.0,
            "min_score_full_hold": 45.0,
            "stop_loss_threshold": -0.12,
        },
    }))

    cfg = load_strategy_config(path)
    assert cfg.asset_lookup()["510300"]["max_weight"] == 0.45
    assert cfg.risk_rules["min_cash_weight"] == 0.05
    assert cfg.strategy["stop_loss_threshold"] == -0.12


def test_load_strategy_config_default_config_is_valid() -> None:
    """The built-in defaults must themselves pass validation."""

    cfg = load_strategy_config()
    assert isinstance(cfg, StrategyConfig)
    # A second sanity check: defaults round-trip the validator unchanged.
    assert cfg.strategy["stop_loss_threshold"] == DEFAULT_STRATEGY_PARAMS[
        "stop_loss_threshold"
    ]


def test_etf_asset_config_post_init_rejects_bad_max_weight() -> None:
    """The dataclass itself guards bounds — defence in depth below the
    loader chokepoint."""

    from src.strategy.etf_rotation_strategy import EtfAssetConfig

    with pytest.raises(ValueError, match="max_weight"):
        EtfAssetConfig(symbol="X", max_weight=2.0)


def test_etf_asset_config_post_init_rejects_negative_min_weight() -> None:
    from src.strategy.etf_rotation_strategy import EtfAssetConfig

    with pytest.raises(ValueError, match="min_weight"):
        EtfAssetConfig(symbol="X", min_weight=-0.1)


def test_etf_risk_rule_config_post_init_rejects_negative_cash_floor() -> None:
    from src.risk.etf_portfolio_rules import EtfRiskRuleConfig

    with pytest.raises(ValueError, match="min_cash_weight"):
        EtfRiskRuleConfig(min_cash_weight=-0.10)


def test_etf_risk_rule_config_post_init_rejects_cap_above_one() -> None:
    from src.risk.etf_portfolio_rules import EtfRiskRuleConfig

    with pytest.raises(ValueError, match="max_single_weight"):
        EtfRiskRuleConfig(max_single_weight=1.5)
