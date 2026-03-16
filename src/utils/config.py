"""
配置管理模块
"""

import os
from typing import Dict, Any
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 数据配置
DATA_CACHE_SIZE = int(os.getenv("DATA_CACHE_SIZE", "100"))
DEFAULT_LOOKBACK_DAYS = int(os.getenv("DEFAULT_LOOKBACK_DAYS", "365"))

# 交易配置
DEFAULT_INITIAL_CAPITAL = float(os.getenv("DEFAULT_INITIAL_CAPITAL", "10000"))
DEFAULT_COMMISSION = float(os.getenv("DEFAULT_COMMISSION", "0.001"))
DEFAULT_SLIPPAGE = float(os.getenv("DEFAULT_SLIPPAGE", "0.001"))

# 策略默认参数
STRATEGY_DEFAULTS = {
    "moving_average": {
        "fast_period": int(os.getenv("MA_FAST_PERIOD", "20")),
        "slow_period": int(os.getenv("MA_SLOW_PERIOD", "50")),
    },
    "rsi": {
        "period": int(os.getenv("RSI_PERIOD", "14")),
        "oversold": int(os.getenv("RSI_OVERSOLD", "30")),
        "overbought": int(os.getenv("RSI_OVERBOUGHT", "70")),
    },
    "bollinger_bands": {
        "period": int(os.getenv("BB_PERIOD", "20")),
        "num_std": float(os.getenv("BB_STD", "2.0")),
    },
    "macd": {
        "fast_period": int(os.getenv("MACD_FAST", "12")),
        "slow_period": int(os.getenv("MACD_SLOW", "26")),
        "signal_period": int(os.getenv("MACD_SIGNAL", "9")),
    },
    "momentum": {
        "fast_window": int(os.getenv("MOMENTUM_FAST", "10")),
        "slow_window": int(os.getenv("MOMENTUM_SLOW", "30")),
    },
}

# 机器学习配置
ML_CONFIG = {
    "random_forest": {
        "n_estimators": int(os.getenv("RF_N_ESTIMATORS", "100")),
        "max_depth": int(os.getenv("RF_MAX_DEPTH", "10")),
        "random_state": 42
    },
    "prediction": {
        "n_estimators": int(os.getenv("PRED_N_ESTIMATORS", "100")),
        "random_state": 42
    }
}

# 回测配置
BACKTEST_DEFAULTS = {
    "position_size": float(os.getenv("DEFAULT_POSITION_SIZE", "1.0")),
    "max_positions": int(os.getenv("MAX_POSITIONS", "1")),
    "trading_days_per_year": int(os.getenv("TRADING_DAYS_PER_YEAR", "252")),
    "risk_free_rate": float(os.getenv("RISK_FREE_RATE", "0.02")),
}

# API配置
# 默认绑定到localhost以提高安全性，生产环境可通过环境变量设置为0.0.0.0
API_HOST = os.getenv("API_HOST", "127.0.0.1")  # 默认仅本地访问
API_PORT = int(os.getenv("API_PORT", "8000"))
API_RELOAD = os.getenv("API_RELOAD", "True").lower() == "true"

# 应用版本
APP_VERSION = os.getenv("APP_VERSION", "3.2.0")

# 前端配置
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
CORS_ORIGINS = [FRONTEND_URL, "http://127.0.0.1:3000", "http://localhost:3000"]

# 性能配置
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 缓存过期时间（秒）

# 网络配置
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))  # API超时时间（秒）
HEALTH_CHECK_TIMEOUT = int(os.getenv("HEALTH_CHECK_TIMEOUT", "5"))  # 健康检查超时（秒）
BACKEND_WAIT_TIMEOUT = int(os.getenv("BACKEND_WAIT_TIMEOUT", "30"))  # 后端启动等待时间（秒）

# 系统监控配置
CPU_WARNING_THRESHOLD = float(os.getenv("CPU_WARNING_THRESHOLD", "80"))  # CPU使用率警告阈值
MEMORY_WARNING_THRESHOLD = float(
    os.getenv("MEMORY_WARNING_THRESHOLD", "85")
)  # 内存使用率警告阈值
DISK_WARNING_THRESHOLD = float(os.getenv("DISK_WARNING_THRESHOLD", "90"))  # 磁盘使用率警告阈值

# GUI配置
DEFAULT_WINDOW_WIDTH = int(os.getenv("DEFAULT_WINDOW_WIDTH", "1200"))
DEFAULT_WINDOW_HEIGHT = int(os.getenv("DEFAULT_WINDOW_HEIGHT", "800"))
COMPACT_MODE = os.getenv("COMPACT_MODE", "True").lower() == "true"  # 紧凑模式（适合Mac）


def setup_logging(level: str = LOG_LEVEL, enable_rotation: bool = True) -> None:
    """设置统一的日志配置

    Args:
        level: 日志级别
        enable_rotation: 是否启用日志轮转
    """
    import logging.handlers

    # 确保日志目录存在
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    # 清除现有的处理器
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 创建格式化器
    formatter = logging.Formatter(LOG_FORMAT)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # 文件处理器
    if enable_rotation:
        # 使用轮转文件处理器
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "system.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
    else:
        file_handler = logging.FileHandler(
            log_dir / "system.log", mode="a", encoding="utf-8"
        )

    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, level.upper()))

    # 配置根日志器
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # 设置第三方库的日志级别
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


def get_config() -> Dict[str, Any]:
    """获取所有配置"""
    return {
        "project_root": PROJECT_ROOT,
        "log_level": LOG_LEVEL,
        "data_cache_size": DATA_CACHE_SIZE,
        "default_lookback_days": DEFAULT_LOOKBACK_DAYS,
        "default_initial_capital": DEFAULT_INITIAL_CAPITAL,
        "default_commission": DEFAULT_COMMISSION,
        "default_slippage": DEFAULT_SLIPPAGE,
        "api_host": API_HOST,
        "api_port": API_PORT,
        "api_reload": API_RELOAD,
        "frontend_url": FRONTEND_URL,
        "cors_origins": CORS_ORIGINS,
        "max_workers": MAX_WORKERS,
        "cache_ttl": CACHE_TTL,
        "api_timeout": API_TIMEOUT,
        "health_check_timeout": HEALTH_CHECK_TIMEOUT,
        "backend_wait_timeout": BACKEND_WAIT_TIMEOUT,
        "cpu_warning_threshold": CPU_WARNING_THRESHOLD,
        "memory_warning_threshold": MEMORY_WARNING_THRESHOLD,
        "disk_warning_threshold": DISK_WARNING_THRESHOLD,
        "app_version": APP_VERSION,
        "default_window_width": DEFAULT_WINDOW_WIDTH,
        "default_window_height": DEFAULT_WINDOW_HEIGHT,
        "compact_mode": COMPACT_MODE,
    }
