"""Industry analysis API package — split from a 1,676-line ``industry.py``.

Sub-routers:
    - ``heatmap``: ``/industries/heatmap*``, ``/bootstrap``
    - ``leaders``: ``/leaders*``, ``/leaders/{symbol}/detail``
    - ``rotation``: catch-all (``/industries/hot``, ``/industries/{name}/...``,
      ``/preferences*``, ``/industries/clusters``, ``/industries/rotation``,
      ``/industries/intelligence``, ``/industries/network``, ``/health``)

The deprecated ``_compat`` module preserves the test-patch monkeypatch surface
that lets existing unit tests do
``monkeypatch.setattr(industry, "_foo", fake)``. New code should NOT rely on
that shim — use ``backend.app.services.industry.runtime`` directly.

Layer charter: ``docs/architecture/industry-layering.md``.
"""

from fastapi import APIRouter

from backend.app.api.v1.endpoints.industry import heatmap, leaders, rotation
from backend.app.api.v1.endpoints.industry._compat import *

# Re-export route handlers so existing tests can call them as plain
# functions via ``industry_endpoint.get_leader_stocks(...)``. New code
# should hit the FastAPI app via ``TestClient`` instead.
from backend.app.api.v1.endpoints.industry.heatmap import (
    get_industry_bootstrap,
    get_industry_heatmap,
    get_industry_heatmap_history,
)
from backend.app.api.v1.endpoints.industry.leaders import (
    get_leader_boards,
    get_leader_detail,
    get_leader_stocks,
)
from backend.app.api.v1.endpoints.industry.rotation import (
    export_industry_preferences,
    get_hot_industries,
    get_industry_clusters,
    get_industry_intelligence,
    get_industry_network,
    get_industry_preferences,
    get_industry_rotation,
    get_industry_stock_build_status,
    get_industry_stocks,
    get_industry_trend,
    health_check,
    import_industry_preferences,
    stream_industry_stock_build_status,
    update_industry_preferences,
)

# Re-export schemas so existing tests can construct response objects via
# ``industry_endpoint.StockResponse(...)`` (the original module imported
# every schema at module scope).
from backend.app.schemas.industry import (
    ClusterResponse,
    HeatmapDataItem,
    HeatmapHistoryItem,
    HeatmapHistoryResponse,
    HeatmapResponse,
    IndustryBootstrapResponse,
    IndustryPolicySignal,
    IndustryPreferencesResponse,
    IndustryRankResponse,
    IndustryRotationResponse,
    IndustryStockBuildStatusResponse,
    IndustryTrendResponse,
    LeaderBoardsResponse,
    LeaderDetailResponse,
    LeaderStockResponse,
    StockResponse,
)

router = APIRouter()
router.include_router(heatmap.router)
router.include_router(leaders.router)
router.include_router(rotation.router)
