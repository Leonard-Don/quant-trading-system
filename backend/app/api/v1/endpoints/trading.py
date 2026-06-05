"""DEPRECATED `/trade/*` compatibility shim.

This module used to drive a second, ephemeral in-memory trading engine
(`src.trading.trade_manager`). That engine has been consolidated into the
single persistent paper-trading engine (`backend.app.services.paper_trading`).

These four routes are kept ONLY so legacy REST callers keep working — each is
marked ``deprecated=True`` and now delegates to the paper engine using the
DEFAULT paper profile (no header / ``profile_id=None``). The response shapes of
the original ``/trade/*`` routes are preserved here by mapping the paper
account/order payloads back onto the legacy ``TradeManager`` field names.

New clients should call the ``/paper/*`` surface directly. See
``route_surface_registry.py`` for the removal condition. The trade WebSocket
push layer was removed in the same change (single-client local tool).
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from backend.app.core.error_handler import AppException
from backend.app.services.paper_trading import (
    PaperTradingError,
    paper_trading_store,
)
from backend.app.services.runtime_state import get_data_manager
from src.data.realtime_manager import realtime_manager

router = APIRouter()
data_manager = get_data_manager()


TRADING_OPERATION_EXCEPTIONS = (
    AttributeError,
    ConnectionError,
    KeyError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
)


class TradeRequest(BaseModel):
    symbol: str
    action: str  # BUY or SELL
    quantity: int
    price: Optional[float] = None  # If None, use current market price


# ---------------------------------------------------------------------------
# Shape adapters: paper engine payloads -> legacy /trade/* response shapes
# ---------------------------------------------------------------------------


def _order_to_legacy_trade(order: dict[str, Any], balance_after: float) -> dict[str, Any]:
    """Map a paper order record onto the legacy ``TradeManager.Trade`` dict."""
    quantity = order.get("quantity", 0)
    price = order.get("fill_price", 0.0)
    return {
        "id": order.get("id"),
        "timestamp": order.get("submitted_at"),
        "symbol": order.get("symbol"),
        "action": order.get("side"),
        "quantity": quantity,
        "price": price,
        "total_amount": float(quantity) * float(price),
        # The legacy engine computed realized PnL on SELLs; the paper engine
        # does not stamp per-fill realized PnL onto the order, so the compat
        # shape degrades to None rather than fabricating a value.
        "pnl": None,
        "balance_after": balance_after,
    }


def _resolve_current_prices(symbols: list[str]) -> dict[str, float]:
    """Best-effort latest prices for held symbols (realtime cache first)."""
    current_prices: dict[str, float] = {}
    if not symbols:
        return current_prices

    try:
        realtime_quotes = realtime_manager.get_quotes_dict(symbols, use_cache=True)
        for symbol in symbols:
            realtime_price = (realtime_quotes.get(symbol) or {}).get("price")
            if realtime_price is not None:
                current_prices[symbol] = realtime_price
    except Exception:
        pass

    for symbol in symbols:
        if symbol in current_prices:
            continue
        try:
            quote = data_manager.get_latest_price(symbol)
            if quote and quote.get("price") is not None:
                current_prices[symbol] = quote["price"]
        except Exception:
            continue
    return current_prices


def _account_to_legacy_portfolio(account: dict[str, Any]) -> dict[str, Any]:
    """Map a paper account onto the legacy ``get_portfolio_status`` shape."""
    initial_capital = float(account.get("initial_capital", 0.0))
    balance = float(account.get("cash", 0.0))
    positions = account.get("positions") or []
    symbols = [position.get("symbol") for position in positions if position.get("symbol")]
    current_prices = _resolve_current_prices(symbols)

    total_market_value = 0.0
    portfolio_positions: list[dict[str, Any]] = []
    for position in positions:
        symbol = position.get("symbol")
        quantity = float(position.get("quantity", 0) or 0)
        avg_price = float(position.get("avg_cost", 0) or 0)
        current_price = current_prices.get(symbol, avg_price)
        market_value = quantity * current_price
        cost_basis = quantity * avg_price
        unrealized_pnl = market_value - cost_basis
        unrealized_pnl_percent = (
            (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
        )
        portfolio_positions.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "avg_price": avg_price,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_percent": unrealized_pnl_percent,
            }
        )
        total_market_value += market_value

    total_equity = balance + total_market_value
    total_pnl = total_equity - initial_capital
    total_pnl_percent = (
        (total_pnl / initial_capital * 100) if initial_capital > 0 else 0.0
    )

    return {
        "balance": balance,
        "total_equity": total_equity,
        "total_market_value": total_market_value,
        "total_pnl": total_pnl,
        "total_pnl_percent": total_pnl_percent,
        "positions": portfolio_positions,
        "trade_count": int(account.get("orders_count", 0) or 0),
    }


@router.get("/portfolio", summary="获取投资组合状态", deprecated=True)
async def get_portfolio():
    """获取当前账户余额、持仓和总资产（已弃用：改用 /paper/account）。"""
    try:
        account = await run_in_threadpool(paper_trading_store.get_account)
        portfolio = await run_in_threadpool(_account_to_legacy_portfolio, account)
        return {"success": True, "data": portfolio}
    except TRADING_OPERATION_EXCEPTIONS as e:
        raise AppException(
            message=str(e),
            error_code="TRADE_PORTFOLIO_FAILED",
        ) from e


@router.post("/execute", summary="执行交易", deprecated=True)
async def execute_trade(trade_request: TradeRequest):
    """执行买入或卖出交易（已弃用：改用 /paper/orders）。"""
    try:
        price = trade_request.price

        # 如果未提供价格，优先复用实时缓存中的最新价，保持与前端实时参考价一致。
        if price is None:
            realtime_quote = await run_in_threadpool(
                lambda: realtime_manager.get_quote_dict(trade_request.symbol, use_cache=True)
            ) or {}
            if "price" in realtime_quote and realtime_quote["price"] is not None:
                price = realtime_quote["price"]

            if price is None:
                quote = await run_in_threadpool(
                    data_manager.get_latest_price, trade_request.symbol
                )
                if quote and "price" in quote:
                    price = quote["price"]

            if price is None:
                raise HTTPException(status_code=400, detail=f"无法获取 {trade_request.symbol} 的最新价格")

        result = await run_in_threadpool(
            paper_trading_store.submit_order,
            {
                "symbol": trade_request.symbol,
                "side": trade_request.action,
                "quantity": trade_request.quantity,
                "order_type": "MARKET",
                "fill_price": price,
            },
        )
        order = result.get("order") or {}
        balance_after = float((result.get("account") or {}).get("cash", 0.0))
        trade_result = _order_to_legacy_trade(order, balance_after)

        return {"success": True, "data": trade_result}
    except HTTPException:
        raise
    except (ValueError, PaperTradingError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except TRADING_OPERATION_EXCEPTIONS as e:
        raise AppException(
            message=str(e),
            error_code="TRADE_EXECUTION_FAILED",
        ) from e


@router.get("/history", summary="获取交易历史", deprecated=True)
async def get_trade_history(limit: int = 50):
    """获取历史交易记录（已弃用：改用 /paper/orders）。"""
    try:
        orders = await run_in_threadpool(
            paper_trading_store.list_orders, None, limit
        )
        # The paper engine doesn't carry a running balance per order, so the
        # legacy `balance_after` field degrades to the current account cash.
        account = await run_in_threadpool(paper_trading_store.get_account)
        balance_after = float(account.get("cash", 0.0))
        history = [_order_to_legacy_trade(order, balance_after) for order in orders]
        return {"success": True, "data": history}
    except (ValueError, *TRADING_OPERATION_EXCEPTIONS) as e:
        raise AppException(
            message=str(e),
            error_code="TRADE_HISTORY_FAILED",
        ) from e


@router.post("/reset", summary="重置账户", deprecated=True)
async def reset_account():
    """重置模拟账户（已弃用：改用 /paper/reset）。"""
    try:
        await run_in_threadpool(paper_trading_store.reset)
        return {"success": True, "message": "账户已重置"}
    except (ValueError, *TRADING_OPERATION_EXCEPTIONS) as e:
        raise AppException(
            message=str(e),
            error_code="TRADE_RESET_FAILED",
        ) from e
