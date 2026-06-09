"""Regression guard: the autouse fixture must isolate the disk-backed analysis
cache away from the developer's real ``<repo>/cache/`` during tests.

Without this, endpoint tests that call ``_set_cached_analysis`` write their
fixtures into the production cache (a fake ``平静股`` low-vol screen result was
once served as real data by a dev server started after a test run) and their
``cache_manager.clear()`` calls wipe the genuine cache.
"""

from __future__ import annotations

from src.utils.cache import cache_manager
from src.utils.config import PROJECT_ROOT


def test_cache_manager_is_redirected_off_the_production_dir():
    prod = PROJECT_ROOT / "cache"
    assert cache_manager.cache_dir is not None
    assert cache_manager.cache_dir.resolve() != prod.resolve(), (
        "autouse fixture must repoint cache_manager.cache_dir to a temp dir so "
        "tests never read/write/clear the real cache"
    )


def test_writes_during_a_test_do_not_touch_production_cache(tmp_path):
    # A set() lands in the isolated temp dir, not <repo>/cache/.
    cache_manager.set("conftest-isolation-probe", {"v": 1})
    prod = PROJECT_ROOT / "cache"
    if prod.exists():
        names = [p.name for p in prod.glob("*.json")]
        # the probe must not have been written into the production cache dir
        assert all("conftest-isolation-probe" not in n for n in names)
    assert cache_manager.get("conftest-isolation-probe") == {"v": 1}
