"""
交易通知 WebSocket 连接管理器
"""

import logging
from datetime import datetime
from typing import Any, Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class TradeConnectionManager:
    """管理交易通知频道的 WebSocket 连接。"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(
            "Trade WebSocket connected. total_connections=%s",
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(
            "Trade WebSocket disconnected. remaining_connections=%s",
            len(self.active_connections),
        )

    async def send_personal_message(self, websocket: WebSocket, message: Dict[str, Any]):
        try:
            await websocket.send_json(message)
        except Exception as exc:
            logger.warning("Failed to send trade websocket message: %s", exc)
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return

        payload = {
            **message,
            "timestamp": message.get("timestamp") or datetime.now().isoformat(),
        }

        disconnected = []
        for websocket in list(self.active_connections):
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.warning("Failed to broadcast trade websocket message: %s", exc)
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket)


trade_ws_manager = TradeConnectionManager()
