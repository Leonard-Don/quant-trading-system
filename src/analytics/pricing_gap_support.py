from __future__ import annotations

from typing import Any, Dict, Optional


def resolve_valuation_view(gap: Dict, valuation: Dict) -> Optional[str]:
    status = valuation.get("valuation_status", {}).get("status", "")
    if status in {"overvalued", "severely_overvalued"}:
        return "overvalued"
    if status in {"undervalued", "severely_undervalued"}:
        return "undervalued"

    gap_pct = gap.get("gap_pct")
    if gap_pct is None:
        return None
    if gap_pct >= 10:
        return "overvalued"
    if gap_pct <= -10:
        return "undervalued"
    return "fair"


def resolve_factor_view(factor: Dict) -> Optional[str]:
    capm = factor.get("capm", {}) or {}
    ff3 = factor.get("fama_french", {}) or {}
    signals = []

    for model in (capm, ff3):
        if "error" in model:
            continue
        alpha_pct = model.get("alpha_pct")
        if alpha_pct is None:
            continue
        numeric = float(alpha_pct)
        if abs(numeric) < 3:
            continue
        signals.append("bullish" if numeric > 0 else "bearish")

    if not signals:
        return None
    bullish = signals.count("bullish")
    bearish = signals.count("bearish")
    if bullish > bearish:
        return "bullish"
    if bearish > bullish:
        return "bearish"
    return None


def assess_factor_valuation_alignment(gap: Dict, factor: Dict, valuation: Dict) -> Optional[str]:
    valuation_view = resolve_valuation_view(gap, valuation)
    factor_view = resolve_factor_view(factor)

    if not valuation_view or valuation_view == "fair":
        return None
    if not factor_view:
        return None
    if valuation_view == "overvalued":
        return "aligned" if factor_view == "bearish" else "conflict"
    if valuation_view == "undervalued":
        return "aligned" if factor_view == "bullish" else "conflict"
    return None


def build_alignment_meta(gap: Dict, factor: Dict, valuation: Dict) -> Dict[str, str]:
    alignment = assess_factor_valuation_alignment(gap, factor, valuation)
    valuation_view = resolve_valuation_view(gap, valuation)
    factor_view = resolve_factor_view(factor)

    if alignment == "aligned":
        if valuation_view == "overvalued":
            return {
                "status": "aligned",
                "label": "同向",
                "summary": "因子信号与高估判断同向，证据互相印证",
            }
        return {
            "status": "aligned",
            "label": "同向",
            "summary": "因子信号与低估判断同向，证据互相印证",
        }

    if alignment == "conflict":
        return {
            "status": "conflict",
            "label": "冲突",
            "summary": "因子信号与估值结论相反，结论需要谨慎解释",
        }

    if factor_view:
        return {
            "status": "partial",
            "label": "待确认",
            "summary": "因子方向已有偏向，但估值结论暂未形成明确同向关系",
        }

    return {
        "status": "neutral",
        "label": "待确认",
        "summary": "当前缺少足够清晰的同向证据，建议结合更多样本复核",
    }


def assess_confidence(gap: Dict, factor: Dict, valuation: Dict) -> Dict[str, Any]:
    score = 0.0
    reasons = []
    components = []

    def add_component(key: str, label: str, delta: float, status: str, detail: str) -> None:
        nonlocal score
        score += delta
        components.append({
            "key": key,
            "label": label,
            "delta": round(delta, 2),
            "status": status,
            "detail": detail,
        })

    fair_value = valuation.get("fair_value", {}) or {}
    if gap.get("gap_pct") is not None and fair_value.get("mid"):
        add_component("gap_anchor", "价格偏差锚点", 0.15, "positive", "当前价格和公允价值中枢都可用")
    else:
        reasons.append("缺少完整的价格偏差锚点")
        add_component("gap_anchor", "价格偏差锚点", 0.0, "negative", "缺少完整的价格偏差锚点")

    capm = factor.get("capm", {}) or {}
    ff3 = factor.get("fama_french", {}) or {}
    if "error" not in capm:
        add_component("capm", "CAPM 覆盖", 0.12, "positive", "CAPM 模型可用")
    else:
        reasons.append("CAPM 模型不可用")
        add_component("capm", "CAPM 覆盖", 0.0, "negative", "CAPM 模型不可用")

    if "error" not in ff3:
        add_component("ff3", "FF3 覆盖", 0.12, "positive", "Fama-French 三因子模型可用")
    else:
        reasons.append("FF3 模型不可用")
        add_component("ff3", "FF3 覆盖", 0.0, "negative", "FF3 模型不可用")

    factor_points = max(
        int(factor.get("data_points") or 0),
        int(capm.get("data_points") or 0),
        int(ff3.get("data_points") or 0),
    )
    if factor_points >= 180:
        add_component("sample_window", "因子样本量", 0.16, "positive", f"样本数 {factor_points}，覆盖充足")
    elif factor_points >= 120:
        add_component("sample_window", "因子样本量", 0.12, "positive", f"样本数 {factor_points}，覆盖较充分")
    elif factor_points >= 60:
        add_component("sample_window", "因子样本量", 0.08, "warning", f"样本数 {factor_points}，窗口偏短")
        reasons.append("因子样本窗口偏短")
    else:
        reasons.append("因子样本不足")
        add_component("sample_window", "因子样本量", 0.0, "negative", f"样本数 {factor_points}，不足以稳定支撑结论")

    dcf = valuation.get("dcf", {}) or {}
    comparable = valuation.get("comparable", {}) or {}
    dcf_value = dcf.get("intrinsic_value")
    comparable_value = comparable.get("fair_value")
    dcf_ok = "error" not in dcf and dcf_value and dcf_value > 0
    comparable_ok = "error" not in comparable and comparable_value and comparable_value > 0
    valuation_methods = int(bool(dcf_ok)) + int(bool(comparable_ok))

    if valuation_methods == 2:
        add_component("valuation_coverage", "估值方法覆盖", 0.16, "positive", "DCF 与可比估值均可用")
    elif valuation_methods == 1:
        add_component("valuation_coverage", "估值方法覆盖", 0.08, "warning", "仅有单一估值方法支撑")
        reasons.append("仅有单一估值方法支撑")
    else:
        reasons.append("缺少可用估值方法")
        add_component("valuation_coverage", "估值方法覆盖", 0.0, "negative", "缺少可用估值方法")

    price_source = valuation.get("current_price_source", "unavailable")
    if price_source == "live":
        add_component("price_source", "现价来源", 0.09, "positive", "当前价格来自实时行情")
    elif price_source in {"fundamental_current_price", "fundamental_regular_market_price"}:
        add_component("price_source", "现价来源", 0.07, "positive", "当前价格来自基本面快照字段")
    elif price_source in {"fundamental_previous_close", "historical_close"}:
        add_component("price_source", "现价来源", 0.04, "warning", "当前价格使用回退值")
        reasons.append("当前价格使用回退值")
    else:
        reasons.append("当前价格来源不可确认")
        add_component("price_source", "现价来源", 0.0, "negative", "当前价格来源不可确认")

    if dcf_ok and comparable_ok:
        midpoint = (float(dcf_value) + float(comparable_value)) / 2
        divergence = abs(float(dcf_value) - float(comparable_value)) / midpoint if midpoint > 0 else None
        if divergence is not None:
            if divergence <= 0.15:
                add_component("valuation_consistency", "估值一致性", 0.10, "positive", "DCF 与可比估值基本一致")
            elif divergence <= 0.30:
                add_component("valuation_consistency", "估值一致性", 0.05, "warning", "DCF 与可比估值存在一定分歧")
                reasons.append("DCF 与可比估值存在一定分歧")
            else:
                reasons.append("DCF 与可比估值分歧较大")
                add_component("valuation_consistency", "估值一致性", 0.0, "negative", "DCF 与可比估值分歧较大")
    else:
        add_component("valuation_consistency", "估值一致性", 0.0, "warning", "估值方法不足，无法比较一致性")

    alignment = assess_factor_valuation_alignment(gap, factor, valuation)
    if alignment == "aligned":
        add_component("factor_alignment", "证据共振", 0.08, "positive", "因子信号与估值结论同向")
    elif alignment == "conflict":
        add_component("factor_alignment", "证据共振", -0.12, "negative", "二级因子表现与估值结论方向不一致")
        reasons.append("二级因子表现与估值结论方向不一致")
    else:
        add_component("factor_alignment", "证据共振", 0.0, "warning", "当前缺少明确的同向或冲突信号")

    score = max(0.0, min(score, 1.0))
    if score >= 0.72:
        level = "high"
    elif score >= 0.45:
        level = "medium"
    else:
        level = "low"

    return {
        "level": level,
        "score": round(score, 2),
        "reasons": reasons[:3],
        "components": components,
    }


def build_trade_setup(
    gap: Dict,
    valuation: Dict,
    alignment_meta: Dict[str, Any],
    confidence_meta: Dict[str, Any],
) -> Dict[str, Any]:
    current_price = gap.get("current_price")
    fair_value_mid = gap.get("fair_value_mid")
    fair_value_low = gap.get("fair_value_low")
    fair_value_high = gap.get("fair_value_high")
    if (current_price is None or fair_value_mid is None) and valuation.get("fair_value"):
        fair_value_meta = valuation.get("fair_value", {}) or {}
        fair_value_mid = fair_value_mid or fair_value_meta.get("mid")
        fair_value_low = fair_value_low or fair_value_meta.get("low")
        fair_value_high = fair_value_high or fair_value_meta.get("high")
    if current_price is None and fair_value_mid and gap.get("gap_pct") is not None:
        current_price = float(fair_value_mid) * (1 + (float(gap.get("gap_pct")) / 100))
    primary_view = "低估" if gap.get("gap_pct") is not None and gap.get("gap_pct") < -10 else "高估" if gap.get("gap_pct") is not None and gap.get("gap_pct") > 10 else "合理"

    if not current_price or not fair_value_mid:
        return {
            "stance": "观察",
            "summary": "缺少足够价格锚点，暂不生成交易情景",
        }

    current_price = float(current_price)
    fair_value_mid = float(fair_value_mid)
    fair_value_low = float(fair_value_low or fair_value_mid)
    fair_value_high = float(fair_value_high or fair_value_mid)
    alignment_status = alignment_meta.get("status")

    if primary_view == "低估":
        stop_loss = round(min(current_price * 0.92, fair_value_low * 0.98), 2)
        target_price = round(fair_value_mid, 2)
        stretch_target = round(fair_value_high, 2)
        upside_pct = round(((target_price - current_price) / current_price) * 100, 1)
        stretch_upside_pct = round(((stretch_target - current_price) / current_price) * 100, 1)
        risk_pct = round(((current_price - stop_loss) / current_price) * 100, 1) if stop_loss < current_price else 0.0
        risk_reward = round(upside_pct / risk_pct, 2) if risk_pct > 0 else None
        summary = "若按低估回归处理，可观察价格向公允价值中枢修复的空间。"
    elif primary_view == "高估":
        stop_loss = round(max(current_price * 1.08, fair_value_high * 1.02), 2)
        target_price = round(fair_value_mid, 2)
        stretch_target = round(fair_value_low, 2)
        upside_pct = round(((current_price - target_price) / current_price) * 100, 1)
        stretch_upside_pct = round(((current_price - stretch_target) / current_price) * 100, 1)
        risk_pct = round(((stop_loss - current_price) / current_price) * 100, 1) if stop_loss > current_price else 0.0
        risk_reward = round(upside_pct / risk_pct, 2) if risk_pct > 0 else None
        summary = "若按高估回归处理，可观察价格回落至公允价值中枢的空间。"
    else:
        return {
            "stance": "观察",
            "summary": "当前偏差不大，更适合继续观察而非依赖单次估值信号交易。",
            "target_price": round(fair_value_mid, 2),
            "reference_range": {
                "low": round(fair_value_low, 2),
                "high": round(fair_value_high, 2),
            },
        }

    quality_note = {
        "aligned": "因子与估值同向，情景可信度更高。",
        "conflict": "因子与估值冲突，建议降低仓位假设。",
    }.get(alignment_status, "因子与估值尚未形成强共振，建议结合更多证据。")

    return {
        "stance": "关注做多修复" if primary_view == "低估" else "关注回归风险",
        "summary": summary,
        "target_price": target_price,
        "stretch_target": stretch_target,
        "stop_loss": stop_loss,
        "upside_pct": upside_pct,
        "stretch_upside_pct": stretch_upside_pct,
        "risk_pct": risk_pct,
        "risk_reward": risk_reward,
        "reference_range": {
            "low": round(fair_value_low, 2),
            "high": round(fair_value_high, 2),
        },
        "confidence_level": confidence_meta.get("level"),
        "quality_note": quality_note,
    }
