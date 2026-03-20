"""
交易流快照与广播辅助工具
"""

from datetime import datetime
from typing import Any, Dict

from src.data.data_manager import DataManager
from src.data.realtime_manager import realtime_manager
from src.trading.trade_manager import trade_manager


data_manager = DataManager()


def resolve_trade_portfolio() -> Dict[str, Any]:
    """获取当前交易账户状态，并尽量补全持仓现价。"""
    current_prices = {}
    symbols = list(trade_manager.positions.keys())

    if symbols:
        try:
            realtime_quotes = realtime_manager.get_quotes_dict(symbols, use_cache=True)
            for symbol in symbols:
                realtime_price = realtime_quotes.get(symbol, {}).get("price")
                if realtime_price is not None:
                    current_prices[symbol] = realtime_price
        except Exception:
            pass

    for symbol in symbols:
        if symbol in current_prices:
            continue
        try:
            quote = data_manager.get_latest_price(symbol)
            if quote and "price" in quote and quote["price"] is not None:
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
