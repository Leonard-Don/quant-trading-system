
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, List, Optional
from pydantic import BaseModel

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
        # 获取持仓股票的最新价格
        current_prices = {}
        for symbol in trade_manager.positions.keys():
            try:
                # 尝试获取最新价格，这里简化处理，实际应复用RealTime逻辑
                quote = data_manager.get_latest_price(symbol)
                if quote and "price" in quote:
                    current_prices[symbol] = quote["price"]
            except Exception:
                pass # 忽略价格获取失败，将使用持仓均价
                
        return {
            "success": True, 
            "data": trade_manager.get_portfolio_status(current_prices)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute", summary="执行交易")
async def execute_trade(trade_request: TradeRequest):
    """执行买入或卖出交易"""
    try:
        price = trade_request.price
        
        # 如果未提供价格，获取当前市场价格
        if price is None:
            quote = data_manager.get_latest_price(trade_request.symbol)
            if not quote or "price" not in quote:
                raise HTTPException(status_code=400, detail=f"无法获取 {trade_request.symbol} 的最新价格")
            price = quote["price"]

        trade_result = trade_manager.execute_trade(
            symbol=trade_request.symbol,
            action=trade_request.action,
            quantity=trade_request.quantity,
            price=price
        )
        
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
        return {"success": True, "message": "账户已重置"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
