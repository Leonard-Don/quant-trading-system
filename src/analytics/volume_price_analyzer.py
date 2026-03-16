"""
量价分析模块
分析成交量与价格的关系，判断市场行为和资金流向
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class VolumePriceAnalyzer:
    """
    量价分析器
    通过量价关系判断市场强弱和资金流向
    
    Args:
        config: 可选配置字典，支持以下参数：
            - volume_periods: 成交量分析周期配置
            - mfi_period: MFI（资金流量指标）计算周期
            - divergence_lookback: 背离检测回溯天数
            - volume_thresholds: 成交量异常阈值
    """

    # 默认配置
    DEFAULT_CONFIG = {
        "volume_periods": {
            "short": 5,      # 短期均量周期
            "medium": 20,    # 中期均量周期
            "long": 60       # 长期均量周期
        },
        "mfi_period": 14,    # MFI计算周期
        "divergence_lookback": 20,  # 背离检测回溯天数
        "volume_thresholds": {
            "explosive": 2.0,     # 爆量阈值（均量的倍数）
            "increasing": 1.5,    # 放量阈值
            "shrinking": 0.5,     # 缩量阈值
            "extremely_low": 0.3, # 地量阈值
            "extremely_high": 3.0 # 天量阈值
        },
        "correlation_thresholds": {
            "strong_positive": 0.5,
            "positive": 0.2,
            "strong_negative": -0.5,
            "negative": -0.2
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化量价分析器
        
        Args:
            config: 自定义配置，将与默认配置合并
        """
        self.config = self._merge_config(config or {})
        self.volume_periods = self.config["volume_periods"]
        self.mfi_period = self.config["mfi_period"]
        self.divergence_lookback = self.config["divergence_lookback"]
        self.volume_thresholds = self.config["volume_thresholds"]
        self.correlation_thresholds = self.config["correlation_thresholds"]
    
    def _merge_config(self, custom_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并自定义配置与默认配置
        """
        merged = {}
        for key, default_value in self.DEFAULT_CONFIG.items():
            if key in custom_config:
                if isinstance(default_value, dict):
                    merged[key] = {**default_value, **custom_config[key]}
                else:
                    merged[key] = custom_config[key]
            else:
                merged[key] = default_value.copy() if isinstance(default_value, dict) else default_value
        return merged

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        综合量价分析

        Args:
            df: 包含OHLCV数据的DataFrame

        Returns:
            量价分析结果
        """
        if df.empty or len(df) < 20:
            return {
                "volume_trend": {
                    "trend": "unknown",
                    "direction": "neutral",
                    "volume_ratio": 0,
                    "avg_volume_5d": 0,
                    "avg_volume_20d": 0,
                    "current_volume": 0
                },
                "price_volume_correlation": 0,
                "money_flow": {},
                "volume_patterns": {},
                "obv_analysis": {},
                "accumulation_distribution": {}
            }

        close = df["close"]
        volume = df["volume"]
        high = df["high"]
        low = df["low"]

        # 1. 量能趋势分析
        volume_trend = self._analyze_volume_trend(volume)

        # 2. 量价相关性
        price_volume_corr = self._calculate_price_volume_correlation(close, volume)

        # 3. 资金流向分析
        money_flow = self._analyze_money_flow(df)

        # 4. 成交量形态
        volume_patterns = self._identify_volume_patterns(df)

        # 5. OBV分析 (能量潮)
        obv_analysis = self._analyze_obv(close, volume)

        # 6. 累积/派发线
        ad_analysis = self._analyze_accumulation_distribution(df)

        # 7. 量价背离
        divergence = self._detect_divergence(df)

        # 8. 筹码分布 (VPVR - Volume Profile Visible Range)
        vpvr_analysis = self._calculate_vpvr(df)

        return {
            "volume_trend": volume_trend,
            "price_volume_correlation": price_volume_corr,
            "money_flow": money_flow,
            "volume_patterns": volume_patterns,
            "obv_analysis": obv_analysis,
            "accumulation_distribution": ad_analysis,
            "divergence": divergence,
            "vpvr_analysis": vpvr_analysis
        }

    def _analyze_volume_trend(self, volume: pd.Series) -> Dict[str, Any]:
        """
        分析成交量趋势
        """
        # 计算不同周期的平均成交量
        vol_5 = volume.rolling(window=5).mean().iloc[-1]
        vol_20 = volume.rolling(window=20).mean().iloc[-1]
        vol_60 = volume.rolling(window=60).mean().iloc[-1] if len(volume) >= 60 else vol_20

        current_vol = volume.iloc[-1]

        # 判断量能状态
        trend = "normal"
        if current_vol > vol_5 * 2:
            trend = "explosive"
        elif current_vol > vol_5 * 1.5:
            trend = "increasing"
        elif current_vol < vol_5 * 0.5:
            trend = "shrinking"

        # 量能趋势方向
        direction = "neutral"
        if vol_5 > vol_20 * 1.2:
            direction = "expanding"
        elif vol_5 < vol_20 * 0.8:
            direction = "contracting"

        return {
            "trend": trend,
            "direction": direction,
            "current_volume": float(current_vol),
            "avg_volume_5d": float(vol_5) if not pd.isna(vol_5) else 0,
            "avg_volume_20d": float(vol_20) if not pd.isna(vol_20) else 0,
            "volume_ratio": round(float(current_vol / vol_20) if not pd.isna(vol_20) and vol_20 > 0 else 1, 2)
        }

    def _calculate_price_volume_correlation(self, close: pd.Series, volume: pd.Series) -> Dict[str, Any]:
        """
        计算价格和成交量的相关性
        """
        # 价格变化率
        price_change = close.pct_change()
        volume_change = volume.pct_change()

        # 相关系数
        corr = price_change.corr(volume_change)

        # 解释相关性
        interpretation = "neutral"
        if corr > 0.5:
            interpretation = "strong_positive"  # 价涨量增，健康上涨
        elif corr > 0.2:
            interpretation = "positive"
        elif corr < -0.5:
            interpretation = "strong_negative"  # 价涨量缩，需警惕
        elif corr < -0.2:
            interpretation = "negative"

        return {
            "correlation": round(float(corr) if not pd.isna(corr) else 0, 3),
            "interpretation": interpretation
        }

    def _analyze_money_flow(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        资金流向分析 (MFI - Money Flow Index)
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        volume = df["volume"]

        # 典型价格
        typical_price = (high + low + close) / 3

        # 资金流量
        money_flow = typical_price * volume

        # 价格上涨和下跌的资金流量
        positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0)
        negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0)

        # 14日资金流量比率
        positive_mf = positive_flow.rolling(window=14).sum()
        negative_mf = negative_flow.rolling(window=14).sum()

        mfi = 100 - (100 / (1 + positive_mf / negative_mf))
        current_mfi = mfi.iloc[-1]

        # 资金流向状态
        flow_status = "neutral"
        if current_mfi > 80:
            flow_status = "overbought"  # 超买
        elif current_mfi > 60:
            flow_status = "strong_inflow"  # 强势流入
        elif current_mfi < 20:
            flow_status = "oversold"  # 超卖
        elif current_mfi < 40:
            flow_status = "strong_outflow"  # 强势流出

        return {
            "mfi": round(float(current_mfi) if not pd.isna(current_mfi) else 50, 2),
            "status": flow_status,
            "net_inflow_14d": round(float(positive_mf.iloc[-1] - negative_mf.iloc[-1]) if not pd.isna(positive_mf.iloc[-1]) else 0, 2)
        }

    def _identify_volume_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        识别成交量形态
        """
        close = df["close"]
        volume = df["volume"]

        patterns = []

        # 获取最近20天数据
        recent_data = df.tail(20)
        vol_avg = volume.rolling(window=20).mean().iloc[-1]

        # 1. 放量突破
        if (close.iloc[-1] > close.iloc[-2] and
            volume.iloc[-1] > vol_avg * 1.5 and
            close.iloc[-1] > close.rolling(window=20).max().iloc[-2]):
            patterns.append({
                "pattern": "breakout_volume",
                "description": "放量突破",
                "signal": "bullish"
            })

        # 2. 缩量下跌
        if (close.iloc[-1] < close.iloc[-5] and
            volume.iloc[-1] < vol_avg * 0.7):
            patterns.append({
                "pattern": "low_volume_decline",
                "description": "缩量下跌",
                "signal": "potential_bottom"
            })

        # 3. 放量滞涨
        recent_vol_increase = volume.tail(5).mean() / vol_avg
        recent_price_change = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100
        if recent_vol_increase > 1.3 and abs(recent_price_change) < 2:
            patterns.append({
                "pattern": "high_volume_stagnation",
                "description": "放量滞涨",
                "signal": "bearish"
            })

        # 4. 地量
        if volume.iloc[-1] < vol_avg * 0.3:
            patterns.append({
                "pattern": "extremely_low_volume",
                "description": "地量",
                "signal": "potential_reversal"
            })

        # 5. 天量
        if volume.iloc[-1] > vol_avg * 3:
            patterns.append({
                "pattern": "extremely_high_volume",
                "description": "天量",
                "signal": "potential_reversal"
            })

        return {
            "patterns_found": len(patterns),
            "patterns": patterns
        }

    def _analyze_obv(self, close: pd.Series, volume: pd.Series) -> Dict[str, Any]:
        """
        能量潮(OBV)分析
        """
        # 计算OBV
        obv = pd.Series(index=close.index, dtype=float)
        obv.iloc[0] = volume.iloc[0]

        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]

        # OBV趋势
        obv_ma5 = obv.rolling(window=5).mean().iloc[-1]
        obv_ma20 = obv.rolling(window=20).mean().iloc[-1]

        trend = "neutral"
        if obv_ma5 > obv_ma20:
            trend = "bullish"
        elif obv_ma5 < obv_ma20:
            trend = "bearish"

        # OBV变化率
        obv_change = (obv.iloc[-1] - obv.iloc[-20]) / abs(obv.iloc[-20]) * 100

        return {
            "current_obv": float(obv.iloc[-1]),
            "obv_trend": trend,
            "obv_change_20d": round(float(obv_change) if not pd.isna(obv_change) else 0, 2),
            "obv_ma5": float(obv_ma5) if not pd.isna(obv_ma5) else 0,
            "obv_ma20": float(obv_ma20) if not pd.isna(obv_ma20) else 0
        }

    def _analyze_accumulation_distribution(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        累积/派发线(A/D Line)分析
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        volume = df["volume"]

        # 计算A/D线
        clv = ((close - low) - (high - close)) / (high - low)
        clv = clv.fillna(0)  # 处理high=low的情况
        ad = (clv * volume).cumsum()

        # A/D趋势
        ad_ma5 = ad.rolling(window=5).mean().iloc[-1]
        ad_ma20 = ad.rolling(window=20).mean().iloc[-1]

        trend = "neutral"
        if ad_ma5 > ad_ma20:
            trend = "accumulation"  # 累积
        elif ad_ma5 < ad_ma20:
            trend = "distribution"  # 派发

        return {
            "current_ad": float(ad.iloc[-1]),
            "ad_trend": trend,
            "ad_ma5": float(ad_ma5) if not pd.isna(ad_ma5) else 0,
            "ad_ma20": float(ad_ma20) if not pd.isna(ad_ma20) else 0
        }

    def _detect_divergence(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测量价背离
        """
        close = df["close"]
        volume = df["volume"]

        # 使用最近20天数据
        recent_close = close.tail(20)
        recent_volume = volume.tail(20)

        divergences = []

        # 顶背离：价格创新高，但OBV未创新高
        if len(recent_close) >= 10:
            price_high_1 = recent_close.tail(10).max()
            price_high_2 = recent_close.head(10).max()

            # 简单的OBV
            obv = pd.Series(index=close.index, dtype=float)
            obv.iloc[0] = volume.iloc[0]
            for i in range(1, len(close)):
                if close.iloc[i] > close.iloc[i-1]:
                    obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
                elif close.iloc[i] < close.iloc[i-1]:
                    obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
                else:
                    obv.iloc[i] = obv.iloc[i-1]

            recent_obv = obv.tail(20)
            obv_high_1 = recent_obv.tail(10).max()
            obv_high_2 = recent_obv.head(10).max()

            if price_high_1 > price_high_2 and obv_high_1 < obv_high_2:
                divergences.append({
                    "type": "bearish_divergence",
                    "description": "顶背离：价格创新高但量能减弱",
                    "signal": "bearish"
                })

            # 底背离：价格创新低，但OBV未创新低
            price_low_1 = recent_close.tail(10).min()
            price_low_2 = recent_close.head(10).min()
            obv_low_1 = recent_obv.tail(10).min()
            obv_low_2 = recent_obv.head(10).min()

            if price_low_1 < price_low_2 and obv_low_1 > obv_low_2:
                divergences.append({
                    "type": "bullish_divergence",
                    "description": "底背离：价格创新低但量能增强",
                    "signal": "bullish"
                })

        return {
            "divergences_found": len(divergences),
            "divergences": divergences
        }

    def _calculate_vpvr(self, df: pd.DataFrame, bins: int = 24) -> Dict[str, Any]:
        """
        计算筹码分布 (VPVR)
        
        Args:
            df: 数据框
            bins: 价格分段数量
        """
        close = df["close"]
        volume = df["volume"]
        high = df["high"]
        low = df["low"]
        
        # 确定价格范围
        price_min = low.min()
        price_max = high.max()
        
        if price_min == price_max:
            return {}

        # 创建价格直方图
        price_range = price_max - price_min
        bin_size = price_range / bins
        
        volume_profile = []
        
        # 将每一天的成交量分配到对应的价格区间
        # 简化算法：假设当天的成交量均匀分布在当天的High-Low范围内
        # 实际更精确的算法需要Tick数据，这里使用估算
        
        # 初始化bins
        bin_volumes = np.zeros(bins)
        bin_prices = [price_min + i * bin_size for i in range(bins + 1)]
        
        for i in range(len(df)):
            day_high = high.iloc[i]
            day_low = low.iloc[i]
            day_vol = volume.iloc[i]
            
            if day_high == day_low:
                # 只有单一价格，找到对应bin
                bin_idx = int((day_high - price_min) / bin_size)
                bin_idx = min(bin_idx, bins - 1)
                bin_volumes[bin_idx] += day_vol
            else:
                # 跨越多个bin
                start_bin = int((day_low - price_min) / bin_size)
                end_bin = int((day_high - price_min) / bin_size)
                end_bin = min(end_bin, bins - 1)
                
                # 涉及的bin数量
                num_bins = end_bin - start_bin + 1
                vol_per_bin = day_vol / num_bins
                
                for b in range(start_bin, end_bin + 1):
                    if 0 <= b < bins:
                        bin_volumes[b] += vol_per_bin
        
        # 寻找POC (Point of Control) - 交易最密集的区域
        max_vol_idx = np.argmax(bin_volumes)
        poc_price = bin_prices[max_vol_idx] + bin_size / 2
        
        # 计算价值区域 (Value Area) - 包含70%成交量的区域
        total_volume = np.sum(bin_volumes)
        target_volume = total_volume * 0.7
        
        # 从POC开始向两边扩展
        current_volume = bin_volumes[max_vol_idx]
        left_idx = max_vol_idx
        right_idx = max_vol_idx
        
        while current_volume < target_volume:
            # 尝试左边
            left_vol = 0
            if left_idx > 0:
                left_vol = bin_volumes[left_idx - 1]
            
            # 尝试右边
            right_vol = 0
            if right_idx < bins - 1:
                right_vol = bin_volumes[right_idx + 1]
            
            # 哪边大加哪边，如果都没有了就退出
            if left_vol == 0 and right_vol == 0:
                break
                
            if left_vol >= right_vol:
                left_idx -= 1
                current_volume += left_vol
            else:
                right_idx += 1
                current_volume += right_vol
                
        vah = bin_prices[right_idx + 1] # Value Area High
        val = bin_prices[left_idx]      # Value Area Low
        
        # 格式化输出
        profile_data = []
        for i in range(bins):
            profile_data.append({
                "price_start": round(bin_prices[i], 2),
                "price_end": round(bin_prices[i+1], 2),
                "volume": float(round(bin_volumes[i], 0)),
                "is_poc": bool(i == max_vol_idx),
                "in_value_area": bool(left_idx <= i <= right_idx)
            })
            
        return {
            "poc": round(float(poc_price), 2),
            "vah": round(float(vah), 2),
            "val": round(float(val), 2),
            "total_volume": float(round(total_volume, 0)),
            "profile": profile_data
        }
