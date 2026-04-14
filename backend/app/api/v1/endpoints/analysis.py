from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from datetime import datetime
import json
import logging
from backend.app.schemas.analysis import TrendAnalysisRequest, TrendAnalysisResponse
import numpy as np
import pandas as pd
from src.analytics.trend_analyzer import TrendAnalyzer
from src.analytics.volume_price_analyzer import VolumePriceAnalyzer
from src.analytics.sentiment_analyzer import SentimentAnalyzer
from src.analytics.comprehensive_scorer import ComprehensiveScorer
from src.analytics.pattern_recognizer import PatternRecognizer
from src.analytics.fundamental_analyzer import FundamentalAnalyzer
from src.data.data_manager import DataManager
from src.utils.cache import cache_manager

router = APIRouter()
logger = logging.getLogger(__name__)
data_manager = DataManager()
trend_analyzer = TrendAnalyzer()
volume_analyzer = VolumePriceAnalyzer()
sentiment_analyzer = SentimentAnalyzer()
comprehensive_scorer = ComprehensiveScorer()
pattern_recognizer = PatternRecognizer()
fundamental_analyzer = FundamentalAnalyzer()

ANALYSIS_CACHE_TTLS = {
    "overview": 180,
    "klines": 180,
    "prediction_compare": 300,
}


def _analysis_cache_key(name: str, request: TrendAnalysisRequest, **extra) -> str:
    payload = {
        "name": name,
        "symbol": request.symbol,
        "interval": request.interval,
        "start_date": request.start_date,
        "end_date": request.end_date,
        **extra,
    }
    return f"analysis::{name}::{json.dumps(payload, sort_keys=True, default=str)}"


def _get_cached_analysis(name: str, request: TrendAnalysisRequest, **extra):
    return cache_manager.get(_analysis_cache_key(name, request, **extra))


def _set_cached_analysis(name: str, request: TrendAnalysisRequest, value, **extra):
    cache_manager.set(
        _analysis_cache_key(name, request, **extra),
        value,
        ttl=ANALYSIS_CACHE_TTLS[name],
    )


def _build_klines(data: pd.DataFrame, limit: int = 150):
    recent_data = data.tail(limit).copy()
    klines = []
    for index, row in recent_data.iterrows():
        try:
            close_val = row["close"]
            if pd.isna(close_val) or np.isinf(close_val):
                continue
            klines.append({
                "date": index.strftime("%Y-%m-%d"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"])
            })
        except Exception as e:
            logger.error(f"Error processing row {index}: {e}")
            continue
    return klines


def _build_overview_fallback_response(request: TrendAnalysisRequest, reason: str = ""):
    note = "总览分析暂时不可用，已回退为中性信号。"
    if reason:
        note = f"{note} {reason}"

    return {
        "symbol": request.symbol,
        "timestamp": datetime.now().isoformat(),
        "overall_score": 50,
        "recommendation": "暂时观望",
        "confidence": "LOW",
        "scores": {
            "trend": 50,
            "volume": 50,
            "sentiment": 50,
            "technical": 50,
        },
        "key_signals": [],
        "risk_warnings": [note],
        "score_explanation": [],
        "recommendation_reasons": ["等待更多稳定数据后再评估。"],
        "indicators": {
            "rsi": {"value": 50, "status": "neutral"},
            "macd": {"value": 0},
            "bollinger": {
                "bandwidth": 0,
                "position": "neutral",
                "signal": "波动率 neutral",
            },
            "signal_strength": {
                "signal": "neutral",
                "strength": 0,
            },
            "overall": {
                "description": "neutral",
                "signal": "neutral",
            },
        },
    }

@router.post("/analyze", response_model=TrendAnalysisResponse, summary="分析股票趋势")
async def analyze_trend(request: TrendAnalysisRequest):
    """
    分析股票趋势，返回趋势方向、支撑阻力位和技术评分
    """
    try:
        # 解析日期
        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        # 获取数据


        data = await run_in_threadpool(
            data_manager.get_historical_data,
            request.symbol,
            start_date,
            end_date,
            request.interval,
        )

        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        # 执行分析
        analysis_result = trend_analyzer.analyze_trend(data)

        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            **analysis_result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing trend: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comprehensive", summary="综合分析")
async def comprehensive_analysis(request: TrendAnalysisRequest):
    """
    综合分析股票，整合趋势、量价、情绪等多维度分析
    返回综合评分和投资建议
    """
    try:
        # 解析日期
        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        # 获取数据
        data = await run_in_threadpool(
            data_manager.get_historical_data,
            request.symbol,
            start_date,
            end_date,
            request.interval,
        )

        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        # 执行综合分析
        result = comprehensive_scorer.comprehensive_analysis(
            data,
            request.symbol,
            include_pattern=True
        )
        
        # 准备近期K线数据 (用于前端图表显示)
        result["klines"] = _build_klines(data, limit=150)

        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in comprehensive analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/overview", summary="分析总览")
async def analysis_overview(request: TrendAnalysisRequest):
    """
    轻量总览分析，返回评分与关键信号
    """
    try:
        cached = _get_cached_analysis("overview", request)
        if cached is not None:
            return cached

        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        data = data_manager.get_historical_data(
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date,
            interval=request.interval,
        )

        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        result = await run_in_threadpool(
            comprehensive_scorer.comprehensive_analysis,
            data,
            request.symbol,
            False,
        )

        # 构造前端技术指标快照所需的格式
        trend_analysis = result.get("trend_analysis", {})
        raw_indicators = trend_analysis.get("indicators", {})
        volatility = trend_analysis.get("volatility", {})
        signal_strength = trend_analysis.get("signal_strength", {})
        
        # 转换 RSI
        rsi_val = raw_indicators.get("rsi", 50)
        rsi_obj = {
            "value": rsi_val,
            "status": "overbought" if rsi_val > 70 else "oversold" if rsi_val < 30 else "neutral"
        }
        
        # 转换 MACD
        macd_val = raw_indicators.get("macd", 0)
        macd_obj = {"value": macd_val}
        
        # 转换 Bollinger (从波动率数据获取宽度, 位置暂无只能估算或缺省)
        bollinger_obj = {
            "bandwidth": volatility.get("bollinger_width", 0),
            "position": "neutral", # TrendAnalyzer 暂未返回详细位置
            "signal": "波动率 " + volatility.get("level", "low")
        }

        formatted_indicators = {
            "rsi": rsi_obj,
            "macd": macd_obj,
            "bollinger": bollinger_obj,
            "signal_strength": signal_strength,
            "overall": { # 兼容旧代码 (如果前端回滚)
                "description": signal_strength.get("signal", "neutral"),
                "signal": signal_strength.get("signal", "neutral")
            }
        }

        response = {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            "overall_score": result.get("overall_score"),
            "recommendation": result.get("recommendation"),
            "confidence": result.get("confidence"),
            "scores": result.get("scores"),
            "key_signals": result.get("key_signals"),
            "risk_warnings": result.get("risk_warnings"),
            "score_explanation": result.get("score_explanation"),
            "recommendation_reasons": result.get("recommendation_reasons"),
            "indicators": formatted_indicators
        }
        _set_cached_analysis("overview", request, response)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in overview analysis: {e}", exc_info=True)
        fallback_response = _build_overview_fallback_response(request, reason=str(e))
        _set_cached_analysis("overview", request, fallback_response)
        return fallback_response


@router.post("/fundamental", summary="基本面分析")
async def analyze_fundamental(request: TrendAnalysisRequest):
    """
    基本面分析
    """
    try:
        result = fundamental_analyzer.analyze(request.symbol)
        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            **result
        }
    except Exception as e:
        logger.error(f"Error in fundamental analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/klines", summary="K线数据")
async def get_klines(request: TrendAnalysisRequest, limit: int = 150):
    """
    获取K线数据（默认150条）
    """
    try:
        cached = _get_cached_analysis("klines", request, limit=limit)
        if cached is not None:
            return cached

        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        data = await run_in_threadpool(
            data_manager.get_historical_data,
            request.symbol,
            start_date,
            end_date,
            request.interval,
        )

        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        response = {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            "klines": _build_klines(data, limit=limit)
        }
        _set_cached_analysis("klines", request, response, limit=limit)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in klines: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/volume-price", summary="量价分析")
async def analyze_volume_price(request: TrendAnalysisRequest):
    """
    分析成交量与价格的关系
    """
    try:
        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        data = data_manager.get_historical_data(
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date,
            interval=request.interval,
        )

        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        result = volume_analyzer.analyze(data)

        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in volume-price analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sentiment", summary="市场情绪分析")
async def analyze_sentiment(request: TrendAnalysisRequest):
    """
    分析市场情绪和恐慌程度
    """
    try:
        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        data = data_manager.get_historical_data(
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date,
            interval=request.interval,
        )

        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        result = sentiment_analyzer.analyze(data, request.symbol)

        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in sentiment analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/patterns", summary="形态识别")
async def recognize_patterns(request: TrendAnalysisRequest):
    """
    识别K线形态和图表形态
    """
    try:
        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        data = data_manager.get_historical_data(
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date,
            interval=request.interval,
        )

        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        result = pattern_recognizer.recognize_patterns(data)

        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            **result
        }

    except Exception as e:
        logger.error(f"Error in pattern recognition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

from src.analytics.predictor import PricePredictor
price_predictor = PricePredictor()

@router.post("/prediction", summary="AI价格预测")
async def predict_prices(request: TrendAnalysisRequest):
    """
    使用AI模型预测未来价格
    """
    try:
        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        data = data_manager.get_historical_data(
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date,
            interval=request.interval,
        )

        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        # 默认预测未来5天，传递symbol确保每只股票使用独立模型
        result = price_predictor.predict_next_days(data, days=5, symbol=request.symbol)

        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in price prediction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel
from typing import List
import numpy as np

class CorrelationRequest(BaseModel):
    symbols: List[str]  # List of stock symbols to analyze
    period_days: int = 90  # Number of days to analyze

@router.post("/correlation", summary="多股票相关性分析")
async def analyze_correlation(request: CorrelationRequest):
    """
    分析多只股票之间的价格相关性
    返回相关性矩阵和统计信息
    """
    try:
        if len(request.symbols) < 2:
            raise HTTPException(status_code=400, detail="至少需要2只股票进行相关性分析")
        
        if len(request.symbols) > 10:
            raise HTTPException(status_code=400, detail="最多支持10只股票同时分析")
        
        # Fetch data for all symbols
        from datetime import timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=request.period_days)
        
        stock_data = {}
        valid_symbols = []
        
        for symbol in request.symbols:
            try:
                data = data_manager.get_historical_data(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    interval="1d"
                )
                if not data.empty and len(data) > 10:
                    # Normalize timezone to UTC-naive to ensure alignment between stocks (market hours) and crypto (24/7)
                    if data.index.tz is not None:
                        data.index = data.index.tz_localize(None)
                    data.index = data.index.normalize() # Ensure we match on date (midnight)
                    stock_data[symbol] = data['close']
                    valid_symbols.append(symbol)
            except Exception as e:
                logger.warning(f"Could not fetch data for {symbol}: {e}")
        
        if len(valid_symbols) < 2:
            raise HTTPException(status_code=400, detail="有效数据不足，无法计算相关性")
        
        # Align dates and calculate returns
        import pandas as pd
        # Use concat with inner join to align dates
        combined = pd.DataFrame(stock_data).dropna()
        
        if len(combined) < 10:
            raise HTTPException(status_code=400, detail="重叠交易日太少，无法计算相关性")
        
        # Calculate daily returns
        returns = combined.pct_change().dropna()
        
        # Calculate correlation matrix
        correlation_matrix = returns.corr()
        
        # Convert to list format for JSON response
        corr_data = []
        for i, sym1 in enumerate(valid_symbols):
            for j, sym2 in enumerate(valid_symbols):
                corr_data.append({
                    "symbol1": sym1,
                    "symbol2": sym2,
                    "correlation": round(correlation_matrix.loc[sym1, sym2], 4)
                })
        
        # Find top correlations (excluding self-correlation)
        pair_correlations = []
        for i, sym1 in enumerate(valid_symbols):
            for j, sym2 in enumerate(valid_symbols):
                if i < j:  # Only upper triangle
                    pair_correlations.append({
                        "pair": f"{sym1}-{sym2}",
                        "correlation": round(correlation_matrix.loc[sym1, sym2], 4)
                    })
        
        # Sort by absolute correlation
        pair_correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        
        # Calculate average correlation
        avg_correlation = np.mean([abs(p["correlation"]) for p in pair_correlations])
        
        return {
            "timestamp": datetime.now().isoformat(),
            "symbols": valid_symbols,
            "period_days": request.period_days,
            "data_points": len(returns),
            "correlation_matrix": corr_data,
            "top_correlations": pair_correlations[:5],
            "average_correlation": round(avg_correlation, 4),
            "interpretation": get_correlation_interpretation(avg_correlation)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in correlation analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def get_correlation_interpretation(avg_corr: float) -> dict:
    """Generate interpretation of correlation results"""
    if avg_corr > 0.8:
        level = "very_high"
        description = "这些股票高度相关，价格走势非常相似，分散化效果差"
    elif avg_corr > 0.6:
        level = "high"
        description = "这些股票相关性较高，建议增加低相关资产以分散风险"
    elif avg_corr > 0.4:
        level = "moderate"
        description = "这些股票呈中等相关，组合有一定分散化效果"
    elif avg_corr > 0.2:
        level = "low"
        description = "这些股票相关性较低，组合分散化效果较好"
    else:
        level = "very_low"
        description = "这些股票几乎不相关，是理想的分散化组合"
    
    return {"level": level, "description": description}


# ==================== 模型比较 API ====================

from src.analytics.model_comparator import model_comparator


@router.post("/prediction/compare", summary="多模型预测对比")
async def compare_model_predictions(request: TrendAnalysisRequest):
    """
    使用多个模型进行预测并对比结果
    同时返回 Random Forest 和 LSTM 的预测结果
    """
    try:
        cached = _get_cached_analysis("prediction_compare", request)
        if cached is not None:
            return cached

        # 获取历史数据
        data = await run_in_threadpool(
            data_manager.get_historical_data,
            request.symbol,
            None,
            None,
            request.interval,
        )
        
        if data.empty:
            raise HTTPException(
                status_code=404, 
                detail=f"No data found for symbol {request.symbol}"
            )
        
        # 比较预测
        result = await run_in_threadpool(
            model_comparator.compare_predictions,
            data,
            request.symbol,
            5,
        )
        
        response = {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            **result
        }
        _set_cached_analysis("prediction_compare", request, response)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing predictions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prediction/lstm", summary="LSTM 模型预测")
async def predict_with_lstm(request: TrendAnalysisRequest):
    """
    使用 LSTM 神经网络模型进行价格预测
    """
    try:
        # 获取历史数据
        data = data_manager.get_historical_data(
            symbol=request.symbol,
            interval=request.interval
        )
        
        if data.empty:
            raise HTTPException(
                status_code=404, 
                detail=f"No data found for symbol {request.symbol}"
            )
        
        # LSTM 预测
        from src.analytics.lstm_predictor import lstm_predictor
        result = lstm_predictor.predict(data, request.symbol, days=5)
        
        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            **result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in LSTM prediction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train/all", summary="训练所有模型")
async def train_all_models(request: TrendAnalysisRequest):
    """
    为指定股票训练所有可用的预测模型
    包括 Random Forest 和 LSTM
    """
    try:
        # 获取历史数据
        data = data_manager.get_historical_data(
            symbol=request.symbol,
            interval=request.interval
        )
        
        if data.empty:
            raise HTTPException(
                status_code=404, 
                detail=f"No data found for symbol {request.symbol}"
            )
        
        if len(data) < 100:
            raise HTTPException(
                status_code=400,
                detail="需要至少100条历史数据来训练模型"
            )
        
        # 训练所有模型
        result = model_comparator.train_all_models(data, request.symbol)
        
        return {
            "timestamp": datetime.now().isoformat(),
            **result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error training models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 市场分析增强 API ====================

def _calculate_rsi(data: pd.DataFrame, periods: int = 14) -> dict:
    """计算 RSI 指标"""
    close = data['close']
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
        "signal": signal
    }


def _calculate_macd(data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """计算 MACD 指标"""
    close = data['close']
    exp1 = close.ewm(span=fast, adjust=False).mean()
    exp2 = close.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    current_macd = float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else 0
    current_signal = float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else 0
    current_hist = float(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else 0
    prev_hist = float(histogram.iloc[-2]) if len(histogram) > 1 and not pd.isna(histogram.iloc[-2]) else 0
    
    if current_macd > current_signal and current_hist > 0:
        status = "bullish"
        if current_hist > prev_hist:
            trend = "加速上涨"
        else:
            trend = "上涨减速"
    elif current_macd < current_signal and current_hist < 0:
        status = "bearish"
        if current_hist < prev_hist:
            trend = "加速下跌"
        else:
            trend = "下跌减速"
    else:
        status = "neutral"
        trend = "横盘整理"
    
    return {
        "value": round(current_macd, 4),
        "signal_line": round(current_signal, 4),
        "histogram": round(current_hist, 4),
        "status": status,
        "trend": trend
    }


def _calculate_bollinger(data: pd.DataFrame, periods: int = 20, std_dev: float = 2.0) -> dict:
    """计算布林带指标"""
    close = data['close']
    middle = close.rolling(window=periods).mean()
    std = close.rolling(window=periods).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    current_close = float(close.iloc[-1])
    current_upper = float(upper.iloc[-1]) if not pd.isna(upper.iloc[-1]) else current_close * 1.05
    current_middle = float(middle.iloc[-1]) if not pd.isna(middle.iloc[-1]) else current_close
    current_lower = float(lower.iloc[-1]) if not pd.isna(lower.iloc[-1]) else current_close * 0.95
    
    bandwidth = ((current_upper - current_lower) / current_middle * 100) if current_middle != 0 else 0
    
    # 判断位置
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
        "signal": signal
    }


@router.post("/technical-indicators", summary="技术指标快照")
async def get_technical_indicators(request: TrendAnalysisRequest):
    """
    获取常用技术指标快照（RSI、MACD、布林带）
    """
    try:
        data = data_manager.get_historical_data(
            symbol=request.symbol,
            interval=request.interval
        )
        
        if data.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol {request.symbol}"
            )
        
        rsi = _calculate_rsi(data)
        macd = _calculate_macd(data)
        bollinger = _calculate_bollinger(data)
        
        # 综合技术信号
        bullish_count = sum([
            rsi["status"] == "oversold",
            macd["status"] == "bullish",
            bollinger["position"] in ["below_lower", "lower_half"]
        ])
        bearish_count = sum([
            rsi["status"] == "overbought",
            macd["status"] == "bearish",
            bollinger["position"] in ["above_upper"]
        ])
        
        if bullish_count >= 2:
            overall_signal = "bullish"
            overall_description = "多数指标看涨"
        elif bearish_count >= 2:
            overall_signal = "bearish"
            overall_description = "多数指标看跌"
        else:
            overall_signal = "neutral"
            overall_description = "技术面分歧"
        
        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            "rsi": rsi,
            "macd": macd,
            "bollinger": bollinger,
            "overall": {
                "signal": overall_signal,
                "description": overall_description,
                "bullish_indicators": bullish_count,
                "bearish_indicators": bearish_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting technical indicators: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sentiment-history", summary="历史情绪趋势")
async def get_sentiment_history(request: TrendAnalysisRequest, days: int = 30):
    """
    获取过去N天的恐慌贪婪指数历史趋势
    """
    try:
        from datetime import timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 50)  # 额外获取数据用于计算
        
        data = data_manager.get_historical_data(
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date,
            interval="1d"
        )
        
        if data.empty or len(data) < 30:
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient data for symbol {request.symbol}"
            )
        
        # 计算每日恐慌贪婪指数
        history = []
        close = data['close']
        volume = data['volume']
        
        for i in range(20, len(data)):
            
            window_data = data.iloc[max(0, i-50):i+1].copy()
            if len(window_data) < 20:
                continue
            
            # 改进的恐慌贪婪指数计算
            score = 50.0
            
            # 1. 动量（20日）- 权重 30%
            momentum = (close.iloc[i] - close.iloc[i-20]) / close.iloc[i-20] * 100
            if momentum > 15:
                score += 20
            elif momentum > 10:
                score += 15
            elif momentum > 5:
                score += 10
            elif momentum > 0:
                score += 5
            elif momentum < -15:
                score -= 20
            elif momentum < -10:
                score -= 15
            elif momentum < -5:
                score -= 10
            elif momentum < 0:
                score -= 5
            
            # 2. 成交量变化（相对20日均量）- 权重 15%
            avg_volume = volume.iloc[max(0, i-20):i].mean()
            if avg_volume > 0:
                volume_ratio = volume.iloc[i] / avg_volume
                if volume_ratio > 1.5:
                    score += 10 if momentum > 0 else -10  # 放量涨为贪婪，放量跌为恐惧
                elif volume_ratio > 1.2:
                    score += 5 if momentum > 0 else -5
                elif volume_ratio < 0.7:
                    score -= 3  # 缩量通常表示观望
            
            # 3. 价格相对位置（距离52周高低点）- 权重 20%
            high_52w = close.iloc[max(0, i-252):i+1].max()
            low_52w = close.iloc[max(0, i-252):i+1].min()
            if high_52w > low_52w:
                price_position = (close.iloc[i] - low_52w) / (high_52w - low_52w)
                if price_position > 0.9:
                    score += 15  # 接近历史高点
                elif price_position > 0.7:
                    score += 8
                elif price_position < 0.2:
                    score -= 15  # 接近历史低点
                elif price_position < 0.4:
                    score -= 8
            
            # 4. 短期动量（5日）- 权重 15%
            short_momentum = (close.iloc[i] - close.iloc[i-5]) / close.iloc[i-5] * 100
            if short_momentum > 5:
                score += 10
            elif short_momentum > 2:
                score += 5
            elif short_momentum < -5:
                score -= 10
            elif short_momentum < -2:
                score -= 5
            
            # 5. 波动率 - 权重 20%
            returns = close.iloc[max(0, i-20):i+1].pct_change()
            volatility = returns.std() * np.sqrt(252) * 100
            if volatility < 15:
                score += 10  # 低波动表示稳定/乐观
            elif volatility < 25:
                score += 5
            elif volatility > 50:
                score -= 15  # 高波动表示恐惧
            elif volatility > 35:
                score -= 8
            
            score = max(0, min(100, score))
            
            date_str = data.index[i].strftime("%Y-%m-%d")
            sentiment = "extreme_greed" if score >= 75 else "greed" if score >= 55 else "neutral" if score >= 45 else "fear" if score >= 25 else "extreme_fear"
            
            history.append({
                "date": date_str,
                "fear_greed_index": round(score, 1),
                "sentiment": sentiment
            })
        
        # 计算趋势
        if len(history) >= 7:
            recent_avg = np.mean([h["fear_greed_index"] for h in history[-7:]])
            older_avg = np.mean([h["fear_greed_index"] for h in history[-14:-7]]) if len(history) >= 14 else recent_avg
            
            if recent_avg > older_avg + 5:
                trend = "increasing"
                trend_description = "情绪转向乐观"
            elif recent_avg < older_avg - 5:
                trend = "decreasing"
                trend_description = "情绪转向悲观"
            else:
                trend = "stable"
                trend_description = "情绪保持稳定"
        else:
            trend = "unknown"
            trend_description = "数据不足"
        
        avg_30d = np.mean([h["fear_greed_index"] for h in history]) if history else 50
        
        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            "history": history[-days:],  # 只返回请求的天数
            "trend": trend,
            "trend_description": trend_description,
            "avg_30d": round(avg_30d, 1),
            "current": history[-1] if history else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sentiment history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/industry-comparison", summary="行业对比分析")
async def get_industry_comparison(request: TrendAnalysisRequest):
    """
    获取同行业公司的关键指标对比
    """
    try:
        # 获取目标股票的基本面数据
        target_fundamental = fundamental_analyzer.analyze(request.symbol)
        
        # fundamental_analyzer.analyze() 直接返回 {metrics, valuation, ...}
        if not target_fundamental or not target_fundamental.get("metrics"):
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental data not available for {request.symbol}"
            )
        
        target_metrics = target_fundamental.get("metrics", {})
        industry = target_metrics.get("industry", "Unknown")
        sector = target_metrics.get("sector", "Unknown")
        
        # 定义同行业竞争对手（根据行业预定义）
        industry_peers = {
            "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC"],
            "Consumer Electronics": ["AAPL", "SONY", "SSNLF", "HPQ", "DELL"],
            "Internet Content & Information": ["GOOGL", "META", "NFLX", "SNAP", "PINS"],
            "Software—Infrastructure": ["MSFT", "ORCL", "CRM", "NOW", "ADBE"],
            "Semiconductors": ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "TSM"],
            "Auto Manufacturers": ["TSLA", "TM", "F", "GM", "RIVN", "LCID"],
            "Banks—Diversified": ["JPM", "BAC", "WFC", "C", "GS", "MS"],
            "Default": ["SPY", "QQQ", "DIA"]  # 默认使用指数对比
        }
        
        # 获取对应行业的竞争对手
        peer_symbols = industry_peers.get(industry, industry_peers.get(sector, industry_peers["Default"]))
        peer_symbols = [s for s in peer_symbols if s != request.symbol][:5]  # 排除自身，最多5个
        
        peers = []
        for peer_symbol in peer_symbols:
            try:
                peer_fundamental = fundamental_analyzer.analyze(peer_symbol)
                if peer_fundamental and peer_fundamental.get("metrics"):
                    metrics = peer_fundamental.get("metrics", {})
                    peers.append({
                        "symbol": peer_symbol,
                        "name": metrics.get("name", peer_symbol),
                        "pe_ratio": round(metrics.get("pe_ratio", 0) or 0, 2),
                        "revenue_growth": round((metrics.get("revenue_growth", 0) or 0) * 100, 2),
                        "profit_margin": round((metrics.get("profit_margin", 0) or 0) * 100, 2),
                        "market_cap": metrics.get("market_cap", 0),
                        "price_to_book": round(metrics.get("price_to_book", 0) or 0, 2)
                    })
            except Exception as e:
                logger.warning(f"Could not fetch data for peer {peer_symbol}: {e}")
        
        # 目标股票数据
        target = {
            "symbol": request.symbol,
            "name": target_metrics.get("name", request.symbol),
            "pe_ratio": round(target_metrics.get("pe_ratio", 0) or 0, 2),
            "revenue_growth": round((target_metrics.get("revenue_growth", 0) or 0) * 100, 2),
            "profit_margin": round((target_metrics.get("profit_margin", 0) or 0) * 100, 2),
            "market_cap": target_metrics.get("market_cap", 0),
            "price_to_book": round(target_metrics.get("price_to_book", 0) or 0, 2)
        }
        
        # 计算行业平均值
        all_companies = [target] + peers
        industry_avg = {
            "pe_ratio": round(np.mean([c["pe_ratio"] for c in all_companies if c["pe_ratio"] > 0]), 2),
            "revenue_growth": round(np.mean([c["revenue_growth"] for c in all_companies]), 2),
            "profit_margin": round(np.mean([c["profit_margin"] for c in all_companies]), 2)
        }
        
        # 计算排名
        sorted_by_pe = sorted([c for c in all_companies if c["pe_ratio"] > 0], key=lambda x: x["pe_ratio"])
        sorted_by_growth = sorted(all_companies, key=lambda x: x["revenue_growth"], reverse=True)
        
        target["pe_rank"] = next((i+1 for i, c in enumerate(sorted_by_pe) if c["symbol"] == request.symbol), 0)
        target["growth_rank"] = next((i+1 for i, c in enumerate(sorted_by_growth) if c["symbol"] == request.symbol), 0)
        
        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            "industry": industry,
            "sector": sector,
            "target": target,
            "peers": peers,
            "industry_avg": industry_avg,
            "total_companies": len(all_companies)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry comparison: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk-metrics", summary="风险评估增强")
async def get_risk_metrics(request: TrendAnalysisRequest):
    """
    获取 VaR、最大回撤、夏普比率等风险指标
    """
    try:
        data = data_manager.get_historical_data(
            symbol=request.symbol,
            interval=request.interval
        )
        
        if data.empty or len(data) < 50:
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient data for risk calculation: {request.symbol}"
            )
        
        close = data['close']
        returns = close.pct_change().dropna()
        
        # 1. VaR 计算 (历史模拟法)
        var_95 = np.percentile(returns, 5) * 100  # 95% VaR
        var_99 = np.percentile(returns, 1) * 100  # 99% VaR
        
        # 2. 最大回撤
        cumulative = (1 + returns).cumprod()
        rolling_max = cumulative.cummax()
        drawdown = (cumulative - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100
        
        # 找出最大回撤区间
        max_dd_end_idx = drawdown.idxmin()
        max_dd_start_idx = cumulative.loc[:max_dd_end_idx].idxmax()
        
        # 3. 年化收益率
        total_return = (close.iloc[-1] - close.iloc[0]) / close.iloc[0]
        years = len(data) / 252  # 假设252个交易日
        annual_return = ((1 + total_return) ** (1/years) - 1) * 100 if years > 0 else 0
        
        # 4. 年化波动率
        annual_volatility = returns.std() * np.sqrt(252) * 100
        
        # 5. 夏普比率 (假设无风险利率 4%)
        risk_free_rate = 0.04
        excess_return = annual_return / 100 - risk_free_rate
        sharpe_ratio = excess_return / (annual_volatility / 100) if annual_volatility != 0 else 0
        
        # 6. 索提诺比率 (仅考虑下行波动率)
        negative_returns = returns[returns < 0]
        downside_volatility = negative_returns.std() * np.sqrt(252) * 100 if len(negative_returns) > 0 else annual_volatility
        sortino_ratio = excess_return / (downside_volatility / 100) if downside_volatility != 0 else 0
        
        # 7. Beta (相对于SPY)
        try:
            spy_data = data_manager.get_historical_data(symbol="SPY", interval=request.interval)
            if not spy_data.empty and len(spy_data) > 50:
                spy_returns = spy_data['close'].pct_change().dropna()
                # 对齐日期
                common_index = returns.index.intersection(spy_returns.index)
                if len(common_index) > 30:
                    aligned_returns = returns.loc[common_index]
                    aligned_spy = spy_returns.loc[common_index]
                    covariance = np.cov(aligned_returns, aligned_spy)[0][1]
                    variance = np.var(aligned_spy)
                    beta = covariance / variance if variance != 0 else 1.0
                else:
                    beta = 1.0
            else:
                beta = 1.0
        except:
            beta = 1.0
        
        # 风险等级判断
        risk_score = 0
        if abs(var_95) > 5:
            risk_score += 2
        if abs(max_drawdown) > 30:
            risk_score += 2
        elif abs(max_drawdown) > 20:
            risk_score += 1
        if annual_volatility > 40:
            risk_score += 2
        elif annual_volatility > 25:
            risk_score += 1
        if sharpe_ratio < 0.5:
            risk_score += 1
        
        if risk_score >= 5:
            risk_level = "very_high"
            risk_description = "风险极高，谨慎投资"
        elif risk_score >= 3:
            risk_level = "high"
            risk_description = "风险较高，需注意仓位控制"
        elif risk_score >= 1:
            risk_level = "medium"
            risk_description = "风险适中"
        else:
            risk_level = "low"
            risk_description = "相对低风险"
        
        return {
            "symbol": request.symbol,
            "timestamp": datetime.now().isoformat(),
            "var_95": round(var_95, 2),
            "var_99": round(var_99, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_period": {
                "start": max_dd_start_idx.strftime("%Y-%m-%d") if hasattr(max_dd_start_idx, 'strftime') else str(max_dd_start_idx),
                "end": max_dd_end_idx.strftime("%Y-%m-%d") if hasattr(max_dd_end_idx, 'strftime') else str(max_dd_end_idx)
            },
            "annual_return": round(annual_return, 2),
            "annual_volatility": round(annual_volatility, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "beta": round(beta, 2),
            "risk_level": risk_level,
            "risk_description": risk_description,
            "data_points": len(returns)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating risk metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
