"""
WebSocket路由端点
"""

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.websocket.connection_manager import manager
from src.data.realtime_manager import realtime_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/quotes")
async def websocket_quotes(websocket: WebSocket):
    """
    WebSocket端点用于实时股票报价
    
    消息格式:
    - 订阅: {"action": "subscribe", "symbol": "AAPL"}
    - 取消订阅: {"action": "unsubscribe", "symbol": "AAPL"}
    - 心跳: {"action": "ping"}
    """
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
                    for symbol in new_symbols:
                        quote = quotes.get(symbol)
                        if quote:
                            await manager.send_personal_message(websocket, {
                                "type": "quote",
                                "symbol": symbol,
                                "data": quote,
                                "timestamp": quote["timestamp"],
                            })

                    logger.info(
                        "Initial realtime snapshot sent: websocket_symbols=%s snapshots=%s duplicates=%s",
                        len(symbols),
                        len(new_symbols),
                        len([result for result in subscription_results if result.get("duplicate")]),
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
    await manager.connect(websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            # 处理交易相关消息
            await manager.send_personal_message(websocket, {
                "type": "ack",
                "message": "Trade notification channel connected"
            })
    except WebSocketDisconnect:
        logger.info("Trade WebSocket client disconnected")
    finally:
        manager.disconnect(websocket)
