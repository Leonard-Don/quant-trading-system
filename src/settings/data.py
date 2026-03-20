"""
数据域配置。
"""

import os

DATA_CACHE_SIZE = int(os.getenv("DATA_CACHE_SIZE", "100"))
DEFAULT_LOOKBACK_DAYS = int(os.getenv("DEFAULT_LOOKBACK_DAYS", "365"))
