"""
性能与监控配置。
"""

import os

MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))

CPU_WARNING_THRESHOLD = float(os.getenv("CPU_WARNING_THRESHOLD", "80"))
MEMORY_WARNING_THRESHOLD = float(os.getenv("MEMORY_WARNING_THRESHOLD", "85"))
DISK_WARNING_THRESHOLD = float(os.getenv("DISK_WARNING_THRESHOLD", "90"))
