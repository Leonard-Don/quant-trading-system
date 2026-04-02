"""
WebSocket路由端点
"""

import asyncio
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


def _is_authorized_websocket(websocket: WebSocket) -> bool:
    expected_token = os.getenv("REALTIME_WS_TOKEN")
    if not expected_token:
        return True

    provided_token = websocket.query_params.get("token")
    return bool(provided_token) and provided_token == expected_token


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
                    loop = asyncio.get_running_loop()
                    quotes = await loop.run_in_executor(
                        None, realtime_manager.get_quotes_dict, new_symbols, True
                    )
                    snapshot_data = {
                        symbol: quote
                        for symbol, quote in quotes.items()
                        if symbol in new_symbols and quote
                    }
                    if snapshot_data:
                        await manager.send_personal_message(websocket, {
                            "type": "snapshot",
                            "symbols": list(snapshot_data.keys()),
                            "data": snapshot_data,
                            "origin": "subscribe",
                            "timestamp": datetime.now().isoformat(),
                        })

                    logger.info(
                        "Initial realtime snapshot sent: websocket_symbols=%s snapshots=%s duplicates=%s",
                        len(symbols),
                        len(snapshot_data),
                        len([result for result in subscription_results if result.get("duplicate")]),
                    )
            elif action == "snapshot":
                target_symbols = symbols or list(manager.subscriptions.get(websocket, set()))
                if target_symbols:
                    loop = asyncio.get_running_loop()
                    quotes = await loop.run_in_executor(
                        None, realtime_manager.get_quotes_dict, target_symbols, True
                    )
                    snapshot_data = {
                        symbol: quote
                        for symbol, quote in quotes.items()
                        if symbol in target_symbols and quote
                    }
                    await manager.send_personal_message(websocket, {
                        "type": "snapshot",
                        "symbols": list(snapshot_data.keys()),
                        "data": snapshot_data,
                        "origin": "manual_refresh",
                        "timestamp": datetime.now().isoformat(),
                    })

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
