"""
产业链信号合成

将招标数据、环评公示、招聘趋势三个维度的数据合成为
统一的 SupplyChainSignalProvider，遵循 BaseAltDataProvider 管道。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from ..base_alt_provider import (
    AltDataCategory,
    AltDataRecord,
    BaseAltDataProvider,
)
from .bidding_crawler import BiddingCrawler, INDUSTRY_FILTERS
from .env_assessment import EnvAssessmentCrawler
from .hiring_tracker import HiringTracker

logger = logging.getLogger(__name__)


class SupplyChainSignalProvider(BaseAltDataProvider):
    """
    产业链信号合成提供器

    整合三大数据源生成产业链景气度信号：
    - 招标数据 → 投资活跃度
    - 环评公示 → 项目管线密度
    - 招聘趋势 → 企业战略方向

    Usage:
        provider = SupplyChainSignalProvider()
        signal = provider.run_pipeline(industries=["solar", "ai_compute"])
    """

    name = "supply_chain"
    category = AltDataCategory.BIDDING
    update_interval = 7200  # 每2小时更新

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.bidding = BiddingCrawler(config=config)
        self.env = EnvAssessmentCrawler(config=config)
        self.hiring = HiringTracker(config=config)

    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """
        步骤一：从三个数据源抓取原始数据

        kwargs:
            industries: 要追踪的产业列表
            days_back: 回溯天数
        """
        industries = kwargs.get("industries", list(INDUSTRY_FILTERS.keys()))
        days_back = kwargs.get("days_back", 30)

        raw_data = []

        # 1. 招标数据
        for industry_id in industries:
            bids = self.bidding.search_bids(
                industry=industry_id, days_back=days_back, limit=20
            )
            for bid in bids:
                bid["data_type"] = "bidding"
                bid["industry_id"] = industry_id
                raw_data.append(bid)

        # 2. 环评数据
        env_keywords = []
        for ind_id in industries:
            if ind_id in INDUSTRY_FILTERS:
                env_keywords.extend(INDUSTRY_FILTERS[ind_id]["keywords"][:2])
        if env_keywords:
            assessments = self.env.search(
                keywords=env_keywords, days_back=days_back
            )
            for item in assessments:
                item["data_type"] = "env_assessment"
                raw_data.append(item)

        # 3. 招聘数据
        hiring_results = self.hiring.analyze_all_companies()
        for company_id, analysis in hiring_results.items():
            analysis["data_type"] = "hiring"
            analysis["company_id"] = company_id
            raw_data.append(analysis)

        return raw_data

    def parse(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        步骤二：解析和结构化

        按数据类型分别处理，提取关键信号
        """
        parsed = []

        for item in raw_data:
            data_type = item.get("data_type", "unknown")

            if data_type == "bidding":
                parsed.append({
                    "type": "bidding",
                    "industry": item.get("industry_id", "unknown"),
                    "title": item.get("title", ""),
                    "amount": item.get("amount", 0),
                    "date": item.get("date", ""),
                    "source": item.get("source", ""),
                    "score": 1.0 if item.get("amount", 0) > 0 else 0.5,
                })

            elif data_type == "env_assessment":
                parsed.append({
                    "type": "env_assessment",
                    "title": item.get("title", ""),
                    "status": item.get("status", ""),
                    "source": item.get("source", ""),
                    "score": 0.8,  # 环评出现即为正面信号
                })

            elif data_type == "hiring":
                signal_score = 0.0
                if item.get("signal") == "bullish":
                    signal_score = item.get("signal_strength", 0.3)
                elif item.get("signal") == "bearish":
                    signal_score = -item.get("signal_strength", 0.3)

                parsed.append({
                    "type": "hiring",
                    "company": item.get("company", ""),
                    "ticker": item.get("ticker"),
                    "dilution_ratio": item.get("key_ratios", {}).get("dilution_ratio", 0),
                    "signal": item.get("signal", "neutral"),
                    "score": signal_score,
                    "alert": item.get("alert", False),
                })

        return parsed

    def normalize(self, parsed_data: List[Dict[str, Any]]) -> List[AltDataRecord]:
        """
        步骤三：转换为 AltDataRecord
        """
        records = []
        now = datetime.now()

        for item in parsed_data:
            item_type = item.get("type", "unknown")

            if item_type == "bidding":
                cat = AltDataCategory.BIDDING
                score = min(1.0, item.get("score", 0.5))
                confidence = 0.6
            elif item_type == "env_assessment":
                cat = AltDataCategory.ENV_ASSESSMENT
                score = item.get("score", 0.5)
                confidence = 0.5
            elif item_type == "hiring":
                cat = AltDataCategory.HIRING
                score = item.get("score", 0)
                confidence = 0.7
            else:
                continue

            record = AltDataRecord(
                timestamp=now,
                source=f"supply_chain:{item_type}",
                category=cat,
                raw_value=item,
                normalized_score=score,
                confidence=confidence,
                tags=[item.get("industry", ""), item.get("company", "")],
            )
            records.append(record)

        return records

    def to_signal(self, records: List[AltDataRecord]) -> Dict[str, Any]:
        """
        步骤四：生成综合产业链信号

        从三个维度合成：投资活跃度 + 项目管线 + 人才结构
        """
        base_signal = super().to_signal(records)

        # 分维度统计
        bidding_scores = [r.normalized_score for r in records if r.category == AltDataCategory.BIDDING]
        env_scores = [r.normalized_score for r in records if r.category == AltDataCategory.ENV_ASSESSMENT]
        hiring_scores = [r.normalized_score for r in records if r.category == AltDataCategory.HIRING]

        dimensions = {
            "investment_activity": {
                "score": round(np.mean(bidding_scores), 4) if bidding_scores else 0,
                "count": len(bidding_scores),
                "label": "投资活跃度",
            },
            "project_pipeline": {
                "score": round(np.mean(env_scores), 4) if env_scores else 0,
                "count": len(env_scores),
                "label": "项目管线密度",
            },
            "talent_structure": {
                "score": round(np.mean(hiring_scores), 4) if hiring_scores else 0,
                "count": len(hiring_scores),
                "label": "人才结构信号",
            },
        }

        # 检测做空预警
        alerts = []
        for record in records:
            if isinstance(record.raw_value, dict) and record.raw_value.get("alert"):
                alerts.append({
                    "company": record.raw_value.get("company", ""),
                    "dilution_ratio": record.raw_value.get("dilution_ratio", 0),
                    "message": record.raw_value.get("alert_message", ""),
                })

        base_signal["dimensions"] = dimensions
        base_signal["alerts"] = alerts
        base_signal["alert_count"] = len(alerts)

        return base_signal
