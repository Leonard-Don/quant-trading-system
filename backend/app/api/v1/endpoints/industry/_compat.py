"""DEPRECATED test-patch compatibility surface for the industry endpoints.

This module exists ONLY to keep existing unit tests working — they patch
helper symbols on ``backend.app.api.v1.endpoints.industry`` directly via
``monkeypatch.setattr(industry_endpoint, "_foo", fake)``. The actual
implementations live in ``backend.app.services.industry.runtime``.

When this module is imported into the package via ``from ._compat import *``,
the wrapper functions and state attributes become attributes of
``backend.app.api.v1.endpoints.industry`` (the package). Tests that
``setattr`` against that package replace those attributes; the wrappers
defined here delegate through ``industry_runtime`` and re-sync state so
any patched helper is visible to downstream service code.

DO NOT add new code here. New helpers should live in ``industry_runtime``
and be referenced from sub-routers via ``industry_runtime._foo`` (or
imported into the sub-router module). This module is a temporary shim;
the long-term plan is to migrate tests to patch ``industry_runtime``
directly and delete this file.
"""

import warnings
from typing import Any

from backend.app.services.industry import runtime as industry_runtime

warnings.warn(
    "backend.app.api.v1.endpoints.industry._compat is a temporary test-patch shim; "
    "patch backend.app.services.industry.runtime helpers directly in new tests.",
    DeprecationWarning,
    stacklevel=2,
)

# Compatibility surface for tests and local debugging that still patch
# helpers on backend.app.api.v1.endpoints.industry directly.
SIX_DIGIT_SYMBOL_PATTERN = industry_runtime.SIX_DIGIT_SYMBOL_PATTERN
_endpoint_cache = industry_runtime._endpoint_cache
_parity_cache = industry_runtime._parity_cache
_stocks_full_build_inflight = industry_runtime._stocks_full_build_inflight
_leading_stock_symbol_lookup_cache = industry_runtime._leading_stock_symbol_lookup_cache
_leading_stock_symbol_lookup_cache_time = industry_runtime._leading_stock_symbol_lookup_cache_time
_heatmap_history = industry_runtime._heatmap_history
_heatmap_history_loaded = industry_runtime._heatmap_history_loaded
_heatmap_history_lock = industry_runtime._heatmap_history_lock
ThreadPoolExecutor = industry_runtime.ThreadPoolExecutor

_INDUSTRY_SERVICE_HELPERS = {
    "_load_symbol_mini_trend": industry_runtime._load_symbol_mini_trend,
    "_attach_leader_mini_trends": industry_runtime._attach_leader_mini_trends,
    "_get_endpoint_cache": industry_runtime._get_endpoint_cache,
    "_set_endpoint_cache": industry_runtime._set_endpoint_cache,
    "_get_stale_endpoint_cache": industry_runtime._get_stale_endpoint_cache,
    "_serialize_heatmap_response": industry_runtime._serialize_heatmap_response,
    "_build_hot_industry_rank_responses": industry_runtime._build_hot_industry_rank_responses,
    "_get_stock_cache_keys": industry_runtime._get_stock_cache_keys,
    "_set_parity_cache": industry_runtime._set_parity_cache,
    "_get_parity_cache": industry_runtime._get_parity_cache,
    "_get_stale_parity_cache": industry_runtime._get_stale_parity_cache,
    "_is_fresh_parity_entry": industry_runtime._is_fresh_parity_entry,
    "_get_matching_parity_cache": industry_runtime._get_matching_parity_cache,
    "_build_parity_price_data": industry_runtime._build_parity_price_data,
    "_build_leader_detail_fallback": industry_runtime._build_leader_detail_fallback,
    "_leader_detail_error_status": industry_runtime._leader_detail_error_status,
    "_extract_leading_stock_symbol_lookup": industry_runtime._extract_leading_stock_symbol_lookup,
    "_collect_hot_leader_candidates": industry_runtime._collect_hot_leader_candidates,
    "_build_leading_stock_symbol_lookup": industry_runtime._build_leading_stock_symbol_lookup,
    "_map_industry_etfs": industry_runtime._map_industry_etfs,
    "_trim_heatmap_history_payload": industry_runtime._trim_heatmap_history_payload,
    "_resolve_industry_profile": industry_runtime._resolve_industry_profile,
    "_get_stock_status_key": industry_runtime._get_stock_status_key,
    "_set_stock_build_status": industry_runtime._set_stock_build_status,
    "_get_stock_build_status": industry_runtime._get_stock_build_status,
    "_load_heatmap_history_from_disk": industry_runtime._load_heatmap_history_from_disk,
    "_persist_heatmap_history_to_disk": industry_runtime._persist_heatmap_history_to_disk,
    "_append_heatmap_history": industry_runtime._append_heatmap_history,
    "_build_heatmap_response_from_history": industry_runtime._build_heatmap_response_from_history,
    "_load_live_heatmap_response": industry_runtime._load_live_heatmap_response,
    "_schedule_heatmap_refresh": industry_runtime._schedule_heatmap_refresh,
    "_resolve_symbol_with_provider": industry_runtime._resolve_symbol_with_provider,
    "_build_stock_responses": industry_runtime._build_stock_responses,
    "_count_quick_stock_detail_fields": industry_runtime._count_quick_stock_detail_fields,
    "_promote_detail_ready_quick_rows": industry_runtime._promote_detail_ready_quick_rows,
    "_load_cached_quick_valuation": industry_runtime._load_cached_quick_valuation,
    "_backfill_quick_rows_with_cached_valuation": industry_runtime._backfill_quick_rows_with_cached_valuation,
    "_build_full_industry_stock_response": industry_runtime._build_full_industry_stock_response,
    "_build_quick_industry_stock_response": industry_runtime._build_quick_industry_stock_response,
    "_coerce_trend_alignment_stock_rows": industry_runtime._coerce_trend_alignment_stock_rows,
    "_load_trend_alignment_stock_rows": industry_runtime._load_trend_alignment_stock_rows,
    "_build_trend_summary_from_stock_rows": industry_runtime._build_trend_summary_from_stock_rows,
    "_should_align_trend_with_stock_rows": industry_runtime._should_align_trend_with_stock_rows,
    "_schedule_full_stock_cache_build": industry_runtime._schedule_full_stock_cache_build,
    "_dedupe_leader_responses": industry_runtime._dedupe_leader_responses,
    "_get_or_create_provider": industry_runtime._get_or_create_provider,
    "get_industry_analyzer": industry_runtime.get_industry_analyzer,
    "get_leader_scorer": industry_runtime.get_leader_scorer,
    "_build_leader_context": industry_runtime._build_leader_context,
    "_get_leader_overview_cache_key": industry_runtime._get_leader_overview_cache_key,
    "_get_leader_provider_stocks_cache_key": industry_runtime._get_leader_provider_stocks_cache_key,
    "_get_leader_snapshot_prewarm_key": industry_runtime._get_leader_snapshot_prewarm_key,
    "_has_leader_board_rows": industry_runtime._has_leader_board_rows,
    "_build_leader_boards_payload": industry_runtime._build_leader_boards_payload,
    "_prewarm_leader_stock_snapshot": industry_runtime._prewarm_leader_stock_snapshot,
    "_schedule_leader_stock_snapshot_prewarm": industry_runtime._schedule_leader_stock_snapshot_prewarm,
    "_compute_and_cache_leader_overview": industry_runtime._compute_and_cache_leader_overview,
    "_schedule_leader_overview_build": industry_runtime._schedule_leader_overview_build,
    "_load_leader_overview_payload": industry_runtime._load_leader_overview_payload,
    "_get_bootstrap_leader_payload": industry_runtime._get_bootstrap_leader_payload,
    "_hydrate_bootstrap_with_cached_leaders": industry_runtime._hydrate_bootstrap_with_cached_leaders,
    "_persist_leader_list_cache": industry_runtime._persist_leader_list_cache,
    "_load_provider_stocks_for_leaders": industry_runtime._load_provider_stocks_for_leaders,
    "_compute_core_leader_stocks": industry_runtime._compute_core_leader_stocks,
    "_compute_hot_leader_stocks": industry_runtime._compute_hot_leader_stocks,
    "_load_leader_stock_list": industry_runtime._load_leader_stock_list,
}
_INDUSTRY_WRAPPERS: dict[str, Any] = {}


def _get_industry_package_namespace() -> dict[str, Any]:
    """Return the namespace dict of the ``industry`` package, or ``_compat``'s.

    Tests patch ``backend.app.api.v1.endpoints.industry`` (the package).
    Sub-routers see helpers via ``from ._compat import _foo`` so a patch on
    the package namespace must be reflected before delegating into
    ``industry_runtime``. Falling back to this module's namespace covers
    the (rare) bootstrap case where the package hasn't been imported yet.
    """
    import sys

    pkg = sys.modules.get("backend.app.api.v1.endpoints.industry")
    if pkg is not None and hasattr(pkg, "__dict__"):
        return pkg.__dict__
    return globals()


def _sync_industry_runtime_state() -> None:
    namespace = _get_industry_package_namespace()
    for state_name in (
        "SIX_DIGIT_SYMBOL_PATTERN",
        "_endpoint_cache",
        "_parity_cache",
        "_stocks_full_build_inflight",
        "_leading_stock_symbol_lookup_cache",
        "_leading_stock_symbol_lookup_cache_time",
        "_heatmap_history",
        "_heatmap_history_loaded",
        "_heatmap_history_lock",
        "ThreadPoolExecutor",
    ):
        if state_name in namespace:
            setattr(industry_runtime, state_name, namespace[state_name])

    for helper_name, original in _INDUSTRY_SERVICE_HELPERS.items():
        current = namespace.get(helper_name, original)
        wrapper = _INDUSTRY_WRAPPERS.get(helper_name)
        setattr(industry_runtime, helper_name, original if current is wrapper else current)


def _call_industry_helper(helper_name: str, *args, **kwargs):
    _sync_industry_runtime_state()
    namespace = _get_industry_package_namespace()
    wrapper = _INDUSTRY_WRAPPERS.get(helper_name)
    current = namespace.get(helper_name, _INDUSTRY_SERVICE_HELPERS[helper_name])
    if current is wrapper:
        # The package still references the wrapper (no test patch in effect)
        # — call the original runtime helper directly.
        return _INDUSTRY_SERVICE_HELPERS[helper_name](*args, **kwargs)
    return current(*args, **kwargs)


def _load_symbol_mini_trend(*args, **kwargs):
    return _call_industry_helper("_load_symbol_mini_trend", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_symbol_mini_trend"] = _load_symbol_mini_trend


def _attach_leader_mini_trends(*args, **kwargs):
    return _call_industry_helper("_attach_leader_mini_trends", *args, **kwargs)


_INDUSTRY_WRAPPERS["_attach_leader_mini_trends"] = _attach_leader_mini_trends


def _get_endpoint_cache(*args, **kwargs):
    return _call_industry_helper("_get_endpoint_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_endpoint_cache"] = _get_endpoint_cache


def _set_endpoint_cache(*args, **kwargs):
    return _call_industry_helper("_set_endpoint_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_set_endpoint_cache"] = _set_endpoint_cache


def _get_stale_endpoint_cache(*args, **kwargs):
    return _call_industry_helper("_get_stale_endpoint_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stale_endpoint_cache"] = _get_stale_endpoint_cache


def _serialize_heatmap_response(*args, **kwargs):
    return _call_industry_helper("_serialize_heatmap_response", *args, **kwargs)


_INDUSTRY_WRAPPERS["_serialize_heatmap_response"] = _serialize_heatmap_response


def _build_hot_industry_rank_responses(*args, **kwargs):
    return _call_industry_helper("_build_hot_industry_rank_responses", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_hot_industry_rank_responses"] = _build_hot_industry_rank_responses


def _get_stock_cache_keys(*args, **kwargs):
    return _call_industry_helper("_get_stock_cache_keys", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stock_cache_keys"] = _get_stock_cache_keys


def _set_parity_cache(*args, **kwargs):
    return _call_industry_helper("_set_parity_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_set_parity_cache"] = _set_parity_cache


def _get_parity_cache(*args, **kwargs):
    return _call_industry_helper("_get_parity_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_parity_cache"] = _get_parity_cache


def _get_stale_parity_cache(*args, **kwargs):
    return _call_industry_helper("_get_stale_parity_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stale_parity_cache"] = _get_stale_parity_cache


def _is_fresh_parity_entry(*args, **kwargs):
    return _call_industry_helper("_is_fresh_parity_entry", *args, **kwargs)


_INDUSTRY_WRAPPERS["_is_fresh_parity_entry"] = _is_fresh_parity_entry


def _get_matching_parity_cache(*args, **kwargs):
    return _call_industry_helper("_get_matching_parity_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_matching_parity_cache"] = _get_matching_parity_cache


def _build_parity_price_data(*args, **kwargs):
    return _call_industry_helper("_build_parity_price_data", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_parity_price_data"] = _build_parity_price_data


def _build_leader_detail_fallback(*args, **kwargs):
    return _call_industry_helper("_build_leader_detail_fallback", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_leader_detail_fallback"] = _build_leader_detail_fallback


def _leader_detail_error_status(*args, **kwargs):
    return _call_industry_helper("_leader_detail_error_status", *args, **kwargs)


_INDUSTRY_WRAPPERS["_leader_detail_error_status"] = _leader_detail_error_status


def _extract_leading_stock_symbol_lookup(*args, **kwargs):
    return _call_industry_helper("_extract_leading_stock_symbol_lookup", *args, **kwargs)


_INDUSTRY_WRAPPERS["_extract_leading_stock_symbol_lookup"] = _extract_leading_stock_symbol_lookup


def _collect_hot_leader_candidates(*args, **kwargs):
    return _call_industry_helper("_collect_hot_leader_candidates", *args, **kwargs)


_INDUSTRY_WRAPPERS["_collect_hot_leader_candidates"] = _collect_hot_leader_candidates


def _build_leading_stock_symbol_lookup(*args, **kwargs):
    return _call_industry_helper("_build_leading_stock_symbol_lookup", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_leading_stock_symbol_lookup"] = _build_leading_stock_symbol_lookup


def _map_industry_etfs(*args, **kwargs):
    return _call_industry_helper("_map_industry_etfs", *args, **kwargs)


_INDUSTRY_WRAPPERS["_map_industry_etfs"] = _map_industry_etfs


def _trim_heatmap_history_payload(*args, **kwargs):
    return _call_industry_helper("_trim_heatmap_history_payload", *args, **kwargs)


_INDUSTRY_WRAPPERS["_trim_heatmap_history_payload"] = _trim_heatmap_history_payload


def _resolve_industry_profile(*args, **kwargs):
    return _call_industry_helper("_resolve_industry_profile", *args, **kwargs)


_INDUSTRY_WRAPPERS["_resolve_industry_profile"] = _resolve_industry_profile


def _get_stock_status_key(*args, **kwargs):
    return _call_industry_helper("_get_stock_status_key", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stock_status_key"] = _get_stock_status_key


def _set_stock_build_status(*args, **kwargs):
    return _call_industry_helper("_set_stock_build_status", *args, **kwargs)


_INDUSTRY_WRAPPERS["_set_stock_build_status"] = _set_stock_build_status


def _get_stock_build_status(*args, **kwargs):
    return _call_industry_helper("_get_stock_build_status", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stock_build_status"] = _get_stock_build_status


def _load_heatmap_history_from_disk(*args, **kwargs):
    return _call_industry_helper("_load_heatmap_history_from_disk", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_heatmap_history_from_disk"] = _load_heatmap_history_from_disk


def _persist_heatmap_history_to_disk(*args, **kwargs):
    return _call_industry_helper("_persist_heatmap_history_to_disk", *args, **kwargs)


_INDUSTRY_WRAPPERS["_persist_heatmap_history_to_disk"] = _persist_heatmap_history_to_disk


def _append_heatmap_history(*args, **kwargs):
    return _call_industry_helper("_append_heatmap_history", *args, **kwargs)


_INDUSTRY_WRAPPERS["_append_heatmap_history"] = _append_heatmap_history


def _build_heatmap_response_from_history(*args, **kwargs):
    return _call_industry_helper("_build_heatmap_response_from_history", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_heatmap_response_from_history"] = _build_heatmap_response_from_history


def _load_live_heatmap_response(*args, **kwargs):
    return _call_industry_helper("_load_live_heatmap_response", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_live_heatmap_response"] = _load_live_heatmap_response


def _schedule_heatmap_refresh(*args, **kwargs):
    return _call_industry_helper("_schedule_heatmap_refresh", *args, **kwargs)


_INDUSTRY_WRAPPERS["_schedule_heatmap_refresh"] = _schedule_heatmap_refresh


def _resolve_symbol_with_provider(*args, **kwargs):
    return _call_industry_helper("_resolve_symbol_with_provider", *args, **kwargs)


_INDUSTRY_WRAPPERS["_resolve_symbol_with_provider"] = _resolve_symbol_with_provider


def _build_stock_responses(*args, **kwargs):
    return _call_industry_helper("_build_stock_responses", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_stock_responses"] = _build_stock_responses


def _count_quick_stock_detail_fields(*args, **kwargs):
    return _call_industry_helper("_count_quick_stock_detail_fields", *args, **kwargs)


_INDUSTRY_WRAPPERS["_count_quick_stock_detail_fields"] = _count_quick_stock_detail_fields


def _promote_detail_ready_quick_rows(*args, **kwargs):
    return _call_industry_helper("_promote_detail_ready_quick_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_promote_detail_ready_quick_rows"] = _promote_detail_ready_quick_rows


def _load_cached_quick_valuation(*args, **kwargs):
    return _call_industry_helper("_load_cached_quick_valuation", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_cached_quick_valuation"] = _load_cached_quick_valuation


def _backfill_quick_rows_with_cached_valuation(*args, **kwargs):
    return _call_industry_helper("_backfill_quick_rows_with_cached_valuation", *args, **kwargs)


_INDUSTRY_WRAPPERS["_backfill_quick_rows_with_cached_valuation"] = (
    _backfill_quick_rows_with_cached_valuation
)


def _build_full_industry_stock_response(*args, **kwargs):
    return _call_industry_helper("_build_full_industry_stock_response", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_full_industry_stock_response"] = _build_full_industry_stock_response


def _build_quick_industry_stock_response(*args, **kwargs):
    return _call_industry_helper("_build_quick_industry_stock_response", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_quick_industry_stock_response"] = _build_quick_industry_stock_response


def _coerce_trend_alignment_stock_rows(*args, **kwargs):
    return _call_industry_helper("_coerce_trend_alignment_stock_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_coerce_trend_alignment_stock_rows"] = _coerce_trend_alignment_stock_rows


def _load_trend_alignment_stock_rows(*args, **kwargs):
    return _call_industry_helper("_load_trend_alignment_stock_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_trend_alignment_stock_rows"] = _load_trend_alignment_stock_rows


def _build_trend_summary_from_stock_rows(*args, **kwargs):
    return _call_industry_helper("_build_trend_summary_from_stock_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_trend_summary_from_stock_rows"] = _build_trend_summary_from_stock_rows


def _should_align_trend_with_stock_rows(*args, **kwargs):
    return _call_industry_helper("_should_align_trend_with_stock_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_should_align_trend_with_stock_rows"] = _should_align_trend_with_stock_rows


def _schedule_full_stock_cache_build(*args, **kwargs):
    return _call_industry_helper("_schedule_full_stock_cache_build", *args, **kwargs)


_INDUSTRY_WRAPPERS["_schedule_full_stock_cache_build"] = _schedule_full_stock_cache_build


def _dedupe_leader_responses(*args, **kwargs):
    return _call_industry_helper("_dedupe_leader_responses", *args, **kwargs)


_INDUSTRY_WRAPPERS["_dedupe_leader_responses"] = _dedupe_leader_responses


def _get_or_create_provider(*args, **kwargs):
    return _call_industry_helper("_get_or_create_provider", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_or_create_provider"] = _get_or_create_provider


def get_industry_analyzer(*args, **kwargs):
    return _call_industry_helper("get_industry_analyzer", *args, **kwargs)


_INDUSTRY_WRAPPERS["get_industry_analyzer"] = get_industry_analyzer


def get_leader_scorer(*args, **kwargs):
    return _call_industry_helper("get_leader_scorer", *args, **kwargs)


_INDUSTRY_WRAPPERS["get_leader_scorer"] = get_leader_scorer


def _build_leader_context(*args, **kwargs):
    return _call_industry_helper("_build_leader_context", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_leader_context"] = _build_leader_context


def _get_leader_overview_cache_key(*args, **kwargs):
    return _call_industry_helper("_get_leader_overview_cache_key", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_leader_overview_cache_key"] = _get_leader_overview_cache_key


def _get_leader_provider_stocks_cache_key(*args, **kwargs):
    return _call_industry_helper("_get_leader_provider_stocks_cache_key", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_leader_provider_stocks_cache_key"] = _get_leader_provider_stocks_cache_key


def _get_leader_snapshot_prewarm_key(*args, **kwargs):
    return _call_industry_helper("_get_leader_snapshot_prewarm_key", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_leader_snapshot_prewarm_key"] = _get_leader_snapshot_prewarm_key


def _has_leader_board_rows(*args, **kwargs):
    return _call_industry_helper("_has_leader_board_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_has_leader_board_rows"] = _has_leader_board_rows


def _build_leader_boards_payload(*args, **kwargs):
    return _call_industry_helper("_build_leader_boards_payload", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_leader_boards_payload"] = _build_leader_boards_payload


def _prewarm_leader_stock_snapshot(*args, **kwargs):
    return _call_industry_helper("_prewarm_leader_stock_snapshot", *args, **kwargs)


_INDUSTRY_WRAPPERS["_prewarm_leader_stock_snapshot"] = _prewarm_leader_stock_snapshot


def _schedule_leader_stock_snapshot_prewarm(*args, **kwargs):
    return _call_industry_helper("_schedule_leader_stock_snapshot_prewarm", *args, **kwargs)


_INDUSTRY_WRAPPERS["_schedule_leader_stock_snapshot_prewarm"] = (
    _schedule_leader_stock_snapshot_prewarm
)


def _compute_and_cache_leader_overview(*args, **kwargs):
    return _call_industry_helper("_compute_and_cache_leader_overview", *args, **kwargs)


_INDUSTRY_WRAPPERS["_compute_and_cache_leader_overview"] = _compute_and_cache_leader_overview


def _schedule_leader_overview_build(*args, **kwargs):
    return _call_industry_helper("_schedule_leader_overview_build", *args, **kwargs)


_INDUSTRY_WRAPPERS["_schedule_leader_overview_build"] = _schedule_leader_overview_build


def _load_leader_overview_payload(*args, **kwargs):
    return _call_industry_helper("_load_leader_overview_payload", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_leader_overview_payload"] = _load_leader_overview_payload


def _get_bootstrap_leader_payload(*args, **kwargs):
    return _call_industry_helper("_get_bootstrap_leader_payload", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_bootstrap_leader_payload"] = _get_bootstrap_leader_payload


def _hydrate_bootstrap_with_cached_leaders(*args, **kwargs):
    return _call_industry_helper("_hydrate_bootstrap_with_cached_leaders", *args, **kwargs)


_INDUSTRY_WRAPPERS["_hydrate_bootstrap_with_cached_leaders"] = (
    _hydrate_bootstrap_with_cached_leaders
)


def _persist_leader_list_cache(*args, **kwargs):
    return _call_industry_helper("_persist_leader_list_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_persist_leader_list_cache"] = _persist_leader_list_cache


def _load_provider_stocks_for_leaders(*args, **kwargs):
    return _call_industry_helper("_load_provider_stocks_for_leaders", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_provider_stocks_for_leaders"] = _load_provider_stocks_for_leaders


def _compute_core_leader_stocks(*args, **kwargs):
    return _call_industry_helper("_compute_core_leader_stocks", *args, **kwargs)


_INDUSTRY_WRAPPERS["_compute_core_leader_stocks"] = _compute_core_leader_stocks


def _compute_hot_leader_stocks(*args, **kwargs):
    return _call_industry_helper("_compute_hot_leader_stocks", *args, **kwargs)


_INDUSTRY_WRAPPERS["_compute_hot_leader_stocks"] = _compute_hot_leader_stocks


def _load_leader_stock_list(*args, **kwargs):
    return _call_industry_helper("_load_leader_stock_list", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_leader_stock_list"] = _load_leader_stock_list


__all__ = [
    "SIX_DIGIT_SYMBOL_PATTERN",
    "_INDUSTRY_SERVICE_HELPERS",
    "_INDUSTRY_WRAPPERS",
    "ThreadPoolExecutor",
    "_append_heatmap_history",
    "_attach_leader_mini_trends",
    "_backfill_quick_rows_with_cached_valuation",
    "_build_full_industry_stock_response",
    "_build_heatmap_response_from_history",
    "_build_hot_industry_rank_responses",
    "_build_leader_boards_payload",
    "_build_leader_context",
    "_build_leader_detail_fallback",
    "_build_leading_stock_symbol_lookup",
    "_build_parity_price_data",
    "_build_quick_industry_stock_response",
    "_build_stock_responses",
    "_build_trend_summary_from_stock_rows",
    "_call_industry_helper",
    "_coerce_trend_alignment_stock_rows",
    "_collect_hot_leader_candidates",
    "_compute_and_cache_leader_overview",
    "_compute_core_leader_stocks",
    "_compute_hot_leader_stocks",
    "_count_quick_stock_detail_fields",
    "_dedupe_leader_responses",
    "_endpoint_cache",
    "_extract_leading_stock_symbol_lookup",
    "_get_bootstrap_leader_payload",
    "_get_endpoint_cache",
    "_get_leader_overview_cache_key",
    "_get_leader_provider_stocks_cache_key",
    "_get_leader_snapshot_prewarm_key",
    "_get_matching_parity_cache",
    "_get_or_create_provider",
    "_get_parity_cache",
    "_get_stale_endpoint_cache",
    "_get_stale_parity_cache",
    "_get_stock_build_status",
    "_get_stock_cache_keys",
    "_get_stock_status_key",
    "_has_leader_board_rows",
    "_heatmap_history",
    "_heatmap_history_loaded",
    "_heatmap_history_lock",
    "_hydrate_bootstrap_with_cached_leaders",
    "_is_fresh_parity_entry",
    "_leader_detail_error_status",
    "_leading_stock_symbol_lookup_cache",
    "_leading_stock_symbol_lookup_cache_time",
    "_load_cached_quick_valuation",
    "_load_heatmap_history_from_disk",
    "_load_leader_overview_payload",
    "_load_leader_stock_list",
    "_load_live_heatmap_response",
    "_load_provider_stocks_for_leaders",
    "_load_symbol_mini_trend",
    "_load_trend_alignment_stock_rows",
    "_map_industry_etfs",
    "_parity_cache",
    "_persist_heatmap_history_to_disk",
    "_persist_leader_list_cache",
    "_prewarm_leader_stock_snapshot",
    "_promote_detail_ready_quick_rows",
    "_resolve_industry_profile",
    "_resolve_symbol_with_provider",
    "_schedule_full_stock_cache_build",
    "_schedule_heatmap_refresh",
    "_schedule_leader_overview_build",
    "_schedule_leader_stock_snapshot_prewarm",
    "_serialize_heatmap_response",
    "_set_endpoint_cache",
    "_set_parity_cache",
    "_set_stock_build_status",
    "_should_align_trend_with_stock_rows",
    "_stocks_full_build_inflight",
    "_sync_industry_runtime_state",
    "_trim_heatmap_history_payload",
    "get_industry_analyzer",
    "get_leader_scorer",
    "industry_runtime",
]
