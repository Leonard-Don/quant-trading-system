"""
宏观错误定价因子 API。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.analytics.macro_factors import FactorCombiner, MacroHistoryStore, build_default_registry
from src.data.alternative import get_alt_data_manager
from src.data.alternative.people import PeopleLayerProvider
from src.data.data_manager import DataManager
from .macro_department import build_department_chaos_summary
from .macro_decay import build_structural_decay_radar
from .macro_evidence import build_factor_evidence, build_overall_evidence
from .macro_quality import (
    apply_conflict_penalty,
    build_input_reliability_summary,
)
from .macro_support import (
    FACTOR_WEIGHTS,
    build_macro_trend,
    build_resonance_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_registry = build_default_registry()
_combiner = FactorCombiner()
_history_store = MacroHistoryStore()
_market_data_manager = DataManager()
_fallback_people_provider = PeopleLayerProvider()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if number != number:
            return default
        return number
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_horizons(raw: str) -> List[int]:
    horizons: List[int] = []
    for item in str(raw or "").split(","):
        try:
            horizon = int(item.strip())
        except ValueError:
            continue
        if 1 <= horizon <= 252 and horizon not in horizons:
            horizons.append(horizon)
    return horizons or [5, 20, 60]


def _signal_direction(score: Any, signal: Any = "") -> int:
    label = str(signal or "").lower()
    if any(token in label for token in ("bear", "risk_off", "short", "negative", "看空")):
        return -1
    if any(token in label for token in ("bull", "risk_on", "long", "positive", "看多")):
        return 1

    numeric_score = _safe_float(score, 0.5)
    if numeric_score >= 0.58:
        return 1
    if numeric_score <= 0.42:
        return -1
    return 0


def _direction_label(direction: int) -> str:
    if direction > 0:
        return "bullish"
    if direction < 0:
        return "bearish"
    return "neutral"


def _extract_close_points(data) -> List[Dict[str, Any]]:
    if data is None or getattr(data, "empty", True) or "close" not in data:
        return []

    frame = data.sort_index()
    points: List[Dict[str, Any]] = []
    for index_value, row in frame.iterrows():
        timestamp = _parse_timestamp(index_value)
        close = _safe_float(row.get("close"), 0.0)
        if timestamp and close > 0:
            points.append({"timestamp": timestamp, "close": close})
    return points


def _find_forward_return(close_points: List[Dict[str, Any]], timestamp: datetime, horizon: int) -> Optional[Dict[str, Any]]:
    start_index = None
    for index, point in enumerate(close_points):
        if point["timestamp"].date() >= timestamp.date():
            start_index = index
            break
    if start_index is None:
        return None

    end_index = start_index + horizon
    if end_index >= len(close_points):
        return None

    start_close = _safe_float(close_points[start_index]["close"])
    end_close = _safe_float(close_points[end_index]["close"])
    if start_close <= 0:
        return None

    return {
        "snapshot_date": close_points[start_index]["timestamp"].date().isoformat(),
        "horizon_end_date": close_points[end_index]["timestamp"].date().isoformat(),
        "forward_return": end_close / start_close - 1.0,
    }


def _summarize_prediction_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    evaluated = [row for row in rows if row.get("direction") != 0]
    if not evaluated:
        return {
            "samples": 0,
            "hit_rate": None,
            "avg_forward_return": None,
            "avg_signed_return": None,
            "long_short_edge": None,
        }

    hit_count = sum(1 for row in evaluated if _safe_float(row.get("direction")) * _safe_float(row.get("forward_return")) > 0)
    avg_forward_return = sum(_safe_float(row.get("forward_return")) for row in evaluated) / len(evaluated)
    signed_returns = [
        _safe_float(row.get("direction")) * _safe_float(row.get("forward_return"))
        for row in evaluated
    ]
    long_returns = [_safe_float(row.get("forward_return")) for row in evaluated if row.get("direction") == 1]
    short_returns = [_safe_float(row.get("forward_return")) for row in evaluated if row.get("direction") == -1]
    long_short_edge = None
    if long_returns and short_returns:
        long_short_edge = (sum(long_returns) / len(long_returns)) - (sum(short_returns) / len(short_returns))

    return {
        "samples": len(evaluated),
        "hit_rate": round(hit_count / len(evaluated), 4),
        "avg_forward_return": round(avg_forward_return, 6),
        "avg_signed_return": round(sum(signed_returns) / len(signed_returns), 6),
        "long_short_edge": round(long_short_edge, 6) if long_short_edge is not None else None,
    }


def _build_people_layer_summary(context: Dict[str, Any]):
    people_signal = (context.get("signals", {}) or {}).get("people_layer", {}) or {}
    if people_signal.get("watchlist"):
        return {
            "label": "fragile" if _safe_float(people_signal.get("avg_fragility_score")) >= 0.52 else "watch" if _safe_float(people_signal.get("avg_fragility_score")) >= 0.36 else "stable",
            "summary": people_signal.get("summary", "人的维度信号已接入，但当前缺少摘要。"),
            "watchlist": people_signal.get("watchlist", []),
            "fragile_companies": people_signal.get("fragile_companies", []),
            "supportive_companies": people_signal.get("supportive_companies", []),
            "fragile_company_count": int(people_signal.get("fragile_company_count", 0) or 0),
            "supportive_company_count": int(people_signal.get("supportive_company_count", 0) or 0),
            "avg_fragility_score": round(_safe_float(people_signal.get("avg_fragility_score")), 2),
            "avg_quality_score": round(_safe_float(people_signal.get("avg_quality_score")), 2),
            "source": "people_layer_provider",
            "source_mode_summary": people_signal.get("source_mode_summary", {}),
        }

    return _build_people_layer_summary_fallback()


def _build_people_layer_summary_fallback():
    try:
        signal = _fallback_people_provider.run_pipeline()
        if signal.get("watchlist"):
            return {
                "label": "fragile" if _safe_float(signal.get("avg_fragility_score")) >= 0.52 else "watch" if _safe_float(signal.get("avg_fragility_score")) >= 0.36 else "stable",
                "summary": signal.get("summary", ""),
                "watchlist": signal.get("watchlist", []),
                "fragile_companies": signal.get("fragile_companies", []),
                "supportive_companies": signal.get("supportive_companies", []),
                "fragile_company_count": int(signal.get("fragile_company_count", 0) or 0),
                "supportive_company_count": int(signal.get("supportive_company_count", 0) or 0),
                "avg_fragility_score": round(_safe_float(signal.get("avg_fragility_score")), 2),
                "avg_quality_score": round(_safe_float(signal.get("avg_quality_score")), 2),
                "source": "people_layer_fallback_provider",
                "source_mode_summary": signal.get("source_mode_summary", {}),
            }
    except Exception:
        pass

    people_profiles = []

    if not people_profiles:
        return {
            "label": "unknown",
            "summary": "暂缺可用的人事层样本。",
            "watchlist": [],
            "fragile_companies": [],
            "supportive_companies": [],
            "fragile_company_count": 0,
            "supportive_company_count": 0,
            "avg_fragility_score": 0.0,
            "avg_quality_score": 0.0,
        }

    avg_fragility = sum(float(item.get("people_fragility_score", 0.0)) for item in people_profiles) / len(people_profiles)
    avg_quality = sum(float(item.get("people_quality_score", 0.0)) for item in people_profiles) / len(people_profiles)
    fragile_companies = [
        item for item in people_profiles if item.get("risk_level") == "high"
    ]
    supportive_companies = [
        item for item in people_profiles if item.get("stance") == "supportive"
    ]
    watchlist = sorted(
        people_profiles,
        key=lambda item: (
            float(item.get("people_fragility_score", 0.0)),
            -float(item.get("people_quality_score", 0.0)),
        ),
        reverse=True,
    )[:5]
    label = "fragile" if avg_fragility >= 0.52 else "watch" if avg_fragility >= 0.36 else "stable"

    return {
        "label": label,
        "summary": (
            f"当前跟踪样本的人事脆弱度均值 {avg_fragility:.2f}，"
            f"其中 {len(fragile_companies)} 家处于高风险区。"
        ),
        "watchlist": [
            {
                "symbol": item.get("symbol"),
                "company_name": item.get("company_name"),
                "risk_level": item.get("risk_level"),
                "stance": item.get("stance"),
                "people_fragility_score": item.get("people_fragility_score"),
                "people_quality_score": item.get("people_quality_score"),
                "summary": item.get("summary"),
                "hiring_signal": item.get("hiring_signal", {}),
                "insider_flow": item.get("insider_flow", {}),
            }
            for item in watchlist
        ],
        "fragile_companies": [
            {
                "symbol": item.get("symbol"),
                "company_name": item.get("company_name"),
                "people_fragility_score": item.get("people_fragility_score"),
                "summary": item.get("summary"),
            }
            for item in sorted(
                fragile_companies,
                key=lambda item: float(item.get("people_fragility_score", 0.0)),
                reverse=True,
            )[:3]
        ],
        "supportive_companies": [
            {
                "symbol": item.get("symbol"),
                "company_name": item.get("company_name"),
                "people_quality_score": item.get("people_quality_score"),
                "summary": item.get("summary"),
            }
            for item in sorted(
                supportive_companies,
                key=lambda item: float(item.get("people_quality_score", 0.0)),
                reverse=True,
            )[:3]
        ],
        "fragile_company_count": len(fragile_companies),
        "supportive_company_count": len(supportive_companies),
        "avg_fragility_score": round(avg_fragility, 2),
        "avg_quality_score": round(avg_quality, 2),
        "source": "people_layer_curated_profiles",
    }


def _build_context(refresh: bool = False):
    manager = get_alt_data_manager()
    snapshot = manager.get_dashboard_snapshot(refresh=refresh)
    return {
        "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
        "snapshot": snapshot,
        "signals": snapshot.get("signals", {}),
        "records": manager.get_records(timeframe="45d", limit=200),
        "market_indicators": _market_data_manager.get_market_indicators(),
        "provider_status": snapshot.get("providers", {}),
        "refresh_status": snapshot.get("refresh_status", {}),
        "data_freshness": snapshot.get("staleness", {}),
        "provider_health": snapshot.get("provider_health", {}),
        "source_mode_summary": snapshot.get("source_mode_summary", {}),
    }


@router.get("/overview", summary="宏观错误定价总览")
async def get_macro_overview(refresh: bool = Query(default=False)):
    try:
        context = _build_context(refresh=refresh)
        factor_results = _registry.compute_all(context)
        combined = _combiner.combine(
            factor_results,
            weights=FACTOR_WEIGHTS,
        )
        overview = {
            "snapshot_timestamp": context["snapshot_timestamp"],
            "macro_score": combined["score"],
            "macro_signal": combined["signal"],
            "confidence": combined["confidence"],
            "factors": combined["factors"],
            "providers": context["provider_status"],
            "provider_status": context["provider_status"],
            "refresh_status": context["refresh_status"],
            "data_freshness": context["data_freshness"],
            "provider_health": context["provider_health"],
            "signals": context["signals"],
            "evidence_summary": build_overall_evidence(context),
            "department_chaos_summary": build_department_chaos_summary(context),
            "people_layer_summary": _build_people_layer_summary(context),
            "source_mode_summary": context["source_mode_summary"],
        }
        for factor in overview["factors"]:
            factor.setdefault("metadata", {})
            factor["metadata"]["evidence_summary"] = build_factor_evidence(factor.get("name", ""), context)
        overview = apply_conflict_penalty(overview)
        overview["input_reliability_summary"] = build_input_reliability_summary(overview)
        overview["structural_decay_radar"] = build_structural_decay_radar(overview)
        previous = _history_store.get_previous_snapshot(context["snapshot_timestamp"])
        overview["trend"] = build_macro_trend(overview, previous)
        overview["resonance_summary"] = build_resonance_summary(overview)
        _history_store.append_snapshot(overview)
        overview["history_length"] = len(_history_store.list_snapshots(limit=1000))
        return overview
    except Exception as exc:
        logger.error("Failed to build macro overview: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history", summary="宏观错误定价历史", deprecated=True)
async def get_macro_history(limit: int = Query(default=30, ge=1, le=200)):
    try:
        records = _history_store.list_snapshots(limit=limit)
        return {
            "records": records,
            "count": len(records),
        }
    except Exception as exc:
        logger.error("Failed to fetch macro history: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/factor-backtest", summary="宏观因子历史验证")
async def get_macro_factor_backtest(
    benchmark: str = Query(default="SPY", description="用于验证宏观信号方向的市场基准"),
    period: str = Query(default="2y", description="基准价格历史区间"),
    horizons: str = Query(default="5,20,60", description="逗号分隔的 forward-return 天数"),
    limit: int = Query(default=250, ge=2, le=1000, description="最多读取的宏观历史快照数量"),
):
    try:
        requested_horizons = _parse_horizons(horizons)
        snapshots = sorted(
            _history_store.list_snapshots(limit=limit),
            key=lambda item: str(item.get("snapshot_timestamp") or item.get("timestamp") or ""),
        )
        benchmark_data = _market_data_manager.get_historical_data(
            benchmark,
            period=period,
            interval="1d",
        )
        close_points = _extract_close_points(benchmark_data)

        if not close_points:
            return {
                "status": "insufficient_market_data",
                "benchmark": benchmark,
                "period": period,
                "horizons": requested_horizons,
                "snapshot_count": len(snapshots),
                "message": "未能获取可用于验证的基准价格序列。",
                "horizon_results": [],
                "factor_results": [],
                "sample_predictions": [],
            }

        prediction_rows: List[Dict[str, Any]] = []
        factor_rows: List[Dict[str, Any]] = []
        skipped_snapshots = 0

        for snapshot in snapshots:
            snapshot_time = _parse_timestamp(
                snapshot.get("snapshot_timestamp") or snapshot.get("timestamp")
            )
            if snapshot_time is None:
                skipped_snapshots += 1
                continue

            macro_direction = _signal_direction(
                snapshot.get("macro_score"),
                snapshot.get("macro_signal"),
            )
            for horizon in requested_horizons:
                forward = _find_forward_return(close_points, snapshot_time, horizon)
                if not forward:
                    continue
                prediction_rows.append({
                    **forward,
                    "horizon_days": horizon,
                    "scope": "macro",
                    "factor": "combined_macro",
                    "score": _safe_float(snapshot.get("macro_score"), 0.5),
                    "confidence": _safe_float(snapshot.get("confidence"), 0.0),
                    "signal": snapshot.get("macro_signal"),
                    "direction": macro_direction,
                    "direction_label": _direction_label(macro_direction),
                })

                for factor in snapshot.get("factors") or []:
                    factor_direction = _signal_direction(
                        factor.get("score"),
                        factor.get("signal") or factor.get("direction"),
                    )
                    factor_rows.append({
                        **forward,
                        "horizon_days": horizon,
                        "scope": "factor",
                        "factor": factor.get("name") or factor.get("factor") or "unknown",
                        "score": _safe_float(factor.get("score"), 0.5),
                        "confidence": _safe_float(factor.get("confidence"), 0.0),
                        "signal": factor.get("signal") or factor.get("direction"),
                        "direction": factor_direction,
                        "direction_label": _direction_label(factor_direction),
                    })

        horizon_results = []
        for horizon in requested_horizons:
            horizon_rows = [row for row in prediction_rows if row.get("horizon_days") == horizon]
            horizon_results.append({
                "horizon_days": horizon,
                **_summarize_prediction_rows(horizon_rows),
            })

        factor_results = []
        factor_names = sorted({row.get("factor") for row in factor_rows if row.get("factor")})
        for factor_name in factor_names:
            rows_for_factor = [row for row in factor_rows if row.get("factor") == factor_name]
            for horizon in requested_horizons:
                rows_for_factor_horizon = [
                    row for row in rows_for_factor if row.get("horizon_days") == horizon
                ]
                summary = _summarize_prediction_rows(rows_for_factor_horizon)
                if summary["samples"]:
                    factor_results.append({
                        "factor": factor_name,
                        "horizon_days": horizon,
                        **summary,
                    })

        total_samples = sum(item.get("samples", 0) for item in horizon_results)
        status = "ok" if total_samples else "insufficient_forward_returns"

        return {
            "status": status,
            "benchmark": benchmark,
            "period": period,
            "horizons": requested_horizons,
            "snapshot_count": len(snapshots),
            "skipped_snapshots": skipped_snapshots,
            "market_points": len(close_points),
            "horizon_results": horizon_results,
            "factor_results": factor_results,
            "sample_predictions": prediction_rows[-20:],
            "diagnostics": {
                "method": "historical_snapshot_forward_return",
                "note": "仅使用已落盘的宏观历史快照与之后真实基准收益对齐；样本不足时不回填或伪造命中率。",
            },
        }
    except Exception as exc:
        logger.error("Failed to run macro factor backtest: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
