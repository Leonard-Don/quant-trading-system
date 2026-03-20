from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

from backend.app.services.trade_stream import build_trade_stream_payload, resolve_trade_portfolio
from backend.app.websocket.trade_connection_manager import trade_ws_manager
from src.data.realtime_manager import realtime_manager
from src.trading.trade_manager import trade_manager
from src.data.data_manager import DataManager

router = APIRouter()
data_manager = DataManager()

class TradeRequest(BaseModel):
    symbol: str
    action: str  # BUY or SELL
    quantity: int
    price: Optional[float] = None  # If None, use current market price

@router.get("/portfolio", summary="获取投资组合状态")
async def get_portfolio():
    """获取当前账户余额、持仓和总资产"""
    try:
        return {
            "success": True, 
            "data": resolve_trade_portfolio()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute", summary="执行交易")
async def execute_trade(trade_request: TradeRequest):
    """执行买入或卖出交易"""
    try:
        price = trade_request.price
        
        # 如果未提供价格，优先复用实时缓存中的最新价，保持与前端实时参考价一致。
        if price is None:
            realtime_quote = realtime_manager.get_quote_dict(trade_request.symbol, use_cache=True) or {}
            if "price" in realtime_quote and realtime_quote["price"] is not None:
                price = realtime_quote["price"]

            if price is None:
                quote = data_manager.get_latest_price(trade_request.symbol)
                if quote and "price" in quote:
                    price = quote["price"]

            if price is None:
                raise HTTPException(status_code=400, detail=f"无法获取 {trade_request.symbol} 的最新价格")

        trade_result = trade_manager.execute_trade(
            symbol=trade_request.symbol,
            action=trade_request.action,
            quantity=trade_request.quantity,
            price=price
        )

        await trade_ws_manager.broadcast({
            "type": "trade_executed",
            "data": {
                **build_trade_stream_payload(),
                "trade": trade_result,
            },
        })
        
        return {"success": True, "data": trade_result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history", summary="获取交易历史")
async def get_trade_history(limit: int = 50):
    """获取历史交易记录"""
    try:
        return {
            "success": True, 
            "data": trade_manager.get_history(limit)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset", summary="重置账户")
async def reset_account():
    """重置模拟账户"""
    try:
        trade_manager.reset_account()
        await trade_ws_manager.broadcast({
            "type": "account_reset",
            "data": {
                **build_trade_stream_payload(),
                "message": "账户已重置",
            },
        })
        return {"success": True, "message": "账户已重置"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
