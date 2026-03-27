"""
政策信号生成器

将 PolicyCrawler + PolicyNLPAnalyzer 组合为完整的
BaseAltDataProvider 管道，输出可消费的交易信号。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base_alt_provider import (
    AltDataCategory,
    AltDataRecord,
    BaseAltDataProvider,
)
from .policy_crawler import PolicyCrawler
from .policy_nlp import PolicyNLPAnalyzer

logger = logging.getLogger(__name__)


class PolicySignalProvider(BaseAltDataProvider):
    """
    政策信号提供器

    实现 BaseAltDataProvider 的四步管道：
    1. fetch: 通过 PolicyCrawler 抓取政策通稿
    2. parse: 通过 PolicyNLPAnalyzer 分析语义
    3. normalize: 转换为 AltDataRecord
    4. to_signal: 生成综合政策信号

    Usage:
        provider = PolicySignalProvider()
        signal = provider.run_pipeline(sources=["ndrc", "nea"])
    """

    name = "policy_radar"
    category = AltDataCategory.POLICY
    update_interval = 3600  # 每小时更新

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.crawler = PolicyCrawler(config=config)
        self.nlp = PolicyNLPAnalyzer(
            mode=self.config.get("nlp_mode", "local"),
            llm_provider=self.config.get("llm_provider", "openai"),
            api_key=self.config.get("llm_api_key", ""),
            config=config,
        )

    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """
        步骤一：抓取政策通稿

        kwargs:
            sources: 数据源列表（默认全部）
            limit: 每个源的最大抓取数
            days_back: 回溯天数
        """
        sources = kwargs.get("sources", list(self.crawler.sources.keys()))
        limit = kwargs.get("limit", 10)
        days_back = kwargs.get("days_back", 30)
        fetch_details = kwargs.get("fetch_details", True)
        detail_limit = kwargs.get("detail_limit", min(limit, 5))

        all_policies = []
        for source_id in sources:
            policies = self.crawler.crawl_source(
                source_id,
                limit=limit,
                days_back=days_back,
                fetch_details=fetch_details,
                detail_limit=detail_limit,
            )
            all_policies.extend(policies)

        return all_policies

    def parse(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        步骤二：NLP 语义分析

        对每条政策进行 policy_shift / will_intensity / industry_impact 分析
        """
        parsed = []
        for policy in raw_data:
            text = policy.get("text", policy.get("title", ""))
            title = policy.get("title", "")
            source = policy.get("source", "")

            analysis = self.nlp.analyze(text=text, title=title, source=source)
            parsed.append({
                **policy,
                **analysis,
                "detail_excerpt": policy.get("detail_excerpt", policy.get("summary", "")),
                "text_length": policy.get("text_length", len(text)),
            })

        return parsed

    def normalize(self, parsed_data: List[Dict[str, Any]]) -> List[AltDataRecord]:
        """
        步骤三：标准化为 AltDataRecord

        将 NLP 分析结果转换为统一数据格式
        """
        records = []
        for item in parsed_data:
            # 综合得分 = 政策转向度（主导） + 意志强烈度修正
            policy_shift = item.get("policy_shift", 0)
            will_intensity = item.get("will_intensity", 0)

            # 意志强烈度 > 70 时放大政策转向信号
            amplifier = 1.0 + max(0, (will_intensity - 50) / 100)
            normalized_score = max(-1.0, min(1.0, policy_shift * amplifier))

            # 提取产业标签
            tags = []
            industry_impact = item.get("industry_impact", {})
            for industry, details in industry_impact.items():
                if isinstance(details, dict) and details.get("impact") != "neutral":
                    tags.append(industry)

            # 解析日期
            date_str = item.get("date", "")
            try:
                timestamp = self.crawler._parse_date(date_str)
            except Exception:
                timestamp = datetime.now()

            record = AltDataRecord(
                timestamp=timestamp,
                source=f"policy_radar:{item.get('source_id', 'unknown')}",
                category=AltDataCategory.POLICY,
                raw_value={
                    "title": item.get("title", ""),
                    "policy_shift": policy_shift,
                    "will_intensity": will_intensity,
                    "industry_impact": industry_impact,
                    "summary": item.get("summary", ""),
                    "excerpt": item.get("detail_excerpt", item.get("summary", "")),
                    "text_length": int(item.get("text_length", 0) or 0),
                },
                normalized_score=normalized_score,
                confidence=item.get("confidence", 0.5),
                metadata={
                    "source_name": item.get("source", ""),
                    "link": item.get("link", ""),
                    "detail_url": item.get("detail_url", item.get("link", "")),
                    "detail_title": item.get("detail_title", item.get("title", "")),
                    "detail_excerpt": item.get("detail_excerpt", item.get("summary", "")),
                    "detail_status": item.get("detail_status", "summary_only"),
                    "detail_quality": item.get("detail_quality", "thin"),
                    "text_length": int(item.get("text_length", 0) or 0),
                    "ingest_mode": item.get("ingest_mode", "html"),
                    "analysis_mode": item.get("analysis_mode", "local"),
                },
                tags=tags,
            )
            records.append(record)

        return records

    def to_signal(self, records: List[AltDataRecord]) -> Dict[str, Any]:
        """
        步骤四：生成综合政策信号

        在默认加权平均的基础上，增加产业影响维度
        """
        # 基础信号
        base_signal = super().to_signal(records)

        # 汇总产业影响
        industry_summary = {}
        for record in records:
            raw = record.raw_value
            if isinstance(raw, dict):
                impacts = raw.get("industry_impact", {})
                for industry, details in impacts.items():
                    if isinstance(details, dict):
                        if industry not in industry_summary:
                            industry_summary[industry] = {
                                "scores": [],
                                "mentions": 0,
                            }
                        industry_summary[industry]["scores"].append(
                            details.get("score", 0)
                        )
                        industry_summary[industry]["mentions"] += details.get(
                            "mentions", 1
                        )

        # 计算产业平均影响
        industry_signals = {}
        for industry, data in industry_summary.items():
            avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
            industry_signals[industry] = {
                "avg_impact": round(avg_score, 4),
                "mentions": data["mentions"],
                "signal": "bullish" if avg_score > 0.2 else ("bearish" if avg_score < -0.2 else "neutral"),
            }

        base_signal["industry_signals"] = industry_signals
        base_signal["policy_count"] = len(records)
        base_signal["source_health"] = self._build_source_health(records)

        return base_signal

    @staticmethod
    def _build_source_health(records: List[AltDataRecord]) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, List[AltDataRecord]] = {}
        for record in records:
            source_key = record.source.split(":", 1)[-1] if ":" in record.source else record.source
            grouped.setdefault(source_key, []).append(record)

        source_health: Dict[str, Dict[str, Any]] = {}
        for source_key, items in grouped.items():
            text_lengths = [int(item.metadata.get("text_length", 0) or 0) for item in items]
            full_text_count = sum(1 for item in items if item.metadata.get("detail_status") == "full_text")
            ingest_modes = {}
            quality_counts = {}
            for item in items:
                ingest_mode = item.metadata.get("ingest_mode", "unknown")
                ingest_modes[ingest_mode] = ingest_modes.get(ingest_mode, 0) + 1
                quality = item.metadata.get("detail_quality", "unknown")
                quality_counts[quality] = quality_counts.get(quality, 0) + 1

            avg_text_length = sum(text_lengths) / len(text_lengths) if text_lengths else 0.0
            full_text_ratio = full_text_count / len(items) if items else 0.0
            if full_text_ratio >= 0.8 and avg_text_length >= 600:
                level = "healthy"
            elif full_text_ratio >= 0.5 and avg_text_length >= 200:
                level = "watch"
            else:
                level = "fragile"

            source_health[source_key] = {
                "record_count": len(items),
                "full_text_ratio": round(full_text_ratio, 4),
                "avg_text_length": round(avg_text_length, 2),
                "ingest_modes": ingest_modes,
                "detail_quality": quality_counts,
                "level": level,
            }

        return source_health
