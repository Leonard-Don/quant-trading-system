"""Route-surface registry for backend endpoints without direct frontend entry.

This file is intentionally small and explicit: every public backend route that
has no production frontend call site must be classified here so future audits do
not confuse API-only / compatibility surfaces with accidental dead code.
"""

from __future__ import annotations

from typing import Final, TypedDict


class RouteSurfaceRow(TypedDict):
    status: str
    owner: str
    entry_strategy: str
    removal_condition: str


ROUTE_SURFACE_REGISTRY: Final[dict[str, RouteSurfaceRow]] = {
    "POST /analysis/comprehensive": {
        "status": "api_only",
        "owner": "analysis API compatibility",
        "entry_strategy": "Keep as API-only aggregate for notebooks/scripts; new UI should compose the narrower analysis endpoints already used by frontend panels.",
        "removal_condition": "Remove only after no external notebook/script depends on the aggregate comprehensive-analysis payload.",
    },
    "POST /backtest/report/base64": {
        "status": "api_only",
        "owner": "report export automation",
        "entry_strategy": "Keep for automation/download clients that need an embeddable base64 report; UI flows should prefer rendered dashboard/export utilities.",
        "removal_condition": "Remove after report export automation migrates to file/download endpoints or frontend export utilities.",
    },
    "GET /market-data/sources/health": {
        "status": "api_only",
        "owner": "market-data operations",
        "entry_strategy": "Keep as ops/admin diagnostics; do not add to user-facing trading panels unless an admin health surface is explicitly built.",
        "removal_condition": "Remove after market-data provider health is represented in infrastructure diagnostics or external monitoring.",
    },
    "GET /trade/portfolio": {
        "status": "deprecated_compat",
        "owner": "legacy trade engine compatibility",
        "entry_strategy": "No new frontend entry; the persistent paper-trading engine (GET /paper/account) is the single source of truth. This route is a thin shim delegating to the default paper profile and preserving the legacy portfolio response shape.",
        "removal_condition": "Remove after one compatibility window with no logs or saved clients calling /trade/portfolio.",
    },
    "POST /trade/execute": {
        "status": "deprecated_compat",
        "owner": "legacy trade engine compatibility",
        "entry_strategy": "No new frontend entry; submit orders via POST /paper/orders. This route is a thin shim that submits a MARKET order to the default paper profile and preserves the legacy trade response shape.",
        "removal_condition": "Remove after one compatibility window with no logs or saved clients calling /trade/execute.",
    },
    "GET /trade/history": {
        "status": "deprecated_compat",
        "owner": "legacy trade engine compatibility",
        "entry_strategy": "No new frontend entry; read order history via GET /paper/orders. This route is a thin shim that maps the default paper profile's orders to the legacy trade-history shape.",
        "removal_condition": "Remove after one compatibility window with no logs or saved clients calling /trade/history.",
    },
    "POST /trade/reset": {
        "status": "deprecated_compat",
        "owner": "legacy trade engine compatibility",
        "entry_strategy": "No new frontend entry; reset via POST /paper/reset. This route is a thin shim that resets the default paper profile.",
        "removal_condition": "Remove after one compatibility window with no logs or saved clients calling /trade/reset.",
    },
    "POST /realtime/subscribe": {
        "status": "deprecated_compat",
        "owner": "legacy realtime subscription compatibility",
        "entry_strategy": "No new frontend entry; current frontend uses websocket/client-side feed management instead of this acknowledgement-only REST compat route.",
        "removal_condition": "Remove after one compatibility window with no logs or saved clients calling /realtime/subscribe.",
    },
    "POST /realtime/unsubscribe": {
        "status": "deprecated_compat",
        "owner": "legacy realtime subscription compatibility",
        "entry_strategy": "No new frontend entry; current frontend uses websocket/client-side feed management instead of this acknowledgement-only REST compat route.",
        "removal_condition": "Remove after one compatibility window with no logs or saved clients calling /realtime/unsubscribe.",
    },
    "GET /system/status": {
        "status": "deprecated_compat",
        "owner": "legacy system dashboard compatibility",
        "entry_strategy": "Do not wire to new UI; prefer infrastructure diagnostics and health checks for active operations surfaces.",
        "removal_condition": "Remove after saved dashboards and probes migrate to infrastructure health/diagnostics routes.",
    },
    "GET /system/performance": {
        "status": "deprecated_compat",
        "owner": "legacy system dashboard compatibility",
        "entry_strategy": "Do not wire to new UI; prefer infrastructure diagnostics and telemetry-specific monitoring.",
        "removal_condition": "Remove after saved dashboards and probes migrate to infrastructure health/diagnostics routes.",
    },
    "GET /system/health-check": {
        "status": "deprecated_compat",
        "owner": "legacy system dashboard compatibility",
        "entry_strategy": "Do not wire to new UI; prefer infrastructure health checks for active operations surfaces.",
        "removal_condition": "Remove after saved probes migrate to infrastructure health/diagnostics routes.",
    },
    "GET /system/metrics": {
        "status": "deprecated_compat",
        "owner": "legacy system dashboard compatibility",
        "entry_strategy": "Do not wire to new UI; prefer infrastructure telemetry or external monitoring for metrics views.",
        "removal_condition": "Remove after saved dashboards and probes migrate to infrastructure telemetry/monitoring.",
    },
    "GET /system/dependencies": {
        "status": "deprecated_compat",
        "owner": "legacy system dashboard compatibility",
        "entry_strategy": "Do not wire to new UI; prefer infrastructure diagnostics for dependency status.",
        "removal_condition": "Remove after saved probes migrate to infrastructure diagnostics routes.",
    },
}
