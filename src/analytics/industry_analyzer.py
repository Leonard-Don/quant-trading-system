"""
行业分析引擎
用于识别热门行业和行业轮动趋势
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from src.analytics.industry_stock_details import (
    build_enriched_industry_stocks,
    extract_stock_detail_fields,
    has_meaningful_numeric,
)
from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)
_TREND_ALIAS_CACHE: Optional[Dict[str, str]] = None


def _load_trend_aliases() -> Dict[str, str]:
    global _TREND_ALIAS_CACHE
    if _TREND_ALIAS_CACHE is not None:
        return _TREND_ALIAS_CACHE

    alias_file = PROJECT_ROOT / "data" / "industry" / "trend_aliases.json"
    try:
        with open(alias_file, "r", encoding="utf-8") as file:
            payload = json.load(file)
            if isinstance(payload, dict):
                _TREND_ALIAS_CACHE = {
                    str(key).strip(): str(value).strip()
                    for key, value in payload.items()
                    if key and value
                }
                return _TREND_ALIAS_CACHE
    except FileNotFoundError:
        logger.warning("Industry trend alias file not found: %s", alias_file)
    except Exception as exc:
        logger.warning("Failed to load industry trend aliases: %s", exc)

    _TREND_ALIAS_CACHE = {}
    return _TREND_ALIAS_CACHE


class IndustryAnalyzer:
    """
    行业分析引擎
    
    核心功能:
    - 分析各行业资金流向趋势
    - 计算行业动量指标
    - K-Means 聚类识别热门行业组
    - 综合排名输出热门行业列表
    
    使用示例:
        from src.data.providers.akshare_provider import AKShareProvider
        
        provider = AKShareProvider()
        analyzer = IndustryAnalyzer(provider)
        
        hot_industries = analyzer.rank_industries(top_n=10)
        heatmap_data = analyzer.get_industry_heatmap_data()
    """
    
    # 行业热度评分权重
    # 当前实时评分仅使用能稳定拿到的横截面因子：动量、资金流、活跃度。
    DEFAULT_WEIGHTS = {
        "momentum": 0.35,       # 价格动量权重
        "money_flow": 0.35,    # 资金流向权重
        "volume_change": 0.15, # 成交量变化权重
        "volatility": -0.15,   # 预留：后续接入真实行业波动率后启用
    }
    
    def __init__(self, data_provider=None, weights: Dict[str, float] = None):
        """
        初始化行业分析引擎
        
        Args:
            data_provider: 数据提供器（AKShareProvider 实例）
            weights: 自定义评分权重
        """
        self.provider = data_provider
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        # Cache structure: {key: {"data": data, "timestamp": datetime}}
        self._cached_data: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = timedelta(minutes=30)  # 缓存30分钟（行业数据日内变化较慢）
    
    def set_provider(self, provider):
        """设置数据提供器"""
        self.provider = provider
        self._clear_cache()
    
    def _clear_cache(self):
        """清除缓存"""
        self._cached_data = {}
    
    def _get_cache_key(self, prefix: str, **kwargs) -> str:
        """生成缓存键"""
        key_parts = [prefix]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        return "|".join(key_parts)
    
    def _update_cache(self, key: str, data: Any):
        """更新缓存（跳过空数据，防止数据源故障时缓存空结果）"""
        import pandas as pd
        # 空列表 / 空 DataFrame / None 不缓存
        if data is None:
            return
        if isinstance(data, (list, tuple)) and len(data) == 0:
            return
        if isinstance(data, pd.DataFrame) and data.empty:
            return
        self._cached_data[key] = {
            "data": data,
            "timestamp": datetime.now()
        }
        
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据，如果不命中或过期返回 None"""
        if key not in self._cached_data:
            return None
            
        entry = self._cached_data[key]
        if datetime.now() - entry["timestamp"] > self._cache_ttl:
            # 过期但不删除，保留给 _get_stale_cache 使用
            return None
            
        return entry["data"]

    def _get_stale_cache(self, key: str) -> Optional[Any]:
        """获取过期缓存数据作为兜底（不检查 TTL）"""
        if key not in self._cached_data:
            return None
        return self._cached_data[key]["data"]

    @staticmethod
    def _derive_size_source(market_cap_source: Any) -> str:
        """将热力图尺寸来源收敛到与 marketCapSource 一致的类别。"""
        source = str(market_cap_source or "unknown").strip()
        if source.startswith("snapshot_"):
            return "snapshot"
        if source == "sina_proxy_stock_sum":
            return "proxy"
        if source == "unknown" or source.startswith("estimated") or source == "constant_fallback":
            return "estimated"
        return "live"

    @staticmethod
    def _scale_rank_score(series: pd.Series) -> pd.Series:
        """
        将横截面原始分数压缩到统一的 0-100 展示口径。

        这里保留 20-95 的可读区间，避免排序分数在样本很集中时出现 0/100 贴边。
        """
        clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
        if clean.empty:
            return clean
        if len(clean) == 1:
            return pd.Series([50.0], index=clean.index, dtype=float)

        s_min = clean.min()
        s_max = clean.max()
        if s_max <= s_min:
            return pd.Series(50.0, index=clean.index, dtype=float)
        return 20 + 75 * (clean - s_min) / (s_max - s_min)

    def _calculate_rank_score_series(self, df: pd.DataFrame) -> pd.Series:
        """
        基于当前可用的横截面因子计算统一行业热度分数。

        因子口径:
        - momentum: change_pct / weighted_change
        - money_flow: flow_strength
        - volume_change: avg_volume，若缺失则退化到 turnover_rate
        - volatility: industry_volatility，高波动率为负向惩罚
        """
        if df.empty:
            return pd.Series(dtype=float)

        scaler = StandardScaler()
        raw_score = pd.Series(0.0, index=df.index, dtype=float)
        used_factor = False

        factor_specs = [
            ("momentum", "change_pct" if "change_pct" in df.columns else "weighted_change"),
            ("money_flow", "flow_strength" if "flow_strength" in df.columns else None),
            ("volume_change", "avg_volume" if "avg_volume" in df.columns else ("turnover_rate" if "turnover_rate" in df.columns else None)),
            ("volatility", "industry_volatility" if "industry_volatility" in df.columns else None),
        ]

        for weight_key, column in factor_specs:
            if not column or column not in df.columns:
                continue
            try:
                factor_values = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
                raw_score += scaler.fit_transform(factor_values.to_frame()).flatten() * self.weights.get(weight_key, 0.0)
                used_factor = True
            except ValueError:
                continue

        if not used_factor:
            return pd.Series(50.0, index=df.index, dtype=float)

        return self._scale_rank_score(raw_score)

    def build_rank_score_breakdown(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not record:
            return []

        change_pct = float(record.get("change_pct", record.get("momentum", 0)) or 0)
        flow_strength = float(record.get("flow_strength", 0) or 0)
        money_flow = float(record.get("money_flow", record.get("main_net_inflow", 0)) or 0)
        turnover_rate = float(record.get("turnover_rate", 0) or 0)
        avg_volume = float(record.get("avg_volume", 0) or 0)
        industry_volatility = float(record.get("industry_volatility", record.get("industryVolatility", 0)) or 0)
        total_market_cap = float(record.get("total_market_cap", 0) or 0)
        score_value = float(record.get("score", record.get("total_score", 0)) or 0)

        volume_source = avg_volume if avg_volume > 0 else turnover_rate
        return [
            {
                "dimension": "价格动量",
                "key": "momentum",
                "value": int(round(np.clip((change_pct + 5) / 10 * 100, 0, 100))),
                "weight": float(self.weights.get("momentum", 0)),
                "metric": round(change_pct, 2),
                "metric_label": "涨跌幅%",
            },
            {
                "dimension": "资金承接",
                "key": "money_flow",
                "value": int(round(np.clip(50 + flow_strength * 18 + np.clip(money_flow / 1e8, -20, 20), 0, 100))),
                "weight": float(self.weights.get("money_flow", 0)),
                "metric": round(money_flow / 1e8, 2),
                "metric_label": "主力净流入(亿)",
            },
            {
                "dimension": "交易活跃",
                "key": "volume_change",
                "value": int(round(np.clip(35 + np.log10(max(volume_source, 1)) * 12 if volume_source > 0 else 35, 0, 100))),
                "weight": float(self.weights.get("volume_change", 0)),
                "metric": round(turnover_rate, 2),
                "metric_label": "换手率%",
            },
            {
                "dimension": "波动稳定",
                "key": "volatility",
                "value": int(round(np.clip(95 - abs(industry_volatility - 2.5) * 16 if industry_volatility > 0 else 48, 0, 100))),
                "weight": abs(float(self.weights.get("volatility", 0))),
                "metric": round(industry_volatility, 2),
                "metric_label": "波动率%",
            },
            {
                "dimension": "板块体量",
                "key": "scale",
                "value": int(round(np.clip(30 + np.log10(max(total_market_cap / 1e8, 1)) * 16 if total_market_cap > 0 else 35, 0, 100))),
                "weight": 0.0,
                "metric": round(total_market_cap / 1e8, 2),
                "metric_label": "总市值(亿)",
            },
            {
                "dimension": "综合得分",
                "key": "total_score",
                "value": int(round(np.clip(score_value, 0, 100))),
                "weight": 1.0,
                "metric": round(score_value, 2),
                "metric_label": "评分",
            },
        ]

    @staticmethod
    def _weighted_std(values: np.ndarray, weights: np.ndarray) -> float:
        """计算加权标准差；权重不可用时退化为普通标准差。"""
        clean_values = np.asarray(values, dtype=float)
        clean_weights = np.asarray(weights, dtype=float)
        if clean_values.size == 0:
            return 0.0
        if clean_values.size == 1:
            return 0.0
        if clean_weights.size != clean_values.size or clean_weights.sum() <= 0:
            return float(np.std(clean_values))
        mean = np.average(clean_values, weights=clean_weights)
        variance = np.average((clean_values - mean) ** 2, weights=clean_weights)
        return float(np.sqrt(max(variance, 0.0)))

    def _ensure_industry_volatility(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        为行业数据补齐统一的波动率字段。

        优先级:
        1. 真实/已有字段 `industry_volatility`
        2. 行业振幅 `amplitude`
        3. 行业换手率 `turnover_rate`
        4. 绝对涨跌幅 `abs(change_pct)` 作为最保守代理
        """
        if df.empty:
            return df

        result = df.copy()
        if "industry_volatility_source" not in result.columns:
            result["industry_volatility_source"] = None
        if "industry_volatility" in result.columns:
            result["industry_volatility"] = pd.to_numeric(result["industry_volatility"], errors="coerce").fillna(0.0)
            result["industry_volatility_source"] = result["industry_volatility_source"].fillna("industry_volatility")
            return result

        if "amplitude" in result.columns:
            result["industry_volatility"] = pd.to_numeric(result["amplitude"], errors="coerce").fillna(0.0)
            result["industry_volatility_source"] = "amplitude_proxy"
            return result

        if "turnover_rate" in result.columns and pd.to_numeric(result["turnover_rate"], errors="coerce").fillna(0).abs().sum() > 0:
            result["industry_volatility"] = pd.to_numeric(result["turnover_rate"], errors="coerce").fillna(0.0)
            result["industry_volatility_source"] = "turnover_rate_proxy"
            return result

        change_col = "change_pct" if "change_pct" in result.columns else ("weighted_change" if "weighted_change" in result.columns else None)
        if change_col:
            result["industry_volatility"] = pd.to_numeric(result[change_col], errors="coerce").fillna(0.0).abs()
            result["industry_volatility_source"] = "change_proxy"
        else:
            result["industry_volatility"] = 0.0
            result["industry_volatility_source"] = "unavailable"
        return result

    @staticmethod
    def _apply_historical_volatility(df: pd.DataFrame, historical_vol_df: pd.DataFrame) -> pd.DataFrame:
        """用真实历史波动率覆盖现有代理波动率。"""
        if df.empty or historical_vol_df.empty:
            return df
        merged = df.merge(
            historical_vol_df[["industry_name", "industry_volatility"]],
            on="industry_name",
            how="left",
            suffixes=("", "_historical"),
        )
        if "industry_volatility_historical" in merged.columns:
            historical_mask = pd.to_numeric(
                merged["industry_volatility_historical"],
                errors="coerce",
            ).notna()
            merged["industry_volatility"] = pd.to_numeric(
                merged["industry_volatility_historical"],
                errors="coerce",
            ).fillna(pd.to_numeric(merged.get("industry_volatility", 0), errors="coerce").fillna(0.0))
            if "industry_volatility_source" not in merged.columns:
                merged["industry_volatility_source"] = None
            merged.loc[historical_mask, "industry_volatility_source"] = "historical_index"
            merged = merged.drop(columns=["industry_volatility_historical"])
        return merged

    def _is_cache_valid(self) -> bool:
        """[Deprecated] Compatibility legacy check"""
        return False

    def _merge_momentum_and_flow(self, momentum_df: pd.DataFrame, money_flow_df: pd.DataFrame) -> pd.DataFrame:
        """
        合并动量数据和资金流向数据的公共逻辑
        
        Args:
            momentum_df: 动量 DataFrame
            money_flow_df: 资金流向 DataFrame
            
        Returns:
            合并后的 DataFrame，包含 change_pct, main_net_inflow, flow_strength 列
        """
        if not money_flow_df.empty:
            # 动态检测可用列，只合并存在的列
            merge_cols = ["industry_name"]
            optional_cols = [
            "change_pct", "main_net_inflow", "flow_strength",
            "turnover_rate", "main_net_ratio", "leading_stock",
            # THS 增强字段
            "industry_index", "total_inflow", "total_outflow",
            "leading_stock_change", "leading_stock_price",
            # AKShare 估值增强字段
            "pe_ttm", "pb", "dividend_yield",
            # 数据来源与质量标记
            "market_cap_source", "valuation_source", "valuation_quality", "data_sources"
        ]
            for col in optional_cols:
                if col in money_flow_df.columns and col not in momentum_df.columns:
                    merge_cols.append(col)
            
            if len(merge_cols) > 1:
                merged_df = momentum_df.merge(
                    money_flow_df[merge_cols],
                    on="industry_name",
                    how="left"
                )
            else:
                merged_df = momentum_df.copy()
        else:
            merged_df = momentum_df.copy()
        
        # 确保必要的列存在
        if "change_pct" not in merged_df.columns:
            merged_df["change_pct"] = merged_df.get("weighted_change", 0)
        if "main_net_inflow" not in merged_df.columns:
            merged_df["main_net_inflow"] = 0
        if "flow_strength" not in merged_df.columns:
            merged_df["flow_strength"] = 0
        
        # 仅对数值列 fillna(0)，保留字符串列（如 leading_stock）的 None
        numeric_cols = merged_df.select_dtypes(include="number").columns
        merged_df[numeric_cols] = merged_df[numeric_cols].fillna(0)
        return merged_df

    def _normalize_money_flow_dataframe(
        self,
        money_flow_df: pd.DataFrame,
        days: int
    ) -> pd.DataFrame:
        """
        标准化不同数据源/不同周期下的行业资金流字段

        统一输出字段:
        - industry_name
        - change_pct
        - main_net_inflow
        - flow_strength
        """
        if money_flow_df.empty:
            return money_flow_df

        df = money_flow_df.copy()

        # 统一行业名称字段
        if "industry_name" not in df.columns:
            for candidate in ["名称", "板块名称", "行业名称", "industry"]:
                if candidate in df.columns:
                    df = df.rename(columns={candidate: "industry_name"})
                    break

        if "industry_name" not in df.columns:
            logger.warning("money flow data missing industry_name column")
            return pd.DataFrame()

        period_prefix = "今日" if days <= 1 else f"{days}日"

        # 统一涨跌幅字段
        if "change_pct" not in df.columns:
            change_candidates = [
                f"{period_prefix}涨跌幅",
                "今日涨跌幅",
                "5日涨跌幅",
                "10日涨跌幅",
                "涨跌幅",
            ]
            for col in change_candidates:
                if col in df.columns:
                    df["change_pct"] = df[col]
                    break
            if "change_pct" not in df.columns:
                fuzzy_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
                if fuzzy_col is not None:
                    df["change_pct"] = df[fuzzy_col]

        # 统一主力净流入字段
        if "main_net_inflow" not in df.columns:
            inflow_candidates = [
                f"{period_prefix}主力净流入-净额",
                "今日主力净流入-净额",
                "5日主力净流入-净额",
                "10日主力净流入-净额",
                "主力净流入-净额",
            ]
            for col in inflow_candidates:
                if col in df.columns:
                    df["main_net_inflow"] = df[col]
                    break
            if "main_net_inflow" not in df.columns:
                fuzzy_col = next(
                    (c for c in df.columns if "主力净流入" in str(c) and "净额" in str(c)),
                    None
                )
                if fuzzy_col is not None:
                    df["main_net_inflow"] = df[fuzzy_col]

        # 数值化与缺省
        if "change_pct" in df.columns:
            df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce").fillna(0)
        else:
            df["change_pct"] = 0.0

        if "main_net_inflow" in df.columns:
            df["main_net_inflow"] = pd.to_numeric(df["main_net_inflow"], errors="coerce").fillna(0)
        else:
            df["main_net_inflow"] = 0.0

        # 统一资金强度字段，保证后续聚类/排行不会缺列。
        # 某些上游会返回全 0 的 flow_strength，这里需要根据可用字段重建，避免聚类图塌成一条线。
        recompute_flow_strength = "flow_strength" not in df.columns
        if not recompute_flow_strength:
            df["flow_strength"] = pd.to_numeric(df["flow_strength"], errors="coerce").fillna(0)
            recompute_flow_strength = (
                (df["flow_strength"].abs() <= 1e-9).all()
                and (df["main_net_inflow"].abs() > 1e-9).any()
            )

        if recompute_flow_strength:
            main_net_ratio = pd.to_numeric(df.get("main_net_ratio", 0), errors="coerce").fillna(0)
            if (main_net_ratio.abs() > 1e-9).any():
                df["flow_strength"] = (main_net_ratio / 100.0).clip(-1.0, 1.0)
            else:
                max_flow = df["main_net_inflow"].abs().max()
                if max_flow > 0:
                    df["flow_strength"] = (df["main_net_inflow"] / max_flow).clip(-1.0, 1.0)
                else:
                    df["flow_strength"] = 0.0

        # 统一换手率字段
        if "turnover_rate" in df.columns:
            df["turnover_rate"] = pd.to_numeric(df["turnover_rate"], errors="coerce").fillna(0)
        else:
            df["turnover_rate"] = 0.0

        if "amplitude" in df.columns:
            df["amplitude"] = pd.to_numeric(df["amplitude"], errors="coerce").fillna(0)

        # 统一主力净占比字段
        if "main_net_ratio" not in df.columns:
            ratio_candidates = [
                f"{period_prefix}主力净流入-净占比",
                "今日主力净流入-净占比",
                "5日主力净流入-净占比",
                "10日主力净流入-净占比",
                "主力净流入-净占比",
            ]
            for col in ratio_candidates:
                if col in df.columns:
                    df["main_net_ratio"] = df[col]
                    break
        
        if "main_net_ratio" in df.columns:
            df["main_net_ratio"] = pd.to_numeric(df["main_net_ratio"], errors="coerce").fillna(0)
        else:
            df["main_net_ratio"] = 0.0

        # Uniform leading stock field
        if "leading_stock" not in df.columns:
            # Try to find leading stock column
            for col in df.columns:
                if "领涨" in str(col) or "最大股" in str(col):
                    df["leading_stock"] = df[col]
                    break
        
        if "leading_stock" not in df.columns:
            df["leading_stock"] = None
        else:
            # 防御性处理：确保 leading_stock 为字符串或 None (数据源可能返回整数 0)
            df["leading_stock"] = df["leading_stock"].apply(
                lambda x: str(x) if x and x != 0 and str(x).strip() else None
            )

        # 统一成分股数量字段
        if "stock_count" not in df.columns:
            for candidate in ["成分股数量", "个股数", "stock_count"]:
                if candidate in df.columns:
                    df["stock_count"] = pd.to_numeric(df[candidate], errors="coerce").fillna(0).astype(int)
                    break
            if "stock_count" not in df.columns:
                df["stock_count"] = 0

        # 统一总市值字段
        if "total_market_cap" not in df.columns:
            for candidate in ["总市值", "流通市值"]:
                if candidate in df.columns:
                    df["total_market_cap"] = pd.to_numeric(df[candidate], errors="coerce").fillna(0)
                    break
            if "total_market_cap" not in df.columns:
                df["total_market_cap"] = 0.0
        else:
            # 即使列已存在，也确保数值类型正确
            df["total_market_cap"] = pd.to_numeric(df["total_market_cap"], errors="coerce").fillna(0)
        
        # [Fallback] 当所有 total_market_cap 为 0 时，使用 main_net_inflow 绝对值估算相对大小
        if (df["total_market_cap"] == 0).all() and "main_net_inflow" in df.columns:
            abs_flow = df["main_net_inflow"].abs()
            if abs_flow.max() > 0:
                logger.info("All total_market_cap are 0, estimating from main_net_inflow")
                df["total_market_cap"] = abs_flow * 1000  # 缩放到合理量级

        return self._ensure_industry_volatility(df)
    
    def analyze_money_flow(self, days: int = 5) -> pd.DataFrame:
        """
        分析各行业资金流向趋势
        
        Args:
            days: 统计周期（1/5/10 天）
            
        Returns:
            行业资金流向分析结果 DataFrame
        """
        if self.provider is None:
            logger.error("Data provider not set")
            return pd.DataFrame()
        
        # Check cache
        cache_key = self._get_cache_key("money_flow", days=days)
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached
        
        try:
            # 获取行业资金流向数据
            money_flow_df = self.provider.get_industry_money_flow(days=days)
            
            if money_flow_df.empty:
                logger.warning(f"No money flow data available for days={days}")
                # 使用过期缓存作为兜底
                stale = self._get_stale_cache(cache_key)
                if stale is not None:
                    logger.info(f"Using stale cached money flow data for days={days}")
                    return stale
                # 尝试 Sina 回退
                money_flow_df = self._try_sina_fallback(days)
                if money_flow_df.empty:
                    return pd.DataFrame()

            money_flow_df = self._normalize_money_flow_dataframe(money_flow_df, days=days)
            if money_flow_df.empty:
                logger.warning("Money flow data normalization produced empty dataframe")
                stale = self._get_stale_cache(cache_key)
                if stale is not None:
                    logger.info(f"Using stale cached money flow data for days={days}")
                    return stale
                return pd.DataFrame()
            
            # Update cache
            self._update_cache(cache_key, money_flow_df)
            return money_flow_df
            
        except Exception as e:
            logger.error(f"Error analyzing money flow: {e}")
            # 使用过期缓存作为兜底
            stale = self._get_stale_cache(cache_key)
            if stale is not None:
                logger.info(f"Using stale cached money flow data for days={days} after error")
                return stale
            # 尝试 Sina 回退
            try:
                money_flow_df = self._try_sina_fallback(days)
                if not money_flow_df.empty:
                    money_flow_df = self._normalize_money_flow_dataframe(money_flow_df, days=days)
                    if not money_flow_df.empty:
                        self._update_cache(cache_key, money_flow_df)
                        return money_flow_df
            except Exception as e2:
                logger.error(f"Sina fallback also failed: {e2}")
            return pd.DataFrame()
    
    def _try_sina_fallback(self, days: int) -> pd.DataFrame:
        """
        当主数据源失败时，尝试使用新浪财经作为备选数据源
        """
        try:
            from src.data.providers.sina_ths_adapter import SinaIndustryAdapter
            
            # 懒初始化 Sina 适配器
            if not hasattr(self, '_sina_fallback'):
                self._sina_fallback = SinaIndustryAdapter()
                logger.info("Initialized Sina fallback adapter")
            
            logger.info(f"Attempting Sina fallback for money flow (days={days})")
            df = self._sina_fallback.get_industry_money_flow(days=days)
            
            if not df.empty:
                logger.info(f"Sina fallback succeeded: {len(df)} industries")
            return df
            
        except Exception as e:
            logger.warning(f"Sina fallback failed: {e}")
            return pd.DataFrame()
    
    def _momentum_from_money_flow_fallback(
        self, lookback: int, cache_key: Optional[str]
    ) -> pd.DataFrame:
        """
        从 Sina 兜底的资金流数据构建动量，用于快/慢路径均失败时的第三层兜底。
        """
        try:
            flow_days = max(int(lookback), 1)
            money_flow_df = self._try_sina_fallback(flow_days)
            if money_flow_df.empty or "change_pct" not in money_flow_df.columns:
                return pd.DataFrame()
            df = money_flow_df.copy()
            if "weighted_change" not in df.columns:
                df["weighted_change"] = df["change_pct"]
            if "avg_change" not in df.columns:
                df["avg_change"] = df["change_pct"]
            if "avg_volume" not in df.columns:
                df["avg_volume"] = df.get("volume", df.get("turnover", 0))
            if "amount" not in df.columns and "turnover" in df.columns:
                df["amount"] = df["turnover"]
            if "total_market_cap" not in df.columns:
                amount = df.get("amount", df.get("turnover", 0))
                if "turnover_rate" in df.columns and (df["turnover_rate"] > 0).any():
                    df["total_market_cap"] = np.where(
                        df["turnover_rate"] > 0,
                        amount / (df["turnover_rate"] / 100),
                        amount * 100
                    )
                else:
                    df["total_market_cap"] = amount * 100
            if "stock_count" not in df.columns:
                df["stock_count"] = 0
            scaler = StandardScaler()
            df["momentum_score"] = scaler.fit_transform(
                df[["weighted_change"]].fillna(0)
            ).flatten()
            historical_vol_df = self.calculate_industry_historical_volatility(
                lookback=lookback,
                industries=df["industry_name"].tolist()
            )
            if not historical_vol_df.empty:
                df = self._apply_historical_volatility(df, historical_vol_df)
            df = self._ensure_industry_volatility(df)
            if cache_key:
                self._update_cache(cache_key, df)
            logger.info("Momentum built from Sina fallback (third-layer)")
            return df
        except Exception as e:
            logger.warning(f"Momentum from Sina fallback failed: {e}")
            return pd.DataFrame()

    def calculate_industry_historical_volatility(
        self,
        lookback: int = 20,
        industries: List[str] = None
    ) -> pd.DataFrame:
        """
        基于行业指数历史收盘价计算真实区间波动率。

        返回字段:
        - industry_name
        - industry_volatility
        """
        if self.provider is None or not hasattr(self.provider, "get_industry_index"):
            return pd.DataFrame()

        cache_key = None
        if industries is None:
            cache_key = self._get_cache_key("industry_volatility", lookback=lookback)
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        industry_df = self.provider.get_industry_classification()
        if industry_df.empty or "industry_name" not in industry_df.columns or "industry_code" not in industry_df.columns:
            return pd.DataFrame()

        working_df = industry_df.copy()
        if industries is not None:
            working_df = working_df[working_df["industry_name"].isin(industries)]
        if working_df.empty:
            return pd.DataFrame()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=max(int(lookback) * 3, 30))

        def _fetch_volatility(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            industry_name = row.get("industry_name")
            industry_code = row.get("industry_code")
            if not industry_name or not industry_code:
                return None
            try:
                hist_df = self.provider.get_industry_index(
                    industry_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                if hist_df.empty or "close" not in hist_df.columns:
                    return None
                close = pd.to_numeric(hist_df["close"], errors="coerce").dropna()
                if len(close) < 2:
                    return None
                returns = close.pct_change().dropna().tail(max(int(lookback), 1))
                if returns.empty:
                    return None
                return {
                    "industry_name": industry_name,
                    "industry_volatility": float(returns.std() * 100),
                }
            except Exception as e:
                logger.debug(f"Failed to fetch historical volatility for {industry_name}: {e}")
                return None

        records = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [
                executor.submit(_fetch_volatility, row)
                for row in working_df[["industry_name", "industry_code"]].to_dict(orient="records")
            ]
            for future in as_completed(futures):
                item = future.result()
                if item is not None:
                    records.append(item)

        if not records:
            return pd.DataFrame()

        result = pd.DataFrame(records).drop_duplicates(subset=["industry_name"], keep="first")
        if cache_key:
            self._update_cache(cache_key, result)
        return result

    def _load_industry_trend_series(
        self,
        industry_name: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """加载行业指数趋势序列，用于详情页走势展示。"""
        if self.provider is None or not hasattr(self.provider, "get_industry_classification") or not hasattr(self.provider, "get_industry_index"):
            return []

        try:
            normalized_name = str(industry_name or "").strip()
            trend_aliases = _load_trend_aliases()

            def resolve_industry_code() -> str:
                candidate_frames = []
                primary_df = self.provider.get_industry_classification()
                if primary_df is not None and not primary_df.empty:
                    candidate_frames.append(primary_df)
                akshare_provider = getattr(self.provider, "akshare", None)
                if akshare_provider is not None and hasattr(akshare_provider, "get_industry_classification"):
                    akshare_df = akshare_provider.get_industry_classification()
                    if akshare_df is not None and not akshare_df.empty:
                        candidate_frames.insert(0, akshare_df)

                search_names = [normalized_name]
                aliased_name = trend_aliases.get(normalized_name)
                if aliased_name and aliased_name not in search_names:
                    search_names.append(aliased_name)

                for frame in candidate_frames:
                    if "industry_name" not in frame.columns or "industry_code" not in frame.columns:
                        continue
                    working_df = frame.copy()
                    working_df["industry_name"] = working_df["industry_name"].astype(str).str.strip()
                    for search_name in search_names:
                        exact_match = working_df[working_df["industry_name"] == search_name]
                        if not exact_match.empty:
                            return str(exact_match.iloc[0].get("industry_code", "")).strip()
                    for search_name in search_names:
                        contains_match = working_df[working_df["industry_name"].str.contains(search_name, na=False)]
                        if not contains_match.empty:
                            return str(contains_match.iloc[0].get("industry_code", "")).strip()
                return ""

            industry_code = resolve_industry_code()
            if not industry_code:
                return []

            end_date = datetime.now()
            start_date = end_date - timedelta(days=max(int(days) * 3, 60))
            hist_df = self.provider.get_industry_index(
                industry_code,
                start_date=start_date,
                end_date=end_date,
            )
            if hist_df is None or hist_df.empty or "close" not in hist_df.columns:
                return []

            normalized_hist = hist_df.copy().sort_index()
            normalized_hist = normalized_hist.tail(max(int(days), 20))
            close_series = pd.to_numeric(normalized_hist["close"], errors="coerce")
            if close_series.dropna().empty:
                return []

            result = []
            prev_close = None
            for idx, row in normalized_hist.iterrows():
                close_value = pd.to_numeric(pd.Series([row.get("close")]), errors="coerce").iloc[0]
                if pd.isna(close_value):
                    continue

                open_value = pd.to_numeric(pd.Series([row.get("open")]), errors="coerce").iloc[0] if "open" in normalized_hist.columns else np.nan
                high_value = pd.to_numeric(pd.Series([row.get("high")]), errors="coerce").iloc[0] if "high" in normalized_hist.columns else np.nan
                low_value = pd.to_numeric(pd.Series([row.get("low")]), errors="coerce").iloc[0] if "low" in normalized_hist.columns else np.nan
                volume_value = pd.to_numeric(pd.Series([row.get("volume")]), errors="coerce").iloc[0] if "volume" in normalized_hist.columns else np.nan
                amount_value = pd.to_numeric(pd.Series([row.get("amount")]), errors="coerce").iloc[0] if "amount" in normalized_hist.columns else np.nan
                change_pct = ((float(close_value) / float(prev_close) - 1) * 100) if prev_close not in (None, 0) else None

                result.append({
                    "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                    "open": None if pd.isna(open_value) else round(float(open_value), 2),
                    "high": None if pd.isna(high_value) else round(float(high_value), 2),
                    "low": None if pd.isna(low_value) else round(float(low_value), 2),
                    "close": round(float(close_value), 2),
                    "volume": None if pd.isna(volume_value) else float(volume_value),
                    "amount": None if pd.isna(amount_value) else float(amount_value),
                    "change_pct": None if change_pct is None else round(float(change_pct), 2),
                })
                prev_close = float(close_value)

            return result
        except Exception as e:
            logger.debug(f"Failed to load industry trend series for {industry_name}: {e}")
            return []
    
    def calculate_industry_momentum(
        self,
        lookback: int = 20,
        industries: List[str] = None
    ) -> pd.DataFrame:
        """
        计算行业动量指标
        
        Args:
            lookback: 回看周期（天数）
            industries: 指定行业列表（可选）
            
        Returns:
            行业动量指标 DataFrame
        """
        if self.provider is None:
            logger.error("Data provider not set")
            return pd.DataFrame()
            
        # Check cache (only for full industry list)
        cache_key = None
        if industries is None:
            cache_key = self._get_cache_key("momentum", lookback=lookback)
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached
            
        # [优化] 尝试使用资金流向数据作为"快速路径"，避免逐个获取行业成分股 (N+1问题)
        try:
            flow_days = max(int(lookback), 1)
            money_flow_df = self.analyze_money_flow(days=flow_days)
            if not money_flow_df.empty and "change_pct" in money_flow_df.columns:
                logger.info("Using aggregated industry data for momentum calculation (Fast Path)")
                
                # 确保必要的列存在
                df = money_flow_df.copy()
                if "weighted_change" not in df.columns:
                    df["weighted_change"] = df["change_pct"] # 近似值
                
                if "avg_change" not in df.columns:
                    df["avg_change"] = df["change_pct"]
                
                if "avg_volume" not in df.columns:
                    # 尝试从成交额/量估算，如果没有则为0
                    df["avg_volume"] = df.get("volume", df.get("turnover", 0))

                if "amount" not in df.columns and "turnover" in df.columns:
                     df["amount"] = df["turnover"]

                if "total_market_cap" not in df.columns:
                    # 更科学的估算：如果有换手率，可以通过 成交额 / 换手率 来精确估算总市值
                    amount = df.get("amount", df.get("turnover", 0))
                    
                    if "turnover_rate" in df.columns:
                        # 避免除以0，单位一致即可（若 turnover_rate 是百分比）
                        df["total_market_cap"] = np.where(df["turnover_rate"] > 0, amount / (df["turnover_rate"] / 100), amount * 100)
                    else:
                        df["total_market_cap"] = amount * 100 # 非常粗略的估算
                
                if "stock_count" not in df.columns:
                     df["stock_count"] = 0  # 数据源未提供时标记为0

                # 归一化计算动量得分
                if "weighted_change" in df.columns:
                    scaler = StandardScaler()
                    df["momentum_score"] = scaler.fit_transform(
                        df[["weighted_change"]].fillna(0)
                    ).flatten()
                df = self._ensure_industry_volatility(df)

                # 首屏行业列表优先使用资金流/换手率代理波动率，避免为了补真实历史波动率
                # 再触发全行业指数历史拉取，拖慢热力图和排行榜冷启动。
                should_fetch_historical_volatility = industries is not None
                if should_fetch_historical_volatility:
                    historical_vol_df = self.calculate_industry_historical_volatility(
                        lookback=lookback,
                        industries=df["industry_name"].tolist()
                    )
                    if not historical_vol_df.empty:
                        df = self._apply_historical_volatility(df, historical_vol_df)
                
                # Update cache
                if cache_key:
                    self._update_cache(cache_key, df)
                    
                return df
        except Exception as e:
            logger.warning(f"Fast path momentum calculation failed: {e}")
            # 快路径异常时，先尝试 Sina 兜底
            df = self._momentum_from_money_flow_fallback(lookback, cache_key)
            if not df.empty:
                return df
        
        # [Slow Path] 原始逻辑：逐个行业获取成分股
        logger.info("Falling back to slow path (fetching stocks for each industry)")
        
        # 获取行业分类
        if industries is None:
            industry_df = self.provider.get_industry_classification()
            industries = industry_df["industry_name"].tolist() if not industry_df.empty else []
        
        momentum_data = []
        
        for industry in industries:
            try:
                # 尝试获取行业成分股来计算行业整体表现
                stocks = self.provider.get_stock_list_by_industry(industry)
                
                if not stocks:
                    continue
                
                # 计算行业内股票的加权平均涨跌幅
                total_market_cap = sum(s.get("market_cap", 0) for s in stocks)
                weighted_change = 0
                avg_change = 0
                avg_volume = 0
                stock_changes = []
                stock_weights = []
                
                for stock in stocks:
                    change_pct = stock.get("change_pct", 0)
                    market_cap = stock.get("market_cap", 0)
                    volume = stock.get("volume", 0)
                    stock_changes.append(float(change_pct or 0))
                    stock_weights.append(float(market_cap or 0))
                    
                    if total_market_cap > 0:
                        weighted_change += change_pct * (market_cap / total_market_cap)
                    avg_change += change_pct
                    avg_volume += volume
                
                stock_count = len(stocks)
                if stock_count > 0:
                    avg_change /= stock_count
                    avg_volume /= stock_count
                industry_volatility = self._weighted_std(stock_changes, stock_weights)
                
                momentum_data.append({
                    "industry_name": industry,
                    "stock_count": stock_count,
                    "weighted_change": weighted_change,
                    "avg_change": avg_change,
                    "avg_volume": avg_volume,
                    "industry_volatility": industry_volatility,
                    "industry_volatility_source": "stock_dispersion",
                    "total_market_cap": total_market_cap,
                })
                
            except Exception as e:
                logger.warning(f"Error calculating momentum for {industry}: {e}")
                continue
        
        if not momentum_data:
            # 慢路径无结果时，尝试 Sina 兜底构建动量（资金流表不依赖成分股）
            df = self._momentum_from_money_flow_fallback(lookback, cache_key)
            if not df.empty:
                return df
            return pd.DataFrame()
        
        df = pd.DataFrame(momentum_data)
        
        # 计算动量得分（归一化）
        if not df.empty and "weighted_change" in df.columns:
            scaler = StandardScaler()
            df["momentum_score"] = scaler.fit_transform(
                df[["weighted_change"]]
            ).flatten()
        historical_vol_df = self.calculate_industry_historical_volatility(
            lookback=lookback,
            industries=df["industry_name"].tolist()
        )
        if not historical_vol_df.empty:
            df = self._apply_historical_volatility(df, historical_vol_df)
        df = self._ensure_industry_volatility(df)
        
        # Update cache
        if cache_key and not df.empty:
            self._update_cache(cache_key, df)
            
        return df
    
    def cluster_hot_industries(
        self,
        n_clusters: int = 4
    ) -> Dict[str, Any]:
        """
        使用 K-Means 聚类识别热门行业组
        
        基于 (收益率, 波动率, 资金流向) 三维特征进行聚类
        
        Args:
            n_clusters: 聚类数量
            
        Returns:
            聚类结果字典，包含:
            - clusters: 各簇的行业列表
            - hot_cluster: 热门行业簇的索引
            - cluster_stats: 各簇的统计特征
        """
        # 获取动量数据
        momentum_df = self.calculate_industry_momentum()
        
        if momentum_df.empty or len(momentum_df) < 3:
            logger.warning("Not enough data for clustering")
            return {
                "clusters": {},
                "hot_cluster": -1,
                "cluster_stats": {},
                "points": [],
                "selected_cluster_count": 0,
                "silhouette_score": None,
                "cluster_candidates": {},
            }
        
        # 获取资金流向数据
        money_flow_df = self.analyze_money_flow()
        
        # 合并数据
        if not money_flow_df.empty:
            # 如果 momentum_df 已经包含了 flow_strength (Fast Path情况)，则不需要重复合并
            if "flow_strength" in momentum_df.columns:
                merged_df = momentum_df
                # 确保用最新的 money_flow 数据更新 (可选，这里假设变化不大或者不需要)
            else:
                merged_df = momentum_df.merge(
                    money_flow_df[["industry_name", "flow_strength"]],
                    on="industry_name",
                    how="left"
                )
            
            if "flow_strength" in merged_df.columns:
                merged_df["flow_strength"] = merged_df["flow_strength"].fillna(0)
        else:
             merged_df = momentum_df
             if "flow_strength" not in merged_df.columns:
                 merged_df["flow_strength"] = 0.0

        
        # 准备聚类特征 (4D: 涨跌幅, 资金强度, PE, PB)
        # 获取最新的估值数据
        valuation_df = money_flow_df[["industry_name", "pe_ttm", "pb"]] if not money_flow_df.empty and "pe_ttm" in money_flow_df.columns else pd.DataFrame()
        
        if not valuation_df.empty:
            merged_df = merged_df.merge(valuation_df, on="industry_name", how="left")
            
        feature_cols = ["weighted_change", "flow_strength"]
        if "pe_ttm" in merged_df.columns:
            # PE/PB 取对数或倒数处理，避免长尾影响；这里简单填充并标准化
            merged_df["pe_feat"] = merged_df["pe_ttm"].apply(lambda x: np.log(max(x, 1.0)) if pd.notna(x) else 0)
            feature_cols.append("pe_feat")
        if "pb" in merged_df.columns:
            merged_df["pb_feat"] = merged_df["pb"].apply(lambda x: np.log(max(x, 1.0)) if pd.notna(x) else 0)
            feature_cols.append("pb_feat")

        features = merged_df[feature_cols].fillna(0).values
        
        # 标准化特征
        scaler = StandardScaler()
        features_scaled = scaler.fit_transform(features)
        
        min_clusters = max(2, min(int(n_clusters or 4), len(merged_df) - 1))
        max_clusters = min(max(min_clusters, int(n_clusters or 4) + 2), max(2, len(merged_df) - 1), 8)
        selected_clusters = min_clusters
        selected_silhouette = None
        cluster_candidates: Dict[int, float] = {}

        if len(merged_df) >= 4:
            for candidate in range(min_clusters, max_clusters + 1):
                if candidate >= len(merged_df):
                    continue
                candidate_model = KMeans(n_clusters=candidate, random_state=42, n_init=10)
                labels = candidate_model.fit_predict(features_scaled)
                if len(set(labels)) < 2:
                    continue
                try:
                    cluster_candidates[candidate] = float(silhouette_score(features_scaled, labels))
                except Exception:
                    continue

            if cluster_candidates:
                selected_clusters, selected_silhouette = max(cluster_candidates.items(), key=lambda item: item[1])

        # K-Means 聚类
        kmeans = KMeans(n_clusters=selected_clusters, random_state=42, n_init=10)
        merged_df["cluster"] = kmeans.fit_predict(features_scaled)
        
        # 识别热门行业簇（平均动量最高的簇）
        cluster_stats = {}
        for i in range(selected_clusters):
            cluster_data = merged_df[merged_df["cluster"] == i]
            avg_momentum = cluster_data["weighted_change"].mean() if len(cluster_data) > 0 else 0
            avg_flow = cluster_data["flow_strength"].mean() if len(cluster_data) > 0 else 0
            cluster_stats[i] = {
                "count": len(cluster_data),
                "avg_momentum": float(avg_momentum) if pd.notna(avg_momentum) else 0.0,
                "avg_flow": float(avg_flow) if pd.notna(avg_flow) else 0.0,
                "industries": cluster_data["industry_name"].tolist(),
            }
        
        # 找出平均动量最高的簇作为热门簇
        hot_cluster = max(cluster_stats.keys(), key=lambda k: cluster_stats[k]["avg_momentum"])
        
        clean_df = merged_df.replace([np.inf, -np.inf], np.nan).fillna(0)
        points = []
        for _, row in clean_df.iterrows():
            points.append({
                "industry_name": row.get("industry_name", ""),
                "cluster": int(row.get("cluster", -1)),
                "weighted_change": float(row.get("weighted_change", 0)),
                "flow_strength": float(row.get("flow_strength", 0)),
                "change_pct": float(row.get("change_pct", row.get("weighted_change", 0))),
                "money_flow": float(row.get("main_net_inflow", 0)),
                "pe_ttm": float(row.get("pe_ttm", 0)) if pd.notna(row.get("pe_ttm")) else 0,
                "pb": float(row.get("pb", 0)) if pd.notna(row.get("pb")) else 0,
            })

        return {
            "clusters": {
                i: stats["industries"] 
                for i, stats in cluster_stats.items()
            },
            "hot_cluster": hot_cluster,
            "cluster_stats": cluster_stats,
            "points": points,
            "selected_cluster_count": selected_clusters,
            "silhouette_score": selected_silhouette,
            "cluster_candidates": cluster_candidates,
        }
    
    def _enrich_stock_counts(self, result: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        为排名结果补充成分股数量（仅对缺失的行业异步获取）
        """
        if self.provider is None:
            return result

        # 只对 stock_count == 0 的行业发起请求
        missing = [(i, r["industry_name"]) for i, r in enumerate(result) if r.get("stock_count", 0) == 0]
        if not missing:
            return result

        def _fetch_count(name: str) -> int:
            try:
                stocks = self.provider.get_stock_list_by_industry(name)
                return len(stocks) if stocks else 0
            except Exception:
                return 0

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_fetch_count, name): idx for idx, name in missing}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    result[idx]["stock_count"] = future.result()
                except Exception:
                    pass

        return result

    def rank_industries(
        self,
        top_n: int = 10,
        sort_by: str = "total_score",
        ascending: bool = False,
        lookback_days: int = 5
    ) -> List[Dict[str, Any]]:
        """
        对行业进行综合排名
        
        Args:
            top_n: 返回排名前 N 的行业
            sort_by: 排序字段 ("total_score" | "change_pct" | "money_flow" | "industry_volatility")
            ascending: 是否升序
            
        Returns:
            排名后的行业列表
        """
        if self.provider is None:
            return []
        
        # 顶层结果缓存
        cache_key = self._get_cache_key(
            "rank", top_n=top_n, sort_by=sort_by,
            ascending=ascending, lookback=lookback_days
        )
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached
            
        # 获取所有行业列表
        industries_df = self.provider.get_industry_classification()
        if industries_df.empty:
            return []
        
        # 获取行业代码列表（用于获取成分股数据）
        industry_list = industries_df["industry_name"].tolist()
        
        lookback_days = max(int(lookback_days), 1)
        
        # [性能优化] 所有排序类型都优先走快速路径，
        # 直接使用 analyze_money_flow() 的聚合数据，避免逐行业获取成分股
        use_fast_path = hasattr(self.provider, "get_industry_money_flow")
        
        mini_trend_lookup = self._build_industry_mini_trend_lookup(max_days=5)

        if use_fast_path:
            # 快速路径：直接使用 provider 的行业列表数据（包含涨跌幅）
            df_fast = self.analyze_money_flow(days=lookback_days)
            if not df_fast.empty:
                # 确保字段存在
                if "money_flow" not in df_fast.columns and "main_net_inflow" in df_fast.columns:
                    df_fast["money_flow"] = df_fast["main_net_inflow"]
                
                # 对 total_score 排序：使用统一行业热度评分
                if sort_by == "total_score":
                    df_fast["total_score"] = self._calculate_rank_score_series(df_fast)
                    sort_col = "total_score"
                elif sort_by == "money_flow":
                    sort_col = "main_net_inflow"
                elif sort_by == "industry_volatility":
                    sort_col = "industry_volatility"
                else:
                    sort_col = sort_by
                    
                if sort_col in df_fast.columns:
                    df_fast = df_fast.sort_values(sort_col, ascending=ascending)
                    top_df = df_fast.head(top_n)
                    
                    result = []
                    for idx, (_, row) in enumerate(top_df.iterrows(), 1):
                        # 综合得分：如果已计算 total_score 就用它，否则启发式计算
                        if "total_score" in row.index and sort_by == "total_score":
                            display_score = row.get("total_score", 0)
                        else:
                            change = row.get("change_pct", 0)
                            flow = row.get("main_net_inflow", 0)
                            flow_score = (flow / 100000000) * 0.5 
                            display_score = (change * 0.7) + (flow_score * 0.3)
                        
                        result.append({
                            "rank": idx,
                            "industry_name": row.get("industry_name", ""),
                            "score": round(float(display_score), 2),
                            "momentum": round(row.get("change_pct", 0), 2),
                            "change_pct": round(row.get("change_pct", 0), 2),
                            "money_flow": row.get("main_net_inflow", 0),
                            "flow_strength": round(row.get("flow_strength", 0), 2),
                            "industry_volatility": float(row.get("industry_volatility", 0) or 0),
                            "industry_volatility_source": row.get("industry_volatility_source", "unavailable"),
                            "stock_count": int(row.get("stock_count", 0)),
                            "total_market_cap": row.get("total_market_cap", 0),
                            "market_cap_source": row.get("market_cap_source", "unknown"),
                            "mini_trend": mini_trend_lookup.get(row.get("industry_name", ""), []),
                        })
                    # [性能优化] 不再阻塞获取 stock_count，直接返回已有数据
                    self._update_cache(cache_key, result)
                    return result

        # 标准路径 (Fallback)：计算动量和得分
        momentum_df = self.calculate_industry_momentum(
            lookback=lookback_days,
            industries=industry_list
        )
        
        if momentum_df.empty:
            return []
        
        # 使用公共合并方法
        money_flow_df = self.analyze_money_flow(days=lookback_days)
        merged_df = self._merge_momentum_and_flow(momentum_df, money_flow_df)
        
        # 统一热度评分口径，确保快/慢路径分数量纲一致
        merged_df["total_score"] = self._calculate_rank_score_series(merged_df)
        
        # 确定排序字段
        sort_col = "total_score"
        if sort_by == "change_pct":
            sort_col = "change_pct"
        elif sort_by == "money_flow":
            sort_col = "main_net_inflow"
        elif sort_by == "industry_volatility":
            sort_col = "industry_volatility"
            
        # 排序并取 top_n
        if sort_col in merged_df.columns:
            merged_df = merged_df.sort_values(sort_col, ascending=ascending)
        else:
             merged_df = merged_df.sort_values("total_score", ascending=False)
             
        top_industries = merged_df.head(top_n)
        
        # 构建结果列表
        result = []
        for idx, (_, row) in enumerate(top_industries.iterrows(), 1):
            result.append({
                "rank": idx,
                "industry_name": row.get("industry_name", ""),
                "score": round(row.get("total_score", 0), 4),
                "momentum": round(row.get("weighted_change", 0), 2),
                "change_pct": round(row.get("change_pct", 0), 2),
                "money_flow": row.get("main_net_inflow", 0),
                "flow_strength": round(row.get("flow_strength", 0), 2),
                "industry_volatility": float(row.get("industry_volatility", 0) or 0),
                "industry_volatility_source": row.get("industry_volatility_source", "unavailable"),
                "stock_count": int(row.get("stock_count", 0)),
                "total_market_cap": row.get("total_market_cap", 0),
                "market_cap_source": row.get("market_cap_source", "unknown"),
                "netInflowRatio": float(row.get("main_net_ratio", 0)),           # 主力净占比 %
                # AKShare 估值增强字段
                "pe_ttm": float(row.get("pe_ttm")) if pd.notna(row.get("pe_ttm")) and row.get("pe_ttm") != 0 else None,
                "pb": float(row.get("pb")) if pd.notna(row.get("pb")) and row.get("pb") != 0 else None,
                "dividend_yield": float(row.get("dividend_yield")) if pd.notna(row.get("dividend_yield")) and row.get("dividend_yield") != 0 else None,
                "mini_trend": mini_trend_lookup.get(row.get("industry_name", ""), []),
            })
        
        self._update_cache(cache_key, result)
        return result

    @staticmethod
    def _build_relative_trend_points_from_cumulative_changes(cumulative_changes: List[float]) -> List[float]:
        if not cumulative_changes:
            return []

        points = []
        ordered_changes = list(cumulative_changes)
        for change in reversed(ordered_changes):
            try:
                denominator = 1 + (float(change) / 100.0)
            except (TypeError, ValueError):
                return []
            if denominator <= 0:
                return []
            points.append(round(100.0 / denominator, 3))
        points.append(100.0)
        return points

    def _build_industry_mini_trend_lookup(self, max_days: int = 5) -> Dict[str, List[float]]:
        max_days = max(2, int(max_days or 5))
        trend_frames = []
        for day in range(1, max_days + 1):
            try:
                day_df = self.analyze_money_flow(days=day)
            except Exception as exc:
                logger.warning("Failed to build industry mini trend for %s-day lookback: %s", day, exc)
                continue
            if day_df.empty or "industry_name" not in day_df.columns or "change_pct" not in day_df.columns:
                continue
            trend_frames.append(
                day_df[["industry_name", "change_pct"]]
                .rename(columns={"change_pct": f"change_pct_{day}"})
            )

        if not trend_frames:
            return {}

        merged_trends = trend_frames[0]
        for frame in trend_frames[1:]:
            merged_trends = merged_trends.merge(frame, on="industry_name", how="outer")

        trend_lookup: Dict[str, List[float]] = {}
        for _, row in merged_trends.iterrows():
            industry_name = row.get("industry_name", "")
            changes = []
            for day in range(1, max_days + 1):
                value = row.get(f"change_pct_{day}")
                if pd.isna(value):
                    changes = []
                    break
                changes.append(float(value))
            if len(changes) >= 2:
                trend_lookup[industry_name] = self._build_relative_trend_points_from_cumulative_changes(changes)
        return trend_lookup
    
    def get_industry_heatmap_data(self, days: int = 5) -> Dict[str, Any]:
        """
        生成热力图可视化数据
        
        Args:
            days: 分析周期（默认5天）
            
        Returns:
            热力图数据，包含:
            - industries: 行业数据列表
            - max_value: 最大值（用于颜色标准化）
            - min_value: 最小值
            - update_time: 更新时间
        """
        # 顶层结果缓存
        cache_key = self._get_cache_key("heatmap", days=days)
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        # 获取动量数据和资金流向，确保周期对齐
        momentum_df = self.calculate_industry_momentum(lookback=days)
        money_flow_df = self.analyze_money_flow(days=days)
        
        if momentum_df.empty:
            return {
                "industries": [],
                "max_value": 0,
                "min_value": 0,
                "update_time": datetime.now().isoformat()
            }
        
        # 使用公共合并方法
        merged_df = self._merge_momentum_and_flow(momentum_df, money_flow_df)
        if "total_score" not in merged_df.columns:
            try:
                merged_df["total_score"] = self._calculate_rank_score_series(merged_df)
            except Exception as e:
                logger.warning(f"Failed to calculate heatmap total_score: {e}")
                merged_df["total_score"] = 0.0

        # 判断是否有真实市值数据（来自成分股汇总）
        has_real_market_cap = (
            "total_market_cap" in merged_df.columns
            and (merged_df["total_market_cap"] > 0).any()
            # 若市值超过某个合理门槛（>1亿），认为是真实值；若=abs(moneyFlow)*1000（估算逻辑），则是估算
            and merged_df["total_market_cap"].max() > 1e8
        )

        # 构建热力图数据
        industries = []
        for _, row in merged_df.iterrows():
            change_pct = row.get("change_pct", row.get("weighted_change", 0))
            mc = row.get("total_market_cap", 0)
            market_cap_source = row.get("market_cap_source", "unknown")
            size_source = self._derive_size_source(market_cap_source)

            industries.append({
                "name": row.get("industry_name", ""),
                "value": round(change_pct, 2),  # 涨跌幅
                "total_score": round(float(row.get("total_score", 0) or 0), 2),
                "size": mc,  # 用于方块大小
                "stockCount": int(row.get("stock_count", 0)),
                "moneyFlow": row.get("main_net_inflow", 0),
                "turnoverRate": float(row.get("turnover_rate", 0)),
                "industryVolatility": float(row.get("industry_volatility", 0) or 0),
                "industryVolatilitySource": row.get("industry_volatility_source", "unavailable"),
                "netInflowRatio": float(row.get("main_net_ratio", 0)),
                "leadingStock": row.get("leading_stock"),
                "sizeSource": size_source,
                "marketCapSource": market_cap_source,
                "marketCapSnapshotAgeHours": float(row.get("market_cap_snapshot_age_hours")) if pd.notna(row.get("market_cap_snapshot_age_hours")) else None,
                "marketCapSnapshotIsStale": bool(row.get("market_cap_snapshot_is_stale", False)),
                "valuationSource": row.get("valuation_source", "unavailable"),
                "valuationQuality": row.get("valuation_quality", "unavailable"),
                "dataSources": row.get("data_sources", []),
                # THS 增强字段
                "industryIndex": float(row.get("industry_index", 0)),
                "totalInflow": float(row.get("total_inflow", 0)),    # 亿元
                "totalOutflow": float(row.get("total_outflow", 0)),  # 亿元
                "leadingStockChange": float(row.get("leading_stock_change", 0)),  # %
                "leadingStockPrice": float(row.get("leading_stock_price", 0)),    # 元
                # AKShare 估值增强字段
                "pe_ttm": float(row.get("pe_ttm")) if pd.notna(row.get("pe_ttm")) and row.get("pe_ttm") != 0 else None,
                "pb": float(row.get("pb")) if pd.notna(row.get("pb")) and row.get("pb") != 0 else None,
                "dividend_yield": float(row.get("dividend_yield")) if pd.notna(row.get("dividend_yield")) and row.get("dividend_yield") != 0 else None,
            })

        # 按涨跌幅排序
        industries.sort(key=lambda x: x["value"], reverse=True)

        # [性能优化] 不再逐行业阻塞获取 stock_count，直接使用已有数据
        # stock_count 为 0 时前端 tooltip 已能优雅显示 "-"

        # [Fallback] 当所有 size 为 0 或均为常数1（降级占位符）时，使用 totalInflow+totalOutflow 或 moneyFlow 作为大小代理
        all_sizes = [i["size"] for i in industries]
        max_size = max(all_sizes) if all_sizes else 0
        if max_size <= 1:  # 包含全0和全1.0（降级常数）两种情况
            logger.warning(f"All industry sizes are placeholder (max={max_size}), using trading volume/moneyFlow as size proxy")
            for ind in industries:
                # 优先用成交总额（THS 提供的 totalInflow + totalOutflow，亿元）
                total_volume = ind.get("totalInflow", 0) + ind.get("totalOutflow", 0)
                if total_volume > 0:
                    proxy_size = total_volume * 1e8  # 亿元转元
                else:
                    proxy_size = abs(ind.get("moneyFlow", 0))
                if proxy_size == 0:
                    proxy_size = max(ind.get("stockCount", 1), 1) * 100 * 1e8  # stockCount × 100亿粗估
                ind["size"] = proxy_size
                ind["sizeSource"] = "estimated"

        
        values = [i["value"] for i in industries]
        
        result = {
            "industries": industries,
            "max_value": max(values) if values else 0,
            "min_value": min(values) if values else 0,
            "update_time": datetime.now().isoformat(),
        }
        
        self._update_cache(cache_key, result)
        return result
    
    def get_industry_trend(
        self,
        industry_name: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取单个行业的趋势分析
        
        Args:
            industry_name: 行业名称
            days: 分析周期
            
        Returns:
            行业趋势分析结果
        """
        if self.provider is None:
            return {"error": "Data provider not set"}
        
        try:
            days = max(int(days), 1)
            update_time = datetime.now().isoformat()

            period_change_pct = 0.0
            period_money_flow = 0.0
            fallback_market_cap = 0.0
            fallback_avg_pe = 0.0
            fallback_volatility = 0.0
            fallback_volatility_source = "unavailable"
            fallback_market_cap_source = "unknown"
            fallback_valuation_source = "unavailable"
            fallback_valuation_quality = "unavailable"

            industry_flow_df = self.analyze_money_flow(days=days)
            matched_flow_row = None
            if not industry_flow_df.empty and "industry_name" in industry_flow_df.columns:
                matched = industry_flow_df[industry_flow_df["industry_name"] == industry_name]
                if not matched.empty:
                    matched_flow_row = matched.iloc[0]
                    period_change_pct = float(matched_flow_row.get("change_pct", 0) or 0)
                    period_money_flow = float(matched_flow_row.get("main_net_inflow", 0) or 0)
                    fallback_market_cap = float(matched_flow_row.get("total_market_cap", 0) or 0)
                    fallback_avg_pe = float(matched_flow_row.get("pe_ttm", 0) or 0)
                    fallback_volatility = float(matched_flow_row.get("industry_volatility", 0) or 0)
                    fallback_volatility_source = matched_flow_row.get("industry_volatility_source", "unavailable")
                    fallback_market_cap_source = matched_flow_row.get("market_cap_source", "unknown")
                    fallback_valuation_source = matched_flow_row.get("valuation_source", "unavailable")
                    fallback_valuation_quality = matched_flow_row.get("valuation_quality", "unavailable")

            historical_vol_df = self.calculate_industry_historical_volatility(
                lookback=days,
                industries=[industry_name],
            )
            if not historical_vol_df.empty:
                hist_row = historical_vol_df.iloc[0]
                fallback_volatility = float(hist_row.get("industry_volatility", 0) or 0)
                fallback_volatility_source = "historical_index"

            trend_series = self._load_industry_trend_series(industry_name, days=days)

            raw_stocks = self.provider.get_stock_list_by_industry(industry_name)
            stocks = build_enriched_industry_stocks(
                self.provider,
                industry_name,
                provider_stocks=raw_stocks,
            )
            expected_count = int(matched_flow_row.get("stock_count", 0) or 0) if matched_flow_row is not None else 0
            expected_count_base = max(expected_count, 1)
            
            if not stocks:
                # 混合数据源下，行业名称可能能在行业热度数据中找到，但无法稳定映射到成分股。
                # 此时返回降级趋势数据，避免前端详情弹窗直接 404。
                if matched_flow_row is not None:
                    return {
                        "industry_name": industry_name,
                        "stock_count": int(matched_flow_row.get("stock_count", 0) or 0),
                        "expected_stock_count": expected_count,
                        "total_market_cap": fallback_market_cap,
                        "avg_pe": round(fallback_avg_pe, 2) if fallback_avg_pe > 0 else 0,
                        "industry_volatility": round(fallback_volatility, 4),
                        "industry_volatility_source": fallback_volatility_source,
                        "period_days": days,
                        "period_change_pct": round(period_change_pct, 2),
                        "period_money_flow": period_money_flow,
                        "top_gainers": [],
                        "top_losers": [],
                        "rise_count": 0,
                        "fall_count": 0,
                        "flat_count": 0,
                        "stock_coverage_ratio": 0.0,
                        "change_coverage_ratio": 0.0,
                        "market_cap_coverage_ratio": 0.0,
                        "pe_coverage_ratio": 0.0,
                        "total_market_cap_fallback": fallback_market_cap > 0,
                        "avg_pe_fallback": fallback_avg_pe > 0,
                        "market_cap_source": fallback_market_cap_source,
                        "valuation_source": fallback_valuation_source,
                        "valuation_quality": fallback_valuation_quality,
                        "trend_series": trend_series,
                        "degraded": True,
                        "note": "当前仅能返回行业聚合数据，成分股明细暂不可用。",
                        "update_time": update_time,
                    }
                return {"error": f"No stocks found for industry: {industry_name}"}
            
            detailed_stocks = []
            valid_change_stocks = []
            for stock in stocks:
                detail = extract_stock_detail_fields(stock)
                enriched_stock = {**stock, **detail}
                detailed_stocks.append(enriched_stock)
                if detail.get("change_pct") is not None:
                    valid_change_stocks.append(enriched_stock)

            valid_market_caps = [
                stock["market_cap"]
                for stock in detailed_stocks
                if has_meaningful_numeric(stock.get("market_cap"))
            ]
            valid_pe_ratios = [
                stock["pe_ratio"]
                for stock in detailed_stocks
                if stock.get("pe_ratio") is not None and 0 < stock["pe_ratio"] < 500
            ]
            valid_pe_weighted_pairs = [
                (stock["market_cap"], stock["pe_ratio"])
                for stock in detailed_stocks
                if has_meaningful_numeric(stock.get("market_cap"))
                and stock.get("pe_ratio") is not None
                and 0 < stock["pe_ratio"] < 500
            ]

            total_market_cap = sum(valid_market_caps)
            total_market_cap_fallback = False
            if valid_pe_weighted_pairs:
                total_pe_market_cap = sum(float(market_cap) for market_cap, _ in valid_pe_weighted_pairs)
                total_earnings_proxy = sum(float(market_cap) / float(pe_ratio) for market_cap, pe_ratio in valid_pe_weighted_pairs if float(pe_ratio) > 0)
                avg_pe = (total_pe_market_cap / total_earnings_proxy) if total_pe_market_cap > 0 and total_earnings_proxy > 0 else np.nan
            else:
                avg_pe = np.mean(valid_pe_ratios) if valid_pe_ratios else np.nan
            avg_pe_fallback = False
            if fallback_market_cap > 0:
                if not valid_market_caps:
                    total_market_cap = fallback_market_cap
                    total_market_cap_fallback = True
                elif expected_count > 10:
                    cap_coverage = len(valid_market_caps) / max(expected_count, 1)
                    if cap_coverage < 0.35 or total_market_cap < fallback_market_cap * 0.25:
                        total_market_cap = fallback_market_cap
                        total_market_cap_fallback = True

            if fallback_avg_pe > 0:
                pe_coverage_base = len(valid_pe_weighted_pairs) if valid_pe_weighted_pairs else len(valid_pe_ratios)
                if pe_coverage_base == 0:
                    avg_pe = fallback_avg_pe
                    avg_pe_fallback = True
                elif expected_count > 10:
                    pe_coverage = pe_coverage_base / max(expected_count, 1)
                    if pe_coverage < 0.35:
                        avg_pe = fallback_avg_pe
                        avg_pe_fallback = True

            stock_coverage_ratio = min(len(stocks) / expected_count_base, 1.0) if expected_count > 0 else (1.0 if len(stocks) > 0 else 0.0)
            change_coverage_ratio = min(len(valid_change_stocks) / expected_count_base, 1.0) if expected_count > 0 else (1.0 if len(valid_change_stocks) > 0 else 0.0)
            market_cap_coverage_ratio = min(len(valid_market_caps) / expected_count_base, 1.0) if expected_count > 0 else (1.0 if len(valid_market_caps) > 0 else 0.0)
            pe_coverage_base = len(valid_pe_weighted_pairs) if valid_pe_weighted_pairs else len(valid_pe_ratios)
            pe_coverage_ratio = min(pe_coverage_base / expected_count_base, 1.0) if expected_count > 0 else (1.0 if pe_coverage_base > 0 else 0.0)

            industry_volatility = float(fallback_volatility or 0)
            industry_volatility_source = fallback_volatility_source
            
            # 找出涨幅前5的股票
            top_gainers = sorted(valid_change_stocks, key=lambda x: x.get("change_pct", 0), reverse=True)[:5]
            
            # 找出跌幅前5的股票
            top_losers = sorted(valid_change_stocks, key=lambda x: x.get("change_pct", 0))[:5]
            
            # 计算涨跌比
            rise_count = sum(1 for s in valid_change_stocks if s.get("change_pct", 0) > 0)
            fall_count = sum(1 for s in valid_change_stocks if s.get("change_pct", 0) < 0)
            flat_count = sum(1 for s in valid_change_stocks if s.get("change_pct", 0) == 0)
            
            note = None
            degraded = False
            # 如果成分股数量极少（比如只有1只），且不是原本就极小的行业，标记为降级/提示
            if len(stocks) <= 3 and expected_count > 10:
                degraded = True
                note = f"成分股列表可能不完整（获取到 {len(stocks)} 只，预期约 {expected_count} 只）。当前展示可能存在偏差。"
            elif len(stocks) == 1:
                 note = "该行业目前仅获取到单只成分股明细，分布数据仅供参考。"

            return {
                "industry_name": industry_name,
                "stock_count": len(stocks),
                "expected_stock_count": expected_count,
                "total_market_cap": total_market_cap,
                "avg_pe": round(avg_pe, 2) if not np.isnan(avg_pe) else 0,
                "industry_volatility": round(industry_volatility, 4),
                "industry_volatility_source": industry_volatility_source,
                "period_days": days,
                "period_change_pct": round(period_change_pct, 2),
                "period_money_flow": period_money_flow,
                "top_gainers": top_gainers,
                "top_losers": top_losers,
                "rise_count": rise_count,
                "fall_count": fall_count,
                "flat_count": flat_count,
                "stock_coverage_ratio": round(stock_coverage_ratio, 4),
                "change_coverage_ratio": round(change_coverage_ratio, 4),
                "market_cap_coverage_ratio": round(market_cap_coverage_ratio, 4),
                "pe_coverage_ratio": round(pe_coverage_ratio, 4),
                "total_market_cap_fallback": total_market_cap_fallback,
                "avg_pe_fallback": avg_pe_fallback,
                "market_cap_source": fallback_market_cap_source,
                "valuation_source": fallback_valuation_source,
                "valuation_quality": fallback_valuation_quality,
                "trend_series": trend_series,
                "degraded": degraded,
                "note": note,
                "update_time": update_time,
            }
            
        except Exception as e:
            logger.error(f"Error analyzing industry trend for {industry_name}: {e}")
            return {"error": str(e)}

    def get_industry_rotation(
        self,
        industry_names: List[str],
        periods: List[int] = None
    ) -> Dict[str, Any]:
        """
        获取行业轮动对比数据
        
        Args:
            industry_names: 要对比的行业列表（2-5个）
            periods: 统计周期列表（天数），默认 [1, 5, 10]
            
        Returns:
            各行业在不同周期的涨跌幅对比数据
        """
        if self.provider is None:
            return {"error": "Data provider not set"}
        
        if periods is None:
            # THS supports 1, 3, 5, 10, 20. For longer ones, we currently rely on the adapter's closest match logic.
            periods = [1, 5, 20]
        
        try:
            industry_names = [str(name).strip() for name in industry_names if str(name).strip()]
            periods = sorted(set(max(int(p), 1) for p in periods))
            if not industry_names:
                return {"industries": [], "periods": periods, "data": [], "update_time": datetime.now().isoformat()}

            cache_key = self._get_cache_key(
                "rotation",
                industries=",".join(industry_names),
                periods=",".join(map(str, periods))
            )
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

            def build_period_data(period: int) -> Tuple[int, Optional[Dict[str, Any]]]:
                money_flow_df = self.analyze_money_flow(days=period)
                if money_flow_df.empty or "industry_name" not in money_flow_df.columns:
                    return period, None

                period_data: Dict[str, Any] = {"period": period}
                for name in industry_names:
                    row = money_flow_df[money_flow_df["industry_name"] == name]
                    if not row.empty:
                        matched = row.iloc[0]
                        period_data[name] = round(float(matched.get("change_pct", 0) or 0), 2)
                        period_data[f"{name}__flow"] = float(matched.get("main_net_inflow", 0) or 0)
                    else:
                        period_data[name] = 0
                        period_data[f"{name}__flow"] = 0.0
                return period, period_data

            period_map: Dict[int, Dict[str, Any]] = {}
            max_workers = min(4, len(periods))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(build_period_data, period) for period in periods]
                for future in as_completed(futures):
                    period, period_data = future.result()
                    if period_data is not None:
                        period_map[period] = period_data

            rotation_data = [period_map[p] for p in periods if p in period_map]

            result = {
                "industries": industry_names,
                "periods": periods,
                "data": rotation_data,
                "update_time": datetime.now().isoformat(),
            }
            self._update_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error getting industry rotation: {e}")
            return {"error": str(e)}
