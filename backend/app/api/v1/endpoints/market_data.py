
import logging
from datetime import datetime

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from backend.app.core.error_handler import AppException
from backend.app.schemas.base import MarketDataRequest
from backend.app.services.runtime_state import get_data_manager
from src.utils.json_utils import clean_data_for_json
from src.utils.performance import timing_decorator

router = APIRouter()
logger = logging.getLogger(__name__)
data_manager = get_data_manager()

@router.get("/sources/health", summary="获取数据源健康状态")
async def get_market_data_source_health():
    """Return normalized provider/source health without probing upstream APIs."""
    return {"success": True, "data": data_manager.get_source_health_report()}


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
    except ValueError as e:
        logger.warning("Invalid market data date parameter: %s", e)
        raise AppException(
            message=str(e),
            error_code="MARKET_DATA_INVALID_REQUEST",
            status_code=400,
        ) from e

    try:
        # 获取数据
        data = await run_in_threadpool(
            lambda: data_manager.get_historical_data(
                symbol=request.symbol,
                start_date=start_date,
                end_date=end_date,
                interval=request.interval,
                period=request.period,
            )
        )

        if data.empty:
            raise AppException(
                message=f"No data found for symbol {request.symbol}",
                error_code="MARKET_DATA_NOT_FOUND",
                status_code=404,
            )

        source_health = getattr(data, "attrs", {}).get("source_health") or {}

        # 处理NaN值并转换为JSON格式
        data_dict = {
            "symbol": request.symbol,
            "data": clean_data_for_json(data.reset_index()),
            "count": len(data),
            "source_health": source_health,
        }

        return {"success": True, "data": data_dict}

    except AppException:
        raise
    except (
        AttributeError,
        ConnectionError,
        KeyError,
        OSError,
        RuntimeError,
        TimeoutError,
        TypeError,
        ValueError,
    ) as e:
        logger.error(f"Error fetching market data: {e}")
        raise AppException(
            message=str(e),
            error_code="MARKET_DATA_FETCH_FAILED",
        ) from e
