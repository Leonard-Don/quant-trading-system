"""
基础配置与版本来源。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from src.utils.version import APP_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 自动加载项目根目录下的 .env，仍允许外部环境变量覆盖。
load_dotenv(PROJECT_ROOT / ".env")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
