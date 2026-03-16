"""
缓存优化器模块

提供智能缓存预热、访问频率追踪和增量数据更新功能
"""

import time
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from collections import defaultdict
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor

from .cache import cache_manager, CacheManager
from .config import PROJECT_ROOT

logger = logging.getLogger(__name__)


class AccessTracker:
    """访问频率追踪器"""

    def __init__(self, persistence_file: Optional[Path] = None):
        """
        初始化访问追踪器

        Args:
            persistence_file: 持久化文件路径
        """
        self.persistence_file = persistence_file or PROJECT_ROOT / "cache" / "access_stats.json"
        self.access_counts: Dict[str, int] = defaultdict(int)
        self.last_access_times: Dict[str, datetime] = {}
        self.access_patterns: Dict[str, List[float]] = defaultdict(list)  # 访问间隔
        self._lock = threading.RLock()
        
        self._load_persisted_data()

    def _load_persisted_data(self):
        """加载持久化的访问数据"""
        if self.persistence_file.exists():
            try:
                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.access_counts = defaultdict(int, data.get("access_counts", {}))
                    # 恢复时间戳
                    last_times = data.get("last_access_times", {})
                    for key, ts in last_times.items():
                        try:
                            self.last_access_times[key] = datetime.fromisoformat(ts)
                        except (ValueError, TypeError):
                            pass
                    self.access_patterns = defaultdict(list, data.get("access_patterns", {}))
                logger.info(f"Loaded access stats: {len(self.access_counts)} keys tracked")
            except Exception as e:
                logger.warning(f"Failed to load access stats: {e}")

    def persist(self):
        """持久化访问数据"""
        with self._lock:
            try:
                self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "access_counts": dict(self.access_counts),
                    "last_access_times": {
                        k: v.isoformat() for k, v in self.last_access_times.items()
                    },
                    "access_patterns": dict(self.access_patterns),
                    "updated_at": datetime.now().isoformat()
                }
                with open(self.persistence_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"Failed to persist access stats: {e}")

    def record_access(self, key: str):
        """
        记录一次访问

        Args:
            key: 缓存键
        """
        with self._lock:
            now = datetime.now()
            
            # 记录访问间隔
            if key in self.last_access_times:
                interval = (now - self.last_access_times[key]).total_seconds()
                patterns = self.access_patterns[key]
                patterns.append(interval)
                # 只保留最近100次访问间隔
                if len(patterns) > 100:
                    self.access_patterns[key] = patterns[-100:]
            
            self.access_counts[key] += 1
            self.last_access_times[key] = now

    def get_access_frequency(self, key: str) -> float:
        """
        获取访问频率（次/小时）

        Args:
            key: 缓存键

        Returns:
            每小时访问次数
        """
        with self._lock:
            if key not in self.access_counts:
                return 0.0
            
            count = self.access_counts[key]
            if key not in self.last_access_times:
                return 0.0
            
            # 基于访问间隔计算频率
            patterns = self.access_patterns.get(key, [])
            if not patterns:
                return 0.0
            
            avg_interval = sum(patterns) / len(patterns)
            if avg_interval == 0:
                return float('inf')
            
            # 转换为每小时访问次数
            return 3600 / avg_interval

    def get_hot_keys(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """
        获取热门访问键

        Args:
            top_n: 返回前N个

        Returns:
            热门键列表，包含访问统计
        """
        with self._lock:
            results = []
            for key in self.access_counts:
                frequency = self.get_access_frequency(key)
                results.append({
                    "key": key,
                    "access_count": self.access_counts[key],
                    "frequency_per_hour": round(frequency, 2),
                    "last_access": self.last_access_times.get(key, None)
                })
            
            # 按访问次数排序
            results.sort(key=lambda x: x["access_count"], reverse=True)
            return results[:top_n]


class CacheOptimizer:
    """
    缓存优化器

    提供：
    - 智能预热：基于访问频率预加载热门数据
    - 增量数据更新：只更新变化的数据
    - 预热优先级计算
    """

    def __init__(
        self,
        cache_manager: CacheManager = None,
        max_preheat_items: int = 50,
        preheat_threshold: float = 0.5  # 每小时至少访问0.5次才预热
    ):
        """
        初始化缓存优化器

        Args:
            cache_manager: 缓存管理器实例
            max_preheat_items: 最大预热项数
            preheat_threshold: 预热阈值（每小时访问次数）
        """
        self.cache_manager = cache_manager or cache_manager
        self.max_preheat_items = max_preheat_items
        self.preheat_threshold = preheat_threshold
        self.access_tracker = AccessTracker()
        
        # 预热注册表：存储预热函数
        self._preheat_registry: Dict[str, Callable] = {}
        self._preheat_stats = {
            "total_preheated": 0,
            "last_preheat_time": None,
            "preheat_duration_ms": 0
        }
        self._lock = threading.RLock()

    def register_preheat_handler(self, key_pattern: str, handler: Callable[[str], Any]):
        """
        注册预热处理函数

        Args:
            key_pattern: 键模式（如 'stock_data:*'）
            handler: 处理函数，接受键名返回数据
        """
        with self._lock:
            self._preheat_registry[key_pattern] = handler
            logger.info(f"Registered preheat handler for pattern: {key_pattern}")

    def calculate_preheat_priority(self, key: str) -> float:
        """
        计算预热优先级分数

        基于：
        - 访问频率（权重 0.5）
        - 最近访问时间（权重 0.3）
        - 访问总次数（权重 0.2）

        Args:
            key: 缓存键

        Returns:
            优先级分数 (0-100)
        """
        with self._lock:
            tracker = self.access_tracker
            
            # 访问频率分数
            frequency = tracker.get_access_frequency(key)
            freq_score = min(frequency * 10, 50)  # 最高50分
            
            # 最近访问时间分数
            recency_score = 0
            if key in tracker.last_access_times:
                hours_ago = (datetime.now() - tracker.last_access_times[key]).total_seconds() / 3600
                recency_score = max(0, 30 - hours_ago)  # 30小时内，越近分数越高
            
            # 访问总次数分数
            count = tracker.access_counts.get(key, 0)
            count_score = min(count / 10, 20)  # 最高20分
            
            return freq_score * 0.5 + recency_score * 0.3 + count_score * 0.2

    def get_preheat_candidates(self) -> List[Dict[str, Any]]:
        """
        获取预热候选列表

        Returns:
            候选列表，按优先级排序
        """
        hot_keys = self.access_tracker.get_hot_keys(self.max_preheat_items * 2)
        
        candidates = []
        for item in hot_keys:
            key = item["key"]
            frequency = item["frequency_per_hour"]
            
            # 过滤低频访问
            if frequency < self.preheat_threshold:
                continue
            
            priority = self.calculate_preheat_priority(key)
            candidates.append({
                **item,
                "priority": round(priority, 2),
                "should_preheat": priority > 10  # 优先级超过10才预热
            })
        
        # 按优先级排序
        candidates.sort(key=lambda x: x["priority"], reverse=True)
        return candidates[:self.max_preheat_items]

    def preheat(
        self,
        data_fetcher: Optional[Callable[[str], Any]] = None,
        keys: Optional[List[str]] = None,
        parallel: bool = True,
        max_workers: int = 4
    ) -> Dict[str, Any]:
        """
        执行智能预热

        Args:
            data_fetcher: 数据获取函数，如果未提供则使用注册的处理器
            keys: 指定要预热的键，如果未提供则自动选择热门键
            parallel: 是否并行预热
            max_workers: 并行工作线程数

        Returns:
            预热统计结果
        """
        start_time = time.time()
        
        # 确定要预热的键
        if keys is None:
            candidates = self.get_preheat_candidates()
            keys = [c["key"] for c in candidates if c["should_preheat"]]
        
        if not keys:
            logger.info("No keys to preheat")
            return {"preheated": 0, "failed": 0, "skipped": 0}
        
        logger.info(f"Starting preheat for {len(keys)} keys")
        
        results = {"preheated": 0, "failed": 0, "skipped": 0, "details": []}
        
        def preheat_single(key: str) -> Dict[str, Any]:
            """预热单个键"""
            try:
                # 检查缓存是否已存在且未过期
                existing = self.cache_manager.get(key)
                if existing is not None:
                    return {"key": key, "status": "skipped", "reason": "already_cached"}
                
                # 使用提供的fetcher或注册的处理器
                fetcher = data_fetcher
                if fetcher is None:
                    # 查找匹配的处理器
                    for pattern, handler in self._preheat_registry.items():
                        if self._match_pattern(key, pattern):
                            fetcher = handler
                            break
                
                if fetcher is None:
                    return {"key": key, "status": "failed", "reason": "no_handler"}
                
                # 获取数据并缓存
                data = fetcher(key)
                if data is not None:
                    self.cache_manager.set(key, data)
                    return {"key": key, "status": "preheated"}
                else:
                    return {"key": key, "status": "failed", "reason": "fetch_failed"}
                    
            except Exception as e:
                logger.warning(f"Failed to preheat key {key}: {e}")
                return {"key": key, "status": "failed", "reason": str(e)}
        
        # 执行预热
        if parallel and len(keys) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                detail_results = list(executor.map(preheat_single, keys))
        else:
            detail_results = [preheat_single(key) for key in keys]
        
        # 统计结果
        for result in detail_results:
            results["details"].append(result)
            if result["status"] == "preheated":
                results["preheated"] += 1
            elif result["status"] == "skipped":
                results["skipped"] += 1
            else:
                results["failed"] += 1
        
        duration_ms = (time.time() - start_time) * 1000
        
        # 更新统计
        with self._lock:
            self._preheat_stats["total_preheated"] += results["preheated"]
            self._preheat_stats["last_preheat_time"] = datetime.now()
            self._preheat_stats["preheat_duration_ms"] = duration_ms
        
        results["duration_ms"] = round(duration_ms, 2)
        logger.info(
            f"Preheat completed: {results['preheated']} preheated, "
            f"{results['skipped']} skipped, {results['failed']} failed "
            f"in {duration_ms:.0f}ms"
        )
        
        return results

    def _match_pattern(self, key: str, pattern: str) -> bool:
        """简单通配符模式匹配"""
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            return key.startswith(pattern[:-1])
        if pattern.startswith("*"):
            return key.endswith(pattern[1:])
        return key == pattern

    def record_access(self, key: str):
        """
        记录缓存访问

        应在每次缓存访问时调用

        Args:
            key: 缓存键
        """
        self.access_tracker.record_access(key)

    def get_stats(self) -> Dict[str, Any]:
        """获取优化器统计信息"""
        cache_stats = self.cache_manager.get_stats() if self.cache_manager else {}
        
        return {
            "preheat_stats": self._preheat_stats,
            "access_tracker": {
                "tracked_keys": len(self.access_tracker.access_counts),
                "hot_keys": self.access_tracker.get_hot_keys(10)
            },
            "cache_stats": cache_stats,
            "registered_handlers": list(self._preheat_registry.keys())
        }

    def persist_tracking_data(self):
        """持久化追踪数据"""
        self.access_tracker.persist()


class IncrementalDataUpdater:
    """
    增量数据更新器

    用于高效更新只有部分数据变化的场景
    """

    def __init__(self, cache_manager: CacheManager = None):
        """
        初始化增量更新器

        Args:
            cache_manager: 缓存管理器实例
        """
        self.cache_manager = cache_manager or cache_manager
        self._version_store: Dict[str, str] = {}
        self._lock = threading.RLock()

    def get_data_version(self, key: str) -> Optional[str]:
        """
        获取数据版本

        Args:
            key: 数据键

        Returns:
            版本字符串，如果不存在返回None
        """
        with self._lock:
            return self._version_store.get(key)

    def set_data_version(self, key: str, version: str):
        """
        设置数据版本

        Args:
            key: 数据键
            version: 版本字符串
        """
        with self._lock:
            self._version_store[key] = version

    def check_needs_update(
        self,
        key: str,
        current_version: str,
        version_fetcher: Optional[Callable[[str], str]] = None
    ) -> bool:
        """
        检查是否需要更新

        Args:
            key: 数据键
            current_version: 当前版本
            version_fetcher: 可选的版本获取函数

        Returns:
            是否需要更新
        """
        cached_version = self.get_data_version(key)
        
        if cached_version is None:
            return True
        
        if version_fetcher:
            try:
                remote_version = version_fetcher(key)
                return remote_version != cached_version
            except Exception as e:
                logger.warning(f"Failed to fetch version for {key}: {e}")
                return True
        
        return current_version != cached_version

    def update_incremental(
        self,
        key: str,
        data_fetcher: Callable[[str, Optional[Any]], Any],
        merge_func: Callable[[Any, Any], Any],
        version: str,
        ttl: Optional[int] = None
    ) -> Any:
        """
        执行增量更新

        Args:
            key: 数据键
            data_fetcher: 数据获取函数，接受(key, existing_data)返回增量数据
            merge_func: 合并函数，接受(existing_data, new_data)返回合并结果
            version: 新版本号
            ttl: 缓存过期时间

        Returns:
            更新后的完整数据
        """
        existing_data = self.cache_manager.get(key)
        
        try:
            # 获取增量数据
            incremental_data = data_fetcher(key, existing_data)
            
            if existing_data is not None and incremental_data is not None:
                # 合并数据
                merged_data = merge_func(existing_data, incremental_data)
            else:
                merged_data = incremental_data if incremental_data is not None else existing_data
            
            # 更新缓存
            if merged_data is not None:
                self.cache_manager.set(key, merged_data, ttl)
                self.set_data_version(key, version)
            
            return merged_data
            
        except Exception as e:
            logger.error(f"Failed to update incrementally for {key}: {e}")
            return existing_data


# 全局实例
cache_optimizer = CacheOptimizer(cache_manager)
incremental_updater = IncrementalDataUpdater(cache_manager)


def tracked_cache_get(key: Any, default: Any = None) -> Any:
    """
    带访问追踪的缓存获取

    Args:
        key: 缓存键
        default: 默认值

    Returns:
        缓存值或默认值
    """
    result = cache_manager.get(key, default)
    if result is not default:
        cache_optimizer.record_access(str(key))
    return result


def schedule_preheat(
    interval_seconds: int = 3600,
    data_fetcher: Optional[Callable] = None
):
    """
    调度定时预热任务

    Args:
        interval_seconds: 预热间隔（秒）
        data_fetcher: 数据获取函数
    """
    import atexit
    
    def preheat_task():
        while True:
            time.sleep(interval_seconds)
            try:
                cache_optimizer.preheat(data_fetcher)
            except Exception as e:
                logger.error(f"Scheduled preheat failed: {e}")
    
    thread = threading.Thread(target=preheat_task, daemon=True)
    thread.start()
    
    # 程序退出时持久化数据
    atexit.register(cache_optimizer.persist_tracking_data)
    
    logger.info(f"Scheduled preheat every {interval_seconds} seconds")
