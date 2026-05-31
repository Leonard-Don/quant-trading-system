"""Regression guard for the fragile industry ``_compat`` ↔ ``runtime`` contract.

``backend/app/api/v1/endpoints/industry/_compat.py`` is a deliberately-temporary
shim: at import it captures runtime helper *objects* into
``_INDUSTRY_SERVICE_HELPERS`` and snapshots a fixed set of module-level state
names, then re-syncs test patches from the endpoint package back onto the
``runtime`` module. That contract is invisible at call sites, so any refactor
that moves a helper out of ``runtime.py`` without re-exporting it (or renames a
synced state attribute) would silently break monkeypatch-based tests and the
sub-router call path.

These pure, side-effect-free assertions pin the contract so such a regression
fails loudly here instead. They are intentionally hermetic (no monkeypatch, no
network) — consistent with the suite's isolation discipline.
"""

import backend.app.api.v1.endpoints.industry as industry_endpoint
from backend.app.api.v1.endpoints.industry import _compat
from backend.app.services.industry import runtime

# The exact set of module-level state names _compat snapshots from runtime and
# re-syncs on every helper call (_sync_industry_runtime_state). If a refactor
# moves any of these out of runtime.py, it MUST be re-imported back so this
# stays true — otherwise the resync setattr targets a missing/stale attribute.
_SYNCED_STATE_NAMES = (
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
)

_EXPECTED_ALL_COUNT = 66


def test_runtime_all_surface_is_stable_and_resolvable():
    """runtime.__all__ must keep its full public surface, every name resolvable."""
    names = list(runtime.__all__)
    assert len(names) == _EXPECTED_ALL_COUNT, (
        f"runtime.__all__ has {len(names)} names, expected {_EXPECTED_ALL_COUNT}. "
        "If you intentionally changed the public surface, update this guard."
    )
    assert len(names) == len(set(names)), "duplicate names in runtime.__all__"
    missing = [n for n in names if not hasattr(runtime, n)]
    assert not missing, f"names in __all__ that do not resolve on runtime: {missing}"


def test_compat_captured_helpers_resolve_on_runtime_as_callables():
    """Every helper _compat captured at import must still resolve on runtime."""
    unresolved = []
    not_callable = []
    for name in _compat._INDUSTRY_SERVICE_HELPERS:
        attr = getattr(runtime, name, None)
        if attr is None:
            unresolved.append(name)
        elif not callable(attr):
            not_callable.append(name)
    assert not unresolved, f"_compat-captured helpers missing from runtime: {unresolved}"
    assert not not_callable, f"_compat-captured helpers not callable on runtime: {not_callable}"


def test_synced_state_names_are_present_on_runtime_and_package():
    """The state names _compat re-syncs must exist on both runtime and the package."""
    missing_runtime = [n for n in _SYNCED_STATE_NAMES if not hasattr(runtime, n)]
    missing_pkg = [n for n in _SYNCED_STATE_NAMES if not hasattr(industry_endpoint, n)]
    assert not missing_runtime, f"synced state missing on runtime: {missing_runtime}"
    assert not missing_pkg, f"synced state missing on endpoint package: {missing_pkg}"


def test_parity_cluster_surface_resolves_on_runtime():
    """Directly guards the parity-cluster extraction: names must stay on runtime."""
    parity_names = (
        "_set_parity_cache",
        "_get_parity_cache",
        "_get_stale_parity_cache",
        "_is_fresh_parity_entry",
        "_get_matching_parity_cache",
        "_build_leader_detail_fallback",
        "_parity_cache",
    )
    missing = [n for n in parity_names if not hasattr(runtime, n)]
    assert not missing, f"parity-cluster names not resolvable on runtime: {missing}"
    # The shared cache dict identity is what _compat's state-sync relies on.
    assert isinstance(runtime._parity_cache, dict)
