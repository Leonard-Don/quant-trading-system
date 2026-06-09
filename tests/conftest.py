"""
pytest配置文件
"""

import copy
import os
import sys

import numpy as np
import pandas as pd
import pytest

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.backtest.backtester import Backtester  # noqa: E402
from src.data.data_manager import DataManager  # noqa: E402
from src.strategy.strategies import MovingAverageCrossover, RSIStrategy  # noqa: E402

# Class-level mutable caches on the data-provider classes. These persist across
# tests (the classes are module singletons), so without isolation a cache or
# tripped circuit breaker written by one test silently changes another's result
# — exactly the bug behind the flaky
# ``test_get_stock_list_by_industry_uses_tushare_leader_final_fallback``. We
# snapshot-and-restore them around every test rather than reset-to-empty, so the
# pre-test state (whatever it was) is preserved and any in-test mutation is
# discarded. Only data caches are listed — never paths, locks, or TTL constants.
# Add new caches here when you add them to a provider class.
_PROVIDER_CACHE_ATTRS: dict[tuple[str, str], tuple[str, ...]] = {
    ("src.data.providers.sina_ths_adapter", "SinaIndustryAdapter"): (
        "_circuit_breakers",
        "_stock_name_to_symbol_cache", "_stock_name_cache_time", "_stock_name_cache_loaded",
        "_ths_catalog_shared_cache", "_ths_catalog_shared_cache_time",
        "_ths_summary_shared_cache", "_ths_summary_shared_cache_time",
        "_ths_js_content_cache", "_ths_hexin_v_cache", "_ths_hexin_v_cache_time",
        "_sina_cached_stock_nodes", "_sina_cached_stock_nodes_time",
        "_candidate_industry_names_cache", "_cached_sina_industry_codes_cache",
        "_sina_industry_list_shared_cache", "_sina_industry_list_shared_cache_time",
        "_history_cache", "_history_cache_loaded",
        "_market_cap_snapshot_payload_cache", "_market_cap_snapshot_payload_cache_meta",
        "_akshare_valuation_snapshot_cache", "_akshare_valuation_snapshot_cache_time",
        "_akshare_valuation_snapshot_failure_at",
    ),
    ("src.data.providers.sina_provider", "SinaFinanceProvider"): (
        "_json_cache_memory",
        "_persistent_industry_list_frame_cache",
        "_persistent_industry_list_lookup_cache",
        "_persistent_industry_stocks_rows_cache",
        "_persistent_industry_stock_codes_cache",
    ),
    ("src.data.providers.akshare_provider", "AKShareProvider"): (
        "_shared_industry_meta_cache", "_shared_industry_meta_cache_time",
        "_shared_industry_stock_snapshot", "_shared_industry_stock_snapshot_time",
    ),
    ("src.analytics.leader_stock_scorer", "LeaderStockScorer"): (
        "_financial_cache", "_financial_cache_loaded",
    ),
}


def _resolve_provider_cache_targets():
    """Yield (class, attr-names) only for provider classes already imported.

    We read ``sys.modules`` rather than importing — a class that isn't loaded
    cannot leak, so there's nothing to isolate and no reason to force its
    (sometimes heavy, e.g. akshare) import on every test.
    """
    for (module_name, class_name), attrs in _PROVIDER_CACHE_ATTRS.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        cls = getattr(module, class_name, None)
        if cls is not None:
            yield cls, attrs


@pytest.fixture(autouse=True)
def _isolate_provider_class_caches(monkeypatch):
    """Keep provider class-level caches and the real Tushare token from bleeding
    across tests — the two shared-state problems behind the flaky Tushare
    fallback tests.

    1. Any helper that loads the developer's real ``.env`` into ``os.environ``
       (process-wide, ``override=False``) can leak a live Tushare token into
       "unit" tests that build a real ``TushareProvider``, turning them into
       live, latency-variable calls against the paid endpoint. Blanking both
       token vars keeps unit tests offline and off the paid quota; a test that
       needs a token still sets its own (its ``monkeypatch`` runs after this
       autouse setup, so it wins).
    2. The data-provider classes carry ~30 class-level caches (catalogs, symbol
       maps, valuation snapshots, circuit breakers …) that persist across tests.
       Snapshot them on setup and restore on teardown so a cache written — or a
       breaker tripped — by one test never changes another's outcome. Replaces
       the per-test hand-rolled save/restore boilerplate scattered through the
       provider test files.
    """

    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("TS_TOKEN", "")

    # The analysis cache (``cache_manager``) is DISK-BACKED — it writes JSON to
    # ``<repo>/cache/``. Without isolation, endpoint tests POLLUTE that real
    # cache with their fixtures (a fake ``平静股`` low-vol screen result written
    # by a test was later served as real data by a dev server) and their
    # ``cache_manager.clear()`` calls WIPE the developer's genuine cache.
    # Repoint it at a fresh per-test tmp dir and isolate the in-memory layer.
    import pathlib
    import shutil
    import tempfile

    from src.utils.cache import cache_manager

    # A standalone temp dir (NOT the test's own ``tmp_path`` — sharing it would
    # add an ``analysis_cache`` entry that tests inspecting ``tmp_path`` count).
    cache_tmp = pathlib.Path(tempfile.mkdtemp(prefix="pytest_analysis_cache_"))
    monkeypatch.setattr(cache_manager, "cache_dir", cache_tmp)
    _saved_memory_cache = dict(getattr(cache_manager, "memory_cache", {}))
    if hasattr(cache_manager, "memory_cache"):
        cache_manager.memory_cache.clear()

    snapshots: list[tuple[type, str, object]] = []
    for cls, attrs in _resolve_provider_cache_targets():
        for attr in attrs:
            if not hasattr(cls, attr):
                continue
            try:
                saved = copy.copy(getattr(cls, attr))
            except Exception:
                saved = getattr(cls, attr)
            snapshots.append((cls, attr, saved))

    try:
        yield
    finally:
        for cls, attr, saved in snapshots:
            setattr(cls, attr, saved)
        # Restore the in-memory cache layer (cache_dir is restored by monkeypatch).
        if hasattr(cache_manager, "memory_cache"):
            cache_manager.memory_cache.clear()
            cache_manager.memory_cache.update(_saved_memory_cache)
        shutil.rmtree(cache_tmp, ignore_errors=True)


@pytest.fixture
def sample_data():
    """生成测试用的样本数据"""
    dates = pd.date_range(start="2023-01-01", end="2023-12-31", freq="D")
    np.random.seed(42)

    # 生成模拟的OHLCV数据
    base_price = 100
    returns = np.random.normal(0.001, 0.02, len(dates))
    prices = base_price * (1 + returns).cumprod()

    data = pd.DataFrame(
        {
            "open": prices * (1 + np.random.normal(0, 0.001, len(dates))),
            "high": prices * (1 + np.abs(np.random.normal(0.002, 0.001, len(dates)))),
            "low": prices * (1 - np.abs(np.random.normal(0.002, 0.001, len(dates)))),
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, len(dates)),
        },
        index=dates,
    )

    # 确保high >= low, open和close在high和low之间
    data["high"] = np.maximum(data["high"], data[["open", "close"]].max(axis=1))
    data["low"] = np.minimum(data["low"], data[["open", "close"]].min(axis=1))

    return data


@pytest.fixture
def data_manager():
    """数据管理器实例"""
    return DataManager()


@pytest.fixture
def moving_average_strategy():
    """移动平均策略实例"""
    return MovingAverageCrossover(fast_period=10, slow_period=20)


@pytest.fixture
def rsi_strategy():
    """RSI策略实例"""
    return RSIStrategy(period=14, oversold=30, overbought=70)


@pytest.fixture
def backtester():
    """回测器实例"""
    return Backtester(initial_capital=10000, commission=0.001)


@pytest.fixture
def api_client():
    """API客户端（需要后端运行）"""
    import requests

    return requests.Session()


@pytest.fixture(scope="session")
def test_config():
    """测试配置"""
    return {
        "api_base_url": "http://localhost:8000",
        "test_symbol": "AAPL",
        "test_date_range": {"start": "2023-01-01", "end": "2023-12-31"},
    }
