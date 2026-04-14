"""First-class people-layer alternative data provider."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..base_alt_provider import AltDataCategory, AltDataRecord, BaseAltDataProvider
from ..supply_chain.hiring_tracker import TRACKED_COMPANIES
from .executive_profile import EXECUTIVE_PROFILE_CATALOG, ExecutiveProfileProvider
from .insider_flow import INSIDER_FLOW_CATALOG, InsiderFlowProvider
from .people_signal import PeopleSignalAnalyzer, _curated_hiring_signal, _resolve_company_id


def _symbol_scope(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if normalized.endswith(".HK"):
        return "hk_equity"
    if normalized:
        return "us_or_adr_equity"
    return "unscoped"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_company_universe() -> List[Dict[str, Any]]:
    universe: Dict[str, Dict[str, Any]] = {}
    for company_id, meta in TRACKED_COMPANIES.items():
        ticker = str(meta.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        universe[ticker] = {
            "symbol": ticker,
            "company_name": meta.get("name", ticker),
            "sector": meta.get("sector", ""),
            "company_id": company_id,
            "entity_scope": _symbol_scope(ticker),
        }

    for ticker in sorted(set(EXECUTIVE_PROFILE_CATALOG) | set(INSIDER_FLOW_CATALOG)):
        universe.setdefault(
            ticker,
            {
                "symbol": ticker,
                "company_name": ticker,
                "sector": "",
                "company_id": _resolve_company_id(ticker) or "",
                "entity_scope": _symbol_scope(ticker),
            },
        )

    return list(universe.values())


def _executive_source_meta(symbol: str) -> Dict[str, Any]:
    normalized = str(symbol or "").strip().upper()
    if normalized in EXECUTIVE_PROFILE_CATALOG:
        return {
            "source_mode": "curated",
            "fallback_reason": "live_proxy_or_def14a_not_connected",
            "lag_days": 21,
            "coverage": 0.82,
            "source_reference": (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={normalized}&owner=exclude&count=40"
                if not normalized.endswith(".HK")
                else f"https://www.hkexnews.hk/sdw/search/searchsdw.aspx"
            ),
        }
    return {
        "source_mode": "curated",
        "fallback_reason": "company_governance_profile_unavailable",
        "lag_days": 45,
        "coverage": 0.48,
        "source_reference": "",
    }


def _insider_source_meta(symbol: str) -> Dict[str, Any]:
    normalized = str(symbol or "").strip().upper()
    if normalized in INSIDER_FLOW_CATALOG:
        return {
            "source_mode": "curated",
            "fallback_reason": "live_form4_or_hkex_feed_not_connected",
            "lag_days": 7,
            "coverage": 0.74,
            "source_reference": (
                "https://www.sec.gov/edgar/search/"
                if not normalized.endswith(".HK")
                else "https://di.hkex.com.hk/di/NSAllFormDateList.aspx"
            ),
        }
    return {
        "source_mode": "curated",
        "fallback_reason": "insider_feed_unavailable",
        "lag_days": 30,
        "coverage": 0.36,
        "source_reference": "",
    }


def _hiring_source_meta(symbol: str) -> Dict[str, Any]:
    company_id = _resolve_company_id(symbol)
    curated = _curated_hiring_signal(symbol)
    if company_id:
        return {
            "source_mode": "proxy",
            "fallback_reason": "",
            "lag_days": 3,
            "coverage": 0.76,
            "source_reference": f"hiring_tracker:{company_id}",
        }
    if curated:
        return {
            "source_mode": "curated",
            "fallback_reason": "live_job_board_signal_not_connected",
            "lag_days": 14,
            "coverage": 0.55,
            "source_reference": "curated_hiring_profiles",
        }
    return {
        "source_mode": "curated",
        "fallback_reason": "hiring_signal_unavailable",
        "lag_days": 45,
        "coverage": 0.22,
        "source_reference": "",
    }


class PeopleLayerProvider(BaseAltDataProvider):
    """Formal people-layer provider for macro and pricing research."""

    name = "people_layer"
    category = AltDataCategory.EXECUTIVE_GOVERNANCE
    update_interval = 6 * 3600

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        analyzer: Optional[PeopleSignalAnalyzer] = None,
        executive_provider: Optional[ExecutiveProfileProvider] = None,
        insider_provider: Optional[InsiderFlowProvider] = None,
    ):
        super().__init__(config)
        self.executive_provider = executive_provider or ExecutiveProfileProvider()
        self.insider_provider = insider_provider or InsiderFlowProvider()
        self.analyzer = analyzer or PeopleSignalAnalyzer(
            executive_provider=self.executive_provider,
            insider_provider=self.insider_provider,
        )

    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        requested_symbols = kwargs.get("symbols") or []
        universe = _build_company_universe()
        if requested_symbols:
            normalized = {str(symbol or "").strip().upper() for symbol in requested_symbols}
            universe = [item for item in universe if item["symbol"] in normalized]
        return universe

    def parse(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        parsed: List[Dict[str, Any]] = []
        for item in raw_data:
            symbol = item["symbol"]
            profile = self.analyzer.analyze(
                symbol,
                item.get("company_name", symbol),
                item.get("sector", ""),
            )
            parsed.append(
                {
                    **item,
                    "profile": profile,
                    "executive_source": _executive_source_meta(symbol),
                    "insider_source": _insider_source_meta(symbol),
                    "hiring_source": _hiring_source_meta(symbol),
                }
            )
        return parsed

    def normalize(self, parsed_data: List[Dict[str, Any]]) -> List[AltDataRecord]:
        now = datetime.now()
        records: List[AltDataRecord] = []
        for item in parsed_data:
            symbol = item["symbol"]
            profile = item["profile"]
            executive = profile.get("executive_profile", {}) or {}
            insider = profile.get("insider_flow", {}) or {}
            hiring = profile.get("hiring_signal", {}) or {}
            entity_scope = item.get("entity_scope") or _symbol_scope(symbol)

            executive_meta = item["executive_source"]
            insider_meta = item["insider_source"]
            hiring_meta = item["hiring_source"]

            executive_score = max(
                -1.0,
                min(
                    1.0,
                    _safe_float(executive.get("governance_risk")) * 0.65
                    + _safe_float(executive.get("capital_markets_pressure")) * 0.25
                    - _safe_float(executive.get("technical_authority_score")) * 0.2,
                ),
            )
            insider_score = max(
                -1.0,
                min(1.0, -_safe_float(insider.get("conviction_score"))),
            )
            hiring_score = max(
                -1.0,
                min(
                    1.0,
                    (_safe_float(hiring.get("dilution_ratio")) - 1.0) / 1.6,
                ),
            )

            base_meta = {
                "symbol": symbol,
                "company_name": profile.get("company_name", symbol),
                "entity_scope": entity_scope,
                "people_fragility_score": profile.get("people_fragility_score", 0.0),
                "people_quality_score": profile.get("people_quality_score", 0.0),
                "risk_level": profile.get("risk_level", "medium"),
                "stance": profile.get("stance", "balanced"),
            }

            records.append(
                AltDataRecord(
                    timestamp=now,
                    source="people_layer:executive_governance",
                    category=AltDataCategory.EXECUTIVE_GOVERNANCE,
                    raw_value={
                        "symbol": symbol,
                        "company": profile.get("company_name", symbol),
                        "technical_authority_score": executive.get("technical_authority_score", 0.0),
                        "capital_markets_pressure": executive.get("capital_markets_pressure", 0.0),
                        "governance_risk": executive.get("governance_risk", 0.0),
                        "leadership_balance": executive.get("leadership_balance", ""),
                        "summary": executive.get("summary", ""),
                    },
                    normalized_score=round(executive_score, 4),
                    confidence=_safe_float(executive.get("confidence"), 0.35),
                    metadata={**base_meta, **executive_meta},
                    tags=[symbol, entity_scope, "people_layer", "executive_governance"],
                )
            )
            records.append(
                AltDataRecord(
                    timestamp=now,
                    source="people_layer:insider_flow",
                    category=AltDataCategory.INSIDER_FLOW,
                    raw_value={
                        "symbol": symbol,
                        "company": profile.get("company_name", symbol),
                        "net_action": insider.get("net_action", "neutral"),
                        "net_value_musd": insider.get("net_value_musd", 0.0),
                        "conviction_score": insider.get("conviction_score", 0.0),
                        "summary": insider.get("summary", ""),
                    },
                    normalized_score=round(insider_score, 4),
                    confidence=_safe_float(insider.get("confidence"), 0.3),
                    metadata={**base_meta, **insider_meta},
                    tags=[symbol, entity_scope, "people_layer", "insider_flow"],
                )
            )
            records.append(
                AltDataRecord(
                    timestamp=now,
                    source="people_layer:hiring_structure",
                    category=AltDataCategory.HIRING,
                    raw_value={
                        "symbol": symbol,
                        "company": profile.get("company_name", symbol),
                        "signal": hiring.get("signal", "neutral"),
                        "signal_strength": hiring.get("signal_strength", 0.0),
                        "dilution_ratio": hiring.get("dilution_ratio", 0.0),
                        "tech_ratio": hiring.get("tech_ratio", 0.0),
                        "core_tech_ratio": hiring.get("core_tech_ratio", 0.0),
                        "marketing_ratio": hiring.get("marketing_ratio", 0.0),
                        "finance_compliance_ratio": hiring.get("finance_compliance_ratio", 0.0),
                        "alert": hiring.get("alert", False),
                        "summary": hiring.get("alert_message", ""),
                    },
                    normalized_score=round(hiring_score, 4),
                    confidence=max(0.25, _safe_float(profile.get("confidence"), 0.35) * 0.82),
                    metadata={**base_meta, **hiring_meta},
                    tags=[symbol, entity_scope, "people_layer", "hiring_structure"],
                )
            )

        return records

    def to_signal(self, records: List[AltDataRecord]) -> Dict[str, Any]:
        if not records:
            return super().to_signal(records)

        company_rows: Dict[str, Dict[str, Any]] = {}
        for record in records:
            meta = record.metadata or {}
            symbol = str(meta.get("symbol") or "")
            row = company_rows.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "company_name": meta.get("company_name", symbol),
                    "entity_scope": meta.get("entity_scope", "unscoped"),
                    "people_fragility_score": _safe_float(meta.get("people_fragility_score")),
                    "people_quality_score": _safe_float(meta.get("people_quality_score")),
                    "risk_level": meta.get("risk_level", "medium"),
                    "stance": meta.get("stance", "balanced"),
                    "evidence": {},
                    "source_modes": set(),
                },
            )
            category = record.category.value
            row["evidence"][category] = {
                "score": round(_safe_float(record.normalized_score), 4),
                "confidence": round(_safe_float(record.confidence), 4),
                "summary": (record.raw_value or {}).get("summary", "") if isinstance(record.raw_value, dict) else "",
                "source_mode": meta.get("source_mode", "curated"),
                "fallback_reason": meta.get("fallback_reason", ""),
                "lag_days": meta.get("lag_days"),
                "coverage": meta.get("coverage"),
            }
            row["source_modes"].add(meta.get("source_mode", "curated"))

        watchlist = sorted(
            company_rows.values(),
            key=lambda item: (
                _safe_float(item.get("people_fragility_score")),
                -_safe_float(item.get("people_quality_score")),
            ),
            reverse=True,
        )
        fragile_companies = [item for item in watchlist if item.get("risk_level") == "high"]
        supportive_companies = [item for item in watchlist if item.get("stance") == "supportive"]
        avg_fragility = sum(_safe_float(item.get("people_fragility_score")) for item in watchlist) / max(len(watchlist), 1)
        avg_quality = sum(_safe_float(item.get("people_quality_score")) for item in watchlist) / max(len(watchlist), 1)
        company_count = len(watchlist)

        source_mode_counts: Dict[str, int] = {}
        for record in records:
            source_mode = str((record.metadata or {}).get("source_mode") or "curated")
            source_mode_counts[source_mode] = source_mode_counts.get(source_mode, 0) + 1

        signal_score = max(
            -1.0,
            min(
                1.0,
                avg_fragility * 0.75
                + len(fragile_companies) / max(company_count, 1) * 0.25
                - avg_quality * 0.18,
            ),
        )
        confidence = min(
            0.94,
            sum(_safe_float(record.confidence) for record in records) / max(len(records), 1) * 0.88 + 0.12,
        )
        signal = 1 if signal_score >= 0.26 else -1 if signal_score <= -0.22 else 0

        return {
            "source": self.name,
            "category": self.category.value,
            "signal": signal,
            "strength": round(abs(signal_score), 4),
            "score": round(signal_score, 4),
            "confidence": round(confidence, 4),
            "record_count": len(records),
            "company_count": company_count,
            "watchlist": watchlist[:6],
            "fragile_companies": fragile_companies[:4],
            "supportive_companies": supportive_companies[:4],
            "fragile_company_count": len(fragile_companies),
            "supportive_company_count": len(supportive_companies),
            "avg_fragility_score": round(avg_fragility, 4),
            "avg_quality_score": round(avg_quality, 4),
            "entity_scope": {
                "tracked_companies": company_count,
                "markets": sorted({item.get("entity_scope", "unscoped") for item in watchlist}),
            },
            "source_mode_summary": {
                "counts": source_mode_counts,
                "dominant": max(source_mode_counts.items(), key=lambda item: item[1])[0] if source_mode_counts else "curated",
            },
            "latest_record": records[-1].to_dict(),
            "summary": (
                f"当前跟踪 {company_count} 家公司，人的维度脆弱度均值 {avg_fragility:.2f}，"
                f"高风险样本 {len(fragile_companies)} 家。"
            ),
            "timestamp": datetime.now().isoformat(),
        }
