from __future__ import annotations

from typing import Any, Dict, List, Optional


SECTOR_HEDGE_MAP = {
    "technology": "XLK",
    "communication services": "XLC",
    "consumer discretionary": "XLY",
    "consumer staples": "XLP",
    "financial services": "XLF",
    "financial": "XLF",
    "healthcare": "XLV",
    "energy": "XLE",
    "industrials": "XLI",
    "materials": "XLB",
    "utilities": "XLU",
    "real estate": "XLRE",
}


def _resolve_sector_hedge(sector: str, industry: str = "") -> str:
    sector_key = str(sector or "").strip().lower()
    industry_key = str(industry or "").strip().lower()
    if "china" in industry_key or "internet" in industry_key:
        return "KWEB"
    if "semiconductor" in industry_key or "software" in industry_key:
        return "QQQ"
    return SECTOR_HEDGE_MAP.get(sector_key, "SPY")


def _build_trade_legs(
    symbol: str,
    sector: str,
    hedge_symbol: str,
    action: str,
    structural_decay: Dict[str, Any],
    people_layer: Dict[str, Any],
) -> List[Dict[str, Any]]:
    dominant_failure = structural_decay.get("dominant_failure_label") or "结构性衰败"
    people_risk = people_layer.get("risk_level", "unknown")

    if action == "structural_short":
        legs = [
            {
                "symbol": symbol,
                "side": "short",
                "role": "core_expression",
                "weight": 0.5,
                "thesis": dominant_failure,
            },
            {
                "symbol": hedge_symbol,
                "side": "long",
                "role": "beta_hedge",
                "weight": 0.3,
                "thesis": f"对冲 {sector or '市场'} Beta 暴露",
            },
        ]
        if people_risk == "high":
            legs.append({
                "symbol": "GLD" if hedge_symbol != "GLD" else "IEF",
                "side": "long",
                "role": "stress_hedge",
                "weight": 0.2,
                "thesis": "保留系统性冲击下的防御缓冲",
            })
        return legs

    if action == "structural_avoid":
        return [
            {
                "symbol": symbol,
                "side": "avoid",
                "role": "core_watch",
                "weight": 1.0,
                "thesis": "优先回避抄底，等待结构修复证据",
            },
            {
                "symbol": hedge_symbol,
                "side": "long",
                "role": "relative_hedge",
                "weight": 0.0,
                "thesis": "若做相对空头表达，可用作板块对冲参考",
            },
        ]

    return [
        {
            "symbol": symbol,
            "side": "watch",
            "role": "watchlist",
            "weight": 1.0,
            "thesis": "先观察人的维度、叙事与估值是否继续恶化",
        }
    ]


def build_macro_mispricing_thesis(
    symbol: str,
    gap: Dict[str, Any],
    valuation: Dict[str, Any],
    people_layer: Dict[str, Any],
    structural_decay: Dict[str, Any],
    trade_setup: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    trade_setup = trade_setup or {}
    symbol_label = symbol or "该标的"
    sector = valuation.get("sector", "")
    industry = valuation.get("industry", "")
    action = structural_decay.get("action", "watch")
    score = float(structural_decay.get("score") or 0.0)
    primary_view = "低估" if float(gap.get("gap_pct") or 0) < -10 else "高估" if float(gap.get("gap_pct") or 0) > 10 else "合理"
    people_risk = people_layer.get("risk_level", "unknown")
    hedge_symbol = _resolve_sector_hedge(sector, industry)
    fair_value_mid = gap.get("fair_value_mid")
    current_price = gap.get("current_price")
    trade_legs = _build_trade_legs(symbol, sector, hedge_symbol, action, structural_decay, people_layer)

    evidence_stack = list(dict.fromkeys([
        *(structural_decay.get("evidence") or []),
        *(people_layer.get("flags") or []),
        people_layer.get("summary") or "",
    ]))
    evidence_stack = [item for item in evidence_stack if item][:5]

    if action == "structural_short":
        thesis_type = "relative_short"
        stance = "结构性做空"
        summary = (
            f"{symbol_label} 更像组织与叙事共同劣化导致的长期错误定价，适合以单名义做空、"
            f"并用 {hedge_symbol} 对冲市场/板块 Beta。"
        )
        primary_leg = {
            "symbol": symbol,
            "side": "short",
            "role": "primary",
            "rationale": structural_decay.get("dominant_failure_label") or "结构性衰败主腿",
        }
        hedge_leg = {
            "symbol": hedge_symbol,
            "side": "long",
            "role": "hedge",
            "rationale": f"对冲 {sector or '市场'} Beta，保留单名义衰败暴露",
        }
    elif action == "structural_avoid":
        thesis_type = "avoid_or_relative_short"
        stance = "回避抄底 / 谨慎相对做空"
        summary = (
            f"{symbol_label} 当前更像价值陷阱或结构性走弱早期，优先避免把低估误判成修复机会；"
            f"若做表达，更适合轻仓相对做空并配 {hedge_symbol} 对冲。"
        )
        primary_leg = {
            "symbol": symbol,
            "side": "avoid",
            "role": "primary",
            "rationale": "优先避免逆势抄底，必要时再做轻仓相对空头表达",
        }
        hedge_leg = {
            "symbol": hedge_symbol,
            "side": "long",
            "role": "hedge",
            "rationale": f"若做相对价值表达，可用 {hedge_symbol} 对冲板块方向性",
        }
    else:
        thesis_type = "watchlist"
        stance = "观察名单"
        summary = (
            f"{symbol_label} 已进入结构性衰败观察名单，但当前更适合持续跟踪人的维度、"
            "估值与叙事是否继续共振恶化。"
        )
        primary_leg = {
            "symbol": symbol,
            "side": "watch",
            "role": "primary",
            "rationale": "暂不直接执行，先做长期衰败观察",
        }
        hedge_leg = None

    kill_conditions: List[str] = [
        "人的维度风险从 high/fragile 明显修复到 medium 或以下",
        "结构性衰败评分回落到 0.50 以下",
        "内部人交易信号由减持转为中性或增持背书",
    ]
    if fair_value_mid and current_price:
        kill_conditions.append(f"价格重新回到公允价值附近（当前中枢 {fair_value_mid}）")

    monitoring_triggers = [
        "招聘稀释度继续抬升或再次突破关键阈值",
        "主导失效模式发生切换",
        "因子与估值结论重新转为同向恶化",
    ]

    execution_notes = [
        "优先表达 idiosyncratic 错价，避免把系统性方向误当 thesis 收益来源",
        "组合腿权重用于研究表达，不代表真实资金配比建议",
    ]
    if action == "structural_short":
        execution_notes.append("若市场进入系统性 risk-off，可适度提高防御腿权重，降低单名义暴露。")
    elif action == "structural_avoid":
        execution_notes.append("当前优先做观察与回避，只有在证据继续恶化时再升级为空头表达。")

    return {
        "thesis_type": thesis_type,
        "stance": stance,
        "score": round(score, 2),
        "primary_view": primary_view,
        "people_risk": people_risk,
        "horizon": structural_decay.get("horizon", "中长期"),
        "summary": summary,
        "primary_leg": primary_leg,
        "hedge_leg": hedge_leg,
        "trade_legs": trade_legs,
        "execution_style": "multi_leg_relative_value" if action == "structural_short" else "watch_or_relative_expression",
        "target_price": trade_setup.get("target_price"),
        "risk_boundary": trade_setup.get("stop_loss"),
        "risk_reward": trade_setup.get("risk_reward"),
        "kill_conditions": kill_conditions,
        "monitoring_triggers": monitoring_triggers,
        "evidence_stack": evidence_stack,
        "execution_notes": execution_notes,
    }
