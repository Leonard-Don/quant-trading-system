"""Curated executive profile signals for people-layer pricing analysis."""

from __future__ import annotations

from typing import Any, Dict, Optional


EXECUTIVE_PROFILE_CATALOG: Dict[str, Dict[str, Any]] = {
    "NVDA": {
        "leadership_style": "technical_founder_led",
        "founder_led": True,
        "technical_founder": True,
        "technical_executive_share": 0.67,
        "finance_legal_share": 0.11,
        "commercial_share": 0.22,
        "board_independence_score": 0.72,
        "average_tenure_years": 9.3,
        "recent_turnover_level": "low",
        "governance_flags": ["研发话语权仍占主导", "技术领袖 continuity 较强"],
        "confidence": 0.78,
    },
    "TSM": {
        "leadership_style": "operations_engineering_led",
        "founder_led": False,
        "technical_founder": False,
        "technical_executive_share": 0.58,
        "finance_legal_share": 0.12,
        "commercial_share": 0.30,
        "board_independence_score": 0.74,
        "average_tenure_years": 8.1,
        "recent_turnover_level": "low",
        "governance_flags": ["制造与工艺背景较强", "资本市场压力可控"],
        "confidence": 0.74,
    },
    "MSFT": {
        "leadership_style": "platform_operator_led",
        "founder_led": False,
        "technical_founder": False,
        "technical_executive_share": 0.55,
        "finance_legal_share": 0.14,
        "commercial_share": 0.31,
        "board_independence_score": 0.76,
        "average_tenure_years": 7.2,
        "recent_turnover_level": "low",
        "governance_flags": ["平台和工程背景保持主导", "组织稳定度较高"],
        "confidence": 0.72,
    },
    "AAPL": {
        "leadership_style": "operations_finance_balanced",
        "founder_led": False,
        "technical_founder": False,
        "technical_executive_share": 0.34,
        "finance_legal_share": 0.28,
        "commercial_share": 0.38,
        "board_independence_score": 0.69,
        "average_tenure_years": 6.8,
        "recent_turnover_level": "medium",
        "governance_flags": ["运营和财务执行力强", "技术愿景对市场叙事依赖管理层再解释"],
        "confidence": 0.69,
    },
    "META": {
        "leadership_style": "founder_product_led",
        "founder_led": True,
        "technical_founder": True,
        "technical_executive_share": 0.51,
        "finance_legal_share": 0.15,
        "commercial_share": 0.34,
        "board_independence_score": 0.62,
        "average_tenure_years": 6.1,
        "recent_turnover_level": "medium",
        "governance_flags": ["创始人控制力强", "治理独立性略弱于成熟平台"],
        "confidence": 0.68,
    },
    "GOOGL": {
        "leadership_style": "technical_platform_led",
        "founder_led": False,
        "technical_founder": False,
        "technical_executive_share": 0.49,
        "finance_legal_share": 0.18,
        "commercial_share": 0.33,
        "board_independence_score": 0.71,
        "average_tenure_years": 6.4,
        "recent_turnover_level": "medium",
        "governance_flags": ["技术文化仍在", "成熟平台的商业化层级持续变厚"],
        "confidence": 0.68,
    },
    "AMZN": {
        "leadership_style": "operator_commercial_led",
        "founder_led": False,
        "technical_founder": False,
        "technical_executive_share": 0.42,
        "finance_legal_share": 0.18,
        "commercial_share": 0.40,
        "board_independence_score": 0.66,
        "average_tenure_years": 5.9,
        "recent_turnover_level": "medium",
        "governance_flags": ["执行力强但业务层级复杂", "商业扩张优先级高于纯技术叙事"],
        "confidence": 0.66,
    },
    "TSLA": {
        "leadership_style": "founder_vision_led",
        "founder_led": True,
        "technical_founder": True,
        "technical_executive_share": 0.38,
        "finance_legal_share": 0.20,
        "commercial_share": 0.42,
        "board_independence_score": 0.48,
        "average_tenure_years": 4.6,
        "recent_turnover_level": "high",
        "governance_flags": ["关键岗位稳定性偏弱", "战略叙事高度依赖核心个人"],
        "confidence": 0.64,
    },
    "BABA": {
        "leadership_style": "commercial_finance_led",
        "founder_led": False,
        "technical_founder": False,
        "technical_executive_share": 0.27,
        "finance_legal_share": 0.31,
        "commercial_share": 0.42,
        "board_independence_score": 0.57,
        "average_tenure_years": 4.8,
        "recent_turnover_level": "high",
        "governance_flags": ["财务与平台治理议题占比高", "技术组织被商业目标稀释的风险偏高"],
        "confidence": 0.7,
    },
    "BIDU": {
        "leadership_style": "founder_ai_transition",
        "founder_led": True,
        "technical_founder": True,
        "technical_executive_share": 0.44,
        "finance_legal_share": 0.19,
        "commercial_share": 0.37,
        "board_independence_score": 0.6,
        "average_tenure_years": 5.1,
        "recent_turnover_level": "medium",
        "governance_flags": ["AI 转型仍在推进", "商业化层与研发层权重接近"],
        "confidence": 0.66,
    },
}


TURNOVER_PENALTY = {
    "low": 0.08,
    "medium": 0.2,
    "high": 0.36,
}


def _fallback_profile(symbol: str, company_name: str = "", sector: str = "") -> Dict[str, Any]:
    technical_bias = 0.48 if sector.lower() in {"technology", "semiconductors", "software"} else 0.36
    commercial_bias = 1.0 - technical_bias - 0.18
    return {
        "leadership_style": "limited_visibility",
        "founder_led": False,
        "technical_founder": False,
        "technical_executive_share": round(technical_bias, 2),
        "finance_legal_share": 0.18,
        "commercial_share": round(max(commercial_bias, 0.18), 2),
        "board_independence_score": 0.6,
        "average_tenure_years": 4.5,
        "recent_turnover_level": "medium",
        "governance_flags": [f"{company_name or symbol} 缺少完整高管结构数据，当前结论以启发式画像为主。"],
        "confidence": 0.35,
    }


class ExecutiveProfileProvider:
    """Return a compact executive and governance profile for a symbol."""

    def get_profile(
        self,
        symbol: str,
        company_name: str = "",
        sector: str = "",
    ) -> Dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()
        base = dict(EXECUTIVE_PROFILE_CATALOG.get(normalized_symbol) or _fallback_profile(normalized_symbol, company_name, sector))
        turnover_level = base.get("recent_turnover_level", "medium")
        turnover_penalty = TURNOVER_PENALTY.get(turnover_level, 0.2)
        technical_share = float(base.get("technical_executive_share", 0.0))
        founder_bonus = 0.12 if base.get("founder_led") and base.get("technical_founder") else 0.05 if base.get("founder_led") else 0.0
        tenure_score = min(float(base.get("average_tenure_years", 0.0)) / 10.0, 1.0)
        board_score = float(base.get("board_independence_score", 0.0))
        finance_share = float(base.get("finance_legal_share", 0.0))
        commercial_share = float(base.get("commercial_share", 0.0))

        technical_authority_score = max(
            0.0,
            min(
                1.0,
                technical_share * 0.45
                + founder_bonus
                + tenure_score * 0.18
                + board_score * 0.17
                - turnover_penalty * 0.15,
            ),
        )
        capital_markets_pressure = max(
            0.0,
            min(
                1.0,
                finance_share * 0.55
                + commercial_share * 0.25
                + turnover_penalty * 0.2,
            ),
        )
        governance_risk = max(
            0.0,
            min(
                1.0,
                (1.0 - board_score) * 0.45
                + turnover_penalty * 0.35
                + max(finance_share - technical_share, 0.0) * 0.2,
            ),
        )
        leadership_balance = "技术主导" if technical_share >= 0.5 else "均衡" if technical_share >= 0.35 else "商业/财务主导"

        summary = (
            f"{company_name or normalized_symbol} 当前管理层画像偏{leadership_balance}，"
            f"技术决策权评分 {technical_authority_score:.2f}，资本市场压力 {capital_markets_pressure:.2f}。"
        )

        return {
            "symbol": normalized_symbol,
            "company_name": company_name or normalized_symbol,
            "leadership_style": base["leadership_style"],
            "founder_led": bool(base.get("founder_led")),
            "technical_founder": bool(base.get("technical_founder")),
            "technical_executive_share": round(technical_share, 2),
            "finance_legal_share": round(finance_share, 2),
            "commercial_share": round(commercial_share, 2),
            "board_independence_score": round(board_score, 2),
            "average_tenure_years": round(float(base.get("average_tenure_years", 0.0)), 1),
            "recent_turnover_level": turnover_level,
            "technical_authority_score": round(technical_authority_score, 2),
            "capital_markets_pressure": round(capital_markets_pressure, 2),
            "governance_risk": round(governance_risk, 2),
            "leadership_balance": leadership_balance,
            "governance_flags": list(base.get("governance_flags") or []),
            "confidence": round(float(base.get("confidence", 0.35)), 2),
            "source": "curated_people_profiles",
            "summary": summary,
        }
