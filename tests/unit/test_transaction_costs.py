"""Unit tests for the transaction-cost modelling layer.

Coverage:

1. ``TransactionCostModel`` construction with defaults / overrides /
   bad inputs.
2. ``apply_transaction_costs`` numerics across the obvious regimes —
   small trades hit the commission floor, large trades hit the bps,
   sub-min trades are skipped, ADV gating only fires above 5%.
3. ``BacktestReport`` integration — net < gross when TC is on, net ==
   gross when TC is off, gross unchanged across (TC on vs off) runs.
4. Walkforward + Comparison thread the tc_model correctly into each
   wrapped backtester and the aggregate TC means are sensible.
5. JSON round-trips: tc_model_params survive ``to_dict`` and the
   ``json.dumps(allow_nan=False)`` strict path.

Fixtures keep all prices in-memory; no disk I/O, no network. Tests run
in well under a second each.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from src.backtest.etf_rotation_backtest import (
    BacktestReport,
    EtfRotationBacktester,
)
from src.backtest.etf_rotation_walkforward import EtfRotationWalkforwardAnalyzer
from src.backtest.strategy_comparison import (
    StrategyComparator,
    build_default_strategy_specs,
)
from src.backtest.transaction_costs import (
    DEFAULT_BID_ASK_SPREAD_BPS,
    DEFAULT_COMMISSION_BPS,
    DEFAULT_MARKET_IMPACT_BPS_PER_PCT_ADV,
    DEFAULT_MIN_COMMISSION_PER_TRADE,
    DEFAULT_MIN_TRADE_SIZE_RMB,
    CostBreakdown,
    RebalanceEventInput,
    TransactionCostModel,
    apply_transaction_costs,
)
from src.strategy.etf_rotation_strategy import (
    EtfAssetConfig,
    EtfRotationConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(symbols: tuple[str, ...] = ("STRONG", "WEAK")) -> EtfRotationConfig:
    return EtfRotationConfig(
        assets=[EtfAssetConfig(symbol=s, max_weight=0.5) for s in symbols],
        gross_cap=0.9,
        warmup_days=60,
    )


def _trend_market(
    symbols: tuple[str, ...] = ("STRONG", "WEAK"),
    days: int = 180,
    seed: int = 42,
) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    rng = np.random.default_rng(seed=seed)
    columns: dict[str, np.ndarray] = {}
    for offset, sym in enumerate(symbols):
        drift = np.linspace(0.0, 0.30 if offset == 0 else -0.20, days)
        noise = rng.normal(0.0, 0.003, days)
        columns[sym] = 100.0 * np.exp(drift + np.cumsum(noise))
    return pd.DataFrame(columns, index=dates)


# ---------------------------------------------------------------------------
# Model construction
# ---------------------------------------------------------------------------


def test_default_model_matches_module_constants() -> None:
    """Defaults are surfaced verbatim from the module-level constants."""

    model = TransactionCostModel()
    assert model.commission_bps == DEFAULT_COMMISSION_BPS == 3.0
    assert (
        model.min_commission_per_trade
        == DEFAULT_MIN_COMMISSION_PER_TRADE
        == 5.0
    )
    assert (
        model.bid_ask_spread_bps == DEFAULT_BID_ASK_SPREAD_BPS == 5.0
    )
    assert (
        model.market_impact_bps_per_pct_adv
        == DEFAULT_MARKET_IMPACT_BPS_PER_PCT_ADV
        == 0.5
    )
    assert model.min_trade_size_rmb == DEFAULT_MIN_TRADE_SIZE_RMB == 100.0


def test_model_overrides_individual_fields() -> None:
    """Per-field overrides keep the other defaults untouched."""

    model = TransactionCostModel(commission_bps=10.0, bid_ask_spread_bps=2.0)
    assert model.commission_bps == 10.0
    assert model.bid_ask_spread_bps == 2.0
    # Untouched fields stay on their defaults.
    assert model.min_commission_per_trade == DEFAULT_MIN_COMMISSION_PER_TRADE
    assert model.market_impact_bps_per_pct_adv == DEFAULT_MARKET_IMPACT_BPS_PER_PCT_ADV


@pytest.mark.parametrize(
    "field",
    [
        "commission_bps",
        "min_commission_per_trade",
        "bid_ask_spread_bps",
        "market_impact_bps_per_pct_adv",
        "min_trade_size_rmb",
    ],
)
def test_model_rejects_negative_parameters(field: str) -> None:
    """Negative parameters would silently fund the strategy — reject."""

    kwargs = {field: -1.0}
    with pytest.raises(ValueError, match=field):
        TransactionCostModel(**kwargs)


def test_from_overrides_with_empty_dict_returns_defaults() -> None:
    """An empty / None overrides block produces the default model."""

    assert TransactionCostModel.from_overrides({}).to_dict() == (
        TransactionCostModel().to_dict()
    )
    assert TransactionCostModel.from_overrides(None).to_dict() == (
        TransactionCostModel().to_dict()
    )


def test_from_overrides_rejects_unknown_keys() -> None:
    """Typos / unknown fields raise rather than silently being dropped."""

    with pytest.raises(TypeError, match="unknown override keys"):
        TransactionCostModel.from_overrides({"commission_bps_typo": 5.0})


# ---------------------------------------------------------------------------
# Cost breakdown numerics
# ---------------------------------------------------------------------------


def test_small_trade_hits_commission_floor() -> None:
    """A 100 RMB trade pays the 5 RMB floor, not 0.03% of 100 = 3 fen."""

    model = TransactionCostModel()
    # 0.1% of 100k = 100 RMB trade; spread = 100 * 5 / 10000 = 0.05 RMB
    event = RebalanceEventInput(
        portfolio_value=100_000.0,
        weight_deltas={"A": 0.001},
    )
    breakdown = apply_transaction_costs(event, model)
    # commission floor (5 RMB) > 100 RMB * 0.03% = 0.03 RMB → floor wins
    assert breakdown.commission_rmb == pytest.approx(5.0)
    # spread = 100 RMB * 5 / 10000 = 0.05 RMB
    assert breakdown.spread_rmb == pytest.approx(0.05)
    assert breakdown.impact_rmb == pytest.approx(0.0)
    assert breakdown.total_cost_rmb == pytest.approx(5.05)


def test_large_trade_bps_dominates_commission_floor() -> None:
    """On a 1M RMB trade, 0.03% = 300 RMB dwarfs the 5 RMB floor."""

    model = TransactionCostModel()
    event = RebalanceEventInput(
        portfolio_value=10_000_000.0,
        weight_deltas={"A": 0.10},  # 1M RMB trade
    )
    breakdown = apply_transaction_costs(event, model)
    assert breakdown.commission_rmb == pytest.approx(300.0)  # 1M * 3/10000
    assert breakdown.spread_rmb == pytest.approx(500.0)  # 1M * 5/10000
    assert breakdown.impact_rmb == pytest.approx(0.0)  # no ADV given


def test_market_impact_only_fires_above_5_pct_adv() -> None:
    """A 3%-of-ADV trade pays no impact; a 10%-of-ADV trade pays (10-5)*0.5=2.5 bps."""

    model = TransactionCostModel()
    # 100k RMB trade, ADV = 100k/0.10 = 1M → 10% of ADV
    event_10pct = RebalanceEventInput(
        portfolio_value=1_000_000.0,
        weight_deltas={"A": 0.10},  # 100k RMB trade
        adv_per_symbol={"A": 1_000_000.0},  # 10% of ADV
    )
    breakdown_10 = apply_transaction_costs(event_10pct, model)
    # Impact = 100k * 2.5 / 10000 = 25 RMB
    assert breakdown_10.impact_rmb == pytest.approx(25.0)

    # Now drop to 3% of ADV → no impact at all
    event_3pct = RebalanceEventInput(
        portfolio_value=1_000_000.0,
        weight_deltas={"A": 0.10},
        adv_per_symbol={"A": 3_333_333.33},  # 100k / 3.33M = 3%
    )
    breakdown_3 = apply_transaction_costs(event_3pct, model)
    assert breakdown_3.impact_rmb == pytest.approx(0.0)


def test_trade_below_min_size_is_skipped() -> None:
    """Trades below 100 RMB notional are not charged anything."""

    model = TransactionCostModel(min_trade_size_rmb=100.0)
    # 0.05% of 100k = 50 RMB trade — below the 100 RMB floor
    event = RebalanceEventInput(
        portfolio_value=100_000.0,
        weight_deltas={"A": 0.0005},
    )
    breakdown = apply_transaction_costs(event, model)
    assert breakdown.n_trades_charged == 0
    assert breakdown.n_trades_skipped_under_min == 1
    assert breakdown.total_cost_rmb == 0.0
    assert breakdown.total_cost_bps_of_portfolio == 0.0
    assert breakdown.per_leg[0]["skipped"] is True


def test_normalized_weight_space_uses_one_aum() -> None:
    """Missing / zero AUM normalizes to 1.0 — bps output stays meaningful."""

    model = TransactionCostModel()
    # Portfolio value 0 → coerced to 1.0; deltas of 0.5 each = 0.5 RMB trades
    # Both below min_trade_size_rmb=100 → all skipped.
    event = RebalanceEventInput(
        portfolio_value=0.0,
        weight_deltas={"A": 0.5, "B": -0.5},
    )
    breakdown = apply_transaction_costs(event, model)
    assert breakdown.portfolio_value == pytest.approx(1.0)
    # Skipped below min size, so cost is 0
    assert breakdown.total_cost_bps_of_portfolio == 0.0


def test_zero_delta_legs_ignored() -> None:
    """Symbols with zero delta_w contribute nothing — not even a skipped row."""

    model = TransactionCostModel()
    event = RebalanceEventInput(
        portfolio_value=100_000.0,
        weight_deltas={"A": 0.05, "B": 0.0, "C": 1e-15},
    )
    breakdown = apply_transaction_costs(event, model)
    assert breakdown.n_trades_charged == 1  # only A
    assert breakdown.n_trades_skipped_under_min == 0
    assert len(breakdown.per_leg) == 1


def test_sample_5_etf_5pct_turnover_100k_portfolio() -> None:
    """Sample TC breakdown for the docstring summary.

    5 ETFs each shifting ±2.5% (5% total turnover) on a 100k portfolio.
    Each leg = 2.5k RMB; commission floor 5 RMB beats 2.5k*0.03%=0.75 RMB
    so each leg pays 5 RMB commission + 1.25 RMB spread = 6.25 RMB.
    Five legs → 31.25 RMB total → 3.125 bps of 100k portfolio.
    """

    model = TransactionCostModel()
    event = RebalanceEventInput(
        portfolio_value=100_000.0,
        weight_deltas={"A": 0.025, "B": -0.025, "C": 0.025, "D": -0.025, "E": 0.025},
    )
    breakdown = apply_transaction_costs(event, model)
    assert breakdown.n_trades_charged == 5
    assert breakdown.commission_rmb == pytest.approx(25.0)  # 5 * 5 floor
    assert breakdown.spread_rmb == pytest.approx(6.25)  # 5 * 2500 * 5/10000
    assert breakdown.impact_rmb == pytest.approx(0.0)
    assert breakdown.total_cost_rmb == pytest.approx(31.25)
    assert breakdown.total_cost_bps_of_portfolio == pytest.approx(3.125)


def test_deterministic_per_leg_ordering() -> None:
    """Per-leg list is symbol-sorted so two runs produce byte-identical output."""

    model = TransactionCostModel()
    event = RebalanceEventInput(
        portfolio_value=100_000.0,
        weight_deltas={"Z": 0.05, "A": 0.05, "M": 0.05},
    )
    breakdown = apply_transaction_costs(event, model)
    symbols = [leg["symbol"] for leg in breakdown.per_leg]
    assert symbols == sorted(symbols)


def test_dict_event_input_works() -> None:
    """``apply_transaction_costs`` accepts a plain dict mapping."""

    model = TransactionCostModel()
    breakdown = apply_transaction_costs(
        {"portfolio_value": 100_000.0, "weight_deltas": {"A": 0.05}},
        model,
    )
    assert isinstance(breakdown, CostBreakdown)
    assert breakdown.n_trades_charged == 1


def test_invalid_event_type_raises() -> None:
    """Non-mapping non-dataclass inputs are rejected explicitly."""

    with pytest.raises(TypeError, match="rebalance_event must be"):
        apply_transaction_costs([1, 2, 3], TransactionCostModel())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Backtester integration
# ---------------------------------------------------------------------------


def test_tc_model_default_is_none_no_behaviour_change() -> None:
    """When tc_model is None, the report runs exactly as v0.1 (gross == net)."""

    config = _make_config()
    prices = _trend_market(days=180)
    report = EtfRotationBacktester(
        config=config, price_history=prices, period_start="2024-04-01",
    ).run()
    # When TC is off, the report still has the new fields, all zero/identity.
    assert report.tc_enabled is False
    assert report.gross_total_return_pct == report.total_return_pct
    assert report.net_total_return_pct == report.total_return_pct
    assert report.total_tc_cost_pct == 0.0
    assert report.avg_tc_per_rebalance_bps == 0.0
    assert report.tc_drag_annualized_pct == 0.0
    assert report.tc_model_params is None
    # Legacy caveat preserved.
    assert "no_transaction_costs_modeled" in report.caveats


def test_tc_enabled_net_is_less_than_gross() -> None:
    """With TC on, net < gross (the cost is real and positive)."""

    config = _make_config()
    prices = _trend_market(days=180)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
        tc_model=TransactionCostModel(),
    ).run()
    assert report.tc_enabled is True
    assert report.gross_total_return_pct > report.net_total_return_pct
    assert report.total_tc_cost_pct > 0.0
    assert report.avg_tc_per_rebalance_bps > 0.0
    assert report.tc_model_params is not None
    assert any("transaction_costs_modeled" in c for c in report.caveats)


def test_tc_run_gross_matches_pure_gross_run() -> None:
    """The gross-equity curve inside a TC run replays the same holdings, so
    gross_total_return_pct must equal the pure-gross run's total_return_pct.
    """

    config = _make_config()
    prices = _trend_market(days=200)
    pure_gross = EtfRotationBacktester(
        config=config, price_history=prices, period_start="2024-04-01",
    ).run()
    with_tc = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
        tc_model=TransactionCostModel(),
    ).run()
    # The gross-of-fees path through the TC backtester must equal the
    # standalone gross run to within float precision.
    assert with_tc.gross_total_return_pct == pytest.approx(
        pure_gross.total_return_pct, abs=1e-9,
    )


def test_tc_drag_annualization_is_correct() -> None:
    """tc_drag_annualized_pct = total_tc_cost_pct / years."""

    config = _make_config()
    prices = _trend_market(days=180)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
        tc_model=TransactionCostModel(),
    ).run()
    # years = n_bars / 252 (TRADING_DAYS_PER_YEAR)
    from src.strategy.etf_rotation_strategy import TRADING_DAYS_PER_YEAR

    years = max(report.n_bars / TRADING_DAYS_PER_YEAR, 1.0 / TRADING_DAYS_PER_YEAR)
    expected_drag = report.total_tc_cost_pct / years
    assert report.tc_drag_annualized_pct == pytest.approx(expected_drag, abs=1e-9)


def test_tc_report_round_trips_through_json() -> None:
    """to_dict() + json.dumps(allow_nan=False) survives TC fields."""

    config = _make_config()
    prices = _trend_market(days=180)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
        tc_model=TransactionCostModel(),
    ).run()
    payload = report.to_dict()
    serialized = json.dumps(payload, allow_nan=False)
    parsed = json.loads(serialized)
    assert parsed["tc_enabled"] is True
    assert parsed["tc_model_params"]["commission_bps"] == 3.0
    assert math.isfinite(parsed["gross_total_return_pct"])
    assert math.isfinite(parsed["net_total_return_pct"])


def test_rebalance_log_carries_per_event_tc_breakdown() -> None:
    """Each rebalance entry should include a ``tc_cost`` dict when TC is on."""

    config = _make_config()
    prices = _trend_market(days=180)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
        tc_model=TransactionCostModel(),
    ).run()
    assert any(entry.get("tc_cost") for entry in report.rebalance_log)
    # Each cost entry has the canonical keys.
    for entry in report.rebalance_log:
        if "tc_cost" in entry:
            cost = entry["tc_cost"]
            assert "total_cost_rmb" in cost
            assert "total_cost_bps" in cost
            assert "commission_rmb" in cost
            assert "spread_rmb" in cost
            assert "impact_rmb" in cost


# ---------------------------------------------------------------------------
# Walkforward + Comparison threading
# ---------------------------------------------------------------------------


def test_walkforward_threads_tc_to_every_window() -> None:
    """The walkforward analyzer must forward tc_model to each window."""

    config = _make_config()
    prices = _trend_market(days=300)
    report = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=2,
        period_start="2024-03-01",
        period_end="2024-09-30",
        tc_model=TransactionCostModel(),
    ).run()
    assert report.tc_enabled is True
    assert report.tc_model_params is not None
    assert all(w.tc_enabled for w in report.windows)
    # Aggregate gross >= net across windows.
    assert report.mean_gross_return_pct >= report.mean_net_return_pct


def test_walkforward_without_tc_model_keeps_legacy_shape() -> None:
    """When tc_model is None, walkforward report has zero TC fields."""

    config = _make_config()
    prices = _trend_market(days=300)
    report = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=2,
        period_start="2024-03-01",
        period_end="2024-09-30",
    ).run()
    assert report.tc_enabled is False
    assert report.mean_tc_cost_pct == 0.0
    assert report.mean_tc_drag_annualized_pct == 0.0
    assert report.tc_model_params is None


def test_comparator_threads_tc_to_every_strategy() -> None:
    """The comparator must forward tc_model to each child backtester."""

    config = _make_config()
    prices = _trend_market(days=240)
    specs = list(build_default_strategy_specs(config).values())
    report = StrategyComparator(
        strategies=specs,
        price_history=prices,
        period_start="2024-03-01",
        period_end="2024-09-30",
        tc_model=TransactionCostModel(),
    ).run()
    assert report.tc_enabled is True
    assert report.tc_model_params is not None
    for label, per_strategy in report.per_strategy_metrics.items():
        assert per_strategy.tc_enabled is True, label
        # net <= gross for every strategy (cost is non-negative).
        assert per_strategy.net_total_return_pct <= per_strategy.gross_total_return_pct + 1e-9


def test_comparator_without_tc_model_keeps_legacy_shape() -> None:
    """ComparisonReport.tc_enabled=False + per-strategy fields zero."""

    config = _make_config()
    prices = _trend_market(days=200)
    specs = list(build_default_strategy_specs(config).values())
    report = StrategyComparator(
        strategies=specs,
        price_history=prices,
        period_start="2024-04-01",
        period_end="2024-08-30",
    ).run()
    assert report.tc_enabled is False
    assert report.tc_model_params is None
    for per_strategy in report.per_strategy_metrics.values():
        assert per_strategy.tc_enabled is False
        assert per_strategy.total_tc_cost_pct == 0.0


def test_comparison_to_dict_includes_tc_fields() -> None:
    """tc_enabled / tc_model_params survive ``json.dumps(allow_nan=False)``."""

    config = _make_config()
    prices = _trend_market(days=200)
    specs = list(build_default_strategy_specs(config).values())
    report = StrategyComparator(
        strategies=specs,
        price_history=prices,
        period_start="2024-04-01",
        period_end="2024-08-30",
        tc_model=TransactionCostModel(commission_bps=6.0),
    ).run()
    payload = report.to_dict()
    serialized = json.dumps(payload, allow_nan=False)
    parsed = json.loads(serialized)
    assert parsed["tc_enabled"] is True
    assert parsed["tc_model_params"]["commission_bps"] == 6.0


# ---------------------------------------------------------------------------
# Backwards-compatibility regression — existing tests rely on the old
# caveat strings + report fields. Add explicit "off path" coverage here so
# any regression that drops legacy fields surfaces immediately.
# ---------------------------------------------------------------------------


def test_legacy_caveat_strings_present_when_tc_disabled() -> None:
    """The original v0.1 caveat strings must stay verbatim when TC is off."""

    config = _make_config()
    prices = _trend_market(days=180)
    report = EtfRotationBacktester(
        config=config, price_history=prices, period_start="2024-04-01",
    ).run()
    assert "no_transaction_costs_modeled" in report.caveats
    assert "no_bid_ask_spread_or_slippage" in report.caveats
    assert "no_market_impact" in report.caveats


def test_tc_caveat_string_when_tc_enabled() -> None:
    """With TC on, a single ``transaction_costs_modeled(...)`` tag replaces the trio."""

    config = _make_config()
    prices = _trend_market(days=180)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
        tc_model=TransactionCostModel(),
    ).run()
    tc_caveats = [c for c in report.caveats if c.startswith("transaction_costs_modeled")]
    assert len(tc_caveats) == 1
    # The legacy "no_…" strings should be gone — we'd give people a false
    # sense of caveat continuity if both were present.
    assert "no_transaction_costs_modeled" not in report.caveats
