"""
TradeManager交易管理器单元测试
"""

import pytest
from unittest.mock import patch
from src.trading.trade_manager import TradeManager, Trade, Position


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
