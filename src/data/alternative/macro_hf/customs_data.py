"""
海关进出口高频数据

追踪关键品类的进出口数据变化趋势，
作为宏观经济和产业链景气度的高频代理指标。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base_alt_provider import AntiCrawlMixin

logger = logging.getLogger(__name__)

# 追踪的关键品类
TRACKED_CATEGORIES = {
    "semiconductors": {
        "name": "半导体/集成电路",
        "hs_codes": ["8541", "8542"],
        "keywords": ["集成电路", "芯片", "半导体器件"],
    },
    "rare_earth": {
        "name": "稀土",
        "hs_codes": ["2846"],
        "keywords": ["稀土", "稀土氧化物"],
    },
    "lithium": {
        "name": "锂矿/碳酸锂",
        "hs_codes": ["2836", "2825"],
        "keywords": ["碳酸锂", "氢氧化锂", "锂矿"],
    },
    "copper_ore": {
        "name": "铜矿/精铜",
        "hs_codes": ["2603", "7403"],
        "keywords": ["铜矿砂", "精炼铜"],
    },
    "crude_oil": {
        "name": "原油",
        "hs_codes": ["2709"],
        "keywords": ["原油", "石油原油"],
    },
    "ev_battery": {
        "name": "动力电池",
        "hs_codes": ["8507"],
        "keywords": ["锂电池", "动力电池", "蓄电池"],
    },
}


class CustomsDataProvider(AntiCrawlMixin):
    """
    海关进出口数据提供器

    追踪关键品类的进出口量和金额变化，
    用于判断：
    - 供需缺口（进口激增 → 国内供不应求）
    - 出口管制影响（出口骤降 → 制裁冲击）
    - 产业链转移信号

    Usage:
        customs = CustomsDataProvider()
        data = customs.get_category_data("semiconductors")
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._min_interval = self.config.get("min_request_interval", 3.0)
        self.logger = logger

    def get_category_data(
        self,
        category: str,
        months_back: int = 12,
    ) -> Dict[str, Any]:
        """
        获取指定品类的进出口数据

        Args:
            category: 品类代码
            months_back: 回溯月数

        Returns:
            进出口数据汇总
        """
        if category not in TRACKED_CATEGORIES:
            return {"error": f"不支持的品类: {category}"}

        cat_info = TRACKED_CATEGORIES[category]

        # 尝试从海关总署公开数据获取
        data = self._fetch_customs_data(category, months_back)

        return {
            "category": category,
            "name": cat_info["name"],
            "hs_codes": cat_info["hs_codes"],
            "data": data,
            "source": "customs_public",
            "source_mode": "official" if data and data.get("source_accessible") else "proxy",
            "timestamp": datetime.now().isoformat(),
        }

    def get_trade_balance_signal(
        self, category: str
    ) -> Dict[str, Any]:
        """
        生成贸易差额信号

        进口增速 > 出口增速 → 国内需求强 → 看多相关资产
        出口骤降 → 可能受制裁 → 看空出口依赖型企业
        """
        data = self.get_category_data(category)

        if data.get("error"):
            return {
                "category": category,
                "signal": 0,
                "confidence": 0,
                "reason": data["error"],
                "source_mode": "curated",
                "fallback_reason": data["error"],
                "lag_days": 30,
                "coverage": 0.0,
            }

        # 无数据时返回中性信号
        return {
            "category": category,
            "name": TRACKED_CATEGORIES.get(category, {}).get("name", category),
            "signal": 0,
            "confidence": 0.3,
            "reason": "数据暂不充足，待接入海关高频数据后增强",
            "source_mode": "proxy" if data and data.get("source_accessible") else "curated",
            "fallback_reason": "customs_series_not_parsed",
            "lag_days": 30,
            "coverage": 0.18 if data and data.get("source_accessible") else 0.08,
            "timestamp": datetime.now().isoformat(),
        }

    def get_all_categories_summary(self) -> Dict[str, Dict[str, Any]]:
        """获取所有品类的汇总"""
        summary = {}
        for cat_id in TRACKED_CATEGORIES:
            summary[cat_id] = self.get_trade_balance_signal(cat_id)
        return summary

    def _fetch_customs_data(
        self, category: str, months_back: int
    ) -> Optional[Dict[str, Any]]:
        """
        从海关总署网站获取数据

        当前为框架实现，待后续对接具体数据源
        """
        try:
            url = "http://www.customs.gov.cn/customs/302249/zfxxgk/2799825/302274/index.html"
            response = self._safe_request(url, timeout=15)

            if response:
                return {
                    "source_accessible": True,
                    "data_available": False,
                    "note": "海关数据源可达，需进一步解析",
                }

        except Exception as e:
            self.logger.debug(f"海关数据获取失败: {e}")

        return None
