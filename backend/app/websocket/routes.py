"""
WebSocket路由端点
"""

import asyncio
import hmac
import logging
import os
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.websocket.connection_manager import manager
from backend.app.websocket.trade_connection_manager import trade_ws_manager
from backend.app.services.trade_stream import build_trade_stream_payload
from src.data.realtime_manager import realtime_manager

router = APIRouter()
logger = logging.getLogger(__name__)


_ws_auth_warned = False


def _is_authorized_websocket(websocket: WebSocket) -> bool:
    global _ws_auth_warned
    expected_token = os.getenv("REALTIME_WS_TOKEN")
    if not expected_token:
        if not _ws_auth_warned:
            logger.warning(
                "REALTIME_WS_TOKEN is not set — WebSocket auth is disabled. "
                "Set the environment variable to enforce token-based access control."
            )
            _ws_auth_warned = True
        return True

    provided_token = websocket.query_params.get("token")
    if not provided_token:
        provided_token = websocket.headers.get("x-ws-token")
    return bool(provided_token) and hmac.compare_digest(str(provided_token), expected_token)


async def _send_quote_snapshot(
    websocket: WebSocket,
    symbols: list[str],
    *,
    origin: str,
    cache_first: bool = False,
    allow_fill: bool = True,
) -> None:
    target_symbols = [symbol for symbol in symbols if isinstance(symbol, str)]
    if not target_symbols:
        return

    loop = asyncio.get_running_loop()
    cached_snapshot = {}
    if cache_first:
        cached_snapshot = await loop.run_in_executor(
            None,
            lambda: realtime_manager.get_cached_quotes_dict(target_symbols),
        )
        if cached_snapshot:
            await manager.send_personal_message(websocket, {
                "type": "snapshot",
                "symbols": list(cached_snapshot.keys()),
                "data": cached_snapshot,
                "origin": origin,
                "stage": "cache",
                "timestamp": datetime.now().isoformat(),
            })

    missing_symbols = [symbol for symbol in target_symbols if symbol not in cached_snapshot]
    if not missing_symbols or not allow_fill:
        return

    quotes = await loop.run_in_executor(
        None,
        lambda: realtime_manager.get_quotes_dict(missing_symbols, use_cache=True),
    )
    snapshot_data = {
        symbol: quote
        for symbol, quote in quotes.items()
        if symbol in missing_symbols and quote
    }
    if snapshot_data:
        await manager.send_personal_message(websocket, {
            "type": "snapshot",
            "symbols": list(snapshot_data.keys()),
            "data": snapshot_data,
            "origin": origin,
            "stage": "fill" if cache_first and cached_snapshot else "full",
            "timestamp": datetime.now().isoformat(),
        })


@router.websocket("/ws/quotes")
async def websocket_quotes(websocket: WebSocket):
    """
    WebSocket端点用于实时股票报价
    
    消息格式:
    - 订阅: {"action": "subscribe", "symbol": "AAPL"}
    - 取消订阅: {"action": "unsubscribe", "symbol": "AAPL"}
    - 心跳: {"action": "ping"}
    """
    if not _is_authorized_websocket(websocket):
        await websocket.close(code=1008, reason="Unauthorized realtime websocket")
        return

    await manager.connect(websocket)
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            action = data.get("action", "").lower()
            
            # 支持单个 symbol 或 symbols 列表
            symbols = data.get("symbols", [])
            if not symbols and data.get("symbol"):
                symbols = [data.get("symbol")]
            
            # 统一转大写
            symbols = [s.upper() for s in symbols if isinstance(s, str)]

            if action == "subscribe":
                # 先批量订阅所有股票
                subscription_results = []
                for symbol in symbols:
                    subscription_results.append(await manager.subscribe(websocket, symbol))

                new_symbols = [result["symbol"] for result in subscription_results if result.get("added")]
                if new_symbols:
                    await _send_quote_snapshot(
                        websocket,
                        new_symbols,
                        origin="subscribe",
                        cache_first=True,
                        allow_fill=len(new_symbols) <= 8,
                    )
                    logger.info(
                        "Initial realtime snapshot sent: websocket_symbols=%s snapshots=%s duplicates=%s allow_fill=%s",
                        len(symbols),
                        len(new_symbols),
                        len([result for result in subscription_results if result.get("duplicate")]),
                        len(new_symbols) <= 8,
                    )
            elif action == "snapshot":
                target_symbols = symbols or list(manager.subscriptions.get(websocket, set()))
                if target_symbols:
                    await _send_quote_snapshot(
                        websocket,
                        target_symbols,
                        origin="manual_refresh",
                        cache_first=True,
                    )

            elif action == "unsubscribe":
                for symbol in symbols:
                    await manager.unsubscribe(websocket, symbol)
                
            elif action == "ping":
                await manager.send_personal_message(websocket, {
                    "type": "pong",
                    "timestamp": asyncio.get_running_loop().time()
                })
                
            else:
                await manager.send_personal_message(websocket, {
                    "type": "error",
                    "message": f"Unknown action: {action}"
                })
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.websocket("/ws/trades")
async def websocket_trades(websocket: WebSocket):
    """
    WebSocket端点用于实时交易通知
    """
    if not _is_authorized_websocket(websocket):
        await websocket.close(code=1008, reason="Unauthorized trade websocket")
        return

    await trade_ws_manager.connect(websocket)
    
    try:
        await trade_ws_manager.send_personal_message(websocket, {
            "type": "connected",
            "channel": "trades",
        })
        await trade_ws_manager.send_personal_message(websocket, {
            "type": "trade_snapshot",
            "data": build_trade_stream_payload(),
        })

        while True:
            data = await websocket.receive_json()
            action = str(data.get("action", "")).lower()

            if action == "ping":
                await trade_ws_manager.send_personal_message(websocket, {
                    "type": "pong",
                })
            elif action == "snapshot":
                await trade_ws_manager.send_personal_message(websocket, {
                    "type": "trade_snapshot",
                    "data": build_trade_stream_payload(),
                })
            else:
                await trade_ws_manager.send_personal_message(websocket, {
                    "type": "error",
                    "message": f"Unknown action: {action}",
                })
    except WebSocketDisconnect:
        logger.info("Trade WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Trade WebSocket error: {e}")
    finally:
        trade_ws_manager.disconnect(websocket)
