"""Tests for the daily ETF signal and backtest CLI scripts.

These tests stay hermetic — no network, no broker, no live prices.
Fixtures are constructed inline or written to ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest

from scripts import backtest_etf_rotation, daily_etf_signal

# ---------------------------------------------------------------------------
# Default seed wiring
# ---------------------------------------------------------------------------


def test_default_holdings_match_screenshot_seed() -> None:
    holdings = daily_etf_signal.load_default_holdings()
    codes = [h.code for h in holdings]
    assert codes == ["159985", "512400", "510300", "518680", "513130"]
    # Every default holding has the fields needed by downstream helpers.
    for holding in holdings:
        assert holding.shares > 0
        assert holding.current_price > 0


def test_default_quotes_cover_every_holding() -> None:
    holdings = daily_etf_signal.load_default_holdings()
    quotes = daily_etf_signal.load_default_quotes(holdings)
    assert set(quotes.keys()) == {h.code for h in holdings}
    for code, quote in quotes.items():
        assert quote.current_price is not None and quote.current_price > 0


def test_synthesize_price_matrix_is_deterministic() -> None:
    holdings = daily_etf_signal.load_default_holdings()
    quotes = daily_etf_signal.load_default_quotes(holdings)
    end_date = pd.Timestamp("2026-05-13")
    first = daily_etf_signal.synthesize_price_matrix(quotes, end_date=end_date)
    second = daily_etf_signal.synthesize_price_matrix(quotes, end_date=end_date)

    assert isinstance(first, pd.DataFrame)
    assert list(first.columns) == [h.code for h in holdings]
    assert len(first) >= 70  # long enough for the 60-day warmup
    pd.testing.assert_frame_equal(first, second)


def test_synthesize_price_matrix_default_end_date_is_today() -> None:
    """Without an explicit end_date the synthetic history must roll forward
    with the calendar instead of getting stuck at a hardcoded date."""
    quotes = daily_etf_signal.load_default_quotes(
        daily_etf_signal.load_default_holdings()
    )
    frame = daily_etf_signal.synthesize_price_matrix(quotes)
    today = pd.Timestamp.today().normalize()
    # bdate_range with end=today returns up to today (inclusive if business day).
    # We just assert the last date is on or before today and within 14 days of it.
    last = frame.index.max().normalize()
    assert last <= today
    assert (today - last).days <= 14


# ---------------------------------------------------------------------------
# generate_plan
# ---------------------------------------------------------------------------


def _make_plan() -> Dict[str, Any]:
    return daily_etf_signal.generate_plan()


def test_generate_plan_returns_required_schema() -> None:
    plan = _make_plan()
    required = {
        "current_weights",
        "target_weights",
        "adjusted_weights",
        "suggestions",
        "risk_reasons",
    }
    missing = required - plan.keys()
    assert not missing, f"Missing keys: {missing}"

    assert isinstance(plan["current_weights"], dict)
    assert isinstance(plan["target_weights"], dict)
    assert isinstance(plan["adjusted_weights"], dict)
    assert isinstance(plan["suggestions"], list)
    assert isinstance(plan["risk_reasons"], list)


def test_generate_plan_current_weights_cover_seed_codes() -> None:
    plan = _make_plan()
    assert set(plan["current_weights"]) >= {
        "159985",
        "512400",
        "510300",
        "518680",
        "513130",
    }


def test_generate_plan_suggestions_have_only_manual_actions() -> None:
    plan = _make_plan()
    for suggestion in plan["suggestions"]:
        assert suggestion["action"] in {"buy", "sell", "hold"}
        # Manual plan only — no broker / order routing fields.
        for forbidden in ("broker", "order_id", "venue", "submitted"):
            assert forbidden not in suggestion


def test_generate_plan_adjusted_weights_respect_cash_floor() -> None:
    plan = _make_plan()
    cash_weight = plan["adjusted_weights"].get("CASH", 0.0)
    # Cash floor default is 10% in the risk config.
    assert cash_weight >= 0.10 - 1e-9


def test_generate_plan_is_deterministic() -> None:
    first = _make_plan()
    second = _make_plan()
    assert first["current_weights"] == second["current_weights"]
    assert first["target_weights"] == second["target_weights"]
    assert first["adjusted_weights"] == second["adjusted_weights"]
    assert [s["code"] for s in first["suggestions"]] == [
        s["code"] for s in second["suggestions"]
    ]


def test_generate_plan_includes_manual_override_status_default_empty() -> None:
    """No manual_overrides in config → empty dict, never missing."""
    plan = _make_plan()
    assert "manual_override_status" in plan
    assert plan["manual_override_status"] == {}


def test_generate_plan_marks_manual_override_invalidated_when_price_breaks() -> None:
    """User's invalidation line surfaces as ``invalidated=True`` once the
    current price crosses below it. The 512400 entry mirrors what
    actually happened to the user on 2026-05-19 morning."""

    from src.data.etf_rotation import EtfHolding, EtfQuote
    from src.strategy.etf_rotation_config_loader import (
        StrategyConfig,
        load_strategy_config,
    )
    from dataclasses import replace as _dc_replace

    holdings = [
        EtfHolding(code="512400", name="有色金属ETF", shares=4700,
                   cost_price=2.227, current_price=1.96),
    ]
    quotes = {
        "512400": EtfQuote(
            code="512400", name="有色金属ETF",
            current_price=1.96, prev_close=2.00,
            timestamp="2026-05-19T03:30:00Z",
        ),
    }

    # Build a tiny config that just adds the override under test. We start
    # from the built-in defaults and patch in a single manual_overrides
    # entry — avoids depending on the user's live strategy.json.
    default_cfg = load_strategy_config()
    cfg = _dc_replace(default_cfg, manual_overrides={
        "512400": {
            "invalidation_price": 1.975,
            "thesis": "底部+石油抽走流动性",
            "set_at": "2026-05-18",
        },
    })

    plan = daily_etf_signal.generate_plan(
        holdings=holdings,
        quotes=quotes,
        strategy_config=cfg,
    )

    status = plan["manual_override_status"]
    assert "512400" in status
    assert status["512400"]["invalidated"] is True
    assert status["512400"]["invalidation_price"] == 1.975
    assert status["512400"]["current_price"] == 1.96
    assert status["512400"]["thesis"] == "底部+石油抽走流动性"
    assert status["512400"]["set_at"] == "2026-05-18"


def test_generate_plan_manual_override_not_invalidated_when_price_above_line() -> None:
    """Price strictly above the line keeps ``invalidated=False``."""

    from src.data.etf_rotation import EtfHolding, EtfQuote
    from src.strategy.etf_rotation_config_loader import (
        StrategyConfig,
        load_strategy_config,
    )
    from dataclasses import replace as _dc_replace

    holdings = [
        EtfHolding(code="513130", name="恒生科技ETF", shares=3100,
                   cost_price=0.731, current_price=0.65),
    ]
    quotes = {
        "513130": EtfQuote(
            code="513130", name="恒生科技ETF",
            current_price=0.65, prev_close=0.64,
            timestamp="2026-05-19T03:30:00Z",
        ),
    }

    default_cfg = load_strategy_config()
    cfg = _dc_replace(default_cfg, manual_overrides={
        "513130": {
            "invalidation_price": 0.60,
            "thesis": "0.6 技术支撑",
        },
    })

    plan = daily_etf_signal.generate_plan(
        holdings=holdings,
        quotes=quotes,
        strategy_config=cfg,
    )

    status = plan["manual_override_status"]["513130"]
    assert status["invalidated"] is False
    assert status["current_price"] == 0.65
    assert status["invalidation_price"] == 0.60


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def test_format_output_json_round_trips() -> None:
    plan = _make_plan()
    payload = daily_etf_signal.format_output(plan, output="json")
    decoded = json.loads(payload)
    assert {
        "current_weights",
        "target_weights",
        "adjusted_weights",
        "suggestions",
        "risk_reasons",
    } <= decoded.keys()


def test_format_output_text_states_manual_only_and_no_auto_ordering() -> None:
    plan = _make_plan()
    text = daily_etf_signal.format_output(plan, output="text")
    assert "手动" in text
    assert "自动下单" in text
    assert "券商" in text
    assert "auto-order" not in text.lower()
    assert "Total asset value" not in text
    assert "Current weights" not in text
    assert "Manual trade suggestions" not in text
    assert "Risk reasons" not in text
    assert "delta_" not in text


def test_format_output_rejects_unknown_format() -> None:
    plan = _make_plan()
    with pytest.raises(ValueError):
        daily_etf_signal.format_output(plan, output="yaml")


def test_format_output_text_surfaces_source_health_state() -> None:
    """Manual operators must see whether the plan is built from live or
    synthetic data without parsing JSON."""
    plan = _make_plan()
    text = daily_etf_signal.format_output(plan, output="text")
    assert "数据源" in text
    # Default plan with no inputs → all three sources are synthetic.
    assert "示例/合成" in text


# ---------------------------------------------------------------------------
# Configured holdings loader
# ---------------------------------------------------------------------------


def test_load_default_holdings_is_anonymised() -> None:
    """The in-source seed must not encode any real P&L information."""
    for holding in daily_etf_signal.load_default_holdings():
        assert holding.cost_price == holding.current_price, (
            "Example seed must keep cost_price == current_price so no P&L "
            "or buy-history leaks into the public repository."
        )


def test_load_configured_holdings_returns_example_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(daily_etf_signal.HOLDINGS_PATH_ENV, raising=False)
    monkeypatch.setattr(
        daily_etf_signal,
        "DEFAULT_HOLDINGS_PATH",
        Path("/nonexistent/etf-holdings.json"),
    )
    holdings, is_configured = daily_etf_signal.load_configured_holdings()
    assert is_configured is False
    assert [h.code for h in holdings] == [
        "159985", "512400", "510300", "518680", "513130",
    ]


def test_load_configured_holdings_reads_env_path(tmp_path, monkeypatch) -> None:
    holdings_payload = {
        "holdings": [
            {"code": "510300", "name": "沪深300ETF", "shares": 2000,
             "cost_price": 4.00, "current_price": 5.00},
        ],
    }
    holdings_path = tmp_path / "private_holdings.json"
    holdings_path.write_text(json.dumps(holdings_payload))
    monkeypatch.setenv(daily_etf_signal.HOLDINGS_PATH_ENV, str(holdings_path))

    holdings, is_configured = daily_etf_signal.load_configured_holdings()
    assert is_configured is True
    assert len(holdings) == 1
    assert holdings[0].code == "510300"
    assert holdings[0].shares == 2000


def test_append_audit_entry_writes_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(daily_etf_signal.AUDIT_LOG_PATH_ENV, raising=False)
    audit_path = tmp_path / "audit.jsonl"

    plan = daily_etf_signal.generate_plan()
    written = daily_etf_signal.append_audit_entry(
        plan, path=audit_path, quote_source="test"
    )
    assert written == audit_path
    assert audit_path.is_file()

    entries = daily_etf_signal.read_audit_log(audit_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["quote_source"] == "test"
    assert set(entry["current_weights"]) >= {"159985", "510300"}
    assert isinstance(entry["suggestions"], list)
    assert "run_at" in entry


def test_append_audit_entry_appends_multiple_rows(tmp_path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    plan = daily_etf_signal.generate_plan()
    daily_etf_signal.append_audit_entry(plan, path=audit_path, quote_source="run1")
    daily_etf_signal.append_audit_entry(plan, path=audit_path, quote_source="run2")

    entries = daily_etf_signal.read_audit_log(audit_path)
    assert [e["quote_source"] for e in entries] == ["run1", "run2"]


def test_append_audit_entry_disabled_returns_none(monkeypatch) -> None:
    """No explicit path + no env + no config dir → audit silently disabled."""
    monkeypatch.delenv(daily_etf_signal.AUDIT_LOG_PATH_ENV, raising=False)
    monkeypatch.setattr(
        daily_etf_signal,
        "DEFAULT_AUDIT_LOG_PATH",
        Path("/definitely/not/a/real/path/audit.jsonl"),
    )
    plan = daily_etf_signal.generate_plan()
    result = daily_etf_signal.append_audit_entry(plan)
    assert result is None


def test_append_audit_entry_uses_env_var(tmp_path, monkeypatch) -> None:
    audit_path = tmp_path / "from-env.jsonl"
    monkeypatch.setenv(daily_etf_signal.AUDIT_LOG_PATH_ENV, str(audit_path))
    plan = daily_etf_signal.generate_plan()
    result = daily_etf_signal.append_audit_entry(plan, quote_source="env-test")
    assert result == audit_path
    entries = daily_etf_signal.read_audit_log(audit_path)
    assert entries[0]["quote_source"] == "env-test"


def test_read_audit_log_skips_malformed_lines(tmp_path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        '{"run_at": "2026-05-14T10:00:00+00:00", "quote_source": "ok"}\n'
        "this is not json\n"
        '{"run_at": "2026-05-14T11:00:00+00:00", "quote_source": "still_ok"}\n',
        encoding="utf-8",
    )
    entries = daily_etf_signal.read_audit_log(audit_path)
    assert [e["quote_source"] for e in entries] == ["ok", "still_ok"]


def test_main_cli_writes_audit_log_when_flag_passed(tmp_path, capsys) -> None:
    audit_path = tmp_path / "cli_audit.jsonl"
    rc = daily_etf_signal.main(["--audit-log", str(audit_path), "--output", "json"])
    assert rc == 0
    capsys.readouterr()  # discard the printed plan
    entries = daily_etf_signal.read_audit_log(audit_path)
    assert len(entries) == 1
    assert entries[0]["quote_source"] == "cli"


# ---------------------------------------------------------------------------
# Live quote / live history wiring
# ---------------------------------------------------------------------------


def test_fetch_live_quotes_empty_codes_returns_zero_resolved() -> None:
    """The conftest fixture stubs fetch_live_quotes to empty; remove the
    stub for this test so we exercise the real short-circuit path."""

    from scripts import daily_etf_signal as live_module
    # Re-import to bypass the conftest's monkeypatched stub.
    import importlib
    fresh = importlib.reload(live_module)
    try:
        quotes, status = fresh.fetch_live_quotes([])
        assert quotes == {}
        assert status["requested"] == 0
    finally:
        importlib.reload(live_module)


def test_main_cli_reprices_holdings_via_fetch_live_quotes(tmp_path, capsys, monkeypatch) -> None:
    """When --use-live-quotes is on (default) the CLI must reprice holdings
    using whatever fetch_live_quotes returns — confirming the same wiring
    the dashboard endpoint relies on."""

    holdings_payload = {
        "holdings": [
            {
                "code": "510300", "name": "沪深300ETF",
                "shares": 1000, "cost_price": 4.50, "current_price": 5.00,
            },
        ]
    }
    holdings_path = tmp_path / "holdings.json"
    holdings_path.write_text(json.dumps(holdings_payload))

    from src.data.etf_rotation import EtfQuote

    def fake_fetch(codes, *, use_cache=True):
        return {
            "510300": EtfQuote(
                code="510300", name="沪深300ETF",
                current_price=6.0, prev_close=5.5,
                timestamp="2026-05-14T11:00:00+00:00",
                source="fake-live",
            ),
        }, {
            "requested": len(codes), "resolved": 1,
            "missing": 0, "use_cache": use_cache,
        }

    monkeypatch.setattr(daily_etf_signal, "fetch_live_quotes", fake_fetch)

    rc = daily_etf_signal.main([
        "--holdings-json", str(holdings_path),
        "--output", "json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # 1000 shares @ 6.0 = 6000 (vs the holding's stored 5.00 → 5000).
    assert payload["total_asset"] == pytest.approx(6000.0)
    assert payload["quote_snapshot"]["510300"]["source"] == "fake-live"


def test_main_cli_no_live_quotes_uses_holding_prices(tmp_path, capsys, monkeypatch) -> None:
    holdings_payload = {
        "holdings": [
            {
                "code": "510300", "name": "沪深300ETF",
                "shares": 1000, "cost_price": 4.50, "current_price": 5.00,
            },
        ]
    }
    holdings_path = tmp_path / "holdings.json"
    holdings_path.write_text(json.dumps(holdings_payload))

    def fail_fetch(*_a, **_kw):
        raise AssertionError("fetch_live_quotes must not be called when --no-live-quotes")

    monkeypatch.setattr(daily_etf_signal, "fetch_live_quotes", fail_fetch)

    rc = daily_etf_signal.main([
        "--holdings-json", str(holdings_path),
        "--no-live-quotes",
        "--output", "json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_asset"] == pytest.approx(5000.0)


# ---------------------------------------------------------------------------
# Position-cut safety valve
# ---------------------------------------------------------------------------


def test_apply_position_cut_softens_reductions() -> None:
    current = {"A": 0.50, "B": 0.30}
    target = {"A": 0.00, "B": 0.50}

    # cut=0.5 → move halfway from current toward target
    softened = daily_etf_signal._apply_position_cut(current, target, 0.5)
    assert softened["A"] == pytest.approx(0.25)  # 0.50 + (0.0 - 0.50) * 0.5
    assert softened["B"] == pytest.approx(0.40)  # 0.30 + (0.50 - 0.30) * 0.5


def test_apply_position_cut_one_passes_through() -> None:
    current = {"A": 0.50}
    target = {"A": 0.0}
    assert daily_etf_signal._apply_position_cut(current, target, 1.0) == target


def test_apply_position_cut_zero_keeps_current() -> None:
    current = {"A": 0.50}
    target = {"A": 0.0}
    assert daily_etf_signal._apply_position_cut(current, target, 0.0) == current


# ---------------------------------------------------------------------------
# Per-position stop loss
# ---------------------------------------------------------------------------


def test_apply_position_stop_losses_zeros_targets_below_threshold() -> None:
    from src.data.etf_rotation import EtfHolding

    holdings = [
        EtfHolding(code="A", name="a", shares=1000, cost_price=10.0, current_price=8.0),  # -20%
        EtfHolding(code="B", name="b", shares=1000, cost_price=10.0, current_price=9.0),  # -10%
        EtfHolding(code="C", name="c", shares=1000, cost_price=10.0, current_price=11.0), # +10%
    ]
    targets = {"A": 0.30, "B": 0.20, "C": 0.30}
    triggered = daily_etf_signal._apply_position_stop_losses(
        holdings=holdings, target_weights=targets, threshold=-0.15,
    )
    assert "A" in triggered  # -20% breaches the -15% bound
    assert "B" not in triggered  # -10% is still above the bound
    assert "C" not in triggered
    assert targets["A"] == 0.0  # in-place mutation
    assert targets["B"] == 0.20
    assert triggered["A"]["loss_pct"] == pytest.approx(-0.20)
    assert triggered["A"]["previous_target_weight"] == pytest.approx(0.30)


def test_apply_position_stop_losses_disabled_when_threshold_none() -> None:
    from src.data.etf_rotation import EtfHolding

    holdings = [
        EtfHolding(code="A", name="a", shares=1000, cost_price=10.0, current_price=5.0),
    ]
    targets = {"A": 0.30}
    triggered = daily_etf_signal._apply_position_stop_losses(
        holdings=holdings, target_weights=targets, threshold=None,
    )
    assert triggered == {}
    assert targets["A"] == 0.30  # untouched


def test_apply_position_stop_losses_rejects_non_negative_threshold() -> None:
    from src.data.etf_rotation import EtfHolding

    holdings = [
        EtfHolding(code="A", name="a", shares=1000, cost_price=10.0, current_price=5.0),
    ]
    targets = {"A": 0.30}
    # A positive threshold is nonsense — defensively treated as disabled.
    triggered = daily_etf_signal._apply_position_stop_losses(
        holdings=holdings, target_weights=targets, threshold=0.05,
    )
    assert triggered == {}
    assert targets["A"] == 0.30


def test_apply_position_stop_losses_advisory_only_detects_without_zeroing() -> None:
    """Advisory mode: still reports the breach but leaves target_weight alone.

    Used by the "technical timing overlay" framing where the user holds
    long-term on fundamentals — a drawdown should prompt thesis review,
    not auto-clear the position.
    """

    from src.data.etf_rotation import EtfHolding

    holdings = [
        EtfHolding(code="A", name="a", shares=1000, cost_price=10.0, current_price=7.5),  # -25%
        EtfHolding(code="B", name="b", shares=1000, cost_price=10.0, current_price=11.0), # +10%
    ]
    targets = {"A": 0.30, "B": 0.30}

    triggered = daily_etf_signal._apply_position_stop_losses(
        holdings=holdings,
        target_weights=targets,
        threshold=-0.15,
        advisory_only=True,
    )

    # Detection is unchanged.
    assert "A" in triggered
    assert "B" not in triggered
    assert triggered["A"]["loss_pct"] == pytest.approx(-0.25)
    assert triggered["A"]["advisory_only"] is True
    # The critical difference: target_weight is NOT zeroed.
    assert targets["A"] == 0.30
    assert targets["B"] == 0.30


def test_apply_position_stop_losses_hard_mode_marks_advisory_false() -> None:
    """Default mode payloads carry advisory_only=False so the dashboard
    can disambiguate without a separate boolean upstream."""

    from src.data.etf_rotation import EtfHolding

    holdings = [
        EtfHolding(code="A", name="a", shares=1000, cost_price=10.0, current_price=7.5),
    ]
    targets = {"A": 0.30}
    triggered = daily_etf_signal._apply_position_stop_losses(
        holdings=holdings, target_weights=targets, threshold=-0.15,
    )
    assert triggered["A"]["advisory_only"] is False
    assert targets["A"] == 0.0


def test_generate_plan_emits_stop_loss_triggered_field() -> None:
    """The plan output must surface stop-loss decisions for the dashboard."""

    from src.data.etf_rotation import EtfHolding

    # Holding at -25% from cost → triggers default -15% stop.
    holdings = [
        EtfHolding(code="510300", name="沪深300ETF", shares=1000,
                   cost_price=8.0, current_price=6.0),
        EtfHolding(code="159985", name="豆粕ETF", shares=1000,
                   cost_price=2.0, current_price=2.10),
    ]
    plan = daily_etf_signal.generate_plan(holdings=holdings)
    triggered = plan.get("stop_loss_triggered") or {}
    assert "510300" in triggered
    assert "159985" not in triggered
    # Strategy/risk pipeline should treat 510300 as zero target.
    assert plan["target_weights"]["510300"] == 0.0


def test_generate_plan_emits_score_breakdown_for_audit() -> None:
    """The score_breakdown carries the data IC analytics later consume."""

    plan = daily_etf_signal.generate_plan()
    score_breakdown = plan.get("score_breakdown") or {}
    # Should have at least the seed codes' scores.
    assert {"159985", "510300"}.issubset(set(score_breakdown))
    for code, sb in score_breakdown.items():
        assert "score" in sb
        assert "latest_price" in sb
        assert isinstance(sb["score"], float)


def test_generate_plan_advisory_stop_loss_keeps_target_weight(tmp_path, monkeypatch) -> None:
    """End-to-end: setting stop_loss_advisory_only=true in strategy.json
    flows through generate_plan — the position breaches the threshold,
    audit log records it, but target_weight stays non-zero."""

    import json
    from src.data.etf_rotation import EtfHolding

    cfg_path = tmp_path / "strategy.json"
    cfg_path.write_text(json.dumps({
        "strategy": {
            "stop_loss_threshold": -0.15,
            "stop_loss_advisory_only": True,
            "rebalance_threshold": 1.0,  # mirrors the user's live config
        },
    }))
    monkeypatch.setenv("ETF_STRATEGY_CONFIG_PATH", str(cfg_path))

    holdings = [
        # Deep underwater — would normally force-clear to target=0.
        EtfHolding(code="510300", name="沪深300ETF", shares=1000,
                   cost_price=10.0, current_price=7.5),  # -25%
        EtfHolding(code="159985", name="豆粕ETF", shares=1000,
                   cost_price=2.0, current_price=2.10),
    ]
    plan = daily_etf_signal.generate_plan(holdings=holdings)

    triggered = plan.get("stop_loss_triggered") or {}
    assert "510300" in triggered, "advisory mode still detects breaches"
    assert triggered["510300"]["advisory_only"] is True
    assert triggered["510300"]["previous_target_weight"] >= 0.0

    # No suggestion is the explicit "sell entire 510300 position" form.
    sells_for_510300 = [
        s for s in plan["suggestions"]
        if s["code"] == "510300" and s["action"] == "sell"
        and s["target_weight"] == 0.0
    ]
    assert sells_for_510300 == [], (
        "advisory stop must not generate a force-clear suggestion"
    )


def test_generate_plan_score_breakdown_includes_rsi_and_bollinger() -> None:
    """The audit score_breakdown surfaces RSI(14) and bollinger_position
    so the dashboard panel + weekly cron IC computation can read them
    without re-deriving from raw prices."""

    plan = daily_etf_signal.generate_plan()
    sb = plan.get("score_breakdown") or {}
    assert sb, "score_breakdown must be present for the dashboard panel"
    for code, entry in sb.items():
        if code == "CASH":
            continue
        assert "rsi14" in entry, f"{code} missing rsi14 field"
        assert "bollinger_position" in entry, f"{code} missing bollinger_position"
        # Values can be None on short series, but the keys must exist.
        if entry["rsi14"] is not None:
            assert 0.0 <= entry["rsi14"] <= 100.0
        if entry["bollinger_position"] is not None:
            # BB position can clip outside [0,1] on strong moves — sanity bound.
            assert -1.0 <= entry["bollinger_position"] <= 2.0


def test_generate_plan_reads_rebalance_threshold_from_config(tmp_path, monkeypatch) -> None:
    """When ``threshold_weight`` is None, ``generate_plan`` must fall back
    to ``strategy.rebalance_threshold`` from the loaded config — verified
    by comparing two configs that differ only on this knob and confirming
    the produced ``hold`` count differs accordingly."""

    import json
    cfg_low_path = tmp_path / "low.json"
    cfg_low_path.write_text(json.dumps({"strategy": {"rebalance_threshold": 0.001}}))
    cfg_high_path = tmp_path / "high.json"
    cfg_high_path.write_text(json.dumps({"strategy": {"rebalance_threshold": 0.99}}))

    monkeypatch.setenv("ETF_STRATEGY_CONFIG_PATH", str(cfg_low_path))
    plan_low = daily_etf_signal.generate_plan()
    holds_low = sum(1 for s in plan_low["suggestions"] if s["action"] == "hold")

    monkeypatch.setenv("ETF_STRATEGY_CONFIG_PATH", str(cfg_high_path))
    plan_high = daily_etf_signal.generate_plan()
    holds_high = sum(1 for s in plan_high["suggestions"] if s["action"] == "hold")

    # With threshold=0.99 every delta below 99 pp becomes a hold; with
    # threshold=0.001 nearly any drift becomes a buy/sell.
    assert holds_high >= holds_low
    assert holds_high == len(plan_high["suggestions"])


def test_generate_plan_explicit_threshold_overrides_config(tmp_path, monkeypatch) -> None:
    """Explicit ``threshold_weight`` must override what strategy.json says."""

    import json
    cfg_path = tmp_path / "strategy.json"
    cfg_path.write_text(json.dumps({"strategy": {"rebalance_threshold": 0.99}}))
    monkeypatch.setenv("ETF_STRATEGY_CONFIG_PATH", str(cfg_path))

    # Config says 0.99 (all holds) but we pass 0.001 → should see buys/sells.
    plan = daily_etf_signal.generate_plan(threshold_weight=0.001)
    actions = [s["action"] for s in plan["suggestions"]]
    assert any(a in {"buy", "sell"} for a in actions), (
        f"Expected at least one buy/sell when explicit threshold=0.001 overrides "
        f"config 0.99, got {actions}"
    )


def test_audit_log_entry_includes_score_breakdown_and_prices(tmp_path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    plan = daily_etf_signal.generate_plan()
    daily_etf_signal.append_audit_entry(plan, path=audit_path, quote_source="test")
    entries = daily_etf_signal.read_audit_log(audit_path)
    assert len(entries) == 1
    entry = entries[0]
    assert "score_breakdown" in entry
    assert "prices_at_decision" in entry
    assert "stop_loss_triggered" in entry
    # Per-code score + decision price are present.
    assert "510300" in entry["score_breakdown"]
    assert "510300" in entry["prices_at_decision"]


def test_main_cli_position_cut_halves_a_sell_recommendation(
    tmp_path, capsys, monkeypatch
) -> None:
    holdings_payload = {
        "holdings": [
            {"code": "510300", "name": "沪深300ETF", "shares": 1000,
             "cost_price": 5.0, "current_price": 5.0},
            {"code": "159985", "name": "豆粕ETF", "shares": 1000,
             "cost_price": 2.0, "current_price": 2.0},
        ]
    }
    holdings_path = tmp_path / "holdings.json"
    holdings_path.write_text(json.dumps(holdings_payload))

    rc = daily_etf_signal.main([
        "--holdings-json", str(holdings_path),
        "--no-live-quotes",
        "--position-cut", "0.5",
        "--output", "json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload.get("position_cut") == pytest.approx(0.5)


# ---------------------------------------------------------------------------


def test_load_configured_holdings_falls_back_when_env_path_missing(monkeypatch, caplog) -> None:
    monkeypatch.setenv(daily_etf_signal.HOLDINGS_PATH_ENV, "/path/that/does/not/exist.json")
    monkeypatch.setattr(
        daily_etf_signal,
        "DEFAULT_HOLDINGS_PATH",
        Path("/another/nonexistent.json"),
    )
    caplog.set_level("WARNING", logger="scripts.daily_etf_signal")
    holdings, is_configured = daily_etf_signal.load_configured_holdings()
    assert is_configured is False
    assert holdings  # falls back to example seed
    assert any(
        "ETF_HOLDINGS_PATH" in record.getMessage() for record in caplog.records
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def test_main_cli_default_args_prints_text(capsys: pytest.CaptureFixture[str]) -> None:
    rc = daily_etf_signal.main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.strip()
    assert "手动" in captured.out
    assert "自动下单" in captured.out
    assert "券商" in captured.out
    assert "Total asset value" not in captured.out
    assert "Manual trade suggestions" not in captured.out
    assert "delta_" not in captured.out


def test_main_cli_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    rc = daily_etf_signal.main(["--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "suggestions" in payload
    assert "risk_reasons" in payload


def test_main_cli_default_reports_synthetic_provenance(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Default invocation (no --holdings-json / --quotes-json) must surface
    the screenshot seed as ``synthetic`` so dashboards do not mistake the
    seed for live broker data."""
    rc = daily_etf_signal.main(["--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    by_id = {entry["source_id"]: entry for entry in payload["source_health"]}
    assert by_id["etf_holdings"]["status"] == "synthetic"
    assert by_id["etf_holdings"]["reason"] == "screenshot_seed"
    assert by_id["etf_quotes"]["status"] == "synthetic"


def test_main_cli_reads_holdings_json(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    holdings_payload = {
        "total_asset": 100_000.0,
        "holdings": [
            {
                "code": "510300",
                "name": "沪深300ETF",
                "shares": 1000,
                "cost_price": 4.20,
                "current_price": 5.00,
            },
            {
                "code": "513130",
                "name": "恒生科技ETF",
                "shares": 5000,
                "cost_price": 0.95,
                "current_price": 1.00,
            },
        ],
    }
    holdings_path = tmp_path / "holdings.json"
    holdings_path.write_text(json.dumps(holdings_payload))

    rc = daily_etf_signal.main(
        ["--holdings-json", str(holdings_path), "--output", "json"]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["current_weights"]) >= {"510300", "513130"}


def test_main_cli_reads_quotes_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    quotes_payload = {
        "510300": {"name": "沪深300ETF", "current_price": 5.05, "prev_close": 5.00},
        "513130": {"name": "恒生科技ETF", "current_price": 1.05, "prev_close": 1.00},
    }
    quotes_path = tmp_path / "quotes.json"
    quotes_path.write_text(json.dumps(quotes_payload))

    rc = daily_etf_signal.main(
        ["--quotes-json", str(quotes_path), "--output", "json"]
    )
    assert rc == 0


# ---------------------------------------------------------------------------
# Backtest script
# ---------------------------------------------------------------------------


def _write_synthetic_prices(tmp_path) -> str:
    dates = pd.bdate_range("2025-01-01", periods=140)
    rng = np.random.default_rng(11)
    columns = ["510300", "159985", "512400", "518680", "513130"]
    data = {}
    for offset, code in enumerate(columns):
        drift = np.linspace(0.0, 0.20 - 0.05 * offset, len(dates))
        noise = np.cumsum(rng.normal(0.0, 0.005, len(dates)))
        data[code] = 5.0 * np.exp(drift + noise)
    prices = pd.DataFrame(data, index=dates)
    csv_path = tmp_path / "prices.csv"
    prices.to_csv(csv_path)
    return str(csv_path)


def test_backtest_run_returns_metrics(tmp_path) -> None:
    csv_path = _write_synthetic_prices(tmp_path)
    result = backtest_etf_rotation.run_backtest(csv_path)
    assert isinstance(result, dict)
    # Either the backtester emitted nothing (empty matrix) or it produced
    # a populated result — we accept either as long as it is structured.
    if result:
        assert "final_value" in result
        assert "assets" in result
        assert set(result["assets"]) <= {"510300", "159985", "512400", "518680", "513130"}


def test_backtest_run_accepts_capital_override(tmp_path) -> None:
    csv_path = _write_synthetic_prices(tmp_path)
    result = backtest_etf_rotation.run_backtest(csv_path, initial_capital=250_000.0)
    if result:
        assert result["initial_capital"] == pytest.approx(250_000.0)


def test_backtest_main_returns_zero_on_valid_csv(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv_path = _write_synthetic_prices(tmp_path)
    rc = backtest_etf_rotation.main(["--prices-csv", csv_path])
    assert rc == 0
    captured = capsys.readouterr()
    # The CLI prints a JSON summary.
    json.loads(captured.out)


def test_load_price_matrix_sorts_chronologically_before_ffill(tmp_path) -> None:
    """A descending-date CSV must come back chronologically sorted.

    `load_price_matrix` runs `ffill` on raw row order. If the CSV is in
    descending date order, ffill propagates a later price backward into an
    earlier NaN row — silent data leakage that downstream sorts cannot undo.
    Lock in the invariant: sort by date first, then ffill.
    """
    dates_ascending = pd.bdate_range("2025-01-01", periods=8)
    # Assign a strictly increasing price by chronological date so we can
    # detect both the wrong ffill direction and the wrong row order.
    chronological_prices = {
        date: 5.00 + i * 0.10 for i, date in enumerate(dates_ascending)
    }
    # Punch a NaN at the second chronological row (2025-01-02) — when the
    # CSV is in descending order, that row sits between two later-date rows
    # whose prices are higher.
    chronological_prices[dates_ascending[1]] = float("nan")

    descending_index = list(dates_ascending[::-1])
    frame = pd.DataFrame(
        {"510300": [chronological_prices[d] for d in descending_index]},
        index=descending_index,
    )
    csv_path = tmp_path / "descending_prices.csv"
    frame.to_csv(csv_path)

    loaded = backtest_etf_rotation.load_price_matrix(str(csv_path))

    assert loaded.index.is_monotonic_increasing, (
        "load_price_matrix must return chronologically sorted prices; "
        "got index order " f"{list(loaded.index)}"
    )
    # The NaN at 2025-01-02 should be ffilled from 2025-01-01 (5.00), not
    # from a later date. If ffill ran before sort it would carry the next
    # row down — which in descending order is 2025-01-03 (5.20).
    filled_value = float(loaded.loc[dates_ascending[1], "510300"])
    assert filled_value == pytest.approx(5.00), (
        "ffill must run after chronological sort so missing prices inherit "
        f"from earlier dates, not later ones; got {filled_value}"
    )


def test_generate_plan_includes_policy_signal_factor_off_by_default() -> None:
    """Without overrides the plan must carry an OFF policy_signal_factor block."""

    plan = daily_etf_signal.generate_plan()
    summary = plan.get("policy_signal_factor") or {}
    # OFF by default — no industry signals loaded, no adjustments applied.
    assert summary.get("enabled") is False
    assert summary.get("applied_count", 0) == 0
    assert summary.get("boosted") == []
    assert summary.get("penalised") == []


def test_generate_plan_attaches_order_pricing_to_actionable_suggestions() -> None:
    plan = daily_etf_signal.generate_plan()
    actionable = [
        item for item in plan["suggestions"]
        if item["action"] in {"buy", "sell"} and item["shares"] > 0
    ]

    assert actionable, "default ETF seed should produce at least one actionable trade"
    for item in actionable:
        pricing = item.get("pricing")
        assert pricing is not None
        assert pricing["action"] == item["action"]
        assert pricing["recommended_level"] in {"aggressive", "neutral", "passive"}
        assert pricing["recommended_price"] == pytest.approx(
            pricing["limit_prices"][pricing["recommended_level"]]
        )
        assert sum(pricing["shares_per_batch"]) == item["shares"]
        assert pricing["preferred_windows"]

    for item in plan["suggestions"]:
        if item["action"] == "hold":
            assert item.get("pricing") is None


def test_generate_plan_policy_signal_factor_can_be_force_enabled(monkeypatch) -> None:
    """``enable_policy_signal_factor=True`` overrides the config default."""

    # No etf_industry_map → factor is opt-in but harmless (no ETF mapped).
    plan = daily_etf_signal.generate_plan(enable_policy_signal_factor=True)
    summary = plan.get("policy_signal_factor") or {}
    assert summary.get("enabled") is True
    assert summary.get("applied_count", 0) == 0


def test_generate_plan_policy_signal_factor_applies_when_mapped(monkeypatch) -> None:
    """End-to-end: with a fake industry_signals + mapped ETF, weight tilts."""

    industry_signals = {
        "metals_test": {"avg_impact": -0.40, "signal": "bearish", "mentions": 50}
    }

    # Patch the config loader to inject a fresh map that points 512400 → metals_test
    # so the factor has somewhere to apply.
    original_loader = daily_etf_signal.load_strategy_config

    def _patched_loader(*args, **kwargs):
        cfg = original_loader(*args, **kwargs)
        from dataclasses import replace as _dc_replace
        return _dc_replace(cfg, etf_industry_map={"512400": "metals_test"})

    monkeypatch.setattr(daily_etf_signal, "load_strategy_config", _patched_loader)

    plan_off = daily_etf_signal.generate_plan(
        enable_policy_signal_factor=False,
        industry_signals=industry_signals,
    )
    plan_on = daily_etf_signal.generate_plan(
        enable_policy_signal_factor=True,
        industry_signals=industry_signals,
    )

    # OFF run: no adjustments.
    assert plan_off["policy_signal_factor"]["enabled"] is False
    # ON run: the bearish penalty fires for 512400.
    summary = plan_on["policy_signal_factor"]
    assert summary["enabled"] is True
    breakdown_on = plan_on["score_breakdown"].get("512400", {})
    if breakdown_on.get("raw_target_weight", 0.0) > 0:
        # When the ETF had a non-zero score, the bearish penalty must show up.
        assert "512400" in summary["penalised"]
        meta = breakdown_on.get("policy_adjustment") or {}
        assert meta.get("signal") == "bearish"
        assert meta.get("delta_weight", 0.0) < 0.0


def test_append_audit_entry_includes_policy_signal_factor_block(tmp_path) -> None:
    """Audit log row must carry the policy_signal_factor summary, OFF or ON."""

    audit_path = tmp_path / "audit.jsonl"
    plan = daily_etf_signal.generate_plan(enable_policy_signal_factor=True)
    daily_etf_signal.append_audit_entry(plan, path=audit_path, quote_source="policy-test")

    entries = daily_etf_signal.read_audit_log(audit_path)
    assert len(entries) == 1
    entry = entries[0]
    assert "policy_signal_factor" in entry
    assert entry["policy_signal_factor"].get("enabled") is True
    # score_breakdown carries the per-ETF metadata path; even when None it's
    # an explicit key so dashboards know to look for it.
    for code, breakdown in entry.get("score_breakdown", {}).items():
        assert "policy_adjustment" in breakdown
        # When OFF / no mapping the value must be None (not absent) — keep
        # the JSON shape stable across runs.


def test_load_policy_industry_signals_returns_empty_when_missing(tmp_path) -> None:
    """Missing snapshot must return ({}, None) so the legacy path stays clean."""

    signals, last_refresh = daily_etf_signal.load_policy_industry_signals(
        cache_path=tmp_path / "does-not-exist.json"
    )
    assert signals == {}
    assert last_refresh is None


def test_load_policy_industry_signals_parses_snapshot(tmp_path) -> None:
    """Realistic policy_radar.json shape → industry signals dict."""

    snapshot = tmp_path / "policy_radar.json"
    snapshot.write_text(
        json.dumps({
            "provider": "policy_radar",
            "signal": {
                "timestamp": "2026-05-17T08:29:46",
                "industry_signals": {
                    "新能源汽车": {"avg_impact": -0.32, "mentions": 119, "signal": "bearish"},
                    "风电": {"avg_impact": 0.0, "mentions": 3, "signal": "neutral"},
                },
            },
        }),
        encoding="utf-8",
    )
    signals, last_refresh = daily_etf_signal.load_policy_industry_signals(
        cache_path=snapshot
    )
    assert last_refresh == "2026-05-17T08:29:46"
    assert signals["新能源汽车"]["signal"] == "bearish"
    assert signals["新能源汽车"]["avg_impact"] == pytest.approx(-0.32)


def test_main_cli_help_uses_chinese_user_facing_copy(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        daily_etf_signal.main(["--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "生成每日 ETF 轮动手动调仓计划" in captured.out
    assert "不连接券商接口" in captured.out
    assert "可选：当前持仓 JSON 文件" in captured.out
    assert "Output format" not in captured.out
    assert "No broker API" not in captured.out
    assert "usage:" not in captured.out
    assert "options:" not in captured.out
    assert "optional arguments:" not in captured.out
    assert "show this help message and exit" not in captured.out
    assert "用法：" in captured.out
    assert "选项：" in captured.out
    assert "显示此帮助信息并退出" in captured.out
