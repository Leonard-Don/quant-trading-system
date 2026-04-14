"""
龙头股评分系统
多维度评分模型，从热门行业中遴选龙头企业
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging
import json
import time
from pathlib import Path
from sklearn.preprocessing import MinMaxScaler, StandardScaler

logger = logging.getLogger(__name__)


class LeaderStockScorer:
    """
    龙头股评分系统
    
    评分维度:
    - 市值: 规模大小（取对数后标准化）
    - ROE: 盈利能力
    - 营收增速: 成长性
    - 利润增速: 盈利增长
    - 波动率: 稳定性（负向指标）
    - 流动性: 交易活跃度
    
    使用示例:
        from src.data.providers.akshare_provider import AKShareProvider
        
        provider = AKShareProvider()
        scorer = LeaderStockScorer(provider)
        
        leaders = scorer.get_leader_stocks(["电子", "医药生物"], top_per_industry=5)
    """
    
    # 统一评分权重（快速评分和完整评分共用）
    DEFAULT_WEIGHTS = {
        "market_cap": 0.20,      # 市值规模
        "valuation": 0.15,       # 估值（PE 适中得分高）
        "profitability": 0.25,   # 盈利能力（ROE / 毛利率）
        "growth": 0.20,          # 成长性（营收利润增速）
        "momentum": 0.10,        # 价格动量（涨跌幅）
        "activity": 0.10,        # 交易活跃度（成交额）
    }
    
    # ROE 合理范围
    ROE_MIN = 0
    ROE_MAX = 50  # 超过50%可能有异常
    
    # 增长率合理范围
    GROWTH_MIN = -100
    GROWTH_MAX = 200  # 超过200%可能有异常
    
    _financial_cache: Dict[str, Any] = {}
    _financial_cache_loaded: bool = False
    _financial_cache_path = Path(__file__).resolve().parents[2] / "cache" / "financial_cache.json"

    @classmethod
    def _ensure_financial_cache_loaded(cls):
        if cls._financial_cache_loaded:
            return
        try:
            if cls._financial_cache_path.exists():
                payload = json.loads(cls._financial_cache_path.read_text(encoding="utf-8"))
                now = time.time()
                cache = payload.get("cache", {})
                for sym, entry in cache.items():
                    if isinstance(entry, dict) and (now - entry.get("ts", 0)) < 86400:
                        cls._financial_cache[sym] = entry
                logger.info(f"Loaded {len(cls._financial_cache)} valid financial cache entries")
        except Exception as e:
            logger.warning(f"Failed to load financial cache: {e}")
        finally:
            cls._financial_cache_loaded = True

    @classmethod
    def _persist_financial_cache(cls):
        if not cls._financial_cache:
            return
        try:
            cls._financial_cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": time.time(),
                "cache": dict(sorted(cls._financial_cache.items())),
            }
            cls._financial_cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to persist financial cache: {e}")

    def _get_cached_financial_data(self, symbol: str) -> Dict[str, Any]:
        if self.provider is None:
            return {"error": "Data provider not set"}
        
        self.__class__._ensure_financial_cache_loaded()
        now = time.time()
        
        entry = self.__class__._financial_cache.get(symbol)
        if entry and (now - entry.get("ts", 0)) < 86400:
            return entry.get("data", {})
            
        financial = self.provider.get_stock_financial_data(symbol)
        if "error" not in financial:
            self.__class__._financial_cache[symbol] = {
                "ts": now,
                "data": financial
            }
            # 注意：不再逐股持久化到磁盘，由调用方在批处理结束后统一调用 _persist_financial_cache()
            
        return financial

    def _get_cached_financial_data_if_available(self, symbol: str) -> Dict[str, Any]:
        """仅返回当前进程/磁盘缓存中的财务数据，不触发新的网络请求。"""
        self.__class__._ensure_financial_cache_loaded()
        entry = self.__class__._financial_cache.get(symbol)
        if not entry:
            return {"error": "Financial cache miss"}
        if (time.time() - entry.get("ts", 0)) >= 86400:
            return {"error": "Financial cache expired"}
        return entry.get("data", {})
    
    def __init__(self, data_provider=None, weights: Dict[str, float] = None):
        """
        初始化龙头股评分系统
        
        Args:
            data_provider: 数据提供器（AKShareProvider 实例）
            weights: 自定义评分权重
        """
        self.provider = data_provider
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

    @staticmethod
    def _normalize_quote_snapshot(quote: Dict[str, Any]) -> Dict[str, Any]:
        """统一实时行情字段，兼容 AKShare/Sina 不同返回口径。"""
        if not quote or "error" in quote:
            return {}

        def pick_number(*keys: str) -> Any:
            for key in keys:
                value = quote.get(key)
                if value not in (None, ""):
                    return value
            return None

        current_price = pick_number("current_price", "price")
        previous_close = pick_number("previous_close", "prev_close", "pre_close")
        change = pick_number("change")

        if change in (None, ""):
            try:
                if current_price not in (None, "") and previous_close not in (None, "", 0):
                    change = float(current_price) - float(previous_close)
            except (TypeError, ValueError):
                change = None

        updated_at = quote.get("updated_at")
        timestamp = quote.get("timestamp")
        if updated_at in (None, "") and timestamp not in (None, ""):
            if hasattr(timestamp, "isoformat"):
                updated_at = timestamp.isoformat()
            else:
                updated_at = str(timestamp)

        return {
            "current_price": current_price,
            "previous_close": previous_close,
            "change": change,
            "high": pick_number("high"),
            "low": pick_number("low"),
            "volume": pick_number("volume"),
            "amount": pick_number("amount"),
            "open": pick_number("open"),
            "bid": pick_number("bid"),
            "ask": pick_number("ask"),
            "source": quote.get("source", "unknown"),
            "updated_at": updated_at,
        }
        
    def set_provider(self, provider):
        """设置数据提供器"""
        self.provider = provider
        self._cache = {}
        
    def set_weights(self, weights: Dict[str, float]):
        """
        设置评分权重
        
        Args:
            weights: 权重字典，键为指标名称，值为权重（-1 到 1）
        """
        self.weights.update(weights)
        
        # 确保权重之和为1（归一化）
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}
    
    def score_stock(
        self,
        symbol: str,
        industry_stats: Dict = None,
        snapshot_data: Dict[str, Any] = None,
        score_type: str = "core"
    ) -> Dict[str, Any]:
        """
        计算单只股票的龙头得分
        
        Args:
            symbol: 股票代码
            industry_stats: 行业统计数据（用于相对评分）
            
        Returns:
            股票评分详情：
            - symbol: 股票代码
            - name: 股票名称  
            - total_score: 综合得分
            - dimension_scores: 各维度得分
            - raw_data: 原始数据
        """
        if self.provider is None:
            return {"symbol": symbol, "error": "Data provider not set"}
        
        try:
            valuation = {}
            if snapshot_data:
                valuation = {
                    "symbol": symbol,
                    "name": snapshot_data.get("name", ""),
                    "market_cap": snapshot_data.get("market_cap", 0),
                    "pe_ttm": snapshot_data.get("pe_ttm", snapshot_data.get("pe_ratio", 0)),
                    "pb": snapshot_data.get("pb", 0),
                    "turnover": snapshot_data.get("turnover", 0),
                    "change_pct": snapshot_data.get("change_pct", 0),
                    "amount": snapshot_data.get("amount", 0),
                }

            missing_valuation = not valuation or (
                (valuation.get("market_cap", 0) in [0, None]) and
                (valuation.get("amount", 0) in [0, None]) and
                (valuation.get("change_pct", 0) in [0, None])
            )

            if missing_valuation:
                valuation = self.provider.get_stock_valuation(symbol)
                if "error" in valuation:
                    return {"symbol": symbol, "error": valuation["error"]}
            
            # 获取财务数据
            financial = self._get_cached_financial_data(symbol)
            if "error" in financial:
                logger.warning(f"Financial data unavailable for {symbol}, using neutral profitability/growth")
                financial = {
                    "roe": None,
                    "revenue_yoy": None,
                    "profit_yoy": None,
                }
            
            # 提取各项指标（统一字段，与 _quick_score 兼容）
            raw_data = {
                "symbol": symbol,
                "name": valuation.get("name", ""),
                "market_cap": valuation.get("market_cap", 0),
                "pe_ttm": valuation.get("pe_ttm", 0),
                "pb": valuation.get("pb", 0),
                "turnover": valuation.get("turnover", 0),
                "net_inflow_ratio": valuation.get("net_inflow_ratio", 0),
                "roe": financial.get("roe"),
                "revenue_yoy": financial.get("revenue_yoy"),
                "profit_yoy": financial.get("profit_yoy"),
                "change_pct": valuation.get("change_pct", 0),
                "amount": valuation.get("amount", 0),
            }
            
            # 计算各维度得分
            dimension_scores = self._calculate_dimension_scores(raw_data, industry_stats, score_type=score_type)
            
            # 计算综合得分
            total_score = self._calculate_total_score(dimension_scores, raw_data, score_type=score_type)
            
            return {
                "symbol": symbol,
                "name": raw_data["name"],
                "total_score": round(total_score, 4),
                "dimension_scores": dimension_scores,
                "raw_data": raw_data,
            }
            
        except Exception as e:
            logger.error(f"Error scoring stock {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    def score_stock_from_snapshot(
        self,
        stock_data: Dict[str, Any],
        industry_stats: Dict = None,
        enrich_financial: bool = False,
        cached_only: bool = False,
        score_type: str = "core"
    ) -> Dict[str, Any]:
        """
        基于已有快照数据进行轻量评分，按需再补财务数据。

        适用于行业热度链路：优先复用 THS-first 成分股已有字段，
        避免每只票都走一遍完整估值/行情接口。
        """
        symbol = stock_data.get("symbol", "")
        if not symbol:
            return {"symbol": symbol, "error": "Missing symbol"}

        score_result = self._quick_score(stock_data, industry_stats, score_type=score_type)
        score_result["raw_data"] = {
            "symbol": symbol,
            "name": stock_data.get("name", ""),
            "market_cap": stock_data.get("market_cap", 0),
            "pe_ttm": stock_data.get("pe_ratio", 0),
            "change_pct": stock_data.get("change_pct", 0),
            "amount": stock_data.get("amount", 0),
            "turnover": stock_data.get("turnover", 0),
            "net_inflow_ratio": stock_data.get("net_inflow_ratio", 0),
            "roe": None,
            "revenue_yoy": None,
            "profit_yoy": None,
        }

        if not enrich_financial or self.provider is None:
            return score_result

        try:
            financial = self._get_cached_financial_data_if_available(symbol) if cached_only else self._get_cached_financial_data(symbol)
            if "error" not in financial:
                raw_data = score_result["raw_data"]
                raw_data["roe"] = financial.get("roe", 0)
                raw_data["revenue_yoy"] = financial.get("revenue_yoy", 0)
                raw_data["profit_yoy"] = financial.get("profit_yoy", 0)

                dimension_scores = self._calculate_dimension_scores(raw_data, industry_stats, score_type=score_type)
                score_result["dimension_scores"] = dimension_scores
                score_result["total_score"] = round(self._calculate_total_score(dimension_scores, raw_data, score_type=score_type), 2)
        except Exception as e:
            logger.warning(f"Financial enrichment failed for {symbol}: {e}")

        return score_result
    
    def _calculate_dimension_scores(
        self,
        raw_data: Dict[str, Any],
        industry_stats: Dict = None,
        score_type: str = "core"
    ) -> Dict[str, float]:
        """
        计算各维度得分（统一评分体系）
        
        维度:
        - market_cap: 市值规模（对数标准化）
        - valuation: 估值水平（PE 适中得分高）
        - profitability: 盈利能力（ROE）
        - growth: 成长性（营收+利润增速组合）
        - momentum: 价格动量（涨跌幅）
        - activity: 交易活跃度（成交额）
        """
        scores = {}
        
        # 1. 市值得分（对数标准化，10亿-1万亿）
        market_cap = raw_data.get("market_cap", 0)
        if market_cap > 0:
            log_cap = np.log10(max(market_cap, 1))
            scores["market_cap"] = self._normalize(log_cap, 9, 12)
        else:
            scores["market_cap"] = 0
        
        # 2. 估值得分（PE 在 10-30 之间较优，过高过低都扣分）
        pe = raw_data.get("pe_ttm", raw_data.get("pe_ratio", 0))
        if pe and pe > 0:
            if 10 <= pe <= 30:
                scores["valuation"] = 1 - abs(pe - 20) / 20
            elif pe < 10:
                scores["valuation"] = pe / 10
            else:
                scores["valuation"] = max(0, 1 - (pe - 30) / 50)
        else:
            scores["valuation"] = 0.3  # PE 无效或为负给中性分
        
        # 3. 盈利能力得分（ROE，0-25% 正常范围）
        roe = raw_data.get("roe")
        if roe is None or pd.isna(roe):
            scores["profitability"] = 0.5
        else:
            roe = self._clip_value(roe, self.ROE_MIN, self.ROE_MAX)
            scores["profitability"] = self._normalize(roe, 0, 25)
        
        # 4. 成长性得分（营收增速 + 利润增速 各 50%）
        revenue_yoy = raw_data.get("revenue_yoy")
        profit_yoy = raw_data.get("profit_yoy")
        if revenue_yoy is None or pd.isna(revenue_yoy):
            rev_score = 0.5
        else:
            revenue_yoy = self._clip_value(revenue_yoy, self.GROWTH_MIN, self.GROWTH_MAX)
            rev_score = self._normalize(revenue_yoy, -20, 50)
        if profit_yoy is None or pd.isna(profit_yoy):
            pft_score = 0.5
        else:
            profit_yoy = self._clip_value(profit_yoy, self.GROWTH_MIN, self.GROWTH_MAX)
            pft_score = self._normalize(profit_yoy, -20, 50)
        scores["growth"] = rev_score * 0.5 + pft_score * 0.5
        
        # 5. 动量得分（涨跌幅，-5% 到 +5% 标准化）
        change_pct = raw_data.get("change_pct", 0)
        scores["momentum"] = self._normalize(change_pct, -5, 5)
        
        # 6. 交易活跃度得分（成交额，对数标准化）
        amount = raw_data.get("amount", 0)
        if amount > 0:
            log_amount = np.log10(max(amount, 1))
            scores["activity"] = self._normalize(log_amount, 6, 10)  # 1百万到100亿
        else:
            # 用换手率作为后备
            turnover = raw_data.get("turnover", 0)
            scores["activity"] = self._normalize(turnover, 0.5, 10)
            
        if score_type == "hot":
            net_inflow_ratio = raw_data.get("net_inflow_ratio", raw_data.get("main_net_ratio", 0))
            scores["momentum"] = min(1.0, max(0.0, (change_pct + 15) / 30))
            scores["money_flow"] = min(1.0, max(0.0, (net_inflow_ratio + 10) / 20))
            scores["valuation"] = 0.5
            scores["profitability"] = 0.5
            scores["growth"] = 0.5
            scores["activity"] = 0.5
            scores["score_type"] = "hot"
        
        return scores
    
    def _calculate_total_score(self, dimension_scores: Dict[str, float], raw_data: Dict[str, Any] = None, score_type: str = "core") -> float:
        """
        计算综合得分
        
        Args:
            dimension_scores: 各维度得分（0-1）
            
        Returns:
            综合得分（0-100）
        """
        if score_type == "hot":
            change_pct = float(raw_data.get("change_pct", 0) or 0)
            net_inflow_ratio = float(raw_data.get("net_inflow_ratio", raw_data.get("main_net_ratio", 0)) or 0)
            
            # Exactly mirrors industry.py hot candidate fallback calculation:
            surge_score = min(100, max(0, (change_pct + 15) / 30 * 50 + max(0, min(50, net_inflow_ratio * 5 + 25))))
            
            # hot 评分使用独立的 0-100 动量量尺，不再压缩到 50 分上限
            return round(surge_score, 2)
            
        total = 0
        for dim, weight in self.weights.items():
            score = dimension_scores.get(dim, 0)
            total += weight * score
        
        # 转换为 0-100 分
        return total * 100
    
    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """
        将值归一化到 0-1 范围
        
        Args:
            value: 原始值
            min_val: 最小值
            max_val: 最大值
            
        Returns:
            归一化后的值（0-1）
        """
        if max_val == min_val:
            return 0.5
        normalized = (value - min_val) / (max_val - min_val)
        return max(0, min(1, normalized))
    
    def _clip_value(self, value: float, min_val: float, max_val: float) -> float:
        """限制值在合理范围内"""
        if pd.isna(value) or value is None:
            return 0
        return max(min_val, min(max_val, value))
    
    def rank_stocks_in_industry(
        self,
        industry_name: str,
        top_n: int = 10,
        score_type: str = "core"
    ) -> List[Dict[str, Any]]:
        """
        在指定行业内排名股票
        
        Args:
            industry_name: 行业名称
            top_n: 返回前 N 名
            
        Returns:
            排名后的股票列表
        """
        if self.provider is None:
            return []
        
        try:
            # 获取行业成分股
            stocks = self.provider.get_stock_list_by_industry(industry_name)
            
            if not stocks:
                logger.warning(f"No stocks found for industry: {industry_name}")
                return []
            
            # 计算行业统计（用于相对评分）
            industry_stats = self._calculate_industry_stats(stocks)
            
            # 对每只股票评分
            scored_stocks = []
            for stock in stocks:
                symbol = stock.get("symbol", "")
                if not symbol:
                    continue
                
                score_data = self.score_stock(symbol, industry_stats, score_type=score_type)
                if "error" not in score_data:
                    scored_stocks.append(score_data)
            
            # 按综合得分排序
            scored_stocks.sort(key=lambda x: x.get("total_score", 0), reverse=True)
            
            # 添加排名
            for idx, stock in enumerate(scored_stocks[:top_n], 1):
                stock["rank"] = idx
                stock["industry"] = industry_name
            
            return scored_stocks[:top_n]
            
        except Exception as e:
            logger.error(f"Error ranking stocks in {industry_name}: {e}")
            return []
    
    def _quick_score(
        self,
        stock_data: Dict[str, Any],
        industry_stats: Dict = None,
        score_type: str = "core"
    ) -> Dict[str, Any]:
        """
        快速评分（使用现有行情数据，与 score_stock 共用统一评分体系）
        
        快速评分无法获取 ROE/增速等财务数据，相关维度给中性分。
        
        Args:
            stock_data: 股票数据（来自 get_stock_list_by_industry）
            industry_stats: 行业统计
            
        Returns:
            评分结果
        """
        symbol = stock_data.get("symbol", "")
        name = stock_data.get("name", "")
        market_cap = stock_data.get("market_cap", 0)
        pe_ratio = stock_data.get("pe_ratio", 0)
        change_pct = stock_data.get("change_pct", 0)
        amount = stock_data.get("amount", 0)
        net_inflow_ratio = stock_data.get("net_inflow_ratio", 0)
        
        # 构建统一的 raw_data 格式
        raw_data = {
            "market_cap": market_cap,
            "pe_ttm": pe_ratio,
            "pe_ratio": pe_ratio,
            "roe": None,          # 快速评分无财务数据，使用中性分
            "revenue_yoy": None,
            "profit_yoy": None,
            "change_pct": change_pct,
            "amount": amount,
            "turnover": 0,
            "net_inflow_ratio": net_inflow_ratio,
        }
        
        # 使用统一评分逻辑
        dimension_scores = self._calculate_dimension_scores(raw_data, industry_stats, score_type=score_type)
        
        total_score = self._calculate_total_score(dimension_scores, raw_data, score_type=score_type)
        
        return {
            "symbol": symbol,
            "name": name,
            "total_score": round(total_score, 2),
            "market_cap": market_cap,
            "pe_ratio": pe_ratio,
            "change_pct": change_pct,
            "dimension_scores": dimension_scores,
        }

    def calculate_industry_stats(self, stocks: List[Dict]) -> Dict[str, Any]:
        """公开的行业统计计算入口，供路由层复用快速评分。"""
        return self._calculate_industry_stats(stocks)

    def score_stock_from_industry_snapshot(
        self,
        stock_data: Dict[str, Any],
        industry_stats: Dict = None,
        score_type: str = "core"
    ) -> Dict[str, Any]:
        """使用行业快照数据对个股做轻量评分。"""
        return self._quick_score(stock_data, industry_stats, score_type=score_type)
    
    def _calculate_industry_stats(self, stocks: List[Dict]) -> Dict[str, Any]:
        """
        计算行业统计数据
        
        Args:
            stocks: 行业成分股列表
            
        Returns:
            行业统计
        """
        if not stocks:
            return {}
        
        market_caps = [s.get("market_cap", 0) for s in stocks if s.get("market_cap", 0) > 0]
        pe_ratios = [s.get("pe_ratio", 0) for s in stocks if 0 < s.get("pe_ratio", 0) < 500]
        
        return {
            "count": len(stocks),
            "avg_market_cap": np.mean(market_caps) if market_caps else 0,
            "median_market_cap": np.median(market_caps) if market_caps else 0,
            "avg_pe": np.mean(pe_ratios) if pe_ratios else 0,
            "median_pe": np.median(pe_ratios) if pe_ratios else 0,
        }
    
    def get_leader_stocks(
        self,
        hot_industries: List[str],
        top_per_industry: int = 5,
        score_type: str = "core"
    ) -> List[Dict[str, Any]]:
        """
        从热门行业中遴选龙头股
        
        Args:
            hot_industries: 热门行业列表
            top_per_industry: 每个行业选取的龙头数量
            
        Returns:
            龙头股列表
        """
        all_leaders = []
        
        for industry in hot_industries:
            try:
                leaders = self.rank_stocks_in_industry(industry, top_n=top_per_industry, score_type=score_type)
                all_leaders.extend(leaders)
            except Exception as e:
                logger.error(f"Error getting leaders for {industry}: {e}")
                continue
        
        # 按综合得分全局排序
        all_leaders.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        
        # 更新全局排名
        for idx, leader in enumerate(all_leaders, 1):
            leader["global_rank"] = idx
        
        return all_leaders
    
    def get_leader_detail(self, symbol: str, score_type: str = "core") -> Dict[str, Any]:
        """
        获取龙头股详细分析
        
        Args:
            symbol: 股票代码
            
        Returns:
            详细分析结果
        """
        if self.provider is None:
            return {"symbol": symbol, "error": "Data provider not set"}
        
        try:
            # 并发获取评分和 K 线数据，进一步压榨加载速度
            import concurrent.futures
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=60)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future_score = executor.submit(self.score_stock, symbol, None, None, score_type)
                future_hist = executor.submit(self.provider.get_historical_data, symbol, start_date, end_date)
                future_quote = (
                    executor.submit(self.provider.get_latest_quote, symbol)
                    if hasattr(self.provider, "get_latest_quote")
                    else None
                )
                
                score_result = future_score.result()
                hist_data = future_hist.result()
                quote_data = future_quote.result() if future_quote is not None else {}

            if "error" in score_result:
                return score_result

            quote_snapshot = self._normalize_quote_snapshot(quote_data)
            if quote_snapshot:
                raw_data = score_result.setdefault("raw_data", {})
                for key, value in quote_snapshot.items():
                    if value not in (None, ""):
                        raw_data[key] = value
            
            # 计算技术指标
            tech_analysis = {}
            if not hist_data.empty:
                closes = hist_data["close"].values
                
                # 计算简单移动平均
                if len(closes) >= 20:
                    tech_analysis["ma5"] = round(closes[-5:].mean(), 2)
                    tech_analysis["ma20"] = round(closes[-20:].mean(), 2)
                    
                # 计算波动率（60日年化）
                if len(closes) >= 10:
                    returns = pd.Series(closes).pct_change().dropna()
                    tech_analysis["volatility_60d"] = round(returns.std() * np.sqrt(252) * 100, 2)
                
                # 最新价位
                tech_analysis["latest_close"] = round(closes[-1], 2)
                tech_analysis["high_60d"] = round(closes.max(), 2)
                tech_analysis["low_60d"] = round(closes.min(), 2)
            
            return {
                **score_result,
                "technical_analysis": tech_analysis,
                "price_data": (
                    hist_data.tail(30)
                    .reset_index()
                    .assign(date=lambda df: df["date"].dt.strftime("%Y-%m-%d") if "date" in df.columns else df.index)
                    .to_dict(orient="records")
                ) if not hist_data.empty else [],
            }
            
        except Exception as e:
            logger.error(f"Error getting leader detail for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}
    
    def optimize_weights(
        self,
        historical_returns: pd.DataFrame,
        target: str = "total_return"
    ) -> Dict[str, float]:
        """
        基于历史表现优化权重参数
        
        Args:
            historical_returns: 历史收益数据
            target: 优化目标 ("total_return" | "sharpe" | "max_drawdown")
            
        Returns:
            优化后的权重
        """
        # 简单实现：使用网格搜索
        # 实际应用中可以使用更复杂的优化算法（如遗传算法、贝叶斯优化）
        
        best_weights = self.weights.copy()
        best_score = float('-inf')
        
        # 生成权重组合
        weight_options = [0.1, 0.15, 0.2, 0.25, 0.3]
        
        for mc in weight_options:
            for roe in weight_options:
                for rg in weight_options:
                    for pg in weight_options:
                        remaining = 1 - mc - roe - rg - pg
                        if remaining < 0:
                            continue
                        
                        test_weights = {
                            "market_cap": mc,
                            "roe": roe,
                            "revenue_growth": rg,
                            "profit_growth": pg,
                            "volatility": -remaining * 0.5,
                            "liquidity": remaining * 0.5,
                        }
                        
                        # 评估这组权重的表现
                        # （简化版：这里需要实际的回测逻辑）
                        score = self._evaluate_weights(test_weights, historical_returns, target)
                        
                        if score > best_score:
                            best_score = score
                            best_weights = test_weights
        
        logger.info(f"Optimized weights: {best_weights}, score: {best_score}")
        return best_weights
    
    def _evaluate_weights(
        self,
        weights: Dict[str, float],
        historical_returns: pd.DataFrame,
        target: str
    ) -> float:
        """基于历史因子与未来收益评估权重组合表现。"""
        if historical_returns is None or historical_returns.empty:
            return float("-inf")

        df = historical_returns.copy()
        candidate_target_cols = [
            target,
            "forward_return",
            "future_return",
            "next_return",
            "total_return",
            "return",
        ]
        target_col = next((column for column in candidate_target_cols if column in df.columns), None)
        if not target_col:
            return float("-inf")

        factor_aliases = {
            "market_cap": ["market_cap", "market_cap_score"],
            "roe": ["roe", "profitability", "profitability_score"],
            "revenue_growth": ["revenue_growth", "growth", "growth_score"],
            "profit_growth": ["profit_growth", "momentum", "momentum_score"],
            "volatility": ["volatility", "volatility_score"],
            "liquidity": ["liquidity", "activity", "activity_score"],
        }

        score = pd.Series(0.0, index=df.index, dtype=float)
        used_factor = False

        for weight_key, weight in weights.items():
            factor_col = next((column for column in factor_aliases.get(weight_key, []) if column in df.columns), None)
            if not factor_col:
                continue
            factor_values = pd.to_numeric(df[factor_col], errors="coerce")
            if factor_values.dropna().empty:
                continue
            mean = factor_values.mean()
            std = factor_values.std(ddof=0) or 1.0
            standardized = ((factor_values - mean) / std).fillna(0.0)
            score += standardized * float(weight)
            used_factor = True

        if not used_factor:
            return float("-inf")

        target_values = pd.to_numeric(df[target_col], errors="coerce").fillna(0.0)
        score_df = pd.DataFrame({
            "score": score,
            "target": target_values,
            "date": df["date"] if "date" in df.columns else "all",
        })

        bucket_returns = []
        for _, group in score_df.groupby("date"):
            if group.empty:
                continue
            threshold = group["score"].quantile(0.8)
            selected = group[group["score"] >= threshold]
            if selected.empty:
                continue
            bucket_returns.append(float(selected["target"].mean()))

        if not bucket_returns:
            return float("-inf")

        returns = pd.Series(bucket_returns, dtype=float)
        mean_return = float(returns.mean())
        std_return = float(returns.std(ddof=0) or 0.0)
        equity_curve = (1 + returns).cumprod()
        running_peak = equity_curve.cummax()
        drawdown = ((equity_curve / running_peak) - 1).min() if not equity_curve.empty else 0.0

        if target == "sharpe":
            return mean_return / std_return if std_return > 0 else float("-inf")
        if target == "max_drawdown":
            return -float(drawdown)
        return mean_return
