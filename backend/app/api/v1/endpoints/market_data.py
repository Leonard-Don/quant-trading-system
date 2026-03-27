
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
