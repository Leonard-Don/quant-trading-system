"""Tests for the order-pricing limit-price suggestion helper."""

from __future__ import annotations

import pytest

from src.data.etf_order_pricing import (
    PricingConfig,
    PricingHints,
    build_config_from_strategy_json,
    build_pricing_hints,
)

# ---------------------------------------------------------------------------
# Limit-price math
# ---------------------------------------------------------------------------


def test_sell_aggressive_is_below_reference_neutral_is_close_passive_is_above() -> None:
    hints = build_pricing_hints(
        action="sell",
        reference_price=10.000,
        shares=1000,
        estimated_amount=10_000.0,
    )
    assert hints is not None
    levels = hints.limit_prices
    # Sell: aggressive crosses the spread (lower price), passive sits above (try for better)
    assert levels["aggressive"] < levels["neutral"] < levels["passive"]
    # With default 2/1/1 ticks at 0.001:
    assert levels["aggressive"] == pytest.approx(9.998)
    assert levels["neutral"] == pytest.approx(9.999)
    assert levels["passive"] == pytest.approx(10.001)


def test_buy_aggressive_is_above_reference_passive_is_below() -> None:
    hints = build_pricing_hints(
        action="buy",
        reference_price=5.020,
        shares=500,
        estimated_amount=2_510.0,
    )
    assert hints is not None
    levels = hints.limit_prices
    # Buy: aggressive crosses up, passive sits below to wait
    assert levels["aggressive"] > levels["neutral"] > levels["passive"]
    assert levels["aggressive"] == pytest.approx(5.022)
    assert levels["neutral"] == pytest.approx(5.021)
    assert levels["passive"] == pytest.approx(5.019)


def test_hold_action_returns_no_hints() -> None:
    assert build_pricing_hints(
        action="hold", reference_price=5.0, shares=0, estimated_amount=0.0,
    ) is None


def test_missing_reference_price_returns_no_hints() -> None:
    assert build_pricing_hints(
        action="sell", reference_price=None, shares=100, estimated_amount=500.0,
    ) is None
    assert build_pricing_hints(
        action="sell", reference_price=0.0, shares=100, estimated_amount=500.0,
    ) is None


def test_zero_shares_returns_no_hints() -> None:
    assert build_pricing_hints(
        action="buy", reference_price=5.0, shares=0, estimated_amount=0.0,
    ) is None


def test_recommended_price_is_neutral_by_default() -> None:
    hints = build_pricing_hints(
        action="sell", reference_price=10.0, shares=1000, estimated_amount=10_000.0,
    )
    assert hints.recommended_level == "neutral"
    assert hints.recommended_price == pytest.approx(9.999)


def test_recommended_level_override_via_config() -> None:
    hints = build_pricing_hints(
        action="sell",
        reference_price=10.0,
        shares=1000,
        estimated_amount=10_000.0,
        config=PricingConfig(default_recommendation="aggressive"),
    )
    assert hints.recommended_level == "aggressive"
    assert hints.recommended_price == pytest.approx(9.998)


def test_tick_snapping_avoids_floating_point_drift() -> None:
    """A reference price like 2.099 should produce clean 3-decimal outputs."""

    hints = build_pricing_hints(
        action="sell", reference_price=2.099, shares=1000, estimated_amount=2099.0,
    )
    for value in hints.limit_prices.values():
        rounded = round(value * 1000)
        assert abs(value * 1000 - rounded) < 1e-6, (
            f"price {value} not on 0.001 tick"
        )


# ---------------------------------------------------------------------------
# Batching plan
# ---------------------------------------------------------------------------


def test_small_orders_use_single_batch() -> None:
    hints = build_pricing_hints(
        action="sell", reference_price=10.0, shares=1000, estimated_amount=10_000.0,
    )
    assert hints.batches == 1
    assert hints.shares_per_batch == [1000]


def test_large_share_orders_split_into_multiple_batches() -> None:
    # 12,000 shares triggers split by share-count breakpoint (5,000 each)
    hints = build_pricing_hints(
        action="sell", reference_price=2.0, shares=12_000, estimated_amount=24_000.0,
    )
    assert hints.batches >= 2
    assert sum(hints.shares_per_batch) == 12_000
    # Lot-aligned
    for batch in hints.shares_per_batch:
        assert batch % 100 == 0 or batch == 12_000 - sum(hints.shares_per_batch[:-1])


def test_large_notional_orders_split_into_multiple_batches() -> None:
    # 1000 shares at ¥50 = ¥50,000 notional, breakpoint is ¥30,000
    hints = build_pricing_hints(
        action="buy", reference_price=50.0, shares=1000, estimated_amount=50_000.0,
    )
    assert hints.batches >= 2
    assert sum(hints.shares_per_batch) == 1000


def test_batch_count_capped_at_three() -> None:
    """Even extreme orders shouldn't suggest more than 3 batches (retail-realistic)."""

    hints = build_pricing_hints(
        action="sell", reference_price=10.0, shares=100_000, estimated_amount=1_000_000.0,
    )
    assert hints.batches <= 3
    assert sum(hints.shares_per_batch) == 100_000


# ---------------------------------------------------------------------------
# Config plumbing
# ---------------------------------------------------------------------------


def test_build_config_from_strategy_json_uses_defaults_when_missing() -> None:
    cfg = build_config_from_strategy_json(None)
    assert isinstance(cfg, PricingConfig)
    assert cfg.tick_size == 0.001
    assert cfg.default_recommendation == "neutral"


def test_build_config_from_strategy_json_overrides_provided_fields() -> None:
    cfg = build_config_from_strategy_json({
        "tick_size": 0.01,
        "aggressive_ticks": 5,
        "default_recommendation": "aggressive",
        "preferred_windows": ["custom window"],
    })
    assert cfg.tick_size == 0.01
    assert cfg.aggressive_ticks == 5
    assert cfg.default_recommendation == "aggressive"
    assert cfg.preferred_windows == ("custom window",)


def test_build_config_from_strategy_json_rejects_unsafe_overrides() -> None:
    cfg = build_config_from_strategy_json({
        "tick_size": 0,
        "aggressive_ticks": "2.5",
        "neutral_ticks": -1,
        "passive_ticks": "bad",
        "default_recommendation": "market",
        "batch_breakpoint_shares": 0,
        "batch_breakpoint_notional": "nan",
        "preferred_windows": "10:00-11:00",
    })
    assert cfg.tick_size == 0.001
    assert cfg.aggressive_ticks == 2
    assert cfg.neutral_ticks == 1
    assert cfg.passive_ticks == 1
    assert cfg.default_recommendation == "neutral"
    assert cfg.batch_breakpoint_shares == 5000
    assert cfg.batch_breakpoint_notional == 30000.0
    assert cfg.preferred_windows == PricingConfig().preferred_windows


def test_bad_batch_config_falls_back_instead_of_crashing() -> None:
    cfg = build_config_from_strategy_json({
        "batch_breakpoint_shares": 0,
        "batch_breakpoint_notional": 0,
    })
    hints = build_pricing_hints(
        action="sell",
        reference_price=10.0,
        shares=12_000,
        estimated_amount=120_000.0,
        config=cfg,
    )
    assert hints is not None
    assert 1 <= hints.batches <= 3
    assert sum(hints.shares_per_batch) == 12_000


def test_hints_to_dict_is_json_serialisable() -> None:
    import json
    hints = build_pricing_hints(
        action="sell", reference_price=10.0, shares=1000, estimated_amount=10_000.0,
    )
    payload = hints.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["recommended_level"] == "neutral"
    assert decoded["limit_prices"]["neutral"] == pytest.approx(9.999)
    assert decoded["batches"] == 1
