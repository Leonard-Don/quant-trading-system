"""In-process response caches for the ETF-rotation endpoint.

Extracted from ``etf_rotation.py`` to keep the whole caching concern in one
place. Each cache maps a parameter-tuple key to ``(cached_at_epoch, payload)``
and is **mutated in place** (``cache[key] = value`` / ``.clear()``) — the names
are never rebound — so importing these dict objects into ``etf_rotation.py``
shares the *exact same* instances the route handlers read and write. The
``reset_*_for_tests`` hooks ``.clear()`` the shared dicts; ``etf_rotation.py``
re-exports them so tests keep calling ``etf_endpoint.reset_*_for_tests()``
unchanged.
"""

from typing import Any

# --- Policy-factor attribution: 5-min TTL; cache keys include audit-log
#     size/mtime so new rows invalidate. The sweep is ~50ms, so this keeps
#     it from firing on every UI poll. ---
_ATTRIBUTION_CACHE_TTL = 300.0  # 5 minutes
_attribution_cache: dict[tuple[int, str, int, int], tuple[float, dict[str, Any]]] = {}


def reset_attribution_cache_for_tests() -> None:
    """Drop the attribution cache — tests call this between scenarios."""

    _attribution_cache.clear()


# --- Walk-forward backtest: 1-hour TTL. The full run is ~30-60s (~13 windows),
#     so a follow-up UI poll returns instantly. Key includes the price-matrix
#     mtime/size so a new CSV invalidates everything in-flight. ---
_WALKFORWARD_CACHE_TTL = 3600.0  # 1 hour
_walkforward_cache: dict[
    tuple[
        str, str, int, int, int, bool, int, float, str, int, int,
    ],
    tuple[float, dict[str, Any]],
] = {}


def reset_walkforward_cache_for_tests() -> None:
    """Drop the walkforward cache — tests call this between scenarios."""

    _walkforward_cache.clear()


# --- Multi-strategy comparison: 1-hour TTL, keyed on every param that
#     materially affects the result + the price CSV mtime/size. ---
_STRATEGY_COMPARISON_CACHE_TTL = 3600.0  # 1 hour
_strategy_comparison_cache: dict[
    tuple[
        str, str, str, int, bool, int, float, str, str, int, int,
    ],
    tuple[float, dict[str, Any]],
] = {}
