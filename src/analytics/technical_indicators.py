"""Technical indicator computations: RSI, MACD, Bollinger Bands.

Pure pandas math, no FastAPI / request coupling. Lifted from the analysis
endpoint where these started life inline.
"""
from __future__ import annotations

import pandas as pd


def calculate_rsi(data: pd.DataFrame, periods: int = 14) -> dict:
    """Relative Strength Index snapshot for the latest bar."""
    close = data["close"]
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

    if current_rsi > 70:
        status = "overbought"
        signal = "超买，可能面临回调"
    elif current_rsi < 30:
        status = "oversold"
        signal = "超卖，可能出现反弹"
    else:
        status = "neutral"
        signal = "中性区间"

    return {
        "value": round(current_rsi, 2),
        "status": status,
        "signal": signal,
    }


def calculate_macd(
    data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> dict:
    """MACD snapshot: macd line, signal line, histogram, status, trend."""
    close = data["close"]
    exp1 = close.ewm(span=fast, adjust=False).mean()
    exp2 = close.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    current_macd = float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else 0
    current_signal = (
        float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else 0
    )
    current_hist = float(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else 0
    prev_hist = (
        float(histogram.iloc[-2])
        if len(histogram) > 1 and not pd.isna(histogram.iloc[-2])
        else 0
    )

    if current_macd > current_signal and current_hist > 0:
        status = "bullish"
        trend = "加速上涨" if current_hist > prev_hist else "上涨减速"
    elif current_macd < current_signal and current_hist < 0:
        status = "bearish"
        trend = "加速下跌" if current_hist < prev_hist else "下跌减速"
    else:
        status = "neutral"
        trend = "横盘整理"

    return {
        "value": round(current_macd, 4),
        "signal_line": round(current_signal, 4),
        "histogram": round(current_hist, 4),
        "status": status,
        "trend": trend,
    }


def calculate_bollinger(
    data: pd.DataFrame, periods: int = 20, std_dev: float = 2.0
) -> dict:
    """Bollinger Bands snapshot with band position classification."""
    close = data["close"]
    middle = close.rolling(window=periods).mean()
    std = close.rolling(window=periods).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)

    current_close = float(close.iloc[-1])
    current_upper = (
        float(upper.iloc[-1]) if not pd.isna(upper.iloc[-1]) else current_close * 1.05
    )
    current_middle = (
        float(middle.iloc[-1]) if not pd.isna(middle.iloc[-1]) else current_close
    )
    current_lower = (
        float(lower.iloc[-1]) if not pd.isna(lower.iloc[-1]) else current_close * 0.95
    )

    bandwidth = (
        ((current_upper - current_lower) / current_middle * 100)
        if current_middle != 0
        else 0
    )

    if current_close >= current_upper:
        position = "above_upper"
        signal = "价格突破上轨，可能超买"
    elif current_close <= current_lower:
        position = "below_lower"
        signal = "价格突破下轨，可能超卖"
    elif current_close > current_middle:
        position = "upper_half"
        signal = "价格在中轨上方，偏强"
    else:
        position = "lower_half"
        signal = "价格在中轨下方，偏弱"

    return {
        "upper": round(current_upper, 2),
        "middle": round(current_middle, 2),
        "lower": round(current_lower, 2),
        "current_price": round(current_close, 2),
        "position": position,
        "bandwidth": round(bandwidth, 2),
        "signal": signal,
    }


__all__ = ["calculate_rsi", "calculate_macd", "calculate_bollinger"]
