"""
配置兼容层。

新的分层配置位于 ``src/settings/``，本模块保留原有导入路径，
避免一次性改动全仓库引用。
"""

from typing import Dict, Any

from src.settings import (
    API_HOST,
    API_PORT,
    API_RELOAD,
    API_TIMEOUT,
    APP_VERSION,
    BACKEND_WAIT_TIMEOUT,
    BACKTEST_DEFAULTS,
    CACHE_TTL,
    COMPACT_MODE,
    CORS_ORIGINS,
    CPU_WARNING_THRESHOLD,
    DATA_CACHE_SIZE,
    DEFAULT_COMMISSION,
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SLIPPAGE,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    DISK_WARNING_THRESHOLD,
    FRONTEND_URL,
    HEALTH_CHECK_TIMEOUT,
    LOG_FORMAT,
    LOG_LEVEL,
    MAX_WORKERS,
    MEMORY_WARNING_THRESHOLD,
    ML_CONFIG,
    PROJECT_ROOT,
    STRATEGY_DEFAULTS,
)


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
    """获取所有配置。

    返回值同时保留原有扁平键，方便旧代码继续工作；
    新代码可优先读取分组后的 ``sections`` 视图。
    """
    sections = {
        "app": {
            "project_root": PROJECT_ROOT,
            "app_version": APP_VERSION,
            "log_level": LOG_LEVEL,
        },
        "data": {
            "data_cache_size": DATA_CACHE_SIZE,
            "default_lookback_days": DEFAULT_LOOKBACK_DAYS,
        },
        "trading": {
            "default_initial_capital": DEFAULT_INITIAL_CAPITAL,
            "default_commission": DEFAULT_COMMISSION,
            "default_slippage": DEFAULT_SLIPPAGE,
            "strategy_defaults": STRATEGY_DEFAULTS,
            "backtest_defaults": BACKTEST_DEFAULTS,
            "ml_config": ML_CONFIG,
        },
        "frontend": {
            "frontend_url": FRONTEND_URL,
            "cors_origins": CORS_ORIGINS,
        },
        "api": {
            "api_host": API_HOST,
            "api_port": API_PORT,
            "api_reload": API_RELOAD,
            "api_timeout": API_TIMEOUT,
            "health_check_timeout": HEALTH_CHECK_TIMEOUT,
            "backend_wait_timeout": BACKEND_WAIT_TIMEOUT,
        },
        "monitoring": {
            "max_workers": MAX_WORKERS,
            "cache_ttl": CACHE_TTL,
            "cpu_warning_threshold": CPU_WARNING_THRESHOLD,
            "memory_warning_threshold": MEMORY_WARNING_THRESHOLD,
            "disk_warning_threshold": DISK_WARNING_THRESHOLD,
        },
        "gui": {
            "default_window_width": DEFAULT_WINDOW_WIDTH,
            "default_window_height": DEFAULT_WINDOW_HEIGHT,
            "compact_mode": COMPACT_MODE,
        },
    }

    return {
        "sections": sections,
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
        "strategy_defaults": STRATEGY_DEFAULTS,
        "backtest_defaults": BACKTEST_DEFAULTS,
        "ml_config": ML_CONFIG,
    }
