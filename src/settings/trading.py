"""
交易、策略与回测配置。
"""

import os

DEFAULT_INITIAL_CAPITAL = float(os.getenv("DEFAULT_INITIAL_CAPITAL", "10000"))
DEFAULT_COMMISSION = float(os.getenv("DEFAULT_COMMISSION", "0.001"))
DEFAULT_SLIPPAGE = float(os.getenv("DEFAULT_SLIPPAGE", "0.001"))

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

ML_CONFIG = {
    "random_forest": {
        "n_estimators": int(os.getenv("RF_N_ESTIMATORS", "100")),
        "max_depth": int(os.getenv("RF_MAX_DEPTH", "10")),
        "random_state": 42,
    },
    "prediction": {
        "n_estimators": int(os.getenv("PRED_N_ESTIMATORS", "100")),
        "random_state": 42,
    },
}

BACKTEST_DEFAULTS = {
    "position_size": float(os.getenv("DEFAULT_POSITION_SIZE", "1.0")),
    "max_positions": int(os.getenv("MAX_POSITIONS", "1")),
    "trading_days_per_year": int(os.getenv("TRADING_DAYS_PER_YEAR", "252")),
    "risk_free_rate": float(os.getenv("RISK_FREE_RATE", "0.02")),
}
