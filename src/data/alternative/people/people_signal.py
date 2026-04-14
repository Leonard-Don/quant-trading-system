"""People-layer synthesis for pricing and macro mispricing research."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..supply_chain.hiring_tracker import HiringTracker, TRACKED_COMPANIES
from .executive_profile import ExecutiveProfileProvider
from .insider_flow import InsiderFlowProvider


CURATED_HIRING_SIGNALS: Dict[str, Dict[str, Any]] = {
    "NVDA": {
        "signal": "bullish",
        "signal_strength": 0.42,
        "alert": False,
        "key_ratios": {
            "tech_ratio": 0.61,
            "core_tech_ratio": 0.39,
            "marketing_ratio": 0.14,
            "finance_compliance_ratio": 0.11,
            "dilution_ratio": 0.64,
        },
        "alert_message": "",
    },
    "TSM": {
        "signal": "bullish",
        "signal_strength": 0.28,
        "alert": False,
        "key_ratios": {
            "tech_ratio": 0.54,
            "core_tech_ratio": 0.33,
            "marketing_ratio": 0.18,
            "finance_compliance_ratio": 0.12,
            "dilution_ratio": 0.91,
        },
        "alert_message": "",
    },
    "BABA": {
        "signal": "bearish",
        "signal_strength": 0.46,
        "alert": True,
        "key_ratios": {
            "tech_ratio": 0.29,
            "core_tech_ratio": 0.18,
            "marketing_ratio": 0.27,
            "finance_compliance_ratio": 0.21,
            "dilution_ratio": 1.72,
        },
        "alert_message": "⚠️ 阿里巴巴 技术高管稀释度 1.72 超过警戒线 1.5",
    },
    "BIDU": {
        "signal": "neutral",
        "signal_strength": 0.08,
        "alert": False,
        "key_ratios": {
            "tech_ratio": 0.41,
            "core_tech_ratio": 0.22,
            "marketing_ratio": 0.22,
            "finance_compliance_ratio": 0.17,
            "dilution_ratio": 1.05,
        },
        "alert_message": "",
    },
}


def _resolve_company_id(symbol: str) -> Optional[str]:
    normalized = str(symbol or "").strip().upper()
    for company_id, meta in TRACKED_COMPANIES.items():
        ticker = str(meta.get("ticker") or "").strip().upper()
        if ticker == normalized:
            return company_id
    return None


def _neutral_hiring_signal(symbol: str) -> Dict[str, Any]:
    return {
        "company": symbol,
        "signal": "neutral",
        "signal_strength": 0.0,
        "alert": False,
        "key_ratios": {
            "tech_ratio": 0.0,
            "core_tech_ratio": 0.0,
            "marketing_ratio": 0.0,
            "finance_compliance_ratio": 0.0,
            "dilution_ratio": 0.0,
        },
        "alert_message": "",
        "source": "unavailable",
    }


def _curated_hiring_signal(symbol: str, company_name: str = "") -> Optional[Dict[str, Any]]:
    normalized = str(symbol or "").strip().upper()
    if normalized not in CURATED_HIRING_SIGNALS:
        return None
    base = CURATED_HIRING_SIGNALS[normalized]
    return {
        "company": company_name or normalized,
        "signal": base["signal"],
        "signal_strength": base["signal_strength"],
        "alert": base["alert"],
        "key_ratios": dict(base["key_ratios"]),
        "alert_message": base["alert_message"],
        "source": "curated_hiring_profiles",
    }


class PeopleSignalAnalyzer:
    """Synthesize executive, insider and hiring structure into a pricing-facing people layer."""

    def __init__(
        self,
        executive_provider: Optional[ExecutiveProfileProvider] = None,
        insider_provider: Optional[InsiderFlowProvider] = None,
        hiring_tracker: Optional[HiringTracker] = None,
    ):
        self.executive_provider = executive_provider or ExecutiveProfileProvider()
        self.insider_provider = insider_provider or InsiderFlowProvider()
        self.hiring_tracker = hiring_tracker or HiringTracker()

    def analyze(self, symbol: str, company_name: str = "", sector: str = "") -> Dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()
        executive = self.executive_provider.get_profile(normalized_symbol, company_name, sector)
        insider = self.insider_provider.get_signal(normalized_symbol, company_name)

        company_id = _resolve_company_id(normalized_symbol)
        hiring = _curated_hiring_signal(normalized_symbol, company_name or normalized_symbol)
        if not hiring and company_id:
            hiring = self.hiring_tracker.analyze_company(company_id)
        if not hiring:
            hiring = _neutral_hiring_signal(company_name or normalized_symbol)
        hiring_ratios = hiring.get("key_ratios", {}) or {}
        dilution_ratio = float(hiring_ratios.get("dilution_ratio", 0.0))
        hiring_pressure = max(0.0, min(1.0, (dilution_ratio - 1.0) / 1.8))
        hiring_signal_bias = (
            float(hiring.get("signal_strength", 0.0))
            if hiring.get("signal") == "bullish"
            else -float(hiring.get("signal_strength", 0.0))
            if hiring.get("signal") == "bearish"
            else 0.0
        )

        people_quality_score = max(
            0.0,
            min(
                1.0,
                executive["technical_authority_score"] * 0.38
                + (1.0 - executive["capital_markets_pressure"]) * 0.16
                + (1.0 - executive["governance_risk"]) * 0.18
                + max(insider["conviction_score"], 0.0) * 0.1
                + max(hiring_signal_bias, 0.0) * 0.08
                + max(0.0, 1.0 - hiring_pressure) * 0.1,
            ),
        )
        people_fragility_score = max(
            0.0,
            min(
                1.0,
                executive["capital_markets_pressure"] * 0.26
                + executive["governance_risk"] * 0.24
                + max(-insider["conviction_score"], 0.0) * 0.18
                + hiring_pressure * 0.22
                + (1.0 - executive["technical_authority_score"]) * 0.1,
            ),
        )

        if people_fragility_score >= 0.62:
            risk_level = "high"
            stance = "fragile"
        elif people_fragility_score >= 0.4:
            risk_level = "medium"
            stance = "balanced"
        else:
            risk_level = "low"
            stance = "supportive"

        if dilution_ratio > 1.5 or executive["capital_markets_pressure"] >= 0.55:
            if risk_level == "low":
                risk_level = "medium"
                stance = "balanced"
        if dilution_ratio > 1.7 and executive["governance_risk"] >= 0.25:
            risk_level = "high"
            stance = "fragile"

        notes = []
        flags = list(executive.get("governance_flags") or [])
        if insider["conviction_score"] <= -0.18:
            notes.append("内部人交易偏减持，说明管理层对当前定价的安全边际未给出强背书。")
        elif insider["conviction_score"] >= 0.18:
            notes.append("内部人交易偏增持，说明管理层对当前估值区间有一定信心。")
        if dilution_ratio > 1.5:
            notes.append(f"招聘结构的技术稀释度达到 {dilution_ratio:.2f}，需警惕商业/合规目标压过技术路线。")
        elif dilution_ratio > 0:
            notes.append(f"招聘结构稀释度 {dilution_ratio:.2f}，当前可继续观察技术岗位占比是否回升。")
        if executive["founder_led"] and executive["technical_founder"]:
            notes.append("创始人与技术路线仍然绑定，人的维度对长期执行力形成一定支撑。")

        summary = (
            f"{company_name or normalized_symbol} 的人事层结论偏"
            f"{'脆弱' if stance == 'fragile' else '支撑' if stance == 'supportive' else '均衡'}，"
            f"组织质量 {people_quality_score:.2f} / 脆弱度 {people_fragility_score:.2f}。"
        )

        confidence = round(
            min(
                0.92,
                executive["confidence"] * 0.45
                + insider["confidence"] * 0.25
                + (0.72 if company_id else 0.35) * 0.3,
            ),
            2,
        )

        return {
            "symbol": normalized_symbol,
            "company_name": company_name or normalized_symbol,
            "stance": stance,
            "risk_level": risk_level,
            "people_quality_score": round(people_quality_score, 2),
            "people_fragility_score": round(people_fragility_score, 2),
            "confidence": confidence,
            "summary": summary,
            "notes": notes,
            "flags": flags[:4],
            "executive_profile": executive,
            "insider_flow": insider,
            "hiring_signal": {
                "company_id": company_id or "",
                "signal": hiring.get("signal", "neutral"),
                "signal_strength": round(float(hiring.get("signal_strength", 0.0)), 2),
                "alert": bool(hiring.get("alert", False)),
                "alert_message": hiring.get("alert_message") or "",
                "dilution_ratio": round(dilution_ratio, 2),
                "tech_ratio": round(float(hiring_ratios.get("tech_ratio", 0.0)), 2),
                "core_tech_ratio": round(float(hiring_ratios.get("core_tech_ratio", 0.0)), 2),
                "marketing_ratio": round(float(hiring_ratios.get("marketing_ratio", 0.0)), 2),
                "finance_compliance_ratio": round(float(hiring_ratios.get("finance_compliance_ratio", 0.0)), 2),
                "source": "hiring_tracker" if company_id else "unavailable",
            },
        }
