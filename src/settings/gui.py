"""
界面与本地桌面配置。
"""

import os

DEFAULT_WINDOW_WIDTH = int(os.getenv("DEFAULT_WINDOW_WIDTH", "1200"))
DEFAULT_WINDOW_HEIGHT = int(os.getenv("DEFAULT_WINDOW_HEIGHT", "800"))
COMPACT_MODE = os.getenv("COMPACT_MODE", "True").lower() == "true"
