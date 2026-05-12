"""Unit tests for the paper trading matching engine (Q1/Q2 slice).

Q1: pending LIMIT orders auto-fill from a market price/tick input.
Q2: open positions auto-close when stop_loss_price or take_profit_price
    is reached by the current market price.

The engine is a thin orchestrator on top of ``PaperTradingStore`` — it
reuses the existing ledger semantics (cash, positions, orders history,
pending_orders) instead of re-implementing them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.paper_trading import PaperTradingStore
from backend.app.services.paper_trading_engine import PaperTradingEngine


@pytest.fixture
def store(tmp_path: Path) -> PaperTradingStore:
    return PaperTradingStore(storage_path=tmp_path)


@pytest.fixture
def engine(store: PaperTradingStore) -> PaperTradingEngine:
    return PaperTradingEngine(store=store)


# ---------------------------------------------------------------------------
# Q1: pending LIMIT auto-fill from market tick
# ---------------------------------------------------------------------------


def test_buy_limit_fills_when_market_price_below_limit(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 95.0,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 94.0, profile_id="alice")

    assert len(result["filled_orders"]) == 1
    filled = result["filled_orders"][0]
    assert filled["symbol"] == "AAPL"
    assert filled["side"] == "BUY"
    assert filled["quantity"] == 5

    account = result["account"]
    assert account["pending_orders"] == []
    assert len(account["positions"]) == 1
    assert account["positions"][0]["symbol"] == "AAPL"
    assert account["positions"][0]["quantity"] == 5


def test_buy_limit_does_not_fill_when_market_above_limit(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 95.0,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 96.0, profile_id="alice")

    assert result["filled_orders"] == []
    account = result["account"]
    assert len(account["pending_orders"]) == 1
    assert account["pending_orders"][0]["limit_price"] == pytest.approx(95.0)
    assert account["positions"] == []
    # Cash untouched while order is still pending.
    assert account["cash"] == pytest.approx(10000.0)


def test_buy_limit_fills_at_exact_limit_price(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 95.0,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 95.0, profile_id="alice")

    assert len(result["filled_orders"]) == 1
    assert result["account"]["pending_orders"] == []


def test_sell_limit_fills_when_market_at_or_above_limit(store, engine):
    # SELL LIMIT requires a position first.
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 10,
            "order_type": "LIMIT",
            "limit_price": 110.0,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 111.0, profile_id="alice")

    assert len(result["filled_orders"]) == 1
    assert result["filled_orders"][0]["side"] == "SELL"
    account = result["account"]
    assert account["pending_orders"] == []
    assert account["positions"] == []
    # Cash should reflect: 10000 - 10 * 100 (BUY) + 10 * 111 (SELL @ market)
    assert account["cash"] == pytest.approx(10000.0 - 1000.0 + 1110.0)


def test_sell_limit_does_not_fill_when_market_below_limit(store, engine):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": 10,
            "order_type": "LIMIT",
            "limit_price": 110.0,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 105.0, profile_id="alice")

    assert result["filled_orders"] == []
    assert len(result["account"]["pending_orders"]) == 1
    # Position still intact since SELL didn't fire.
    assert result["account"]["positions"][0]["quantity"] == 10


def test_buy_limit_uses_market_price_as_fill_price(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 95.0,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 90.0, profile_id="alice")

    filled = result["filled_orders"][0]
    assert filled["fill_price"] == pytest.approx(90.0)
    account = result["account"]
    # Cash debited at the better (lower) market price, not at limit.
    assert account["cash"] == pytest.approx(10000.0 - 5 * 90.0)
    assert account["positions"][0]["avg_cost"] == pytest.approx(90.0)


def test_limit_fill_recorded_in_orders_history(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 95.0,
        },
        profile_id="alice",
    )

    engine.on_market_tick("AAPL", 94.0, profile_id="alice")

    orders = store.list_orders(profile_id="alice")
    assert len(orders) == 1
    assert orders[0]["symbol"] == "AAPL"
    assert orders[0]["side"] == "BUY"
    assert orders[0]["quantity"] == 5


def test_only_pending_orders_for_tick_symbol_evaluated(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 95.0,
        },
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "MSFT",
            "side": "BUY",
            "quantity": 2,
            "order_type": "LIMIT",
            "limit_price": 200.0,
        },
        profile_id="alice",
    )

    # Tick MSFT below its limit — only MSFT's pending fills.
    result = engine.on_market_tick("MSFT", 195.0, profile_id="alice")

    assert len(result["filled_orders"]) == 1
    assert result["filled_orders"][0]["symbol"] == "MSFT"

    account = result["account"]
    pending_symbols = [order["symbol"] for order in account["pending_orders"]]
    assert pending_symbols == ["AAPL"]


def test_tick_for_symbol_with_no_pending_orders_is_noop_for_q1(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 95.0,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("MSFT", 50.0, profile_id="alice")

    assert result["filled_orders"] == []
    assert len(result["account"]["pending_orders"]) == 1


def test_engine_isolates_per_profile(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 95.0,
        },
        profile_id="alice",
    )

    # Bob has no pending — alice's pending must stay untouched.
    result = engine.on_market_tick("AAPL", 90.0, profile_id="bob")

    assert result["filled_orders"] == []
    alice_account = store.get_account(profile_id="alice")
    assert len(alice_account["pending_orders"]) == 1


# ---------------------------------------------------------------------------
# Q2: stop_loss / take_profit auto-close
# ---------------------------------------------------------------------------


def test_stop_loss_triggers_when_market_below_stop_price(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    # stop_loss_price = 100 * (1 - 0.05) = 95

    result = engine.on_market_tick("AAPL", 94.0, profile_id="alice")

    assert len(result["closed_positions"]) == 1
    closed = result["closed_positions"][0]
    assert closed["symbol"] == "AAPL"
    assert closed["reason"] == "stop_loss"
    assert closed["quantity"] == 10

    account = result["account"]
    assert account["positions"] == []
    # Cash: 10000 - 10*100 (BUY) + 10*94 (SELL @ market)
    assert account["cash"] == pytest.approx(10000.0 - 1000.0 + 940.0)


def test_stop_loss_triggers_at_exact_stop_price(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 95.0, profile_id="alice")

    assert len(result["closed_positions"]) == 1
    assert result["account"]["positions"] == []


def test_stop_loss_does_not_trigger_above_stop(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 96.0, profile_id="alice")

    assert result["closed_positions"] == []
    assert len(result["account"]["positions"]) == 1
    assert result["account"]["positions"][0]["quantity"] == 10


def test_take_profit_triggers_when_market_above_target(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "take_profit_pct": 0.10,
        },
        profile_id="alice",
    )
    # take_profit_price = 100 * 1.10 = 110

    result = engine.on_market_tick("AAPL", 111.0, profile_id="alice")

    assert len(result["closed_positions"]) == 1
    closed = result["closed_positions"][0]
    assert closed["symbol"] == "AAPL"
    assert closed["reason"] == "take_profit"

    account = result["account"]
    assert account["positions"] == []
    assert account["cash"] == pytest.approx(10000.0 - 1000.0 + 10 * 111.0)


def test_take_profit_triggers_at_exact_target(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "take_profit_pct": 0.10,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 110.0, profile_id="alice")

    assert len(result["closed_positions"]) == 1
    assert result["account"]["positions"] == []


def test_take_profit_does_not_trigger_below_target(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "take_profit_pct": 0.10,
        },
        profile_id="alice",
    )

    result = engine.on_market_tick("AAPL", 105.0, profile_id="alice")

    assert result["closed_positions"] == []
    assert len(result["account"]["positions"]) == 1


def test_position_without_sl_or_tp_unaffected_by_market_tick(store, engine):
    store.submit_order(
        {"symbol": "AAPL", "side": "BUY", "quantity": 10, "fill_price": 100.0},
        profile_id="alice",
    )

    # Even an extreme tick should not auto-close a position with no SL/TP.
    result = engine.on_market_tick("AAPL", 50.0, profile_id="alice")

    assert result["closed_positions"] == []
    assert len(result["account"]["positions"]) == 1
    assert result["account"]["positions"][0]["quantity"] == 10


def test_only_positions_for_tick_symbol_evaluated(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    store.submit_order(
        {
            "symbol": "MSFT",
            "side": "BUY",
            "quantity": 5,
            "fill_price": 200.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )
    # AAPL stop is at 95, MSFT stop at 190.
    # Tick MSFT at 100 (well below MSFT stop) — only MSFT closes.
    result = engine.on_market_tick("MSFT", 100.0, profile_id="alice")

    assert len(result["closed_positions"]) == 1
    assert result["closed_positions"][0]["symbol"] == "MSFT"

    aapl_positions = [
        position
        for position in result["account"]["positions"]
        if position["symbol"] == "AAPL"
    ]
    assert len(aapl_positions) == 1
    assert aapl_positions[0]["quantity"] == 10


def test_auto_close_records_sell_in_orders_history(store, engine):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "fill_price": 100.0,
            "stop_loss_pct": 0.05,
        },
        profile_id="alice",
    )

    engine.on_market_tick("AAPL", 94.0, profile_id="alice")

    orders = store.list_orders(profile_id="alice")
    # Two orders: original BUY plus auto-close SELL.
    assert len(orders) == 2
    sells = [order for order in orders if order["side"] == "SELL"]
    assert len(sells) == 1
    assert sells[0]["symbol"] == "AAPL"
    assert sells[0]["quantity"] == 10


def test_tick_persists_to_disk(store, engine, tmp_path):
    store.submit_order(
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 5,
            "order_type": "LIMIT",
            "limit_price": 95.0,
        },
        profile_id="alice",
    )

    engine.on_market_tick("AAPL", 94.0, profile_id="alice")

    fresh_store = PaperTradingStore(storage_path=tmp_path)
    fresh_account = fresh_store.get_account(profile_id="alice")
    assert fresh_account["pending_orders"] == []
    assert len(fresh_account["positions"]) == 1
    assert fresh_account["positions"][0]["symbol"] == "AAPL"
