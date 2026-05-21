"""集成测试：CacheManager 支撑下的 industry heatmap 缓存周期。

This integration suite exercises ``src.utils.cache.CacheManager`` as the
persistence boundary for an industry-heatmap-shaped payload, covering:

* cold-cache miss + full computation
* warm-cache hit (no recompute)
* TTL expiry forcing recomputation
* disk-snapshot reload after a simulated process restart

Mapping note: ``IndustryAnalyzer.get_industry_heatmap_data`` in
``src/analytics/industry_analyzer.py`` currently caches via its own
in-process dict (``self._cached_data``, 30-minute TTL) rather than the
shared ``CacheManager`` utility. This integration test therefore targets
the closest existing reusable cache boundary -- ``CacheManager`` -- so
the memory + disk persistence cycle is exercised end-to-end with a
payload that mirrors the canonical heatmap shape (``industries`` /
``max_value`` / ``min_value`` / ``update_time``). Synthetic deterministic
data only; no network, no DB, no analyzer dependencies.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.utils.cache import CacheManager

HEATMAP_KEY = "industry_heatmap|days:5"


def _synthetic_heatmap_payload(seed: int) -> Dict[str, Any]:
    """Return a deterministic heatmap-shaped dict.

    Mirrors ``IndustryAnalyzer.get_industry_heatmap_data`` closely enough
    to exercise serialization (lists of dicts, mixed numeric types)
    without touching any DataFrame or analyzer code.
    """
    industries: List[Dict[str, Any]] = [
        {
            "name": f"sector-{i}",
            "value": seed * 10 + i,
            "total_score": 50 + i,
            "size": (seed * 100 + i) * 1_000_000,
            "stockCount": 10 + i,
            "moneyFlow": seed + i,
            "industryVolatilitySource": "synthetic",
        }
        for i in range(3)
    ]
    values = [item["value"] for item in industries]
    return {
        "industries": industries,
        "max_value": max(values),
        "min_value": min(values),
        "update_time": "2026-05-09T00:00:00",
        "seed": seed,
    }


class _RecordingHeatmapBuilder:
    """Test double for an industry heatmap computation pipeline.

    Increments ``calls`` each time ``compute()`` runs so tests can prove
    whether a cache lookup short-circuited the (notionally expensive)
    heatmap build.
    """

    def __init__(self) -> None:
        self.calls = 0

    def compute(self) -> Dict[str, Any]:
        self.calls += 1
        return _synthetic_heatmap_payload(seed=self.calls)


def _heatmap_compute_or_get(
    cache: CacheManager,
    key: str,
    builder: _RecordingHeatmapBuilder,
    *,
    ttl: int,
) -> Dict[str, Any]:
    """Compute-or-fetch boundary mirroring how a heatmap service would use the cache."""
    cached = cache.get(key)
    if cached is not None:
        return cached
    fresh = builder.compute()
    cache.set(key, fresh, ttl=ttl)
    return fresh


@pytest.fixture
def heatmap_cache(tmp_path) -> CacheManager:
    """A disk-backed CacheManager isolated to ``tmp_path`` (no project pollution)."""
    return CacheManager(
        cache_dir=str(tmp_path / "heatmap_cache"),
        default_ttl=3600,
        use_disk=True,
    )


def test_cold_industry_heatmap_miss_runs_full_computation(heatmap_cache):
    builder = _RecordingHeatmapBuilder()

    payload = _heatmap_compute_or_get(heatmap_cache, HEATMAP_KEY, builder, ttl=3600)

    assert builder.calls == 1, "cold cache must invoke the heatmap builder exactly once"
    assert {"industries", "max_value", "min_value", "update_time"} <= payload.keys()
    assert payload["industries"][0]["name"] == "sector-0"
    assert payload["max_value"] >= payload["min_value"]

    stats = heatmap_cache.get_stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 0
    assert stats["sets"] == 1
    assert stats["disk_cache_files"] == 1
    assert stats["memory_cache_size"] == 1


def test_warm_industry_heatmap_cache_hit_skips_recompute(heatmap_cache):
    builder = _RecordingHeatmapBuilder()

    first = _heatmap_compute_or_get(heatmap_cache, HEATMAP_KEY, builder, ttl=3600)
    second = _heatmap_compute_or_get(heatmap_cache, HEATMAP_KEY, builder, ttl=3600)

    assert builder.calls == 1, "warm cache must short-circuit; builder runs once"
    assert second == first

    stats = heatmap_cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["sets"] == 1


def test_industry_heatmap_ttl_expiry_forces_recompute(heatmap_cache):
    builder = _RecordingHeatmapBuilder()

    _heatmap_compute_or_get(heatmap_cache, HEATMAP_KEY, builder, ttl=3600)
    assert builder.calls == 1

    # Simulate TTL elapsing without sleeping the test: backdate ``expires_at``
    # in both the in-memory entry and the on-disk snapshot. CacheManager
    # treats either backend's expiry as authoritative (see ``_is_expired``).
    cache_key = heatmap_cache._generate_key(HEATMAP_KEY)
    # Use a generous offset so CI clock granularity or scheduling delays cannot
    # make the synthetic expiry appear fresh at the comparison boundary.
    backdated = datetime.now() - timedelta(minutes=1)
    heatmap_cache.memory_cache[cache_key]["expires_at"] = backdated

    cache_file = heatmap_cache.cache_dir / f"{cache_key}.json"
    raw = json.loads(cache_file.read_text(encoding="utf-8"))
    raw["expires_at"] = backdated.isoformat()
    cache_file.write_text(json.dumps(raw, default=str), encoding="utf-8")

    refreshed = _heatmap_compute_or_get(heatmap_cache, HEATMAP_KEY, builder, ttl=3600)

    assert builder.calls == 2, "expired cache must trigger a fresh heatmap build"
    assert refreshed["seed"] == 2

    after = json.loads(cache_file.read_text(encoding="utf-8"))
    assert after["value"]["seed"] == 2


def test_industry_heatmap_disk_snapshot_survives_restart(tmp_path):
    cache_dir = tmp_path / "heatmap_cache_persistent"

    first_cache = CacheManager(cache_dir=str(cache_dir), default_ttl=3600, use_disk=True)
    builder = _RecordingHeatmapBuilder()
    original = _heatmap_compute_or_get(first_cache, HEATMAP_KEY, builder, ttl=3600)

    assert builder.calls == 1
    snapshot_path: Path = cache_dir / f"{first_cache._generate_key(HEATMAP_KEY)}.json"
    assert snapshot_path.exists(), "disk snapshot must be written on cold compute"

    # Drop the in-memory cache and stand up a fresh one against the same disk dir
    del first_cache
    second_cache = CacheManager(cache_dir=str(cache_dir), default_ttl=3600, use_disk=True)
    assert len(second_cache.memory_cache) == 0

    reloaded = second_cache.get(HEATMAP_KEY)
    assert reloaded == original
    second_stats = second_cache.get_stats()
    assert second_stats["hits"] == 1
    assert second_stats["misses"] == 0

    rebuild_after_restart = _RecordingHeatmapBuilder()
    again = _heatmap_compute_or_get(
        second_cache, HEATMAP_KEY, rebuild_after_restart, ttl=3600
    )
    assert rebuild_after_restart.calls == 0
    assert again == original
