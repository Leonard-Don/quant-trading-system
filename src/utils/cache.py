"""
高级缓存管理模块
"""

import hashlib
import json

# import pickle  # 安全考虑：避免使用pickle，改用json序列化
import time
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Callable, List
from functools import wraps
import threading

# import os  # 暂时未使用
from pathlib import Path

from .config import PROJECT_ROOT, CACHE_TTL


class CacheManager:
    """高级缓存管理器"""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        default_ttl: int = CACHE_TTL,
        max_memory_items: int = 1000,
        use_disk: bool = True,
    ):
        self.use_disk = use_disk
        if self.use_disk:
            self.cache_dir = Path(cache_dir) if cache_dir else PROJECT_ROOT / "cache"
            self.cache_dir.mkdir(exist_ok=True)
        else:
            self.cache_dir = None
        self.default_ttl = default_ttl
        self.max_memory_items = max_memory_items
        self.memory_cache = {}
        self.access_times = {}  # LRU tracking
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
            "disk_reads": 0,
            "disk_writes": 0,
            "memory_usage": 0,
            "disk_usage": 0,
        }
        self._lock = threading.RLock()

    def _generate_key(self, key_data: Any) -> str:
        """生成缓存键 - 优化版本"""
        if isinstance(key_data, str):
            # 对于字符串，直接使用更快的哈希
            return hashlib.sha256(key_data.encode()).hexdigest()[:16]
        else:
            # 对于复杂对象，使用JSON序列化
            serialized = json.dumps(
                key_data, sort_keys=True, default=str, separators=(",", ":")
            )
            return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    def _is_expired(self, cache_entry: Dict) -> bool:
        """检查缓存是否过期"""
        if "expires_at" not in cache_entry:
            return False
        return datetime.now() > cache_entry["expires_at"]

    def _evict_lru_if_needed(self):
        """如果内存缓存超过限制，移除最少使用的项"""
        if len(self.memory_cache) >= self.max_memory_items:
            # 找到最少使用的项
            lru_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            del self.memory_cache[lru_key]
            del self.access_times[lru_key]
            self.cache_stats["evictions"] += 1
            self.cache_stats["deletes"] += 1

    def get(self, key: Any, default: Any = None) -> Any:
        """获取缓存值"""
        with self._lock:
            cache_key = self._generate_key(key)

            # 首先检查内存缓存
            if cache_key in self.memory_cache:
                entry = self.memory_cache[cache_key]
                if not self._is_expired(entry):
                    self.cache_stats["hits"] += 1
                    # 更新访问时间用于LRU
                    self.access_times[cache_key] = time.time()
                    return entry["value"]
                else:
                    del self.memory_cache[cache_key]
                    if cache_key in self.access_times:
                        del self.access_times[cache_key]


            # 检查磁盘缓存
            if self.use_disk:
                cache_file = self.cache_dir / f"{cache_key}.json"
                if cache_file.exists():
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            # 使用安全的json加载
                            entry = json.load(f)
                            
                            # 恢复 datetime 对象
                            if "expires_at" in entry and entry["expires_at"]:
                                try:
                                    entry["expires_at"] = datetime.fromisoformat(entry["expires_at"])
                                except (ValueError, TypeError):
                                    pass
                                    
                            if "created_at" in entry and entry["created_at"]:
                                try:
                                    entry["created_at"] = datetime.fromisoformat(entry["created_at"])
                                except (ValueError, TypeError):
                                    pass

                        if not self._is_expired(entry):
                            # 加载到内存缓存
                            self.memory_cache[cache_key] = entry
                            self.cache_stats["hits"] += 1
                            return entry["value"]
                        else:
                            cache_file.unlink()  # 删除过期文件
                    except Exception:
                        cache_file.unlink()  # 删除损坏的缓存文件

            self.cache_stats["misses"] += 1
            return default

    def set(self, key: Any, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        with self._lock:
            cache_key = self._generate_key(key)
            ttl = ttl or self.default_ttl

            entry = {
                "value": value,
                "created_at": datetime.now(),
                "expires_at": (
                    datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
                ),
            }

            # 检查是否需要清理内存缓存
            self._evict_lru_if_needed()

            # 存储到内存缓存
            self.memory_cache[cache_key] = entry
            self.access_times[cache_key] = time.time()

            # 异步存储到磁盘缓存（避免阻塞）
            if self.use_disk:
                cache_file = self.cache_dir / f"{cache_key}.json"
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(entry, f, ensure_ascii=False, indent=2, default=str)
                except Exception as e:
                    # 使用logging而不是print
                    import logging

                    logging.getLogger(__name__).warning(
                        f"Failed to write cache to disk: {e}"
                    )

            self.cache_stats["sets"] += 1

    def put(self, key: Any, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值的别名，用于兼容测试代码"""
        self.set(key, value, ttl)

    def __contains__(self, key: Any) -> bool:
        """检查缓存中是否存在该键"""
        with self._lock:
            cache_key = self._generate_key(key)
            if cache_key in self.memory_cache:
                entry = self.memory_cache[cache_key]
                if not self._is_expired(entry):
                    return True
            
            if self.use_disk:
                cache_file = self.cache_dir / f"{cache_key}.json"
                return cache_file.exists()
            
            return False

    def __len__(self) -> int:
        """返回缓存项数量"""
        return len(self.memory_cache)

    def size(self) -> int:
        """返回缓存项数量，用于兼容测试"""
        return len(self.memory_cache)

    @property
    def max_size(self) -> int:
        """返回最大缓存项数，用于兼容测试"""
        return self.max_memory_items

    def delete(self, key: Any) -> bool:
        """删除缓存项"""
        with self._lock:
            cache_key = self._generate_key(key)
            deleted = False

            # 从内存缓存删除
            if cache_key in self.memory_cache:
                del self.memory_cache[cache_key]
                deleted = True

            # 从磁盘缓存删除
            if self.use_disk:
                cache_file = self.cache_dir / f"{cache_key}.json"
                if cache_file.exists():
                    cache_file.unlink()
                    deleted = True

            if deleted:
                self.cache_stats["deletes"] += 1

            return deleted

    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            # 清空内存缓存
            self.memory_cache.clear()

            # 清空磁盘缓存
            if self.use_disk:
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink()

            # 重置统计
            self.cache_stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0}

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (
            self.cache_stats["hits"] / total_requests if total_requests > 0 else 0
        )

        return {
            **self.cache_stats,
            "hit_rate": hit_rate,
            "memory_cache_size": len(self.memory_cache),
            "disk_cache_files": len(list(self.cache_dir.glob("*.json"))),
        }


# 全局缓存管理器实例
cache_manager = CacheManager()


def cached(ttl: int = None, key_func: Callable = None):
    """缓存装饰器"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = {"func": func.__name__, "args": args, "kwargs": kwargs}

            # 尝试从缓存获取
            result = cache_manager.get(cache_key)
            if result is not None:
                return result

            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl)
            return result

        return wrapper

    return decorator


def cache_clear():
    """清空缓存的便捷函数"""
    cache_manager.clear()


def cache_stats():
    """获取缓存统计的便捷函数"""
    return cache_manager.get_stats()


class CacheAnalyzer:
    """缓存分析器"""

    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager
        self.logger = logging.getLogger(__name__)

    def get_cache_report(self) -> Dict[str, Any]:
        """获取缓存报告"""
        stats = self.cache_manager.get_stats()

        # 计算命中率
        total_requests = stats["hits"] + stats["misses"]
        hit_rate = (stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        # 计算内存使用情况
        memory_items = len(self.cache_manager.memory_cache)
        memory_usage_percent = memory_items / self.cache_manager.max_memory_items * 100

        return {
            "hit_rate": round(hit_rate, 2),
            "total_requests": total_requests,
            "memory_items": memory_items,
            "memory_usage_percent": round(memory_usage_percent, 2),
            "max_memory_items": self.cache_manager.max_memory_items,
            "stats": stats,
            "recommendations": self._get_recommendations(
                stats, hit_rate, memory_usage_percent
            ),
        }

    def _get_recommendations(
        self, stats: Dict, hit_rate: float, memory_usage: float
    ) -> List[str]:
        """获取优化建议"""
        recommendations = []

        if hit_rate < 50:
            recommendations.append("缓存命中率较低，考虑增加缓存TTL或优化缓存策略")

        if memory_usage > 90:
            recommendations.append("内存缓存使用率过高，考虑增加max_memory_items")

        if stats["evictions"] > stats["hits"] * 0.1:
            recommendations.append("缓存淘汰频繁，建议增加内存缓存大小")

        return recommendations

    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        cleaned_count = 0

        # 清理内存缓存中的过期项
        with self.cache_manager._lock:
            expired_keys = []
            for key, entry in self.cache_manager.memory_cache.items():
                if self.cache_manager._is_expired(entry):
                    expired_keys.append(key)

            for key in expired_keys:
                del self.cache_manager.memory_cache[key]
                if key in self.cache_manager.access_times:
                    del self.cache_manager.access_times[key]
                cleaned_count += 1

        self.logger.info(f"Cleaned {cleaned_count} expired cache entries")
        return cleaned_count


# 全局缓存分析器实例
cache_analyzer = CacheAnalyzer(cache_manager)
