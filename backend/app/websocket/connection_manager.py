"""
WebSocket实时数据推送模块
"""

import asyncio
import logging
from typing import Dict, Set, Any, Optional, Tuple
from datetime import datetime
from fastapi import WebSocket
from src.data.realtime_manager import realtime_manager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket连接管理器"""

    OUTBOUND_QUEUE_MAXSIZE = 128

    def __init__(self):
        # symbol -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # websocket -> set of subscribed symbols
        self.subscriptions: Dict[WebSocket, Set[str]] = {}
        self._send_queues: Dict[WebSocket, asyncio.Queue[Tuple[Dict[str, Any], Optional[asyncio.Future]]]] = {}
        self._send_tasks: Dict[WebSocket, asyncio.Task] = {}
        self.loop = None

    async def connect(self, websocket: WebSocket):
        """接受新的WebSocket连接"""
        await websocket.accept()
        # 捕获主事件循环
        if self.loop is None:
            self.loop = asyncio.get_running_loop()

        self.subscriptions[websocket] = set()
        self._send_queues[websocket] = asyncio.Queue(maxsize=self.OUTBOUND_QUEUE_MAXSIZE)
        self._send_tasks[websocket] = asyncio.create_task(
            self._socket_sender(websocket),
            name=f"realtime-ws-sender-{id(websocket)}",
        )
        logger.info(f"New WebSocket connection established. Total connections: {len(self.subscriptions)}")

    def disconnect(self, websocket: WebSocket):
        """断开WebSocket连接"""
        send_task = self._send_tasks.pop(websocket, None)
        if send_task is not None:
            send_task.cancel()

        pending_queue = self._send_queues.pop(websocket, None)
        if pending_queue is not None:
            self._fail_pending_messages(pending_queue)

        was_connected = websocket in self.subscriptions
        # 从所有订阅中移除
        if was_connected:
            for symbol in list(self.subscriptions[websocket]):
                if symbol in self.active_connections:
                    self.active_connections[symbol].discard(websocket)
                    # 如果没有订阅者了，清理
                    if not self.active_connections[symbol]:
                        del self.active_connections[symbol]
                        # 同时也从 RealTimeManager 取消订阅
                        realtime_manager.unsubscribe_symbol(symbol, self._handle_realtime_update)
            del self.subscriptions[websocket]
        if was_connected:
            logger.info(f"WebSocket disconnected. Remaining connections: {len(self.subscriptions)}")

    def _resolve_delivery(self, delivery_future: Optional[asyncio.Future], value: bool) -> None:
        if delivery_future is None or delivery_future.done():
            return

        def _set_result() -> None:
            if not delivery_future.done():
                delivery_future.set_result(value)

        delivery_future.get_loop().call_soon_threadsafe(_set_result)

    def _fail_pending_messages(self, queue: asyncio.Queue) -> None:
        while True:
            try:
                _, delivery_future = queue.get_nowait()
                queue.task_done()
                self._resolve_delivery(delivery_future, False)
            except asyncio.QueueEmpty:
                break

    async def _socket_sender(self, websocket: WebSocket) -> None:
        queue = self._send_queues.get(websocket)
        if queue is None:
            return

        try:
            while True:
                message, delivery_future = await queue.get()
                try:
                    await websocket.send_json(message)
                    self._resolve_delivery(delivery_future, True)
                except Exception as exc:
                    logger.info("Dropping websocket connection after send failure: %s", exc)
                    self._resolve_delivery(delivery_future, False)
                    self.disconnect(websocket)
                    return
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            raise
        finally:
            self._fail_pending_messages(queue)

    async def _send_direct_message(self, websocket: WebSocket, message: Dict[str, Any]) -> bool:
        try:
            await websocket.send_json(message)
            return True
        except Exception as exc:
            logger.info("Dropping websocket connection after send failure: %s", exc)
            self.disconnect(websocket)
            return False

    def _enqueue_message(
        self,
        websocket: WebSocket,
        message: Dict[str, Any],
        delivery_future: Optional[asyncio.Future] = None,
    ) -> bool:
        queue = self._send_queues.get(websocket)
        if queue is None:
            return False

        if delivery_future is None and message.get("type") == "quote":
            if self._replace_pending_quote(queue, message):
                return True

        try:
            queue.put_nowait((message, delivery_future))
            return True
        except asyncio.QueueFull:
            logger.warning(
                "Realtime websocket outbound queue overflow. Disconnecting websocket=%s queue_size=%s",
                id(websocket),
                queue.qsize(),
            )
            self._resolve_delivery(delivery_future, False)
            self.disconnect(websocket)
            return False

    def _replace_pending_quote(self, queue: asyncio.Queue, message: Dict[str, Any]) -> bool:
        """如果队列里已有同 symbol 的未发送 quote，则只保留最新值。"""
        symbol = str(message.get("symbol") or "").upper()
        if not symbol:
            return False

        pending_items = queue._queue  # asyncio.Queue uses deque internally.
        for index in range(len(pending_items) - 1, -1, -1):
            pending_message, delivery_future = pending_items[index]
            if delivery_future is not None:
                continue
            if pending_message.get("type") != "quote":
                continue
            if str(pending_message.get("symbol") or "").upper() != symbol:
                continue
            pending_items[index] = (message, None)
            return True
        return False

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

        direct_deliveries = []
        for websocket in list(self.active_connections[symbol]):
            if websocket not in self.subscriptions:
                continue
            if self._send_queues.get(websocket) is None:
                direct_deliveries.append(self._send_direct_message(websocket, message))
                continue
            self._enqueue_message(websocket, message)

        if direct_deliveries:
            await asyncio.gather(*direct_deliveries, return_exceptions=True)

    async def send_personal_message(self, websocket: WebSocket, message: Dict[str, Any]) -> bool:
        """发送个人消息"""
        if websocket not in self.subscriptions:
            return False

        queue = self._send_queues.get(websocket)
        if queue is None:
            return await self._send_direct_message(websocket, message)

        delivery_future = asyncio.get_running_loop().create_future()
        if not self._enqueue_message(websocket, message, delivery_future):
            return False
        return await delivery_future


# 全局连接管理器实例
manager = ConnectionManager()
