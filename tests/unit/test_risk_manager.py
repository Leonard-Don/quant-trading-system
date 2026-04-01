import pandas as pd

from src.backtest.risk_manager import RiskAction, RiskContext, RiskManager


def make_context(**overrides):
    context = RiskContext(
        current_price=100.0,
        current_date=pd.Timestamp("2024-01-10"),
        position_size=10.0,
        entry_price=100.0,
        entry_date=pd.Timestamp("2024-01-01"),
        current_equity=10_000.0,
        peak_equity=10_500.0,
        initial_capital=10_000.0,
        daily_return=0.0,
        recent_trade_pnls=[100.0, -50.0],
    )
    for key, value in overrides.items():
        setattr(context, key, value)
    return context


def test_risk_manager_stop_loss_forces_exit():
    manager = RiskManager(stop_loss_pct=0.05)
    decision = manager.evaluate(make_context(current_price=94.0))

    assert decision.action is RiskAction.FORCE_EXIT
    assert "stop_loss" in decision.triggered_rules


def test_risk_manager_take_profit_forces_exit():
    manager = RiskManager(take_profit_pct=0.08)
    decision = manager.evaluate(make_context(current_price=109.0))

    assert decision.action is RiskAction.FORCE_EXIT
    assert "take_profit" in decision.triggered_rules


def test_risk_manager_blocks_entry_after_drawdown_breach():
    manager = RiskManager(max_drawdown_limit=0.10)
    decision = manager.evaluate(make_context(position_size=0.0, current_equity=8_900.0, peak_equity=10_000.0))

    assert decision.action is RiskAction.BLOCK_ENTRY
    assert "max_drawdown_limit" in decision.triggered_rules


def test_risk_manager_enforces_daily_loss_limit():
    manager = RiskManager(max_daily_loss_pct=0.03)
    decision = manager.evaluate(make_context(daily_return=-0.04))

    assert decision.action is RiskAction.FORCE_EXIT
    assert "max_daily_loss" in decision.triggered_rules


def test_risk_manager_blocks_entry_after_consecutive_losses():
    manager = RiskManager(max_consecutive_losses=3)
    decision = manager.evaluate(
        make_context(
            position_size=0.0,
            recent_trade_pnls=[50.0, -10.0, -20.0, -30.0],
        )
    )

    assert decision.action is RiskAction.BLOCK_ENTRY
    assert "max_consecutive_losses" in decision.triggered_rules


def test_risk_manager_time_stop_forces_exit():
    manager = RiskManager(max_holding_days=5)
    decision = manager.evaluate(
        make_context(
            current_date=pd.Timestamp("2024-01-10"),
            entry_date=pd.Timestamp("2024-01-01"),
        )
    )

    assert decision.action is RiskAction.FORCE_EXIT
    assert "max_holding_days" in decision.triggered_rules


def test_risk_manager_volatility_scaling_reduces_size_when_realized_vol_is_high():
    manager = RiskManager(volatility_scaling=True, volatility_target=0.10, volatility_lookback=5)
    for daily_return in [0.06, -0.05, 0.07, -0.06]:
        manager.evaluate(make_context(daily_return=daily_return))

    decision = manager.evaluate(make_context(daily_return=0.05))

    assert decision.action is RiskAction.REDUCE_SIZE
    assert decision.scale_factor < 1.0
    assert "volatility_scaling" in decision.triggered_rules


def test_risk_manager_summary_includes_time_stop_rule():
    manager = RiskManager(max_holding_days=7)
    summary = manager.summary()

    assert summary["rules"]["max_holding_days"] == 7
