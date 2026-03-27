"""
另类数据实体统一。

把公司名、ticker、主题标签、商品别名收敛成统一实体，
便于做证据去重、聚合和后续研究引用。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


ENTITY_ALIASES: Dict[str, Dict[str, Any]] = {
    "NVDA": {
        "entity_type": "company",
        "aliases": ["nvda", "nvidia", "英伟达"],
    },
    "TSM": {
        "entity_type": "company",
        "aliases": ["tsm", "tsmc", "台积电"],
    },
    "BABA": {
        "entity_type": "company",
        "aliases": ["baba", "alibaba", "阿里", "阿里巴巴"],
    },
    "BIDU": {
        "entity_type": "company",
        "aliases": ["bidu", "baidu", "百度"],
    },
    "0700.HK": {
        "entity_type": "company",
        "aliases": ["0700.hk", "tencent", "腾讯"],
    },
    "HUAWEI": {
        "entity_type": "company",
        "aliases": ["华为", "huawei"],
    },
    "BYTEDANCE": {
        "entity_type": "company",
        "aliases": ["字节", "字节跳动", "bytedance"],
    },
    "AI_COMPUTE": {
        "entity_type": "theme",
        "aliases": ["ai算力", "算力", "智算", "数据中心", "gpu", "人工智能"],
    },
    "SEMICONDUCTOR": {
        "entity_type": "theme",
        "aliases": ["半导体", "芯片", "集成电路", "晶圆"],
    },
    "GRID": {
        "entity_type": "theme",
        "aliases": ["电网", "特高压", "输电", "配电", "变压器"],
    },
    "NUCLEAR": {
        "entity_type": "theme",
        "aliases": ["核电", "核能"],
    },
    "SOLAR": {
        "entity_type": "theme",
        "aliases": ["光伏", "太阳能", "组件", "逆变器"],
    },
    "WIND": {
        "entity_type": "theme",
        "aliases": ["风电", "风机", "海上风电"],
    },
    "STORAGE": {
        "entity_type": "theme",
        "aliases": ["储能", "抽水蓄能", "电池储能"],
    },
    "EV": {
        "entity_type": "theme",
        "aliases": ["新能源汽车", "电动车", "动力电池", "充电桩"],
    },
    "COPPER": {
        "entity_type": "commodity",
        "aliases": ["copper", "铜", "hg=f"],
    },
    "GOLD": {
        "entity_type": "commodity",
        "aliases": ["gold", "黄金", "gc=f"],
    },
    "WTI": {
        "entity_type": "commodity",
        "aliases": ["wti", "原油", "cl=f"],
    },
}


def resolve_entity(raw_value: Any = None, tags: Iterable[str] | None = None, headline: str = "") -> Dict[str, Any]:
    raw = raw_value if isinstance(raw_value, dict) else {}
    candidates = [
        str(headline or ""),
        str(raw.get("title", "")),
        str(raw.get("company", "")),
        str(raw.get("ticker", "")),
        str(raw.get("industry", "")),
        str(raw.get("industry_id", "")),
        str(raw.get("source_name", "")),
        " ".join([str(tag) for tag in (tags or []) if tag]),
    ]
    haystack = " ".join([item.strip().lower() for item in candidates if item and item.strip()])

    for canonical, config in ENTITY_ALIASES.items():
        aliases = [item.lower() for item in config.get("aliases", [])]
        if any(alias and alias in haystack for alias in aliases):
            return {
                "canonical": canonical,
                "entity_type": config.get("entity_type", "unknown"),
                "aliases": config.get("aliases", []),
            }

    fallback = str(raw.get("company") or raw.get("ticker") or raw.get("industry") or raw.get("industry_id") or "").strip()
    if fallback:
        return {
            "canonical": fallback.upper() if fallback.isascii() else fallback,
            "entity_type": "unknown",
            "aliases": [fallback],
        }

    return {
        "canonical": "",
        "entity_type": "",
        "aliases": [],
    }


def aggregate_entities(evidence_items: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for item in evidence_items:
        entity = item.get("canonical_entity") or ""
        if not entity:
            continue
        bucket = buckets.setdefault(
            entity,
            {
                "entity": entity,
                "entity_type": item.get("entity_type", ""),
                "count": 0,
                "latest_timestamp": item.get("timestamp", ""),
            },
        )
        bucket["count"] += 1
        if str(item.get("timestamp", "")) > str(bucket.get("latest_timestamp", "")):
            bucket["latest_timestamp"] = item.get("timestamp", "")

    return sorted(
        buckets.values(),
        key=lambda item: (-int(item.get("count", 0)), str(item.get("entity", ""))),
    )[:limit]
