"""
pytest配置文件
"""

import copy
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.backtest.backtester import Backtester  # noqa: E402
from src.data.data_manager import DataManager  # noqa: E402
from src.strategy.strategies import MovingAverageCrossover, RSIStrategy  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_etf_rotation_external_state(monkeypatch, tmp_path):
    """Keep ETF rotation tests independent of the developer's local config.

    The CLI/API auto-load ``~/.config/etf-rotation/holdings.json`` and call
    ``realtime_manager`` for live quotes by default. Both must be neutralised
    in unit tests so the same suite passes on a fresh checkout and a fully
    configured workstation. Individual tests can monkeypatch the helpers
    back to a real implementation when they want to exercise that path.
    """

    monkeypatch.delenv("ETF_HOLDINGS_PATH", raising=False)
    monkeypatch.delenv("ETF_AUDIT_LOG_PATH", raising=False)
    monkeypatch.delenv("ETF_STRATEGY_CONFIG_PATH", raising=False)
    monkeypatch.setenv("ETF_PREFERENCES_PATH", str(tmp_path / "etf_preferences.json"))

    # Neutralise the strategy.json loader so the dev workstation's live
    # config (with real manual_overrides, holdings, etc.) never bleeds
    # into a "should be a fresh default" unit-test path. Tests that want
    # to exercise specific config can still pass `path=` explicitly to
    # ``load_strategy_config``.
    try:
        from src.strategy import etf_rotation_config_loader as _cfg_loader
        monkeypatch.setattr(
            _cfg_loader,
            "DEFAULT_CONFIG_PATH",
            Path("/nonexistent/etf-rotation/strategy.json"),
        )
    except ImportError:
        pass

    try:
        from scripts import daily_etf_signal
    except ImportError:
        # Skip the isolation when daily_etf_signal isn't on the path —
        # tests that don't touch it shouldn't care.
        return

    monkeypatch.setattr(
        daily_etf_signal,
        "DEFAULT_HOLDINGS_PATH",
        Path("/nonexistent/etf-rotation/holdings.json"),
    )
    monkeypatch.setattr(
        daily_etf_signal,
        "DEFAULT_AUDIT_LOG_PATH",
        Path("/nonexistent/etf-rotation/audit.jsonl"),
    )

    def _empty_quote_fetch(codes, *, use_cache=True):
        return {}, {
            "requested": len(codes) if codes else 0,
            "resolved": 0,
            "missing": len(codes) if codes else 0,
            "use_cache": use_cache,
            "offline": True,
        }

    monkeypatch.setattr(daily_etf_signal, "fetch_live_quotes", _empty_quote_fetch)

    # Reset the EtfRotationService singleton between tests so each test
    # starts with no cached plan (the FastAPI lifespan hook installs one
    # in production, but in unit tests we want isolation).
    try:
        from backend.app.api.v1.endpoints import etf_rotation as etf_endpoint
    except ImportError:
        return
    etf_endpoint.reset_service_for_tests()
    etf_endpoint.reset_preferences_for_tests()
    try:
        from src.strategy.etf_rotation_preferences import reset_preferences_store_for_tests
    except ImportError:
        return
    reset_preferences_store_for_tests()


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

    1. ``etf_price_history._get_tushare_token()`` loads the developer's real
       ``.env`` into ``os.environ`` (process-wide, ``override=False``). Once any
       ETF test triggered it, later "unit" tests that built a real
       ``TushareProvider`` issued live, latency-variable calls against the paid
       endpoint. Blanking both token vars keeps unit tests offline and off the
       paid quota; a test that needs a token still sets its own (its
       ``monkeypatch`` runs after this autouse setup, so it wins).
    2. The data-provider classes carry ~30 class-level caches (catalogs, symbol
       maps, valuation snapshots, circuit breakers …) that persist across tests.
       Snapshot them on setup and restore on teardown so a cache written — or a
       breaker tripped — by one test never changes another's outcome. Replaces
       the per-test hand-rolled save/restore boilerplate scattered through the
       provider test files.
    """

    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("TS_TOKEN", "")

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
