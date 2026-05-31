import logging
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Body, HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.app.core.error_handler import AppException
from backend.app.services.runtime_state import get_data_manager
from src.analytics.portfolio_optimizer import PortfolioOptimizer

router = APIRouter()
logger = logging.getLogger(__name__)
data_manager = get_data_manager()
optimizer = PortfolioOptimizer()


def _optimize_portfolio_sync(symbols, start_date, end_date, objective):
    """Run the blocking data-fetch + optimization off the event loop.

    References the module-level ``data_manager``/``optimizer`` singletons at
    call time so test monkeypatches on them are honored.
    """
    # Fetch data for all symbols
    # DataManager.get_historical_data retrieves one by one.
    # Ideally DataManager should support batch fetch. Here we loop.
    price_data = {}
    for symbol in symbols:
        df = data_manager.get_historical_data(symbol, start_date=start_date, end_date=end_date)
        if not df.empty:
            # Assuming 'close' is adjusted close
            price_data[symbol] = df["close"]
        else:
            logger.warning(f"No data for {symbol}, skipping in optimization")

    if len(price_data) < 2:
        raise HTTPException(
            status_code=400,
            detail="Insufficient data for optimization (need at least 2 valid assets)",
        )

    # Create combined DataFrame
    combined_df = pd.DataFrame(price_data)

    # Optimize
    return optimizer.optimize_portfolio(combined_df, objective)


@router.post("/optimize", summary="投资组合优化")
async def optimize_portfolio(
    symbols: list[str] = Body(..., embed=True),
    period: str = Body("1y", embed=True),  # 1y, 6m, 3m
    objective: str = Body("max_sharpe", embed=True),
):
    """
    计算投资组合的最优资产配置权重
    """
    try:
        if len(symbols) < 2:
            raise HTTPException(
                status_code=400,
                detail="Portfolio must contain at least 2 assets",
            )

        # Determine start date based on period
        end_date = datetime.now()
        if period == "1y":
            start_date = end_date.replace(year=end_date.year - 1)
        elif period == "6m":
            start_date = end_date.replace(
                month=end_date.month - 6 if end_date.month > 6 else end_date.month + 6
            )  # Simple approx
            # Better date logic needed for edge cases but sufficient for prototype
            from dateutil.relativedelta import relativedelta

            start_date = end_date - relativedelta(months=6)
        else:
            from dateutil.relativedelta import relativedelta

            start_date = end_date - relativedelta(months=3)

        # Offload the blocking per-symbol fetch loop + optimization to a
        # threadpool so this async handler does not stall the event loop.
        result = await run_in_threadpool(
            _optimize_portfolio_sync, symbols, start_date, end_date, objective
        )

        if not result["success"]:
            raise AppException(
                message=result.get("error", "Optimization failed"),
                error_code="PORTFOLIO_OPTIMIZATION_FAILED",
            )

        return {"timestamp": datetime.now().isoformat(), **result}

    except HTTPException:
        raise
    except AppException:
        raise
    except (
        AttributeError,
        ImportError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as e:
        logger.error(f"Error in portfolio optimization endpoint: {e}", exc_info=True)
        raise AppException(
            message=str(e),
            error_code="PORTFOLIO_OPTIMIZATION_FAILED",
        ) from e
