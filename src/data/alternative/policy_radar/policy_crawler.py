"""
政策通稿爬虫

定向抓取发改委、国家能源局、美联储等机构的政策文件、通稿与公告。
提取政策标题、发布日期、全文文本，为下游 NLP 分析提供原始语料。
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from ..base_alt_provider import AntiCrawlMixin

logger = logging.getLogger(__name__)


class PolicySource:
    """政策数据源配置"""

    def __init__(
        self,
        name: str,
        base_url: str,
        list_url: str,
        encoding: str = "utf-8",
        language: str = "zh",
        selectors: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.base_url = base_url
        self.list_url = list_url
        self.encoding = encoding
        self.language = language
        self.selectors = selectors or {}


# ── 预配置的政策源 ──

POLICY_SOURCES = {
    "ndrc": PolicySource(
        name="国家发改委",
        base_url="https://www.ndrc.gov.cn",
        list_url="https://www.ndrc.gov.cn/xxgk/zcfb/",
        encoding="utf-8",
        language="zh",
        selectors={
            "list_container": ".list_con li",
            "title": "a",
            "date": "span",
            "link": "a",
        },
    ),
    "nea": PolicySource(
        name="国家能源局",
        base_url="https://www.nea.gov.cn",
        list_url="https://www.nea.gov.cn/policy/zc.htm",
        encoding="utf-8",
        language="zh",
        selectors={
            "list_container": ".list_con li",
            "title": "a",
            "date": "span",
            "link": "a",
        },
    ),
    "fed": PolicySource(
        name="美联储",
        base_url="https://www.federalreserve.gov",
        list_url="https://www.federalreserve.gov/newsevents/pressreleases.htm",
        encoding="utf-8",
        language="en",
        selectors={
            "list_container": ".row.ng-scope",
            "title": ".col-xs-9 a",
            "date": ".col-xs-3 time",
            "link": ".col-xs-9 a",
        },
    ),
}


class PolicyCrawler(AntiCrawlMixin):
    """
    政策通稿爬虫

    支持多政策源的自动抓取和结构化输出。

    Usage:
        crawler = PolicyCrawler()
        policies = crawler.crawl_source("ndrc", limit=20)
        for p in policies:
            print(f"[{p['date']}] {p['title']}")
    """

    def __init__(
        self,
        sources: Optional[Dict[str, PolicySource]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.sources = sources or POLICY_SOURCES
        self.config = config or {}
        self._min_interval = self.config.get("min_request_interval", 2.0)
        self.logger = logger

    def crawl_source(
        self,
        source_id: str,
        limit: int = 20,
        days_back: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        抓取指定政策源的文件列表

        Args:
            source_id: 数据源标识（ndrc/nea/fed）
            limit: 最大抓取数量
            days_back: 回溯天数

        Returns:
            政策文件列表
        """
        if source_id not in self.sources:
            self.logger.error(f"未知的政策源: {source_id}")
            return []

        source = self.sources[source_id]
        self.logger.info(f"[PolicyCrawler] 开始抓取 {source.name} ({source_id})")

        try:
            response = self._safe_request(source.list_url, timeout=30)
            if not response:
                self.logger.warning(f"无法访问 {source.name} 列表页面")
                return self._get_fallback_data(source_id, limit)

            if source.encoding:
                response.encoding = source.encoding

            if not HAS_BS4:
                self.logger.warning("BeautifulSoup4 未安装，使用 fallback 数据")
                return self._get_fallback_data(source_id, limit)

            soup = BeautifulSoup(response.text, "html.parser")
            policies = self._parse_list_page(soup, source)

            # 按日期过滤
            cutoff = datetime.now() - timedelta(days=days_back)
            policies = [
                p for p in policies
                if p.get("date") and self._parse_date(p["date"]) >= cutoff
            ]

            # 限制数量
            policies = policies[:limit]

            self.logger.info(f"[PolicyCrawler] {source.name} 获取到 {len(policies)} 条政策")
            return policies

        except Exception as e:
            self.logger.error(f"抓取 {source.name} 失败: {e}")
            return self._get_fallback_data(source_id, limit)

    def crawl_all_sources(
        self,
        limit_per_source: int = 10,
        days_back: int = 30,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        抓取所有配置的政策源

        Returns:
            {source_id: [policies]}
        """
        results = {}
        for source_id in self.sources:
            policies = self.crawl_source(source_id, limit_per_source, days_back)
            results[source_id] = policies
        return results

    def fetch_policy_detail(
        self,
        url: str,
        source_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        抓取政策文件详情页

        Args:
            url: 政策详情页 URL
            source_id: 数据源标识

        Returns:
            包含全文的政策详情字典
        """
        source = self.sources.get(source_id)
        if not source:
            return None

        try:
            full_url = url if url.startswith("http") else urljoin(source.base_url, url)
            response = self._safe_request(full_url, timeout=30)
            if not response:
                return None

            if source.encoding:
                response.encoding = source.encoding

            if not HAS_BS4:
                return {"url": full_url, "text": response.text[:5000]}

            soup = BeautifulSoup(response.text, "html.parser")

            # 尝试提取正文
            content_selectors = [
                ".TRS_Editor", ".article-content", ".content",
                "#UCAP-CONTENT", "article", ".detail_con",
            ]
            text = ""
            for sel in content_selectors:
                elem = soup.select_one(sel)
                if elem:
                    text = elem.get_text(strip=True, separator="\n")
                    break

            if not text:
                # 兜底：提取 body 文本
                body = soup.find("body")
                text = body.get_text(strip=True, separator="\n")[:5000] if body else ""

            return {
                "url": full_url,
                "title": soup.title.string if soup.title else "",
                "text": text,
                "text_length": len(text),
            }

        except Exception as e:
            self.logger.error(f"抓取政策详情失败 {url}: {e}")
            return None

    def _parse_list_page(
        self, soup: "BeautifulSoup", source: PolicySource
    ) -> List[Dict[str, Any]]:
        """解析列表页面"""
        policies = []
        sel = source.selectors

        container_sel = sel.get("list_container", "li")
        items = soup.select(container_sel)

        for item in items:
            try:
                # 标题
                title_elem = item.select_one(sel.get("title", "a"))
                title = title_elem.get_text(strip=True) if title_elem else ""

                # 链接
                link_elem = item.select_one(sel.get("link", "a"))
                link = link_elem.get("href", "") if link_elem else ""

                # 日期
                date_elem = item.select_one(sel.get("date", "span"))
                date_str = date_elem.get_text(strip=True) if date_elem else ""

                if title:
                    policies.append({
                        "title": title,
                        "link": link,
                        "date": date_str,
                        "source": source.name,
                        "source_id": next(
                            (k for k, v in self.sources.items() if v == source), ""
                        ),
                    })
            except Exception:
                continue

        return policies

    def _parse_date(self, date_str: str) -> datetime:
        """解析日期字符串"""
        date_str = date_str.strip().strip("[]（）()")
        formats = [
            "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
            "%Y年%m月%d日", "%m/%d/%Y", "%B %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # 尝试正则提取日期
        match = re.search(r"(\d{4})[-.年/](\d{1,2})[-.月/](\d{1,2})", date_str)
        if match:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))

        return datetime.now()

    def _get_fallback_data(
        self, source_id: str, limit: int
    ) -> List[Dict[str, Any]]:
        """
        返回结构化的空数据（在网络不可用时使用）

        这确保下游管道不会因为网络问题而完全中断。
        """
        self.logger.info(f"[PolicyCrawler] 使用 fallback 数据 for {source_id}")
        return []
