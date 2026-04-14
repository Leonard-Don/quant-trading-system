"""Shared rate-limit runtime for middleware and infrastructure controls."""

from __future__ import annotations

from src.middleware.rate_limiter import RateLimiter


rate_limiter = RateLimiter(requests_per_minute=100, burst_size=120)
rate_limiter.configure_endpoint_rules(
    [
        {"id": "backtest", "pattern": "/api/v1/backtest*", "requests_per_minute": 24, "burst_size": 36},
        {"id": "quant_lab", "pattern": "/api/v1/quant-lab*", "requests_per_minute": 40, "burst_size": 60},
        {"id": "realtime", "pattern": "/api/v1/realtime*", "requests_per_minute": 180, "burst_size": 240},
        {"id": "pricing", "pattern": "/api/v1/pricing*", "requests_per_minute": 45, "burst_size": 70},
        {"id": "industry", "pattern": "/api/v1/industry*", "requests_per_minute": 75, "burst_size": 100},
    ]
)
