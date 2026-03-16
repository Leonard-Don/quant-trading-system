"""
缓存中间件
实现HTTP响应缓存
"""

import hashlib
import time
import logging
from typing import Dict, Optional
from threading import Lock
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class CacheEntry:
    """缓存条目"""

    def __init__(self, response: Response, ttl: int):
        """
        Args:
            response: HTTP响应
            ttl: 生存时间（秒）
        """
        self.response = response
        self.created_at = time.time()
        self.ttl = ttl

    def is_expired(self) -> bool:
        """检查是否过期"""
        return (time.time() - self.created_at) > self.ttl


class CacheMiddleware(BaseHTTPMiddleware):
    """
    缓存中间件
    缓存GET请求的响应
    """

    def __init__(
        self,
        app,
        ttl: int = 300,  # 默认5分钟
        max_size: int = 1000,
        cacheable_methods: Optional[list] = None,
        cacheable_paths: Optional[list] = None,
    ):
        """
        Args:
            app: FastAPI应用实例
            ttl: 缓存生存时间（秒）
            max_size: 最大缓存条目数
            cacheable_methods: 可缓存的HTTP方法列表
            cacheable_paths: 可缓存的路径前缀列表
        """
        super().__init__(app)
        self.ttl = ttl
        self.max_size = max_size
        self.cacheable_methods = cacheable_methods or ["GET"]
        self.cacheable_paths = cacheable_paths or [
            "/strategies",
            "/symbols/search",
            "/market-data",
        ]

        self.cache: Dict[str, CacheEntry] = {}
        self.lock = Lock()

        # 统计信息
        self.hits = 0
        self.misses = 0

        logger.info(
            f"缓存中间件初始化: TTL={ttl}秒, " f"最大大小={max_size}, " f"可缓存方法={cacheable_methods}"
        )

    def _generate_cache_key(self, request: Request) -> str:
        """
        生成缓存键

        Args:
            request: HTTP请求

        Returns:
            缓存键
        """
        # 包含方法、路径和查询参数
        key_parts = [request.method, str(request.url.path), str(request.url.query)]

        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode(), usedforsecurity=False).hexdigest()

    def _is_cacheable(self, request: Request) -> bool:
        """
        检查请求是否可缓存

        Args:
            request: HTTP请求

        Returns:
            是否可缓存
        """
        # 检查HTTP方法
        if request.method not in self.cacheable_methods:
            return False

        # 检查路径
        path = request.url.path
        for cacheable_path in self.cacheable_paths:
            if path.startswith(cacheable_path):
                return True

        return False

    def _get_from_cache(self, cache_key: str) -> Optional[Response]:
        """
        从缓存中获取响应

        Args:
            cache_key: 缓存键

        Returns:
            缓存的响应，如果不存在或已过期则返回None
        """
        with self.lock:
            entry = self.cache.get(cache_key)

            if entry is None:
                self.misses += 1
                return None

            if entry.is_expired():
                # 删除过期条目
                del self.cache[cache_key]
                self.misses += 1
                return None

            self.hits += 1
            logger.debug(f"缓存命中: {cache_key}")
            return entry.response

    def _put_in_cache(self, cache_key: str, response: Response):
        """
        将响应放入缓存

        Args:
            cache_key: 缓存键
            response: HTTP响应
        """
        with self.lock:
            # 如果缓存已满，删除最旧的条目（简单LRU）
            if len(self.cache) >= self.max_size:
                oldest_key = min(
                    self.cache.keys(), key=lambda k: self.cache[k].created_at
                )
                del self.cache[oldest_key]
                logger.debug(f"缓存已满，删除最旧条目: {oldest_key}")

            self.cache[cache_key] = CacheEntry(response, self.ttl)
            logger.debug(f"响应已缓存: {cache_key}")

    def get_stats(self) -> Dict:
        """
        获取缓存统计信息

        Returns:
            统计信息字典
        """
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_requests": total_requests,
            "hit_rate": f"{hit_rate:.2f}%",
            "cache_size": len(self.cache),
            "max_size": self.max_size,
        }

    async def dispatch(self, request: Request, call_next):
        """
        处理请求

        Args:
            request: HTTP请求
            call_next: 下一个中间件或路由处理器

        Returns:
            HTTP响应
        """
        # 检查是否可缓存
        if not self._is_cacheable(request):
            return await call_next(request)

        # 生成缓存键
        cache_key = self._generate_cache_key(request)

        # 尝试从缓存获取
        cached_response = self._get_from_cache(cache_key)
        if cached_response:
            # 添加缓存头
            headers = dict(cached_response.headers)
            headers["X-Cache"] = "HIT"
            return Response(
                content=cached_response.body,
                status_code=cached_response.status_code,
                headers=headers,
                media_type=cached_response.media_type,
            )

        # 调用下一个处理器
        response = await call_next(request)

        # 只缓存成功的响应
        if 200 <= response.status_code < 300:
            # 读取响应体
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # 创建新的响应用于缓存
            cached_response = Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

            # 放入缓存
            self._put_in_cache(cache_key, cached_response)

            # 创建新的响应返回给客户端
            headers = dict(response.headers)
            headers["X-Cache"] = "MISS"
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

        return response
