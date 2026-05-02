"""
交易通知 WebSocket 连接管理器
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class TradeConnectionManager:
    """管理交易通知频道的 WebSocket 连接。"""

    OUTBOUND_QUEUE_MAXSIZE = 64

    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self._send_queues: dict[WebSocket, asyncio.Queue[tuple[dict[str, Any], Optional[asyncio.Future]]]] = {}
        self._send_tasks: dict[WebSocket, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        self._send_queues[websocket] = asyncio.Queue(maxsize=self.OUTBOUND_QUEUE_MAXSIZE)
        self._send_tasks[websocket] = asyncio.create_task(
            self._socket_sender(websocket),
            name=f"trade-ws-sender-{id(websocket)}",
        )
        logger.info(
            "Trade WebSocket connected. total_connections=%s",
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket):
        send_task = self._send_tasks.pop(websocket, None)
        if send_task is not None:
            send_task.cancel()

        pending_queue = self._send_queues.pop(websocket, None)
        if pending_queue is not None:
            self._fail_pending_messages(pending_queue)

        was_connected = websocket in self.active_connections
        self.active_connections.discard(websocket)
        if was_connected:
            logger.info(
                "Trade WebSocket disconnected. remaining_connections=%s",
                len(self.active_connections),
            )

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
                    logger.info("Dropping trade websocket connection after send failure: %s", exc)
                    self._resolve_delivery(delivery_future, False)
                    self.disconnect(websocket)
                    return
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            raise
        finally:
            self._fail_pending_messages(queue)

    async def _send_direct_message(self, websocket: WebSocket, message: dict[str, Any]) -> bool:
        try:
            await websocket.send_json(message)
            return True
        except Exception as exc:
            logger.info("Dropping trade websocket connection after send failure: %s", exc)
            self.disconnect(websocket)
            return False

    def _enqueue_message(
        self,
        websocket: WebSocket,
        message: dict[str, Any],
        delivery_future: Optional[asyncio.Future] = None,
    ) -> bool:
        queue = self._send_queues.get(websocket)
        if queue is None:
            return False

        try:
            queue.put_nowait((message, delivery_future))
            return True
        except asyncio.QueueFull:
            logger.warning(
                "Trade websocket outbound queue overflow. Disconnecting websocket=%s queue_size=%s",
                id(websocket),
                queue.qsize(),
            )
            self._resolve_delivery(delivery_future, False)
            self.disconnect(websocket)
            return False

    async def send_personal_message(self, websocket: WebSocket, message: dict[str, Any]) -> bool:
        if websocket not in self.active_connections:
            return False
        queue = self._send_queues.get(websocket)
        if queue is None:
            return await self._send_direct_message(websocket, message)

        delivery_future = asyncio.get_running_loop().create_future()
        if not self._enqueue_message(websocket, message, delivery_future):
            return False
        return await delivery_future

    async def broadcast(self, message: dict[str, Any]):
        if not self.active_connections:
            return

        payload = {
            **message,
            "timestamp": message.get("timestamp") or datetime.now().isoformat(),
        }

        await asyncio.gather(
            *(self.send_personal_message(websocket, payload) for websocket in list(self.active_connections)),
            return_exceptions=True,
        )


trade_ws_manager = TradeConnectionManager()
