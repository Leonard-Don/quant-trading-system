"""Department-level policy execution and chaos provider."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any, Dict, List, Optional

from ..base_alt_provider import AltDataCategory, AltDataRecord, BaseAltDataProvider
from .policy_signals import PolicySignalProvider


DEPARTMENT_LABELS = {
    "ndrc": "发改委",
    "nea": "能源局",
    "miit": "工信部",
    "mof": "财政部",
    "pboc": "央行",
    "csrc": "证监会",
    "local": "地方政府",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _department_label(key: str) -> str:
    normalized = str(key or "").strip().lower()
    return DEPARTMENT_LABELS.get(normalized, normalized.upper() if normalized else "未知部门")


def _sign(value: float) -> int:
    if value > 0.12:
        return 1
    if value < -0.12:
        return -1
    return 0


def _reversal_count(values: List[float]) -> int:
    signs = [_sign(value) for value in values if _sign(value) != 0]
    if len(signs) < 2:
        return 0
    return sum(1 for previous, current in zip(signs, signs[1:]) if previous != current)


class PolicyExecutionProvider(BaseAltDataProvider):
    """Formal provider that derives department-level execution disorder from policy radar."""

    name = "policy_execution"
    category = AltDataCategory.POLICY_EXECUTION
    update_interval = 2 * 3600

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        policy_provider: Optional[PolicySignalProvider] = None,
    ):
        super().__init__(config)
        self.policy_provider = policy_provider or PolicySignalProvider(config=config)

    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        if self.policy_provider.needs_update() or not self.policy_provider.get_history(limit=1):
            self.policy_provider.run_pipeline(**kwargs)

        records = self.policy_provider.get_history(limit=200)
        return [record.to_dict() for record in records]

    def parse(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for payload in raw_data:
            raw = payload.get("raw_value") if isinstance(payload.get("raw_value"), dict) else {}
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            source = str(payload.get("source") or "")
            department = str(
                raw.get("department")
                or raw.get("agency")
                or raw.get("source_key")
                or (source.split(":", 1)[1] if ":" in source else source)
                or "unknown"
            ).strip().lower()
            grouped[department].append(
                {
                    "record_id": payload.get("record_id"),
                    "timestamp": payload.get("timestamp"),
                    "source": source,
                    "department": department,
                    "department_label": _department_label(department),
                    "title": str(raw.get("title") or ""),
                    "policy_shift": _safe_float(raw.get("policy_shift")),
                    "will_intensity": _safe_float(raw.get("will_intensity")),
                    "text_length": int(raw.get("text_length", 0) or 0),
                    "detail_status": str(metadata.get("detail_status") or "summary_only"),
                    "detail_quality": str(metadata.get("detail_quality") or "thin"),
                    "confidence": _safe_float(payload.get("confidence"), 0.5),
                    "tags": payload.get("tags") or [],
                }
            )

        parsed: List[Dict[str, Any]] = []
        for department, items in grouped.items():
            ordered = sorted(items, key=lambda item: str(item.get("timestamp") or ""))
            shifts = [_safe_float(item.get("policy_shift")) for item in ordered]
            reversals = _reversal_count(shifts)
            reversal_group = f"{department}:rev_{reversals}" if reversals else f"{department}:stable"
            full_text_ratio = sum(1 for item in ordered if item.get("detail_status") == "full_text") / max(len(ordered), 1)
            avg_shift = mean(abs(value) for value in shifts) if shifts else 0.0
            avg_will = mean(_safe_float(item.get("will_intensity")) for item in ordered) if ordered else 0.0
            latest = ordered[-1]
            latest_dt = datetime.fromisoformat(str(latest.get("timestamp")).replace("Z", "+00:00"))
            lag_days = max((datetime.now() - latest_dt.replace(tzinfo=None)).days, 0)
            if full_text_ratio < 0.35:
                execution_status = "thin_visibility"
            elif lag_days > 21:
                execution_status = "execution_lag"
            elif reversals >= 2:
                execution_status = "reversal_cluster"
            else:
                execution_status = "active"
            for index, item in enumerate(ordered, start=1):
                parsed.append(
                    {
                        **item,
                        "policy_id": item.get("record_id") or f"{department}-{index}",
                        "published_at": item.get("timestamp"),
                        "full_text_ratio": round(full_text_ratio, 4),
                        "reversal_group": reversal_group,
                        "execution_status": execution_status,
                        "reversal_count": reversals,
                        "avg_abs_policy_shift": round(avg_shift, 4),
                        "avg_will_intensity": round(avg_will, 4),
                        "lag_days": lag_days,
                    }
                )
        return parsed

    def normalize(self, parsed_data: List[Dict[str, Any]]) -> List[AltDataRecord]:
        records: List[AltDataRecord] = []
        for item in parsed_data:
            timestamp = datetime.fromisoformat(str(item.get("published_at")).replace("Z", "+00:00")).replace(tzinfo=None)
            chaos_score = max(
                0.0,
                min(
                    1.0,
                    item.get("avg_abs_policy_shift", 0.0) * 0.32
                    + min(1.0, item.get("reversal_count", 0) / 3.0) * 0.28
                    + item.get("avg_will_intensity", 0.0) * 0.18
                    + (1.0 - _safe_float(item.get("full_text_ratio"), 0.0)) * 0.14
                    + min(1.0, _safe_float(item.get("lag_days"), 0.0) / 30.0) * 0.08,
                ),
            )
            records.append(
                AltDataRecord(
                    timestamp=timestamp,
                    source=f"policy_execution:{item.get('department', 'unknown')}",
                    category=AltDataCategory.POLICY_EXECUTION,
                    raw_value={
                        "title": item.get("title", ""),
                        "department": item.get("department", ""),
                        "department_label": item.get("department_label", ""),
                        "policy_id": item.get("policy_id", ""),
                        "published_at": item.get("published_at", ""),
                        "policy_shift": item.get("policy_shift", 0.0),
                        "will_intensity": item.get("will_intensity", 0.0),
                        "full_text_ratio": item.get("full_text_ratio", 0.0),
                        "reversal_group": item.get("reversal_group", ""),
                        "execution_status": item.get("execution_status", ""),
                        "reversal_count": item.get("reversal_count", 0),
                        "lag_days": item.get("lag_days", 0),
                    },
                    normalized_score=round(chaos_score, 4),
                    confidence=max(0.3, _safe_float(item.get("confidence"), 0.5) * 0.9),
                    metadata={
                        "department": item.get("department", ""),
                        "department_label": item.get("department_label", ""),
                        "source_mode": "official" if item.get("department") in {"ndrc", "nea", "miit", "mof", "pboc", "csrc"} else "derived",
                        "fallback_reason": "" if item.get("department") in {"ndrc", "nea", "miit", "mof", "pboc", "csrc"} else "department_attribution_heuristic",
                        "lag_days": item.get("lag_days", 0),
                        "coverage": round(_safe_float(item.get("full_text_ratio"), 0.0), 4),
                        "entity_scope": "department_policy_execution",
                    },
                    tags=[
                        item.get("department", ""),
                        item.get("execution_status", ""),
                        "policy_execution",
                    ],
                )
            )
        return records

    def to_signal(self, records: List[AltDataRecord]) -> Dict[str, Any]:
        if not records:
            return super().to_signal(records)

        grouped: Dict[str, List[AltDataRecord]] = defaultdict(list)
        for record in records:
            grouped[str((record.metadata or {}).get("department") or "unknown")].append(record)

        department_board: List[Dict[str, Any]] = []
        source_mode_counts: Dict[str, int] = {}
        for department, items in grouped.items():
            ordered = sorted(items, key=lambda item: item.timestamp, reverse=True)
            latest = ordered[0]
            avg_chaos = sum(_safe_float(item.normalized_score) for item in items) / max(len(items), 1)
            full_text_ratio = mean(
                _safe_float((item.raw_value or {}).get("full_text_ratio"))
                for item in items
                if isinstance(item.raw_value, dict)
            )
            reversal_count = max(
                int((item.raw_value or {}).get("reversal_count", 0))
                for item in items
                if isinstance(item.raw_value, dict)
            ) if items else 0
            execution_status = str((latest.raw_value or {}).get("execution_status") or "active")
            department_board.append(
                {
                    "department": department,
                    "department_label": (latest.raw_value or {}).get("department_label", _department_label(department)),
                    "record_count": len(items),
                    "chaos_score": round(avg_chaos, 4),
                    "label": "chaotic" if avg_chaos >= 0.62 else "watch" if avg_chaos >= 0.38 else "stable",
                    "policy_reversal_count": reversal_count,
                    "full_text_ratio": round(full_text_ratio, 4),
                    "execution_status": execution_status,
                    "lag_days": int((latest.raw_value or {}).get("lag_days", 0) or 0),
                    "latest_title": (latest.raw_value or {}).get("title", ""),
                    "reason": (
                        f"反转 {reversal_count} 次，正文覆盖 {full_text_ratio:.2f}，"
                        f"执行状态 {execution_status}"
                    ),
                }
            )
            mode = str((latest.metadata or {}).get("source_mode") or "derived")
            source_mode_counts[mode] = source_mode_counts.get(mode, 0) + 1

        department_board.sort(key=lambda item: (item["chaos_score"], item["record_count"]), reverse=True)
        avg_score = sum(item["chaos_score"] for item in department_board) / max(len(department_board), 1)
        chaotic_departments = [item for item in department_board if item["label"] == "chaotic"]
        degraded_departments = [item for item in department_board if item["full_text_ratio"] < 0.35]
        lagging_departments = [item for item in department_board if item["lag_days"] > 21]
        signal = 1 if avg_score >= 0.28 else 0

        return {
            "source": self.name,
            "category": self.category.value,
            "signal": signal,
            "strength": round(avg_score, 4),
            "score": round(avg_score, 4),
            "confidence": round(
                sum(_safe_float(item.confidence) for item in records) / max(len(records), 1),
                4,
            ),
            "record_count": len(records),
            "department_count": len(department_board),
            "chaotic_department_count": len(chaotic_departments),
            "reversal_count": sum(item["policy_reversal_count"] for item in department_board),
            "department_board": department_board[:8],
            "top_departments": department_board[:5],
            "degraded_departments": degraded_departments[:5],
            "lagging_departments": lagging_departments[:5],
            "source_mode_summary": {
                "counts": source_mode_counts,
                "dominant": max(source_mode_counts.items(), key=lambda item: item[1])[0] if source_mode_counts else "derived",
            },
            "summary": (
                f"当前跟踪 {len(department_board)} 个部门，"
                f"{len(chaotic_departments)} 个进入高混乱区，平均混乱度 {avg_score:.2f}。"
            ),
            "latest_record": records[-1].to_dict(),
            "timestamp": datetime.now().isoformat(),
        }
