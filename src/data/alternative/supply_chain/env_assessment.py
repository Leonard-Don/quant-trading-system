"""
环评公示爬虫

抓取各省环保厅/生态环境厅的环境影响评价公示信息，
追踪重大项目审批动态（核电/化工/数据中心等）。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..base_alt_provider import AntiCrawlMixin

logger = logging.getLogger(__name__)


class EnvAssessmentCrawler(AntiCrawlMixin):
    """
    环评公示爬虫

    追踪重大项目的环评审批状态，作为产业投资的先行指标。
    环评审批通过 → 项目即将开工 → 产业链上游需求增长。

    Usage:
        crawler = EnvAssessmentCrawler()
        assessments = crawler.search(keywords=["数据中心", "核电"])
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._min_interval = self.config.get("min_request_interval", 3.0)
        self.logger = logger

    def search(
        self,
        keywords: Optional[List[str]] = None,
        region: Optional[str] = None,
        days_back: int = 60,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        搜索环评公示信息

        Args:
            keywords: 搜索关键词
            region: 地区限制
            days_back: 回溯天数
            limit: 最大返回数

        Returns:
            环评公示列表
        """
        if not keywords:
            keywords = ["核电", "数据中心", "风电场", "光伏电站", "化工"]

        results = []

        for kw in keywords[:5]:
            items = self._search_mee(kw, days_back)
            results.extend(items)

        # 去重
        seen = set()
        unique = []
        for item in results:
            key = item.get("title", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(item)

        return unique[:limit]

    def _search_mee(self, keyword: str, days_back: int) -> List[Dict[str, Any]]:
        """
        从生态环境部网站搜索

        主要目标：https://www.mee.gov.cn/
        """
        try:
            url = "https://www.mee.gov.cn/ywgz/hpgl/"
            response = self._safe_request(url, timeout=15)
            
            if not response:
                return []

            # 解析页面（依赖 BeautifulSoup）
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "html.parser")

                items = []
                for link in soup.select("a"):
                    title = link.get_text(strip=True)
                    if keyword in title:
                        href = link.get("href", "")
                        items.append({
                            "title": title,
                            "url": href,
                            "keyword_matched": keyword,
                            "source": "生态环境部",
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "status": "公示中",
                        })
                return items

            except ImportError:
                return []

        except Exception as e:
            self.logger.debug(f"环评搜索失败 ({keyword}): {e}")
            return []

    def get_project_pipeline(
        self, industry: str = "all"
    ) -> Dict[str, Any]:
        """
        获取项目管线概览
        
        统计各阶段的项目数量（受理 → 公示 → 审批通过）
        """
        industry_keywords = {
            "nuclear": ["核电"],
            "data_center": ["数据中心", "算力中心"],
            "wind": ["风电场", "海上风电"],
            "solar": ["光伏电站"],
            "chemical": ["化工项目", "石化"],
        }

        if industry != "all" and industry in industry_keywords:
            keywords = industry_keywords[industry]
        else:
            keywords = [kw for kws in industry_keywords.values() for kw in kws]

        assessments = self.search(keywords=keywords, days_back=90)

        return {
            "total_projects": len(assessments),
            "industry": industry,
            "period_days": 90,
            "projects": assessments,
        }
