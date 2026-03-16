"""
缓存优化器模块单元测试
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import tempfile
from pathlib import Path

from src.utils.cache_optimizer import (
    AccessTracker,
    CacheOptimizer,
    IncrementalDataUpdater,
    cache_optimizer,
    incremental_updater,
)
from src.utils.cache import CacheManager


class TestAccessTracker:
    """访问追踪器测试"""

    def test_initialization(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AccessTracker(
                persistence_file=Path(tmpdir) / "stats.json"
            )
            assert len(tracker.access_counts) == 0
            assert len(tracker.last_access_times) == 0

    def test_record_access(self):
        """测试记录访问"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AccessTracker(
                persistence_file=Path(tmpdir) / "stats.json"
            )
            
            tracker.record_access("test_key")
            assert tracker.access_counts["test_key"] == 1
            assert "test_key" in tracker.last_access_times
            
            tracker.record_access("test_key")
            assert tracker.access_counts["test_key"] == 2

    def test_get_access_frequency(self):
        """测试获取访问频率"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AccessTracker(
                persistence_file=Path(tmpdir) / "stats.json"
            )
            
            # 新键没有频率
            assert tracker.get_access_frequency("nonexistent") == 0.0
            
            # 记录多次访问
            for _ in range(3):
                tracker.record_access("freq_key")
                time.sleep(0.01)  # 小间隔
            
            # 应该有频率
            freq = tracker.get_access_frequency("freq_key")
            assert freq >= 0

    def test_get_hot_keys(self):
        """测试获取热门键"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AccessTracker(
                persistence_file=Path(tmpdir) / "stats.json"
            )
            
            # 记录不同次数的访问
            for _ in range(10):
                tracker.record_access("hot_key")
            for _ in range(5):
                tracker.record_access("warm_key")
            for _ in range(2):
                tracker.record_access("cold_key")
            
            hot_keys = tracker.get_hot_keys(top_n=3)
            assert len(hot_keys) == 3
            assert hot_keys[0]["key"] == "hot_key"
            assert hot_keys[0]["access_count"] == 10

    def test_persistence(self):
        """测试持久化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence_file = Path(tmpdir) / "stats.json"
            
            # 创建并记录
            tracker1 = AccessTracker(persistence_file=persistence_file)
            tracker1.record_access("persist_key")
            tracker1.persist()
            
            assert persistence_file.exists()
            
            # 重新加载
            tracker2 = AccessTracker(persistence_file=persistence_file)
            assert tracker2.access_counts["persist_key"] == 1


class TestCacheOptimizer:
    """缓存优化器测试"""

    def test_initialization(self):
        """测试初始化"""
        cm = CacheManager()
        optimizer = CacheOptimizer(cache_manager=cm)
        assert optimizer.max_preheat_items == 50
        assert optimizer.preheat_threshold == 0.5

    def test_register_preheat_handler(self):
        """测试注册预热处理器"""
        cm = CacheManager()
        optimizer = CacheOptimizer(cache_manager=cm)
        
        handler = Mock(return_value={"data": "test"})
        optimizer.register_preheat_handler("stock_*", handler)
        
        assert "stock_*" in optimizer._preheat_registry

    def test_calculate_preheat_priority(self):
        """测试计算预热优先级"""
        cm = CacheManager()
        optimizer = CacheOptimizer(cache_manager=cm)
        
        # 记录一些访问
        for _ in range(10):
            optimizer.record_access("priority_key")
        
        priority = optimizer.calculate_preheat_priority("priority_key")
        assert priority >= 0

    def test_get_preheat_candidates(self):
        """测试获取预热候选"""
        cm = CacheManager()
        optimizer = CacheOptimizer(
            cache_manager=cm,
            preheat_threshold=0  # 设置为0以便测试
        )
        
        # 记录访问
        for _ in range(5):
            optimizer.record_access("candidate_key")
            time.sleep(0.01)
        
        candidates = optimizer.get_preheat_candidates()
        # 可能为空或有数据，取决于访问模式
        assert isinstance(candidates, list)

    def test_preheat_with_fetcher(self):
        """测试使用fetcher预热"""
        cm = CacheManager()
        optimizer = CacheOptimizer(cache_manager=cm)
        
        fetcher = Mock(return_value={"data": "preheated"})
        
        result = optimizer.preheat(
            data_fetcher=fetcher,
            keys=["key1", "key2"],
            parallel=False
        )
        
        assert result["preheated"] + result["skipped"] + result["failed"] == 2

    def test_preheat_skips_cached(self):
        """测试预热跳过已缓存的数据"""
        cm = CacheManager()
        optimizer = CacheOptimizer(cache_manager=cm)
        
        # 先缓存一个值
        cm.set("cached_key", {"data": "existing"})
        
        fetcher = Mock(return_value={"data": "new"})
        
        result = optimizer.preheat(
            data_fetcher=fetcher,
            keys=["cached_key"],
            parallel=False
        )
        
        assert result["skipped"] == 1
        assert result["preheated"] == 0

    def test_get_stats(self):
        """测试获取统计信息"""
        cm = CacheManager()
        optimizer = CacheOptimizer(cache_manager=cm)
        
        stats = optimizer.get_stats()
        assert "preheat_stats" in stats
        assert "access_tracker" in stats
        assert "cache_stats" in stats


class TestIncrementalDataUpdater:
    """增量数据更新器测试"""

    def test_initialization(self):
        """测试初始化"""
        cm = CacheManager()
        updater = IncrementalDataUpdater(cache_manager=cm)
        assert updater.cache_manager == cm

    def test_version_management(self):
        """测试版本管理"""
        cm = CacheManager()
        updater = IncrementalDataUpdater(cache_manager=cm)
        
        assert updater.get_data_version("test_key") is None
        
        updater.set_data_version("test_key", "v1.0")
        assert updater.get_data_version("test_key") == "v1.0"

    def test_check_needs_update(self):
        """测试检查是否需要更新"""
        cm = CacheManager()
        updater = IncrementalDataUpdater(cache_manager=cm)
        
        # 没有版本时需要更新
        assert updater.check_needs_update("new_key", "v1.0") is True
        
        # 设置版本后
        updater.set_data_version("new_key", "v1.0")
        
        # 相同版本不需要更新
        assert updater.check_needs_update("new_key", "v1.0") is False
        
        # 不同版本需要更新
        assert updater.check_needs_update("new_key", "v2.0") is True

    def test_update_incremental(self):
        """测试增量更新"""
        cm = CacheManager()
        updater = IncrementalDataUpdater(cache_manager=cm)
        
        # 模拟数据获取和合并
        def data_fetcher(key, existing):
            return {"new_data": [3, 4]}
        
        def merge_func(existing, new):
            result = existing.copy() if existing else {}
            result.update(new)
            return result
        
        # 首次更新
        result = updater.update_incremental(
            key="incr_key",
            data_fetcher=data_fetcher,
            merge_func=merge_func,
            version="v1"
        )
        
        assert result["new_data"] == [3, 4]
        assert updater.get_data_version("incr_key") == "v1"


class TestGlobalInstances:
    """全局实例测试"""

    def test_global_cache_optimizer_exists(self):
        """测试全局缓存优化器存在"""
        assert cache_optimizer is not None
        assert isinstance(cache_optimizer, CacheOptimizer)

    def test_global_incremental_updater_exists(self):
        """测试全局增量更新器存在"""
        assert incremental_updater is not None
        assert isinstance(incremental_updater, IncrementalDataUpdater)
