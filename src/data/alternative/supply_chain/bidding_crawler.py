"""
招标网数据爬虫

抓取全国公共资源交易平台、中国招标投标公共服务平台的招标数据，
支持按产业链（光伏/风电/AI算力/核电）过滤，追踪产业投资前瞻信号。
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..base_alt_provider import AntiCrawlMixin

logger = logging.getLogger(__name__)

# 产业链关键词过滤器
INDUSTRY_FILTERS = {
    "solar": {
        "name": "光伏",
        "keywords": ["光伏", "太阳能", "硅片", "组件", "逆变器", "光伏电站", "分布式光伏"],
    },
    "wind": {
        "name": "风电",
        "keywords": ["风电", "风机", "风力发电", "海上风电", "风电场", "风电叶片"],
    },
    "nuclear": {
        "name": "核电",
        "keywords": ["核电", "核能", "核反应堆", "核电站", "核燃料", "核电机组"],
    },
    "ai_compute": {
        "name": "AI算力",
        "keywords": ["数据中心", "算力中心", "智算中心", "GPU", "服务器集群", "人工智能"],
    },
    "grid": {
        "name": "电网",
        "keywords": ["特高压", "变压器", "输电线路", "配电网", "电网改造", "智能电网"],
    },
    "storage": {
        "name": "储能",
        "keywords": ["储能", "电池储能", "抽水蓄能", "储能电站", "锂电池"],
    },
}


class BiddingCrawler(AntiCrawlMixin):
    """
    招标网数据爬虫

    抓取公共招标信息，按产业链分类统计，
    用于计算产业投资景气度的前瞻指标。

    Usage:
        crawler = BiddingCrawler()
        bids = crawler.search_bids(industry="solar", limit=20)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._min_interval = self.config.get("min_request_interval", 2.0)
        self.logger = logger

    def search_bids(
        self,
        industry: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        days_back: int = 30,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        搜索招标信息

        Args:
            industry: 产业类别（solar/wind/nuclear/ai_compute/grid/storage）
            keywords: 自定义搜索关键词
            days_back: 回溯天数
            limit: 最大返回数量

        Returns:
            招标信息列表
        """
        search_keywords = []
        
        if industry and industry in INDUSTRY_FILTERS:
            search_keywords = INDUSTRY_FILTERS[industry]["keywords"]
        elif keywords:
            search_keywords = keywords

        if not search_keywords:
            self.logger.warning("未指定搜索关键词")
            return []

        results = []
        for kw in search_keywords[:3]:  # 限制搜索词数量避免过多请求
            bids = self._search_single_keyword(kw, days_back=days_back)
            results.extend(bids)

        # 去重（按标题）
        seen_titles = set()
        unique_results = []
        for bid in results:
            title = bid.get("title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_results.append(bid)

        return unique_results[:limit]

    def get_industry_stats(
        self, days_back: int = 30
    ) -> Dict[str, Dict[str, Any]]:
        """
        获取各产业链的招标统计
        
        Returns:
            {industry_id: {count, total_amount, avg_amount, trend}}
        """
        stats = {}
        for industry_id, industry_info in INDUSTRY_FILTERS.items():
            bids = self.search_bids(industry=industry_id, days_back=days_back)
            
            total_amount = 0
            valid_amounts = []
            for bid in bids:
                amount = bid.get("amount", 0)
                if amount > 0:
                    total_amount += amount
                    valid_amounts.append(amount)

            stats[industry_id] = {
                "name": industry_info["name"],
                "count": len(bids),
                "total_amount": total_amount,
                "avg_amount": total_amount / len(valid_amounts) if valid_amounts else 0,
                "period_days": days_back,
            }

        return stats

    def _search_single_keyword(
        self, keyword: str, days_back: int = 30
    ) -> List[Dict[str, Any]]:
        """搜索单个关键词的招标信息"""
        try:
            # 尝试从公共资源交易平台获取
            url = f"http://deal.ggzy.gov.cn/ds/deal/dealList_search.jsp"
            params = {
                "SEARCH_KEYWORD": keyword,
                "TIMEBEGIN_SHOW": (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d"),
                "TIMEEND_SHOW": datetime.now().strftime("%Y-%m-%d"),
                "DEAL_CLASSIFY": "01",  # 工程建设
                "pageNo": 1,
                "pageSize": 20,
            }

            response = self._safe_request(url, params=params, timeout=15)
            if response:
                return self._parse_ggzy_response(response)

        except Exception as e:
            self.logger.debug(f"公共资源交易平台查询失败 ({keyword}): {e}")

        return []

    def _parse_ggzy_response(self, response) -> List[Dict[str, Any]]:
        """解析公共资源交易平台的响应"""
        bids = []
        try:
            data = response.json()
            items = data.get("data", [])
            
            for item in items:
                bid = {
                    "title": item.get("title", ""),
                    "type": item.get("dealClassifyName", ""),
                    "region": item.get("districtShow", ""),
                    "date": item.get("timeShow", ""),
                    "amount": self._extract_amount(item.get("title", "")),
                    "source": "公共资源交易平台",
                    "url": item.get("url", ""),
                }
                bids.append(bid)
        except Exception as e:
            self.logger.debug(f"解析招标响应失败: {e}")

        return bids

    @staticmethod
    def _extract_amount(text: str) -> float:
        """从文本中提取金额"""
        patterns = [
            r'(\d+(?:\.\d+)?)\s*亿',
            r'(\d+(?:\.\d+)?)\s*万',
            r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:元|RMB)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = float(match.group(1).replace(',', ''))
                if '亿' in text[match.start():match.end() + 2]:
                    return value * 1e8
                elif '万' in text[match.start():match.end() + 2]:
                    return value * 1e4
                return value
        return 0
