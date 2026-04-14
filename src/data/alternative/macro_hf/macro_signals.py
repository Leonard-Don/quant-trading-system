"""
全球宏观高频信号合成器。
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from ..base_alt_provider import AltDataCategory, AltDataRecord, BaseAltDataProvider
from .customs_data import CustomsDataProvider
from .lme_inventory import LMEInventoryProvider
from .port_congestion import PortCongestionProvider

logger = logging.getLogger(__name__)


class MacroHFSignalProvider(BaseAltDataProvider):
    """整合贸易、库存、物流三条宏观高频数据线。"""

    name = "macro_hf"
    category = AltDataCategory.COMMODITY_INVENTORY
    update_interval = 14400

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.customs = CustomsDataProvider(config=config)
        self.lme = LMEInventoryProvider(config=config)
        self.ports = PortCongestionProvider(config=config)

    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        metals = kwargs.get("metals", ["copper", "aluminium"])
        categories = kwargs.get(
            "categories",
            ["semiconductors", "copper_ore", "ev_battery"],
        )

        raw_data: List[Dict[str, Any]] = []

        for metal in metals:
            raw_data.append(
                {
                    "data_type": "inventory",
                    **self.lme.analyze_inventory_trend(metal),
                }
            )

        for category in categories:
            raw_data.append(
                {
                    "data_type": "customs",
                    **self.customs.get_trade_balance_signal(category),
                }
            )

        raw_data.append(
            {
                "data_type": "ports",
                **self.ports.get_global_congestion_index(),
            }
        )
        return raw_data

    def parse(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        parsed: List[Dict[str, Any]] = []
        for item in raw_data:
            data_type = item.get("data_type")
            if data_type == "inventory":
                parsed.append(
                    {
                        "type": "inventory",
                        "name": item.get("name", item.get("metal", "")),
                        "score": float(item.get("signal", 0)) * max(
                            0.2, float(item.get("confidence", 0.0))
                        ),
                        "confidence": float(item.get("confidence", 0.0)),
                        "trend": item.get("trend", "unknown"),
                        "source_mode": item.get("source_mode", "proxy"),
                        "fallback_reason": item.get("fallback_reason", ""),
                        "lag_days": item.get("lag_days"),
                        "coverage": item.get("coverage"),
                        "raw": item,
                    }
                )
            elif data_type == "customs":
                parsed.append(
                    {
                        "type": "customs",
                        "name": item.get("name", item.get("category", "")),
                        "score": float(item.get("signal", 0))
                        * max(0.2, float(item.get("confidence", 0.0))),
                        "confidence": float(item.get("confidence", 0.0)),
                        "reason": item.get("reason", ""),
                        "source_mode": item.get("source_mode", "proxy"),
                        "fallback_reason": item.get("fallback_reason", ""),
                        "lag_days": item.get("lag_days"),
                        "coverage": item.get("coverage"),
                        "raw": item,
                    }
                )
            elif data_type == "ports":
                global_index = float(item.get("global_index", 50.0))
                parsed.append(
                    {
                        "type": "ports",
                        "name": "global_ports",
                        "score": round((global_index - 50.0) / 50.0, 4),
                        "confidence": 0.45,
                        "status": item.get("status", "normal"),
                        "source_mode": item.get("source_mode", "proxy"),
                        "fallback_reason": item.get("fallback_reason", ""),
                        "lag_days": item.get("lag_days"),
                        "coverage": item.get("coverage"),
                        "raw": item,
                    }
                )
        return parsed

    def normalize(self, parsed_data: List[Dict[str, Any]]) -> List[AltDataRecord]:
        now = datetime.now()
        records: List[AltDataRecord] = []
        for item in parsed_data:
            item_type = item["type"]
            if item_type == "inventory":
                category = AltDataCategory.COMMODITY_INVENTORY
            elif item_type == "customs":
                category = AltDataCategory.CUSTOMS
            else:
                category = AltDataCategory.PORT_CONGESTION

            records.append(
                AltDataRecord(
                    timestamp=now,
                    source=f"macro_hf:{item_type}",
                    category=category,
                    raw_value=item["raw"],
                    normalized_score=max(-1.0, min(1.0, float(item["score"]))),
                    confidence=max(0.0, min(1.0, float(item["confidence"]))),
                    tags=[item.get("name", ""), item_type],
                    metadata={
                        "label": item.get("name", ""),
                        "source_mode": item.get("source_mode", "proxy"),
                        "fallback_reason": item.get("fallback_reason", ""),
                        "lag_days": item.get("lag_days"),
                        "coverage": item.get("coverage"),
                    },
                )
            )
        return records

    def to_signal(self, records: List[AltDataRecord]) -> Dict[str, Any]:
        signal = super().to_signal(records)
        dimensions = {
            "inventory": _average_score(records, AltDataCategory.COMMODITY_INVENTORY),
            "trade": _average_score(records, AltDataCategory.CUSTOMS),
            "logistics": _average_score(records, AltDataCategory.PORT_CONGESTION),
        }
        signal["dimensions"] = dimensions
        signal["macro_pressure"] = round(
            dimensions["inventory"]["score"] * 0.45
            + dimensions["trade"]["score"] * 0.35
            + dimensions["logistics"]["score"] * 0.20,
            4,
        )
        source_mode_counts: Dict[str, int] = {}
        for record in records:
            mode = str((record.metadata or {}).get("source_mode") or "proxy")
            source_mode_counts[mode] = source_mode_counts.get(mode, 0) + 1
        signal["source_mode_summary"] = {
            "counts": source_mode_counts,
            "dominant": max(source_mode_counts.items(), key=lambda item: item[1])[0] if source_mode_counts else "proxy",
        }
        return signal


def _average_score(records: List[AltDataRecord], category: AltDataCategory) -> Dict[str, Any]:
    scores = [record.normalized_score for record in records if record.category == category]
    return {
        "count": len(scores),
        "score": round(sum(scores) / len(scores), 4) if scores else 0.0,
    }
