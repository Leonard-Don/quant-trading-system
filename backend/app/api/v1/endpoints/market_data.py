
from fastapi import APIRouter, HTTPException
from datetime import datetime
from backend.app.schemas.base import MarketDataRequest
from src.data.data_manager import DataManager
from src.utils.json_utils import clean_data_for_json
from src.utils.performance import timing_decorator
import logging

router = APIRouter()
logger = logging.getLogger(__name__)
data_manager = DataManager()

@router.post("/", summary="获取市场数据")
@timing_decorator
async def get_market_data(request: MarketDataRequest):
    """获取市场数据"""
    try:
        # 解析日期
        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        # 获取数据
        data = data_manager.get_historical_data(
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date,
            interval=request.interval,
            period=request.period
        )

        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        # 处理NaN值并转换为JSON格式
        data_dict = {
            "symbol": request.symbol,
            "data": clean_data_for_json(data.reset_index()),
            "count": len(data),
        }

        return {"success": True, "data": data_dict}

    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search", summary="搜索股票代码")
async def search_symbols(query: str):
    """搜索股票代码"""
    # 常见股票代码列表
    common_symbols = [
        {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"},
        {"symbol": "MSFT", "name": "Microsoft Corporation", "exchange": "NASDAQ"},
        {"symbol": "GOOGL", "name": "Alphabet Inc.", "exchange": "NASDAQ"},
        {"symbol": "AMZN", "name": "Amazon.com Inc.", "exchange": "NASDAQ"},
        {"symbol": "TSLA", "name": "Tesla Inc.", "exchange": "NASDAQ"},
        {"symbol": "META", "name": "Meta Platforms Inc.", "exchange": "NASDAQ"},
        {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ"},
        {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "exchange": "NYSE"},
        {"symbol": "JNJ", "name": "Johnson & Johnson", "exchange": "NYSE"},
        {"symbol": "V", "name": "Visa Inc.", "exchange": "NYSE"},
        {"symbol": "PG", "name": "Procter & Gamble Co.", "exchange": "NYSE"},
        {"symbol": "UNH", "name": "UnitedHealth Group Inc.", "exchange": "NYSE"},
        {"symbol": "HD", "name": "Home Depot Inc.", "exchange": "NYSE"},
        {"symbol": "MA", "name": "Mastercard Inc.", "exchange": "NYSE"},
        {"symbol": "BAC", "name": "Bank of America Corp.", "exchange": "NYSE"},
    ]

    # 简单的搜索过滤
    query = query.upper()
    filtered = [
        s for s in common_symbols if query in s["symbol"] or query in s["name"].upper()
    ]

    return {"symbols": filtered[:10]}  # 限制返回10个结果
