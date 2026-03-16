"""
WebSocket实时数据推送模块
"""

import asyncio
import logging
from typing import Dict, Set, Any
from datetime import datetime
from fastapi import WebSocket
from src.data.realtime_manager import realtime_manager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # symbol -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # websocket -> set of subscribed symbols
        self.subscriptions: Dict[WebSocket, Set[str]] = {}
        self.loop = None
        
    async def connect(self, websocket: WebSocket):
        """接受新的WebSocket连接"""
        await websocket.accept()
        # 捕获主事件循环
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
            
        self.subscriptions[websocket] = set()
        logger.info(f"New WebSocket connection established. Total connections: {len(self.subscriptions)}")
        
    def disconnect(self, websocket: WebSocket):
        """断开WebSocket连接"""
        # 从所有订阅中移除
        if websocket in self.subscriptions:
            for symbol in list(self.subscriptions[websocket]):
                if symbol in self.active_connections:
                    self.active_connections[symbol].discard(websocket)
                    # 如果没有订阅者了，清理
                    if not self.active_connections[symbol]:
                        del self.active_connections[symbol]
                        # 同时也从 RealTimeManager 取消订阅
                        realtime_manager.unsubscribe_symbol(symbol, self._handle_realtime_update)
            del self.subscriptions[websocket]
        logger.info(f"WebSocket disconnected. Remaining connections: {len(self.subscriptions)}")

    def _handle_realtime_update(self, quote):
        """处理实时数据更新回调 (Sync -> Async Bridge)"""
        try:
            if self.loop and self.loop.is_running():
                symbol = quote.symbol
                # 使用 run_coroutine_threadsafe 将异步任务提交到主事件循环
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_quote(symbol, quote.to_dict()), 
                    self.loop
                )
            else:
                logger.warning("Event loop not available for realtime update")
        except Exception as e:
            logger.error(f"Error handling realtime update for {quote.symbol}: {e}")

    async def subscribe(self, websocket: WebSocket, symbol: str) -> Dict[str, Any]:
        """订阅股票实时数据"""
        symbol = symbol.upper()

        if websocket in self.subscriptions and symbol in self.subscriptions[websocket]:
            logger.info("Duplicate websocket subscribe ignored: symbol=%s", symbol)
            await websocket.send_json({
                "type": "subscription",
                "action": "subscribed",
                "symbol": symbol,
                "duplicate": True,
                "timestamp": datetime.now().isoformat()
            })
            return {"symbol": symbol, "added": False, "duplicate": True}

        is_first_subscriber = symbol not in self.active_connections

        # 添加到订阅列表
        if symbol not in self.active_connections:
            self.active_connections[symbol] = set()
        self.active_connections[symbol].add(websocket)

        if websocket in self.subscriptions:
            self.subscriptions[websocket].add(symbol)

        subscriber_count = len(self.active_connections.get(symbol, set()))
        logger.info(
            "Subscribed to %s. Total subscribers=%s active_symbols=%s",
            symbol,
            subscriber_count,
            len(self.active_connections),
        )

        # 如果是该股票的第一个订阅者，向 RealTimeManager 注册
        if is_first_subscriber:
            realtime_manager.subscribe_symbol(symbol, self._handle_realtime_update)

        # 发送确认消息
        await websocket.send_json({
            "type": "subscription",
            "action": "subscribed",
            "symbol": symbol,
            "duplicate": False,
            "timestamp": datetime.now().isoformat()
        })
        return {"symbol": symbol, "added": True, "duplicate": False}

    async def unsubscribe(self, websocket: WebSocket, symbol: str) -> Dict[str, Any]:
        """取消订阅"""
        symbol = symbol.upper()

        was_subscribed = websocket in self.subscriptions and symbol in self.subscriptions[websocket]

        if symbol in self.active_connections:
            self.active_connections[symbol].discard(websocket)
            # 如果没有订阅者了，从 RealTimeManager 取消订阅
            if not self.active_connections[symbol]:
                del self.active_connections[symbol]
                realtime_manager.unsubscribe_symbol(symbol, self._handle_realtime_update)

        if websocket in self.subscriptions:
            self.subscriptions[websocket].discard(symbol)

        logger.info(
            "Unsubscribed from %s. was_subscribed=%s active_symbols=%s",
            symbol,
            was_subscribed,
            len(self.active_connections),
        )

        await websocket.send_json({
            "type": "subscription",
            "action": "unsubscribed",
            "symbol": symbol,
            "noop": not was_subscribed,
            "timestamp": datetime.now().isoformat()
        })
        return {"symbol": symbol, "removed": was_subscribed}

    async def broadcast_quote(self, symbol: str, quote_data: Dict[str, Any]):
        """向所有订阅者广播股票报价"""
        symbol = symbol.upper()
        
        if symbol not in self.active_connections:
            return
            
        message = {
            "type": "quote",
            "symbol": symbol,
            "data": quote_data,
            "timestamp": datetime.now().isoformat()
        }
        
        # 向所有订阅者发送
        disconnected = []
        for websocket in list(self.active_connections[symbol]):
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to websocket: {e}")
                disconnected.append(websocket)
                
        # 清理断开的连接
        for ws in disconnected:
            self.disconnect(ws)
            
    async def send_personal_message(self, websocket: WebSocket, message: Dict[str, Any]):
        """发送个人消息"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")


# 全局连接管理器实例
manager = ConnectionManager()
