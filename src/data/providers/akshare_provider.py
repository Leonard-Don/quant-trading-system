"""
AKShare 数据提供器
用于获取中国 A 股市场数据，包括行业分类、行业指数、资金流向、个股财务等
"""

import os
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging
import requests
from pathlib import Path
import threading

from .base_provider import BaseDataProvider, DataProviderError

logger = logging.getLogger(__name__)

# 默认加载 akshare （原强制禁用代理的相关代码已移除以防止 Fake-IP 路由失败）
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
    logger.info("AKShare loaded successfully")
except ImportError:
    AKSHARE_AVAILABLE = False
    logger.warning("AKShare not installed. Install with: pip install akshare")


class AKShareProvider(BaseDataProvider):
    """
    A 股数据提供器
    
    基于 AKShare 开源库，提供中国 A 股市场数据:
    - 申万行业分类
    - 行业指数历史数据
    - 行业资金流向
    - 个股财务数据（ROE、营收、利润等）
    - 宏观经济指标
    
    使用示例:
        provider = AKShareProvider()
        industries = provider.get_industry_classification()
        hot_industries = provider.get_industry_money_flow()
    """
    
    name: str = "akshare"
    priority: int = 50  # 高优先级用于 A 股
    rate_limit: int = 100  # 每分钟请求限制
    requires_api_key: bool = False
    
    def __init__(self):
        super().__init__()
        self._market_cap_cache = {}
        self._market_cap_cache_time = None
    
    # 申万一级行业代码映射
    SW_INDUSTRY_MAP = {
        "农林牧渔": "801010",
        "基础化工": "801030", 
        "钢铁": "801040",
        "有色金属": "801050",
        "电子": "801080",
        "汽车": "801880",
        "家用电器": "801110",
        "食品饮料": "801120",
        "纺织服饰": "801130",
        "轻工制造": "801140",
        "医药生物": "801150",
        "公用事业": "801160",
        "交通运输": "801170",
        "房地产": "801180",
        "商贸零售": "801200",
        "社会服务": "801210",
        "银行": "801780",
        "非银金融": "801790",
        "综合": "801230",
        "建筑材料": "801710",
        "建筑装饰": "801720",
        "电力设备": "801730",
        "国防军工": "801740",
        "计算机": "801750",
        "传媒": "801760",
        "通信": "801770",
        "煤炭": "801020",
        "石油石化": "801960",
        "环保": "801970",
        "美容护理": "801980",
    }
    _industry_meta_cache_path = Path(__file__).resolve().parents[3] / "cache" / "industry_metadata_cache.json"
    _industry_meta_heatmap_fallback_path = Path(__file__).resolve().parents[3] / "data" / "industry" / "heatmap_history.json"
    _shared_industry_meta_cache: pd.DataFrame | None = None
    _shared_industry_meta_cache_time: datetime | None = None
    _shared_industry_meta_failure_at: datetime | None = None
    _industry_meta_failure_cooldown_seconds: int = 300
    _industry_meta_lock = threading.Lock()
    
    def __init__(self, api_key: Optional[str] = None, config: Dict[str, Any] = None):
        """初始化 AKShare 提供器"""
        super().__init__(api_key, config)
        
        # 清除代理环境变量，因为 AKShare 使用的东方财富 API 在代理环境下会失败
        self._clear_proxy_settings()
        
        if not AKSHARE_AVAILABLE:
            logger.warning("AKShare not available, provider will use fallback mode")
        else:
            logger.info("AKShareProvider initialized (proxy settings cleared)")
    
    def _clear_proxy_settings(self):
        """清除可能干扰 AKShare API 调用的代理设置（彻底阻断苹果系统的 scutil 注入）"""
        import os
        import urllib.request
        
        # 1. 直接阻断底层 Mac OS 获取系统代理的路径
        urllib.request.getproxies = lambda: {}
        
        # 2. 移除并重置环境变量
        proxy_vars = [
            'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
            'ALL_PROXY', 'all_proxy'
        ]
        for var in proxy_vars:
            if var in os.environ:
                logger.debug(f"Clearing proxy environment variable: {var}")
                del os.environ[var]
            # 防御性覆盖，确保不会被回退获取
            os.environ[var] = ""
                
        # 3. 强制 requests 忽略局部代理
        os.environ['NO_PROXY'] = '*'
        os.environ['no_proxy'] = '*'

    @classmethod
    def _load_persistent_industry_metadata(cls) -> tuple[pd.DataFrame | None, datetime | None]:
        cache_path = cls._industry_meta_cache_path
        if not cache_path.exists():
            return None, None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            rows = payload.get("data", [])
            updated_at_raw = payload.get("updated_at")
            if not rows:
                return None, None
            df = pd.DataFrame(rows)
            if "market_cap_source" not in df.columns:
                df["market_cap_source"] = "akshare_metadata"
            updated_at = datetime.fromisoformat(updated_at_raw) if updated_at_raw else None
            logger.info("Loaded persistent industry metadata cache with %s industries", len(df))
            return df, updated_at
        except Exception as e:
            logger.warning(f"Failed to load persistent industry metadata cache: {e}")
            return None, None

    @classmethod
    def _load_heatmap_history_metadata_fallback(cls) -> tuple[pd.DataFrame | None, datetime | None]:
        history_path = cls._industry_meta_heatmap_fallback_path
        if not history_path.exists():
            return None, None

        try:
            payload = json.loads(history_path.read_text(encoding="utf-8"))
            if not isinstance(payload, list) or not payload:
                return None, None

            for snapshot in payload:
                industries = snapshot.get("industries") or []
                rows = []
                for item in industries:
                    source = str(item.get("marketCapSource", "unknown") or "unknown").strip()
                    total_market_cap = pd.to_numeric(item.get("size"), errors="coerce")
                    turnover_rate = pd.to_numeric(item.get("turnoverRate"), errors="coerce")
                    industry_name = str(item.get("name") or "").strip()
                    if not industry_name or not pd.notna(total_market_cap) or float(total_market_cap) <= 0:
                        continue
                    if source == "unknown" or source.startswith("estimated") or source == "constant_fallback":
                        continue

                    rows.append({
                        "industry_name": industry_name,
                        "original_name": industry_name,
                        "total_market_cap": float(total_market_cap),
                        "turnover_rate": float(turnover_rate) if pd.notna(turnover_rate) else 0.0,
                        "market_cap_source": source,
                    })

                if rows:
                    updated_at_raw = snapshot.get("captured_at") or snapshot.get("update_time")
                    updated_at = datetime.fromisoformat(updated_at_raw) if updated_at_raw else None
                    df = pd.DataFrame(rows).drop_duplicates(subset=["industry_name"], keep="first")
                    logger.info("Loaded heatmap-history metadata fallback with %s industries", len(df))
                    return df, updated_at
        except Exception as e:
            logger.warning(f"Failed to load heatmap-history metadata fallback: {e}")

        return None, None

    @classmethod
    def _persist_industry_metadata(cls, df_meta: pd.DataFrame, updated_at: datetime) -> None:
        try:
            cls._industry_meta_cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": updated_at.isoformat(),
                "data": df_meta.to_dict(orient="records"),
            }
            cls._industry_meta_cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to persist industry metadata cache: {e}")
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d"
    ) -> pd.DataFrame:
        """
        获取 A 股历史 K 线数据
        
        Args:
            symbol: 股票代码（如 "000001" 或 "600519"）
            start_date: 开始日期
            end_date: 结束日期
            interval: 数据间隔（目前仅支持日线 "1d"）
            
        Returns:
            包含 OHLCV 数据的 DataFrame
        """
        if not AKSHARE_AVAILABLE:
            return pd.DataFrame()
        
        try:
            # 设置默认日期范围
            if end_date is None:
                end_date = datetime.now()
            if start_date is None:
                start_date = end_date - timedelta(days=365)
            
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            
            # 使用东方财富接口获取日线数据
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="qfq"  # 前复权
            )
            
            if df.empty:
                return pd.DataFrame()
            
            # 标准化列名
            df = df.rename(columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "涨跌幅": "pct_change",
                "涨跌额": "change",
                "换手率": "turnover"
            })
            
            # 设置日期索引
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            
            return self._standardize_dataframe(df)
            
        except Exception as e:
            logger.error(f"Error fetching A-share data for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """
        获取 A 股最新报价
        
        Args:
            symbol: 股票代码
            
        Returns:
            最新报价信息字典
        """
        if not AKSHARE_AVAILABLE:
            return {"symbol": symbol, "error": "AKShare not available"}
        
        try:
            # 获取实时行情（利用缓存）
            df = self._get_all_stocks_spot()
            
            # 查找指定股票
            stock_data = df[df["代码"] == symbol]
            
            if stock_data.empty:
                return {"symbol": symbol, "error": "Stock not found"}
            
            row = stock_data.iloc[0]
            
            return {
                "symbol": symbol,
                "name": row.get("名称", ""),
                "price": float(row.get("最新价", 0)),
                "change": float(row.get("涨跌额", 0)),
                "change_percent": float(row.get("涨跌幅", 0)),
                "volume": int(row.get("成交量", 0)),
                "amount": float(row.get("成交额", 0)),
                "high": float(row.get("最高", 0)),
                "low": float(row.get("最低", 0)),
                "open": float(row.get("今开", 0)),
                "prev_close": float(row.get("昨收", 0)),
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}
    
    def get_industry_classification(self) -> pd.DataFrame:
        """
        获取申万行业分类
        
        Returns:
            行业分类 DataFrame，包含行业代码、名称、成分股数量等
        """
        if not AKSHARE_AVAILABLE:
            return pd.DataFrame()
        
        try:
            # 获取申万一级行业分类
            df = ak.index_stock_cons_weight_csindex(symbol="000300")
            
            # 构建行业分类数据
            industries = []
            for name, code in self.SW_INDUSTRY_MAP.items():
                industries.append({
                    "industry_code": code,
                    "industry_name": name,
                })
            
            return pd.DataFrame(industries)
            
        except Exception as e:
            logger.error(f"Error fetching industry classification: {e}")
            # 返回静态行业列表作为备选
            industries = [
                {"industry_code": code, "industry_name": name}
                for name, code in self.SW_INDUSTRY_MAP.items()
            ]
            return pd.DataFrame(industries)
    
    def get_industry_index(
        self,
        industry_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        获取行业指数历史数据
        
        Args:
            industry_code: 申万行业代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            行业指数 OHLCV 数据
        """
        if not AKSHARE_AVAILABLE:
            return pd.DataFrame()
        
        try:
            if end_date is None:
                end_date = datetime.now()
            if start_date is None:
                start_date = end_date - timedelta(days=365)
            
            # 获取申万行业指数
            df = ak.index_hist_sw(symbol=industry_code)
            
            if df.empty:
                return pd.DataFrame()
            
            # 标准化列名
            df = df.rename(columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount"
            })
            
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            
            # 筛选日期范围
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            return self._standardize_dataframe(df)
            
        except Exception as e:
            logger.error(f"Error fetching industry index {industry_code}: {e}")
            return pd.DataFrame()
    
    def get_industry_money_flow(self, days: int = 5) -> pd.DataFrame:
        """
        获取行业资金流向数据
        
        Args:
            days: 统计天数（1/5/10）
            
        Returns:
            行业资金流向 DataFrame
        """
        if not AKSHARE_AVAILABLE:
            return pd.DataFrame()
        
        try:
            # 获取行业资金流向
            if days <= 1:
                df = ak.stock_sector_fund_flow_rank(indicator="今日")
            elif days <= 5:
                df = ak.stock_sector_fund_flow_rank(indicator="5日")
            else:
                df = ak.stock_sector_fund_flow_rank(indicator="10日")
            
            if df.empty:
                return pd.DataFrame()
            
            # 标准化列名 - 注意 AKShare 返回的列名带有 "今日" 前缀
            df = df.rename(columns={
                "名称": "industry_name",
                "今日涨跌幅": "change_pct",
                "今日主力净流入-净额": "main_net_inflow",
                "今日主力净流入-净占比": "main_net_ratio",
                "今日超大单净流入-净额": "super_large_net",
                "今日超大单净流入-净占比": "super_large_ratio",
                "今日大单净流入-净额": "large_net",
                "今日大单净流入-净占比": "large_ratio",
                "今日中单净流入-净额": "medium_net",
                "今日中单净流入-净占比": "medium_ratio",
                "今日小单净流入-净额": "small_net",
                "今日小单净流入-净占比": "small_ratio",
                "今日主力净流入最大股": "leading_stock",
            })

            # [Enhanced] Fetch industry metadata (Market Cap) from EastMoney
            meta_merged = False
            try:
                df_meta = self._get_industry_metadata()
                
                if not df_meta.empty and "total_market_cap" in df_meta.columns:
                    # Merge market cap into flow data
                    # Use LEFT join so industries without metadata are NOT dropped
                    df = df.merge(
                        df_meta[["industry_name", "original_name", "total_market_cap", "turnover_rate"]],
                        left_on="industry_name",
                        right_on="original_name",
                        how="left" 
                    )
                    
                    # Use the clean industry_name from metadata where available
                    if "industry_name_y" in df.columns:
                        df["industry_name"] = df["industry_name_y"].fillna(df["industry_name_x"])
                        df = df.drop(columns=["industry_name_x", "industry_name_y"], errors="ignore")
                    if "original_name" in df.columns:
                        df = df.drop(columns=["original_name"], errors="ignore")
                    
                    # Fill NaN market caps with 0
                    df["total_market_cap"] = pd.to_numeric(df["total_market_cap"], errors="coerce").fillna(0)
                    df["turnover_rate"] = pd.to_numeric(df["turnover_rate"], errors="coerce").fillna(0)
                    meta_merged = True
                        
            except Exception as e:
                logger.warning(f"Error fetching industry metadata for market cap: {e}")
            
            # [Fallback] 当 metadata 不可用或 merge 后市值全为 0 时，
            # 使用主力净流入绝对值作为相对大小代理
            if not meta_merged or ("total_market_cap" in df.columns and (df["total_market_cap"] == 0).all()):
                logger.info("Market cap metadata unavailable, estimating from money flow data")
                # 找到主力净流入列（可能是中文或英文名称）
                inflow_col = None
                for col_name in ["main_net_inflow"]:
                    if col_name in df.columns:
                        inflow_col = col_name
                        break
                if inflow_col is None:
                    # 尝试中文列名
                    for col in df.columns:
                        if "主力净流入" in str(col) and "净额" in str(col):
                            inflow_col = col
                            break
                
                if inflow_col is not None:
                    # 使用净流入绝对值作为相对大小代理
                    # 乘以 1000 缩放到合理量级，使 treemap 大小差异明显
                    abs_flow = pd.to_numeric(df[inflow_col], errors="coerce").abs().fillna(0)
                    df["total_market_cap"] = abs_flow * 1000
                else:
                    df["total_market_cap"] = 1.0  # 最后兜底：均匀大小
                
                if "turnover_rate" not in df.columns:
                    df["turnover_rate"] = 0.0
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching industry money flow: {e}")
            return pd.DataFrame()
    
    def _get_industry_metadata(self) -> pd.DataFrame:
        """
        Fetch and cache industry metadata (Market Cap, Turnover)
        includes filtering logic for duplicate industries.
        
        Cache strategy:
        - 缓存有效期 4 小时（市值数据日内变化极小）
        - 刷新失败时保留过期缓存作为兜底
        - 自动重试 1 次
        """
        import time
        
        cls = self.__class__

        # Lazy init cache
        if not hasattr(self, '_industry_meta_cache'):
            logger.info("Initializing industry metadata cache (lazy)")
            self._industry_meta_cache = cls._shared_industry_meta_cache
            self._industry_meta_cache_time = cls._shared_industry_meta_cache_time
            if self._industry_meta_cache is None:
                persistent_df, persistent_time = self._load_persistent_industry_metadata()
                if persistent_df is not None and not persistent_df.empty:
                    self._industry_meta_cache = persistent_df
                    self._industry_meta_cache_time = persistent_time or datetime.now() - timedelta(days=1)
                    cls._shared_industry_meta_cache = persistent_df
                    cls._shared_industry_meta_cache_time = self._industry_meta_cache_time
            
        current_time = datetime.now()

        # Check shared cache first so repeated provider instances reuse the same snapshot.
        if (
            cls._shared_industry_meta_cache is not None
            and cls._shared_industry_meta_cache_time
            and current_time - cls._shared_industry_meta_cache_time < timedelta(hours=4)
        ):
            self._industry_meta_cache = cls._shared_industry_meta_cache
            self._industry_meta_cache_time = cls._shared_industry_meta_cache_time
            return cls._shared_industry_meta_cache
        
        # Check cache (valid for 4 hours as metadata is slow changing)
        if (self._industry_meta_cache is not None and 
            self._industry_meta_cache_time and 
            current_time - self._industry_meta_cache_time < timedelta(hours=4)):
            return self._industry_meta_cache

        # Fast-fail during a recent upstream outage to avoid re-triggering dozens of retries
        # from parallel cold-start requests.
        if (
            cls._shared_industry_meta_failure_at is not None
            and current_time - cls._shared_industry_meta_failure_at
            < timedelta(seconds=cls._industry_meta_failure_cooldown_seconds)
        ):
            if self._industry_meta_cache is not None:
                logger.info("Skipping AKShare metadata refresh during cooldown; using in-memory snapshot")
                return self._industry_meta_cache
            persistent_df, persistent_time = self._load_persistent_industry_metadata()
            if persistent_df is not None and not persistent_df.empty:
                self._industry_meta_cache = persistent_df
                self._industry_meta_cache_time = persistent_time or datetime.now() - timedelta(days=1)
                cls._shared_industry_meta_cache = persistent_df
                cls._shared_industry_meta_cache_time = self._industry_meta_cache_time
                logger.info("Skipping AKShare metadata refresh during cooldown; using persistent snapshot")
                return persistent_df
            heatmap_df, heatmap_time = self._load_heatmap_history_metadata_fallback()
            if heatmap_df is not None and not heatmap_df.empty:
                self._industry_meta_cache = heatmap_df
                self._industry_meta_cache_time = heatmap_time or datetime.now() - timedelta(hours=6)
                cls._shared_industry_meta_cache = heatmap_df
                cls._shared_industry_meta_cache_time = self._industry_meta_cache_time
                logger.info("Skipping AKShare metadata refresh during cooldown; using heatmap-history snapshot")
                return heatmap_df
            logger.info("Skipping AKShare metadata refresh during cooldown; no fallback snapshot available")
            return pd.DataFrame()
        
        # Try to refresh with 1 retry
        last_error = None
        with cls._industry_meta_lock:
            # Another request may have already refreshed the shared cache while we waited.
            if (
                cls._shared_industry_meta_cache is not None
                and cls._shared_industry_meta_cache_time
                and current_time - cls._shared_industry_meta_cache_time < timedelta(hours=4)
            ):
                self._industry_meta_cache = cls._shared_industry_meta_cache
                self._industry_meta_cache_time = cls._shared_industry_meta_cache_time
                return cls._shared_industry_meta_cache

            for attempt in range(2):
                try:
                    if attempt > 0:
                        time.sleep(1)  # 重试前等待 1 秒
                    logger.info(f"Fetching industry metadata from AKShare (attempt {attempt + 1})...")
                    df_meta = ak.stock_board_industry_name_em()
                    if df_meta.empty:
                        continue
                        
                    # [Filter Duplicate Industries]
                    # Logic: 
                    # 1. Remove names ending with 'III' (usually redundant L3)
                    # 2. Remove names ending with 'II' ONLY IF the base name exists
                    
                    df_meta['base_name'] = df_meta['板块名称'].astype(str)
                    all_names = set(df_meta['base_name'].tolist())
                    
                    filter_indices = []
                    for idx, row in df_meta.iterrows():
                        name = row['base_name']
                        keep = True
                        
                        if name.endswith('Ⅲ'):
                            keep = False
                        elif name.endswith('Ⅱ'):
                            base = name[:-1]
                            if base in all_names:
                                keep = False
                                
                        if keep:
                            filter_indices.append(idx)
                            
                    df_meta = df_meta.loc[filter_indices].drop(columns=['base_name'])

                    # Preserve original name for matching
                    df_meta['original_name'] = df_meta['板块名称']

                    # [Clean Names] Remove Roman numerals from the display name
                    # e.g., "白酒Ⅱ" -> "白酒", "证券Ⅱ" -> "证券"
                    df_meta['板块名称'] = df_meta['板块名称'].str.replace(r'[ⅡⅢⅢ]$', '', regex=True)

                    # Rename columns to match for merge
                    df_meta = df_meta.rename(columns={
                        "板块名称": "industry_name",
                        "总市值": "total_market_cap",
                        "换手率": "turnover_rate",
                        "涨跌幅": "change_pct_meta"  # Avoid conflict
                    })
                    if "market_cap_source" not in df_meta.columns:
                        df_meta["market_cap_source"] = "akshare_metadata"
                    
                    # Update Cache
                    self._industry_meta_cache = df_meta
                    self._industry_meta_cache_time = current_time
                    cls._shared_industry_meta_cache = df_meta
                    cls._shared_industry_meta_cache_time = current_time
                    cls._shared_industry_meta_failure_at = None
                    self._persist_industry_metadata(df_meta, current_time)
                    logger.info(f"Industry metadata fetched successfully: {len(df_meta)} industries")
                    
                    return df_meta
                    
                except Exception as e:
                    last_error = e
                    logger.warning(f"_get_industry_metadata attempt {attempt + 1} failed: {e}")
            cls._shared_industry_meta_failure_at = current_time
        
        # All retries failed - use stale cache as fallback
        if self._industry_meta_cache is not None:
            logger.warning(f"Using stale metadata cache as fallback (last error: {last_error})")
            return self._industry_meta_cache

        persistent_df, persistent_time = self._load_persistent_industry_metadata()
        if persistent_df is not None and not persistent_df.empty:
            self._industry_meta_cache = persistent_df
            self._industry_meta_cache_time = persistent_time or datetime.now() - timedelta(days=1)
            cls._shared_industry_meta_cache = persistent_df
            cls._shared_industry_meta_cache_time = self._industry_meta_cache_time
            logger.warning(f"Using persistent metadata snapshot as fallback (last error: {last_error})")
            return persistent_df
        heatmap_df, heatmap_time = self._load_heatmap_history_metadata_fallback()
        if heatmap_df is not None and not heatmap_df.empty:
            self._industry_meta_cache = heatmap_df
            self._industry_meta_cache_time = heatmap_time or datetime.now() - timedelta(hours=6)
            cls._shared_industry_meta_cache = heatmap_df
            cls._shared_industry_meta_cache_time = self._industry_meta_cache_time
            logger.warning(f"Using heatmap-history metadata snapshot as fallback (last error: {last_error})")
            return heatmap_df
        
        logger.error(f"_get_industry_metadata failed with no cache fallback: {last_error}")
        return pd.DataFrame()

    def _get_all_stocks_spot(self) -> pd.DataFrame:
        """
        获取所有股票最新行情及估值数据（带缓存，5分钟有效）
        
        Returns:
            pd.DataFrame 包含全量股票基本及财务信息
        """
        if not hasattr(self, '_spot_cache'):
            logger.info("Initializing spot cache (lazy)")
            self._spot_cache = pd.DataFrame()
            self._spot_cache_time = None
            
        current_time = datetime.now()
        
        if (not self._spot_cache.empty and self._spot_cache_time and 
            current_time - self._spot_cache_time < timedelta(minutes=5)):
            return self._spot_cache
            
        try:
            logger.info("Fetching all stocks spot data from AKShare (EM)...")
            df = ak.stock_zh_a_spot_em()
            if not df.empty:
                self._spot_cache = df
                self._spot_cache_time = current_time
                return self._spot_cache
        except Exception as e:
            logger.warning(f"Error fetching EM spots: {e}, falling back to Sina spots...")
            try:
                # 降级：走新浪的全市场快照接口 (字段有所不同，后续需要映射兼容)
                df_sina = ak.stock_zh_a_spot()
                if not df_sina.empty:
                    # 将 Sina 中文列名粗暴向 EM 看齐以满足外层读取
                    df_sina = df_sina.rename(columns={
                        "symbol": "代码", 
                        "name": "名称", 
                        "mktcap": "总市值", 
                        "mktcap": "流通市值" # Sina 这个接口并没有直接的动态 PE，所以 PE 校验只能放空让它跳过
                    })
                    self._spot_cache = df_sina
                    self._spot_cache_time = current_time
                    return self._spot_cache
            except Exception as e2:
                logger.error(f"Error fetching Sina spots: {e2}")

        return self._spot_cache
            
    def _get_all_stocks_market_cap(self) -> Dict[str, float]:
        """
        获取所有股票的市值数据（从缓存）
        
        Returns:
            Dict[symbol, market_cap]
        """
        df = self._get_all_stocks_spot()
        if df.empty:
            return {}
            
        market_cap_map = {}
        for _, row in df.iterrows():
            symbol = str(row.get("代码", ""))
            market_cap = self._safe_float(row.get("总市值"))
            if symbol and market_cap > 0:
                market_cap_map[symbol] = market_cap
                
        return market_cap_map

    def get_stock_list_by_industry(self, industry_name: str) -> List[Dict[str, Any]]:
        """
        获取行业成分股列表
        
        Args:
            industry_name: 行业名称
            
        Returns:
            成分股列表
        """
        if not AKSHARE_AVAILABLE:
            return []
        
        try:
            # [Fix] Resolve original name if possible
            # The input industry_name might be a cleaned name (e.g. "白酒")
            # We need the original name (e.g. "白酒Ⅱ") to fetch stocks
            target_name = industry_name
            
            # Try to find mapping in metadata
            try:
                df_meta = self._get_industry_metadata()
                if not df_meta.empty and "industry_name" in df_meta.columns and "original_name" in df_meta.columns:
                    # Find identifying row
                    match = df_meta[df_meta["industry_name"] == industry_name]
                    if not match.empty:
                        target_name = match.iloc[0]["original_name"]
                        if target_name != industry_name:
                            logger.info(f"Resolved industry name: {industry_name} -> {target_name}")
            except Exception as e:
                logger.warning(f"Failed to resolve original industry name: {e}")

            # 获取板块成分股
            df = ak.stock_board_industry_cons_em(symbol=target_name)
            
            if df.empty:
                return []
            
            # 获取全市场市值数据
            market_cap_map = self._get_all_stocks_market_cap()
            
            stocks = []
            for _, row in df.iterrows():
                symbol = str(row.get("代码", ""))
                market_cap = market_cap_map.get(symbol, 0)
                
                stocks.append({
                    "symbol": symbol,
                    "name": row.get("名称", ""),
                    "price": float(row.get("最新价", 0)) if pd.notna(row.get("最新价")) else 0,
                    "change_pct": float(row.get("涨跌幅", 0)) if pd.notna(row.get("涨跌幅")) else 0,
                    "volume": float(row.get("成交量", 0)) if pd.notna(row.get("成交量")) else 0,
                    "amount": float(row.get("成交额", 0)) if pd.notna(row.get("成交额")) else 0,
                    "market_cap": market_cap, # 从全市场数据获取
                    "pe_ratio": float(row.get("市盈率-动态", 0)) if pd.notna(row.get("市盈率-动态")) else 0,
                })
            
            return stocks
            
        except Exception as e:
            logger.error(f"Error fetching stocks for industry {industry_name}: {e}")
            return []
    
    def get_stock_financial_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取个股财务数据
        
        Args:
            symbol: 股票代码
            
        Returns:
            财务数据字典（ROE、营收、利润、增速等）
        """
        if not AKSHARE_AVAILABLE:
            return {"symbol": symbol, "error": "AKShare not available"}
        
        try:
            # 获取财务指标
            df = ak.stock_financial_abstract_ths(symbol=symbol)
            
            if df.empty:
                return {"symbol": symbol, "error": "Financial data not found"}
            
            # [修复] 取最新一期数据（iloc[-1]），而非最旧（iloc[0]）
            # stock_financial_abstract_ths 返回按时间正序排列
            latest = df.iloc[-1]
            
            result = {
                "symbol": symbol,
                "report_date": str(latest.get("报告期", "")),
                "roe": self._safe_float(latest.get("净资产收益率")),
                "gross_margin": self._safe_float(latest.get("销售毛利率")),
                "net_margin": self._safe_float(latest.get("销售净利率")),
                "revenue": self._safe_float(latest.get("营业总收入")),
                "net_profit": self._safe_float(latest.get("净利润")),
                "revenue_yoy": self._safe_float(latest.get("营业总收入同比增长率")),
                "profit_yoy": self._safe_float(latest.get("净利润同比增长率")),
                "eps": self._safe_float(latest.get("基本每股收益")),
                "bps": self._safe_float(latest.get("每股净资产")),
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching financial data for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}
    
    def get_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """获取基本面数据（实现基类方法）"""
        return self.get_stock_financial_data(symbol)
    
    def get_stock_valuation(self, symbol: str) -> Dict[str, Any]:
        """
        获取个股估值数据
        
        Args:
            symbol: 股票代码
            
        Returns:
            估值数据字典（PE、PB、PS、市值等）
        """
        if not AKSHARE_AVAILABLE:
            return {"symbol": symbol, "error": "AKShare not available"}
        
        try:
            # 获取实时行情中的估值数据（利用缓存）
            df = self._get_all_stocks_spot()
            stock_data = df[df["代码"] == symbol]
            
            if stock_data.empty:
                return {"symbol": symbol, "error": "Stock not found"}
            
            row = stock_data.iloc[0]
            
            return {
                "symbol": symbol,
                "name": row.get("名称", ""),
                "pe_ttm": self._safe_float(row.get("市盈率-动态")),
                "pb": self._safe_float(row.get("市净率")),
                "market_cap": self._safe_float(row.get("总市值")),
                "float_market_cap": self._safe_float(row.get("流通市值")),
                "turnover": self._safe_float(row.get("换手率")),
                "volume_ratio": self._safe_float(row.get("量比")),
                "amount": self._safe_float(row.get("成交额")),
                "change_pct": self._safe_float(row.get("涨跌幅")),
            }
            
        except Exception as e:
            logger.error(f"Error fetching valuation for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}
    
    def get_macro_indicators(self) -> Dict[str, Any]:
        """
        获取宏观经济指标
        
        Returns:
            宏观指标字典（PMI、CPI、M2 等）
        """
        if not AKSHARE_AVAILABLE:
            return {"error": "AKShare not available"}
        
        result = {}
        
        try:
            # 获取 PMI 数据
            pmi_df = ak.macro_china_pmi_yearly()
            if not pmi_df.empty:
                latest_pmi = pmi_df.iloc[-1]
                result["pmi"] = {
                    "date": str(latest_pmi.get("月份", "")),
                    "manufacturing": self._safe_float(latest_pmi.get("制造业PMI")),
                }
        except Exception as e:
            logger.warning(f"Error fetching PMI: {e}")
        
        try:
            # 获取 CPI 数据
            cpi_df = ak.macro_china_cpi_yearly()
            if not cpi_df.empty:
                latest_cpi = cpi_df.iloc[-1]
                result["cpi"] = {
                    "date": str(latest_cpi.get("月份", "")),
                    "yoy": self._safe_float(latest_cpi.get("今年以来")),
                }
        except Exception as e:
            logger.warning(f"Error fetching CPI: {e}")
        
        try:
            # 获取市场整体行情
            market_df = ak.stock_zh_a_spot_em()
            if not market_df.empty:
                # 计算市场整体涨跌
                up_count = len(market_df[market_df["涨跌幅"] > 0])
                down_count = len(market_df[market_df["涨跌幅"] < 0])
                result["market_sentiment"] = {
                    "total_stocks": len(market_df),
                    "up_count": up_count,
                    "down_count": down_count,
                    "up_ratio": up_count / len(market_df) if len(market_df) > 0 else 0,
                }
        except Exception as e:
            logger.warning(f"Error fetching market sentiment: {e}")
        
        return result
    
    def get_all_a_stocks(self) -> pd.DataFrame:
        """
        获取所有 A 股股票列表
        
        Returns:
            股票列表 DataFrame
        """
        if not AKSHARE_AVAILABLE:
            return pd.DataFrame()
        
        try:
            df = ak.stock_zh_a_spot_em()
            return df
        except Exception as e:
            logger.error(f"Error fetching all A stocks: {e}")
            return pd.DataFrame()
    
    def is_available(self) -> bool:
        """检查 AKShare 是否可用"""
        if not AKSHARE_AVAILABLE:
            return False
        
        try:
            # 简单测试：获取市场行情
            df = ak.stock_zh_a_spot_em()
            return not df.empty
        except Exception:
            return False
    
    def _safe_float(self, value: Any) -> float:
        """
        安全转换为浮点数
        
        支持格式:
        - 普通数字: 3.14, 100
        - 百分号: '8.32%' → 8.32
        - 中文单位: '3000.48万' → 30004800, '2.68亿' → 268000000
        - 布尔值 False、'--'、空值 → 0.0
        """
        if value is None or value is False or value == "--" or value == "":
            return 0.0
        try:
            if pd.isna(value):
                return 0.0
        except (TypeError, ValueError):
            pass
        
        # 数字类型直接转
        if isinstance(value, (int, float)):
            return float(value)
        
        # 字符串类型需要解析
        s = str(value).strip()
        if not s:
            return 0.0
        
        try:
            # 去掉百分号
            if s.endswith('%'):
                return float(s[:-1])
            # 中文单位
            if s.endswith('万亿'):
                return float(s[:-2]) * 1e12
            if s.endswith('亿'):
                return float(s[:-1]) * 1e8
            if s.endswith('万'):
                return float(s[:-1]) * 1e4
            return float(s)
        except (ValueError, TypeError):
            return 0.0
