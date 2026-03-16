"""
自定义异常类
"""


class TradingSystemError(Exception):
    """交易系统基础异常"""

    pass


class DataError(TradingSystemError):
    """数据相关异常"""

    pass


class StrategyError(TradingSystemError):
    """策略相关异常"""

    pass


class BacktestError(TradingSystemError):
    """回测相关异常"""

    pass


class ValidationError(TradingSystemError):
    """验证相关异常"""

    pass


class ConfigError(TradingSystemError):
    """配置相关异常"""

    pass


class NetworkError(TradingSystemError):
    """网络相关异常"""

    pass
