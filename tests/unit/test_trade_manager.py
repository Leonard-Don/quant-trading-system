"""
TradeManager交易管理器单元测试
"""

import math

import pytest

from src.trading.trade_manager import TradeManager


class TestTradeManager:
    """TradeManager测试类"""

    @pytest.fixture
    def fresh_trade_manager(self):
        """创建一个新的TradeManager实例用于测试"""
        # 重置单例
        TradeManager._instance = None
        manager = TradeManager()
        yield manager
        # 清理
        TradeManager._instance = None

    def test_initialization(self, fresh_trade_manager):
        """测试TradeManager初始化"""
        manager = fresh_trade_manager
        assert manager.initial_balance == 100000.0
        assert manager.balance == 100000.0
        assert len(manager.positions) == 0
        assert len(manager.trade_history) == 0

    def test_buy_trade(self, fresh_trade_manager):
        """测试买入交易"""
        manager = fresh_trade_manager

        result = manager.execute_trade(
            symbol="AAPL",
            action="BUY",
            quantity=10,
            price=150.0
        )

        assert result["symbol"] == "AAPL"
        assert result["action"] == "BUY"
        assert result["quantity"] == 10
        assert result["price"] == 150.0
        assert result["total_amount"] == 1500.0
        assert result["pnl"] is None  # 买入没有实现盈亏

        # 检查余额更新
        assert manager.balance == 100000.0 - 1500.0

        # 检查持仓
        assert "AAPL" in manager.positions
        assert manager.positions["AAPL"].quantity == 10
        assert manager.positions["AAPL"].avg_price == 150.0

    def test_sell_trade(self, fresh_trade_manager):
        """测试卖出交易"""
        manager = fresh_trade_manager

        # 先买入
        manager.execute_trade("AAPL", "BUY", 10, 150.0)

        # 再卖出部分
        result = manager.execute_trade("AAPL", "SELL", 5, 160.0)

        assert result["action"] == "SELL"
        assert result["quantity"] == 5
        assert result["pnl"] == 50.0  # (160-150) * 5 = 50

        # 检查持仓减少
        assert manager.positions["AAPL"].quantity == 5

    def test_sell_all_position(self, fresh_trade_manager):
        """测试全部卖出持仓"""
        manager = fresh_trade_manager

        manager.execute_trade("AAPL", "BUY", 10, 150.0)
        manager.execute_trade("AAPL", "SELL", 10, 160.0)

        # 持仓应该被清空
        assert "AAPL" not in manager.positions

    def test_insufficient_funds(self, fresh_trade_manager):
        """测试资金不足"""
        manager = fresh_trade_manager

        with pytest.raises(ValueError, match="Insufficient funds"):
            manager.execute_trade("AAPL", "BUY", 1000, 200.0)  # 需要$200,000

    def test_sell_without_position(self, fresh_trade_manager):
        """测试在没有持仓时卖出"""
        manager = fresh_trade_manager

        with pytest.raises(ValueError, match="No position found"):
            manager.execute_trade("AAPL", "SELL", 10, 150.0)

    def test_sell_more_than_owned(self, fresh_trade_manager):
        """测试卖出超过持有数量"""
        manager = fresh_trade_manager

        manager.execute_trade("AAPL", "BUY", 10, 150.0)

        with pytest.raises(ValueError, match="Insufficient quantity"):
            manager.execute_trade("AAPL", "SELL", 20, 160.0)

    def test_invalid_action(self, fresh_trade_manager):
        """测试无效的交易动作"""
        manager = fresh_trade_manager

        with pytest.raises(ValueError, match="Invalid action"):
            manager.execute_trade("AAPL", "HOLD", 10, 150.0)

    def test_multiple_buys_average_price(self, fresh_trade_manager):
        """测试多次买入的平均成本计算"""
        manager = fresh_trade_manager

        # 第一次买入
        manager.execute_trade("AAPL", "BUY", 10, 100.0)  # 成本 1000
        # 第二次买入
        manager.execute_trade("AAPL", "BUY", 10, 200.0)  # 成本 2000

        # 平均成本应该是 (1000 + 2000) / 20 = 150
        assert manager.positions["AAPL"].quantity == 20
        assert manager.positions["AAPL"].avg_price == 150.0

    def test_get_portfolio_status(self, fresh_trade_manager):
        """测试获取投资组合状态"""
        manager = fresh_trade_manager

        manager.execute_trade("AAPL", "BUY", 10, 150.0)

        status = manager.get_portfolio_status({"AAPL": 160.0})

        assert status["balance"] == 98500.0
        assert status["total_market_value"] == 1600.0
        assert status["total_equity"] == 100100.0
        assert status["total_pnl"] == 100.0
        assert len(status["positions"]) == 1

    def test_get_history(self, fresh_trade_manager):
        """测试获取交易历史"""
        manager = fresh_trade_manager

        manager.execute_trade("AAPL", "BUY", 10, 150.0)
        manager.execute_trade("MSFT", "BUY", 5, 300.0)

        history = manager.get_history(limit=10)

        assert len(history) == 2
        # 最新交易在前
        assert history[0]["symbol"] == "MSFT"
        assert history[1]["symbol"] == "AAPL"

    def test_reset_account(self, fresh_trade_manager):
        """测试重置账户"""
        manager = fresh_trade_manager

        manager.execute_trade("AAPL", "BUY", 10, 150.0)
        manager.reset_account()

        assert manager.balance == 100000.0
        assert len(manager.positions) == 0
        assert len(manager.trade_history) == 0

    def test_symbol_case_insensitive(self, fresh_trade_manager):
        """测试股票代码大小写不敏感"""
        manager = fresh_trade_manager

        manager.execute_trade("aapl", "BUY", 10, 150.0)

        assert "AAPL" in manager.positions

    def test_action_lowercase_is_normalized(self, fresh_trade_manager):
        """Lowercase action strings should be normalized to upper-case."""
        manager = fresh_trade_manager

        buy_result = manager.execute_trade("AAPL", "buy", 10, 150.0)
        sell_result = manager.execute_trade("AAPL", "sell", 4, 200.0)

        assert buy_result["action"] == "BUY"
        assert sell_result["action"] == "SELL"
        assert manager.positions["AAPL"].quantity == 6

    def test_get_history_limit_zero_returns_empty(self, fresh_trade_manager):
        """A limit of zero must return an empty history slice."""
        manager = fresh_trade_manager
        manager.execute_trade("AAPL", "BUY", 1, 10.0)

        assert manager.get_history(limit=0) == []

    def test_get_history_limit_exceeds_count_returns_all(self, fresh_trade_manager):
        """Asking for more entries than exist returns the full history."""
        manager = fresh_trade_manager
        manager.execute_trade("AAPL", "BUY", 1, 10.0)
        manager.execute_trade("MSFT", "BUY", 2, 20.0)

        history = manager.get_history(limit=100)

        assert len(history) == 2
        assert history[0]["symbol"] == "MSFT"
        assert history[1]["symbol"] == "AAPL"

    def test_portfolio_status_no_argument_falls_back_to_avg_price(self, fresh_trade_manager):
        """Without prices, market value should fall back to position avg_price."""
        manager = fresh_trade_manager
        manager.execute_trade("AAPL", "BUY", 10, 150.0)

        status = manager.get_portfolio_status()

        assert status["total_market_value"] == 1500.0
        assert status["total_pnl"] == 0.0
        assert status["positions"][0]["unrealized_pnl"] == 0.0
        assert status["positions"][0]["unrealized_pnl_percent"] == 0.0

    def test_portfolio_status_partial_prices_uses_fallback_per_symbol(self, fresh_trade_manager):
        """Symbols missing from the price map should fall back to avg_price."""
        manager = fresh_trade_manager
        manager.execute_trade("AAPL", "BUY", 10, 100.0)
        manager.execute_trade("MSFT", "BUY", 5, 200.0)

        status = manager.get_portfolio_status({"AAPL": 110.0})

        positions = {p["symbol"]: p for p in status["positions"]}
        assert positions["AAPL"]["current_price"] == 110.0
        assert positions["AAPL"]["unrealized_pnl"] == 100.0
        assert positions["MSFT"]["current_price"] == 200.0  # fallback
        assert positions["MSFT"]["unrealized_pnl"] == 0.0

    def test_portfolio_status_with_no_positions(self, fresh_trade_manager):
        """Empty portfolio should yield zeroed market value and equity == balance."""
        manager = fresh_trade_manager

        status = manager.get_portfolio_status({"AAPL": 999.0})

        assert status["positions"] == []
        assert status["total_market_value"] == 0.0
        assert status["total_equity"] == manager.balance
        assert status["total_pnl"] == 0.0

    def test_partial_sell_balance_and_pnl_invariants(self, fresh_trade_manager):
        """Partial sell should adjust balance, leave avg_price intact, and report realized PnL."""
        manager = fresh_trade_manager
        manager.execute_trade("AAPL", "BUY", 10, 150.0)  # spend 1500
        starting_balance = manager.balance

        result = manager.execute_trade("AAPL", "SELL", 4, 175.0)  # gain 700

        assert manager.balance == starting_balance + 700.0
        assert result["pnl"] == (175.0 - 150.0) * 4
        # avg_price should remain unchanged on a partial sell
        assert manager.positions["AAPL"].quantity == 6
        assert manager.positions["AAPL"].avg_price == 150.0
        assert result["balance_after"] == manager.balance

    def test_final_sell_clears_position_and_recovers_cash(self, fresh_trade_manager):
        """Selling the last share should remove the position and restore total cash."""
        manager = fresh_trade_manager
        initial = manager.balance

        manager.execute_trade("AAPL", "BUY", 10, 150.0)
        manager.execute_trade("AAPL", "SELL", 6, 150.0)
        manager.execute_trade("AAPL", "SELL", 4, 150.0)

        assert "AAPL" not in manager.positions
        assert manager.balance == initial  # break-even round trip

    def test_buy_rejects_zero_quantity(self, fresh_trade_manager):
        """Zero-quantity buys must be rejected (would create a phantom position)."""
        manager = fresh_trade_manager

        with pytest.raises(ValueError, match="quantity"):
            manager.execute_trade("AAPL", "BUY", 0, 150.0)

        assert "AAPL" not in manager.positions
        assert manager.trade_history == []
        assert manager.balance == manager.initial_balance

    def test_buy_rejects_negative_quantity(self, fresh_trade_manager):
        """Negative-quantity buys must be rejected (would credit cash and create short)."""
        manager = fresh_trade_manager

        with pytest.raises(ValueError, match="quantity"):
            manager.execute_trade("AAPL", "BUY", -5, 150.0)

        assert "AAPL" not in manager.positions
        assert manager.balance == manager.initial_balance

    def test_buy_rejects_zero_price(self, fresh_trade_manager):
        """Zero-price buys must be rejected (would mint free shares)."""
        manager = fresh_trade_manager

        with pytest.raises(ValueError, match="price"):
            manager.execute_trade("AAPL", "BUY", 10, 0.0)

        assert "AAPL" not in manager.positions

    def test_buy_rejects_negative_price(self, fresh_trade_manager):
        """Negative-price buys must be rejected (would credit cash)."""
        manager = fresh_trade_manager

        with pytest.raises(ValueError, match="price"):
            manager.execute_trade("AAPL", "BUY", 10, -50.0)

        assert manager.balance == manager.initial_balance

    def test_sell_rejects_zero_quantity(self, fresh_trade_manager):
        """Zero-quantity sells must be rejected (no-op trade with bogus history entry)."""
        manager = fresh_trade_manager
        manager.execute_trade("AAPL", "BUY", 10, 150.0)
        balance_before = manager.balance
        history_len = len(manager.trade_history)

        with pytest.raises(ValueError, match="quantity"):
            manager.execute_trade("AAPL", "SELL", 0, 175.0)

        assert manager.balance == balance_before
        assert len(manager.trade_history) == history_len
        assert manager.positions["AAPL"].quantity == 10

    def test_sell_rejects_negative_quantity(self, fresh_trade_manager):
        """Negative-quantity sells must be rejected."""
        manager = fresh_trade_manager
        manager.execute_trade("AAPL", "BUY", 10, 150.0)

        with pytest.raises(ValueError, match="quantity"):
            manager.execute_trade("AAPL", "SELL", -3, 175.0)

        assert manager.positions["AAPL"].quantity == 10

    def test_sell_rejects_non_positive_price(self, fresh_trade_manager):
        """Non-positive sell prices must be rejected."""
        manager = fresh_trade_manager
        manager.execute_trade("AAPL", "BUY", 10, 150.0)

        with pytest.raises(ValueError, match="price"):
            manager.execute_trade("AAPL", "SELL", 5, 0.0)
        with pytest.raises(ValueError, match="price"):
            manager.execute_trade("AAPL", "SELL", 5, -10.0)

        assert manager.positions["AAPL"].quantity == 10

    def test_rejects_non_finite_quantity_and_price(self, fresh_trade_manager):
        """NaN/Inf quantities or prices must not mutate cash, positions, or history."""
        manager = fresh_trade_manager

        invalid_orders = [
            ("AAPL", "BUY", math.inf, 150.0, "quantity"),
            ("AAPL", "BUY", math.nan, 150.0, "quantity"),
            ("AAPL", "BUY", 10, math.inf, "price"),
            ("AAPL", "BUY", 10, math.nan, "price"),
        ]
        for symbol, action, quantity, price, message in invalid_orders:
            with pytest.raises(ValueError, match=message):
                manager.execute_trade(symbol, action, quantity, price)

        assert manager.balance == manager.initial_balance
        assert manager.positions == {}
        assert manager.trade_history == []
