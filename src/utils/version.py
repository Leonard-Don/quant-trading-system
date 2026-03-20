"""
应用版本管理。
"""

from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = PROJECT_ROOT / "VERSION"
DEFAULT_VERSION = "0.0.0"


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """从根目录 VERSION 文件读取统一版本号。"""
    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return DEFAULT_VERSION

    return version or DEFAULT_VERSION


APP_VERSION = get_app_version()
