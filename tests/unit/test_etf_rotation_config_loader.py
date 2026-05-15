"""Tests for the externalised ETF rotation strategy config loader."""

from __future__ import annotations

import json
from pathlib import Path

from src.strategy.etf_rotation_config_loader import (
    CONFIG_PATH_ENV,
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
    path.write_text(json.dumps({"strategy": {"min_score_to_hold": 40.0}}))
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
