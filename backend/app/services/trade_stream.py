"""
交易流快照与广播辅助工具
"""

from datetime import datetime
from typing import Any, Dict

from src.data.data_manager import DataManager
from src.trading.trade_manager import trade_manager


data_manager = DataManager()


def resolve_trade_portfolio() -> Dict[str, Any]:
    """获取当前交易账户状态，并尽量补全持仓现价。"""
    current_prices = {}

    for symbol in trade_manager.positions.keys():
        try:
            quote = data_manager.get_latest_price(symbol)
            if quote and "price" in quote:
                current_prices[symbol] = quote["price"]
        except Exception:
            continue

    return trade_manager.get_portfolio_status(current_prices)


def build_trade_stream_payload(history_limit: int = 50) -> Dict[str, Any]:
    """构建交易频道推送使用的快照载荷。"""
    return {
        "portfolio": resolve_trade_portfolio(),
        "history": trade_manager.get_history(history_limit),
        "timestamp": datetime.now().isoformat(),
    }
