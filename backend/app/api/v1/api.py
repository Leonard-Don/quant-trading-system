from fastapi import APIRouter

from backend.app.api.v1.endpoints import (
    analysis,
    backtest,
    cross_market,
    events,
    industry,
    infrastructure,
    market_data,
    optimization,
    realtime,
    research_journal,
    strategies,
    system,
    trading,
)

api_router = APIRouter()

api_router.include_router(
    market_data.router, prefix="/market-data", tags=["Market Data"]
)
api_router.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])
api_router.include_router(backtest.router, prefix="/backtest", tags=["Backtest"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(realtime.router, prefix="/realtime", tags=["Realtime"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
api_router.include_router(
    optimization.router, prefix="/optimization", tags=["Optimization"]
)
api_router.include_router(trading.router, prefix="/trade", tags=["Trading"])
api_router.include_router(industry.router, prefix="/industry", tags=["Industry Analysis"])
api_router.include_router(events.router, prefix="/events", tags=["Events"])
api_router.include_router(cross_market.router, prefix="/cross-market", tags=["Cross Market"])
api_router.include_router(
    infrastructure.router,
    prefix="/infrastructure",
    tags=["Infrastructure"],
)
api_router.include_router(
    research_journal.router,
    prefix="/research-journal",
    tags=["Research Journal"],
)
