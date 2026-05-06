"""
WebSocket路由端点
"""

import asyncio
import hmac
import logging
import os
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.services.trade_stream import build_trade_stream_payload
from backend.app.websocket.connection_manager import manager
from backend.app.websocket.trade_connection_manager import trade_ws_manager
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


def _is_expected_websocket_teardown(exc: Exception) -> bool:
    message = str(exc)
    return any(
        token in message
        for token in (
            "WebSocket is not connected",
            'Need to call "accept" first',
            "Cannot call",
        )
    )


def _build_subscription_message(action: str, results: list[dict]) -> dict:
    symbols = [result["symbol"] for result in results if result.get("symbol")]
    duplicates = [result["symbol"] for result in results if result.get("duplicate")]
    noop_symbols = [result["symbol"] for result in results if result.get("removed") is False]
    payload = {
        "type": "subscription",
        "action": action,
        "symbols": symbols,
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }
    if len(symbols) == 1:
        payload["symbol"] = symbols[0]
        if action == "subscribed":
            payload["duplicate"] = bool(duplicates)
        elif action == "unsubscribed":
            payload["noop"] = bool(noop_symbols)
    if duplicates:
        payload["duplicates"] = duplicates
    if noop_symbols:
        payload["noop_symbols"] = noop_symbols
    return payload


async def _send_quote_snapshot(
    websocket: WebSocket,
    symbols: list[str],
    *,
    origin: str,
    cache_first: bool = False,
    allow_fill: bool = True,
) -> bool:
    target_symbols = [symbol for symbol in symbols if isinstance(symbol, str)]
    if not target_symbols:
        return True

    loop = asyncio.get_running_loop()
    cached_snapshot = {}
    if cache_first:
        cached_snapshot = await loop.run_in_executor(
            None,
            lambda: realtime_manager.get_cached_quotes_dict(target_symbols),
        )
        if cached_snapshot:
            delivered = await manager.send_personal_message(websocket, {
                "type": "snapshot",
                "symbols": list(cached_snapshot.keys()),
                "data": cached_snapshot,
                "origin": origin,
                "stage": "cache",
                "timestamp": datetime.now().isoformat(),
            })
            if not delivered:
                return False

    missing_symbols = [symbol for symbol in target_symbols if symbol not in cached_snapshot]
    if not missing_symbols or not allow_fill:
        return True

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
        delivered = await manager.send_personal_message(websocket, {
            "type": "snapshot",
            "symbols": list(snapshot_data.keys()),
            "data": snapshot_data,
            "origin": origin,
            "stage": "fill" if cache_first and cached_snapshot else "full",
            "timestamp": datetime.now().isoformat(),
        })
        if not delivered:
            return False
    return True


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
                    result = await manager.subscribe(websocket, symbol)
                    subscription_results.append(result)
                if subscription_results:
                    delivered = await manager.send_personal_message(
                        websocket,
                        _build_subscription_message("subscribed", subscription_results),
                    )
                    if not delivered:
                        return

                new_symbols = [result["symbol"] for result in subscription_results if result.get("added")]
                if new_symbols:
                    delivered = await _send_quote_snapshot(
                        websocket,
                        new_symbols,
                        origin="subscribe",
                        cache_first=True,
                        allow_fill=len(new_symbols) <= 8,
                    )
                    if not delivered:
                        logger.info("Realtime WebSocket closed before initial snapshot completed")
                        return
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
                    delivered = await _send_quote_snapshot(
                        websocket,
                        target_symbols,
                        origin="manual_refresh",
                        cache_first=True,
                    )
                    if not delivered:
                        logger.info("Realtime WebSocket closed before snapshot refresh completed")
                        return

            elif action == "unsubscribe":
                unsubscribe_results = []
                for symbol in symbols:
                    result = await manager.unsubscribe(websocket, symbol)
                    unsubscribe_results.append(result)
                if unsubscribe_results:
                    delivered = await manager.send_personal_message(
                        websocket,
                        _build_subscription_message("unsubscribed", unsubscribe_results),
                    )
                    if not delivered:
                        return

            elif action == "ping":
                delivered = await manager.send_personal_message(websocket, {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat(),
                })
                if not delivered:
                    return

            else:
                delivered = await manager.send_personal_message(websocket, {
                    "type": "error",
                    "message": f"Unknown action: {action}"
                })
                if not delivered:
                    return

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        if _is_expected_websocket_teardown(e):
            logger.info("Realtime WebSocket closed during teardown: %s", e)
        else:
            logger.error("WebSocket error: %s", e, exc_info=True)
    finally:
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
        if not await trade_ws_manager.send_personal_message(websocket, {
            "type": "connected",
            "channel": "trades",
        }):
            return
        if not await trade_ws_manager.send_personal_message(websocket, {
            "type": "trade_snapshot",
            "data": build_trade_stream_payload(),
        }):
            return

        while True:
            data = await websocket.receive_json()
            action = str(data.get("action", "")).lower()

            if action == "ping":
                if not await trade_ws_manager.send_personal_message(websocket, {
                    "type": "pong",
                }):
                    return
            elif action == "snapshot":
                if not await trade_ws_manager.send_personal_message(websocket, {
                    "type": "trade_snapshot",
                    "data": build_trade_stream_payload(),
                }):
                    return
            else:
                if not await trade_ws_manager.send_personal_message(websocket, {
                    "type": "error",
                    "message": f"Unknown action: {action}",
                }):
                    return
    except WebSocketDisconnect:
        logger.info("Trade WebSocket client disconnected")
    except Exception as e:
        if _is_expected_websocket_teardown(e):
            logger.info("Trade WebSocket closed during teardown: %s", e)
        else:
            logger.error("Trade WebSocket error: %s", e, exc_info=True)
    finally:
        trade_ws_manager.disconnect(websocket)
