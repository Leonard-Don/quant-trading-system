"""
API请求限流中间件
实现基于令牌桶算法的速率限制
"""

import time
import logging
import hashlib
from typing import Any, Dict, List, Optional
from collections import defaultdict
from threading import Lock
from functools import wraps
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)


class TokenBucket:
    """令牌桶实现"""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: 桶的容量（最大令牌数）
            refill_rate: 令牌填充速率（令牌/秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = Lock()

    def consume(self, tokens: int = 1) -> Dict[str, Any]:
        """
        消费令牌

        Args:
            tokens: 要消费的令牌数

        Returns:
            包含允许状态、剩余令牌与建议重试时间
        """
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return {
                    "allowed": True,
                    "remaining": max(0, int(self.tokens)),
                    "retry_after": 0,
                }
            missing_tokens = max(0.0, tokens - self.tokens)
            retry_after = (missing_tokens / self.refill_rate) if self.refill_rate > 0 else 60.0
            return {
                "allowed": False,
                "remaining": max(0, int(self.tokens)),
                "retry_after": max(1, int(retry_after) + 1),
            }

    def _refill(self):
        """重新填充令牌"""
        now = time.time()
        elapsed = now - self.last_refill

        # 根据经过的时间计算应该添加的令牌数
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now


class RateLimiter:
    """速率限制器"""

    def __init__(self, requests_per_minute: int = 60, burst_size: Optional[int] = None):
        """
        Args:
            requests_per_minute: 每分钟允许的请求数
            burst_size: 突发请求大小（默认为requests_per_minute）
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size or requests_per_minute

        # 每秒填充速率
        self.refill_rate = requests_per_minute / 60.0

        # 客户端令牌桶映射
        self.buckets: Dict[str, TokenBucket] = {}
        self.endpoint_rules: List[Dict[str, Any]] = []
        self.endpoint_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"allowed": 0, "blocked": 0, "last_seen": None, "rule_pattern": "default"}
        )
        self.identity_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"allowed": 0, "blocked": 0, "last_seen": None}
        )
        self.recent_blocks: List[Dict[str, Any]] = []

        self.lock = Lock()
        logger.info(
            f"速率限制器初始化: {requests_per_minute} 请求/分钟, " f"突发大小: {self.burst_size}"
        )

    def _make_bucket(self, rule: Dict[str, Any]) -> TokenBucket:
        return TokenBucket(
            int(rule.get("burst_size") or self.burst_size),
            float(rule.get("requests_per_minute") or self.requests_per_minute) / 60.0,
        )

    def configure_endpoint_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_rules = []
        for index, rule in enumerate(rules or []):
            if not isinstance(rule, dict):
                continue
            pattern = str(rule.get("pattern") or "").strip()
            if not pattern:
                continue
            requests_per_minute = int(rule.get("requests_per_minute") or self.requests_per_minute)
            burst_size = int(rule.get("burst_size") or requests_per_minute)
            normalized_rules.append(
                {
                    "id": str(rule.get("id") or f"rule_{index + 1}"),
                    "pattern": pattern,
                    "requests_per_minute": max(1, requests_per_minute),
                    "burst_size": max(1, burst_size),
                    "enabled": bool(rule.get("enabled", True)),
                }
            )
        with self.lock:
            self.endpoint_rules = normalized_rules
            self.buckets = {}
        return list(self.endpoint_rules)

    def configure_defaults(self, requests_per_minute: int, burst_size: Optional[int] = None) -> None:
        with self.lock:
            self.requests_per_minute = max(1, int(requests_per_minute))
            self.burst_size = max(1, int(burst_size or requests_per_minute))
            self.refill_rate = self.requests_per_minute / 60.0
            self.buckets = {}

    def _match_rule(self, endpoint: str) -> Dict[str, Any]:
        with self.lock:
            active_rules = list(self.endpoint_rules)
        for rule in active_rules:
            if not rule.get("enabled", True):
                continue
            pattern = str(rule.get("pattern") or "")
            if pattern.endswith("*") and endpoint.startswith(pattern[:-1]):
                return dict(rule)
            if endpoint == pattern:
                return dict(rule)
        return {
            "id": "default",
            "pattern": "default",
            "requests_per_minute": self.requests_per_minute,
            "burst_size": self.burst_size,
            "enabled": True,
        }

    def is_local_request(self, request: Request) -> bool:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            client_host = forwarded_for.split(",")[0].strip().lower()
            if client_host in {"127.0.0.1", "::1", "localhost"}:
                return True
        real_ip = str(request.headers.get("X-Real-IP") or "").strip().lower()
        if real_ip in {"127.0.0.1", "::1", "localhost"}:
            return True
        if request.client and str(request.client.host).strip().lower() in {"127.0.0.1", "::1", "localhost"}:
            return True
        return False

    def get_client_identity(self, request: Request) -> Dict[str, str]:
        endpoint = request.url.path
        auth_header = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")
        user_hint = request.headers.get("X-User-Id", "")
        if auth_header.lower().startswith("bearer "):
            digest = hashlib.sha256(auth_header.encode("utf-8")).hexdigest()[:16]
            return {"identity_type": "bearer", "subject": f"user-token:{digest}", "endpoint": endpoint}
        if api_key:
            digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
            return {"identity_type": "api_key", "subject": f"api-key:{digest}", "endpoint": endpoint}
        if user_hint:
            digest = hashlib.sha256(user_hint.encode("utf-8")).hexdigest()[:16]
            return {"identity_type": "user", "subject": f"user:{digest}", "endpoint": endpoint}

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return {"identity_type": "ip", "subject": f"ip:{forwarded_for.split(',')[0].strip()}", "endpoint": endpoint}

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return {"identity_type": "ip", "subject": f"ip:{real_ip}", "endpoint": endpoint}

        if request.client:
            return {"identity_type": "ip", "subject": f"ip:{request.client.host}", "endpoint": endpoint}

        return {"identity_type": "unknown", "subject": "unknown", "endpoint": endpoint}

    def get_client_id(self, request: Request) -> str:
        """
        获取客户端标识

        Args:
            request: FastAPI请求对象

        Returns:
            客户端标识
        """
        identity = self.get_client_identity(request)
        return f"{identity['subject']}:{identity['endpoint']}"

    def evaluate(self, request: Request) -> Dict[str, Any]:
        identity = self.get_client_identity(request)
        endpoint = identity["endpoint"]
        rule = self._match_rule(endpoint)
        bucket_key = f"{identity['subject']}:{endpoint}:{rule['pattern']}"
        with self.lock:
            bucket = self.buckets.get(bucket_key)
            expected_capacity = int(rule.get("burst_size") or self.burst_size)
            expected_refill = float(rule.get("requests_per_minute") or self.requests_per_minute) / 60.0
            if bucket is None or bucket.capacity != expected_capacity or abs(bucket.refill_rate - expected_refill) > 1e-9:
                bucket = self._make_bucket(rule)
                self.buckets[bucket_key] = bucket

        bucket_result = bucket.consume(1)
        now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        endpoint_stat = self.endpoint_stats[endpoint]
        identity_stat = self.identity_stats[identity["subject"]]
        endpoint_stat["last_seen"] = now
        endpoint_stat["rule_pattern"] = rule.get("pattern") or "default"
        identity_stat["last_seen"] = now
        if bucket_result["allowed"]:
            endpoint_stat["allowed"] += 1
            identity_stat["allowed"] += 1
        else:
            endpoint_stat["blocked"] += 1
            identity_stat["blocked"] += 1
            with self.lock:
                self.recent_blocks = [
                    {
                        "endpoint": endpoint,
                        "identity_type": identity["identity_type"],
                        "subject": identity["subject"],
                        "rule_pattern": rule.get("pattern") or "default",
                        "timestamp": now,
                        "retry_after": bucket_result["retry_after"],
                    },
                    *self.recent_blocks,
                ][:40]
        return {
            **bucket_result,
            "limit": int(rule.get("requests_per_minute") or self.requests_per_minute),
            "burst_size": int(rule.get("burst_size") or self.burst_size),
            "endpoint": endpoint,
            "identity_type": identity["identity_type"],
            "rule_pattern": rule.get("pattern") or "default",
            "subject": identity["subject"],
        }

    def status(self) -> Dict[str, Any]:
        with self.lock:
            endpoint_rows = [
                {
                    "endpoint": endpoint,
                    "allowed": stats["allowed"],
                    "blocked": stats["blocked"],
                    "last_seen": stats["last_seen"],
                    "rule_pattern": stats["rule_pattern"],
                }
                for endpoint, stats in self.endpoint_stats.items()
            ]
            identity_rows = [
                {
                    "subject": subject,
                    "allowed": stats["allowed"],
                    "blocked": stats["blocked"],
                    "last_seen": stats["last_seen"],
                }
                for subject, stats in self.identity_stats.items()
            ]
            endpoint_rows.sort(key=lambda item: (item["blocked"], item["allowed"]), reverse=True)
            identity_rows.sort(key=lambda item: (item["blocked"], item["allowed"]), reverse=True)
            rules = list(self.endpoint_rules)
            recent_blocks = list(self.recent_blocks)
            tracked_buckets = len(self.buckets)
        return {
            "default_rule": {
                "requests_per_minute": self.requests_per_minute,
                "burst_size": self.burst_size,
            },
            "rules": rules,
            "tracked_buckets": tracked_buckets,
            "top_endpoints": endpoint_rows[:20],
            "top_subjects": identity_rows[:20],
            "recent_blocks": recent_blocks,
        }

    async def __call__(self, request: Request):
        """
        中间件调用方法

        Args:
            request: FastAPI请求对象

        Raises:
            HTTPException: 如果超过速率限制
        """
        result = self.evaluate(request)

        if not result["allowed"]:
            logger.warning(f"速率限制触发: 客户端 {result['subject']} @ {result['endpoint']}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "速率限制",
                    "message": f"超过请求限制，请在 {result['retry_after']:.0f} 秒后重试",
                    "limit": result["limit"],
                    "window": "1分钟",
                    "endpoint": result["endpoint"],
                },
            )


# 装饰器形式的速率限制
def rate_limit(requests_per_minute: int = 60, burst_size: Optional[int] = None):
    """
    速率限制装饰器

    Args:
        requests_per_minute: 每分钟允许的请求数
        burst_size: 突发请求大小
    """
    limiter = RateLimiter(requests_per_minute, burst_size)

    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            await limiter(request)
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
