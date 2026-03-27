"""
官方政策 Feed 适配器

把不同机构的 RSS/Atom feed 解析方式收敛成统一接口，
让 PolicyCrawler 可以用同一条链路接入更多公开政策源。
"""

from __future__ import annotations

from typing import Any, Dict, List
from xml.etree import ElementTree


class OfficialFeedAdapter:
    """官方 Feed 解析适配器基类。"""

    def parse_items(
        self,
        root: ElementTree.Element,
        source: Any,
        source_id: str,
        limit: int,
        helpers: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        policies: List[Dict[str, Any]] = []
        for item in items[:limit]:
            title = helpers["feed_text"](item, "title")
            link = helpers["feed_link"](item)
            date_str = (
                helpers["feed_text"](item, "pubDate")
                or helpers["feed_text"](item, "updated")
                or helpers["feed_text"](item, "published")
            )
            summary = helpers["feed_text"](item, "description") or helpers["feed_text"](item, "summary")
            if not title:
                continue
            policies.append(
                {
                    "title": title.strip(),
                    "link": link,
                    "date": date_str.strip(),
                    "summary": helpers["strip_html"](summary)[:500],
                    "source": source.name,
                    "source_id": source_id,
                    "ingest_mode": "feed",
                    "feed_adapter": getattr(source, "feed_adapter", "generic_rss"),
                }
            )
        return policies


class GenericRssFeedAdapter(OfficialFeedAdapter):
    """默认 RSS/Atom 适配器。"""


class FedFeedAdapter(OfficialFeedAdapter):
    """美联储 feed，保留默认逻辑。"""


class EcbFeedAdapter(OfficialFeedAdapter):
    """欧洲央行 feed，保留默认逻辑。"""


class BoeFeedAdapter(OfficialFeedAdapter):
    """英国央行 feed，保留默认逻辑。"""


OFFICIAL_FEED_ADAPTERS = {
    "generic_rss": GenericRssFeedAdapter(),
    "fed_press": FedFeedAdapter(),
    "ecb_press": EcbFeedAdapter(),
    "boe_news": BoeFeedAdapter(),
}
