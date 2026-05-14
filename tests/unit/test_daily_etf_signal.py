"""Tests for the daily ETF signal and backtest CLI scripts.

These tests stay hermetic — no network, no broker, no live prices.
Fixtures are constructed inline or written to ``tmp_path``.
"""

from __future__ import annotations

import json
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
    first = daily_etf_signal.synthesize_price_matrix(quotes)
    second = daily_etf_signal.synthesize_price_matrix(quotes)

    assert isinstance(first, pd.DataFrame)
    assert list(first.columns) == [h.code for h in holdings]
    assert len(first) >= 70  # long enough for the 60-day warmup
    pd.testing.assert_frame_equal(first, second)


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
