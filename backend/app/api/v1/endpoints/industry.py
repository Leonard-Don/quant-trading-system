"""
行业分析 API 端点
提供热门行业识别和龙头股遴选功能
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Any, Dict, List, Literal, Optional
import logging
import time
import re
import threading
import json
import math
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.data.providers.sina_ths_adapter import map_ths_to_sina
from src.analytics.industry_stock_details import (
    backfill_stock_details_with_valuation,
    build_enriched_industry_stocks,
    extract_stock_detail_fields,
    has_meaningful_numeric,
    normalize_symbol,
)
from backend.app.services.industry_preferences import (
    industry_preferences_store,
    DEFAULT_ALERT_THRESHOLDS,
)
from src.utils.config import PROJECT_ROOT

from backend.app.schemas.industry import (
    IndustryRankResponse,
    StockResponse,
    LeaderStockResponse,
    LeaderDetailResponse,
    HeatmapResponse,
    HeatmapHistoryItem,
    HeatmapHistoryResponse,
    HeatmapDataItem,
    IndustryTrendResponse,
    ClusterResponse,
    IndustryRotationResponse,
    IndustryStockBuildStatusResponse,
    IndustryPreferencesResponse,
)

# 延迟导入分析模块，避免启动时错误
_industry_analyzer = None
_leader_scorer = None
_akshare_provider = None

logger = logging.getLogger(__name__)

router = APIRouter()

# 端点级别结果缓存（第二层防护，避免短时间内重复计算）
_endpoint_cache: dict = {}  # {key: {"data": ..., "ts": float}}
_ENDPOINT_CACHE_TTL = 180  # 3分钟
_stocks_full_build_executor = ThreadPoolExecutor(max_workers=2)
_stocks_full_build_lock = threading.Lock()
_stocks_full_build_inflight: set[str] = set()
_stocks_full_build_status: dict[str, dict] = {}
_heatmap_history_lock = threading.Lock()
_heatmap_history: list[dict] = []
_heatmap_history_loaded = False
_HEATMAP_HISTORY_MAX_ITEMS = 48
_HEATMAP_HISTORY_MAX_FILE_BYTES = 2 * 1024 * 1024
_HEATMAP_HISTORY_FILE = PROJECT_ROOT / "data" / "industry" / "heatmap_history.json"

# 独立的 Parity 缓存（评分一致性保障，TTL 更长）
_parity_cache: dict = {}  # {key: {"data": ..., "ts": float}}
_PARITY_CACHE_TTL = 1800  # 30分钟（评分在交易日内变化缓慢）

INDUSTRY_ETF_MAP: Dict[str, List[Dict[str, str]]] = {
    "半导体": [{"symbol": "SOXX", "market": "US"}, {"symbol": "512760.SS", "market": "CN"}],
    "芯片": [{"symbol": "SOXX", "market": "US"}, {"symbol": "159995.SZ", "market": "CN"}],
    "人工智能": [{"symbol": "AIQ", "market": "US"}, {"symbol": "CHAT", "market": "US"}],
    "软件": [{"symbol": "IGV", "market": "US"}, {"symbol": "515230.SS", "market": "CN"}],
    "新能源": [{"symbol": "ICLN", "market": "US"}, {"symbol": "516160.SS", "market": "CN"}],
    "光伏": [{"symbol": "TAN", "market": "US"}, {"symbol": "515790.SS", "market": "CN"}],
    "电池": [{"symbol": "LIT", "market": "US"}, {"symbol": "159755.SZ", "market": "CN"}],
    "医药": [{"symbol": "XLV", "market": "US"}, {"symbol": "512010.SS", "market": "CN"}],
    "医疗": [{"symbol": "XLV", "market": "US"}, {"symbol": "159883.SZ", "market": "CN"}],
    "消费": [{"symbol": "XLY", "market": "US"}, {"symbol": "159928.SZ", "market": "CN"}],
    "白酒": [{"symbol": "512690.SS", "market": "CN"}],
    "金融": [{"symbol": "XLF", "market": "US"}, {"symbol": "510230.SS", "market": "CN"}],
    "银行": [{"symbol": "KBE", "market": "US"}, {"symbol": "512800.SS", "market": "CN"}],
    "证券": [{"symbol": "KCE", "market": "US"}, {"symbol": "512880.SS", "market": "CN"}],
    "地产": [{"symbol": "VNQ", "market": "US"}, {"symbol": "512200.SS", "market": "CN"}],
    "军工": [{"symbol": "ITA", "market": "US"}, {"symbol": "512660.SS", "market": "CN"}],
    "能源": [{"symbol": "XLE", "market": "US"}, {"symbol": "159930.SZ", "market": "CN"}],
    "煤炭": [{"symbol": "KOL", "market": "US"}, {"symbol": "515220.SS", "market": "CN"}],
    "有色": [{"symbol": "XME", "market": "US"}, {"symbol": "512400.SS", "market": "CN"}],
    "汽车": [{"symbol": "CARZ", "market": "US"}, {"symbol": "516110.SS", "market": "CN"}],
}


def _normalize_sparkline_points(points: list[float], max_points: int = 20) -> list[float]:
    normalized = []
    for point in points or []:
        try:
            value = float(point)
        except (TypeError, ValueError):
            continue
        if value > 0:
            normalized.append(round(value, 3))
    if len(normalized) <= max_points:
        return normalized
    step = max(1, len(normalized) // max_points)
    sampled = normalized[::step][:max_points]
    if sampled[-1] != normalized[-1]:
        sampled[-1] = normalized[-1]
    return sampled


def _load_symbol_mini_trend(symbol: str) -> list[float]:
    scorer = get_leader_scorer()
    provider = getattr(scorer, "provider", None)
    if provider is None or not hasattr(provider, "get_historical_data"):
        return []

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=45)
        hist_data = provider.get_historical_data(symbol, start_date, end_date)
        if hist_data is None or hist_data.empty or "close" not in hist_data.columns:
            return []
        return _normalize_sparkline_points(hist_data["close"].tail(20).tolist(), max_points=20)
    except Exception as exc:
        logger.warning("Failed to load mini trend for leader %s: %s", symbol, exc)
        return []


def _attach_leader_mini_trends(leaders: list[LeaderStockResponse]) -> list[LeaderStockResponse]:
    if not leaders:
        return leaders

    symbols = [leader.symbol for leader in leaders if re.fullmatch(r"\d{6}", leader.symbol or "")]
    if not symbols:
        return leaders

    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as executor:
        trend_values = list(executor.map(_load_symbol_mini_trend, symbols))

    trend_map = {symbol: trend for symbol, trend in zip(symbols, trend_values)}
    for leader in leaders:
        leader.mini_trend = trend_map.get(leader.symbol, [])
    return leaders


def _get_endpoint_cache(key: str):
    """Get cached endpoint result if not expired"""
    entry = _endpoint_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _ENDPOINT_CACHE_TTL:
        return entry["data"]
    return None


def _set_endpoint_cache(key: str, data):
    """Set endpoint result cache (skip empty results)"""
    # 不缓存空结果，防止数据源临时故障时导致长时间返回空
    if data is None:
        return
    if isinstance(data, (list, tuple)) and len(data) == 0:
        return
    if isinstance(data, dict):
        # heatmap 返回的 industries 为空时不缓存
        industries = data.get("industries")
        if isinstance(industries, list) and len(industries) == 0:
            return
    _endpoint_cache[key] = {"data": data, "ts": time.time()}


def _get_stale_endpoint_cache(key: str):
    """获取过期缓存作为兜底。"""
    entry = _endpoint_cache.get(key)
    return entry["data"] if entry else None


def _get_stock_cache_keys(industry_name: str, top_n: int) -> tuple[str, str]:
    """生成行业成分股快/全量缓存键。"""
    return (
        f"stocks:quick:{industry_name}:{top_n}",
        f"stocks:full:{industry_name}:{top_n}",
    )


def _set_parity_cache(symbol: str, score_type: str, data):
    """保存列表评分快照到独立 parity 缓存"""
    if data is None:
        return
    key = f"{symbol}:{score_type}"
    _parity_cache[key] = {"data": data, "ts": time.time()}


def _get_parity_cache(symbol: str, score_type: str):
    """获取有效的 parity 缓存（未过期）"""
    key = f"{symbol}:{score_type}"
    entry = _parity_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _PARITY_CACHE_TTL:
        return entry["data"]
    return None


def _get_stale_parity_cache(symbol: str, score_type: str):
    """获取过期的 parity 缓存作为兜底（不检查 TTL）"""
    key = f"{symbol}:{score_type}"
    entry = _parity_cache.get(key)
    return entry["data"] if entry else None


def _map_industry_etfs(industry_name: str) -> List[Dict[str, str]]:
    normalized = str(industry_name or "")
    matches: List[Dict[str, str]] = []
    for keyword, etfs in INDUSTRY_ETF_MAP.items():
        if keyword in normalized:
            matches.extend(etfs)
    if not matches:
        matches = [{"symbol": "SPY", "market": "US"}, {"symbol": "510300.SS", "market": "CN"}]
    seen = set()
    result = []
    for item in matches:
        key = item["symbol"]
        if key in seen:
            continue
        seen.add(key)
        result.append({**item, "reason": f"{industry_name} ETF proxy"})
    return result


def _classify_industry_lifecycle(row: Dict[str, Any]) -> Dict[str, Any]:
    score = float(row.get("score") or row.get("total_score") or 0)
    momentum = float(row.get("momentum") or 0)
    change_pct = float(row.get("change_pct") or 0)
    flow = float(row.get("money_flow") or row.get("flow_strength") or 0)
    volatility = abs(float(row.get("industry_volatility") or 0))

    if score >= 75 and momentum > 0 and flow >= 0:
        stage = "成长期"
        confidence = min(0.95, 0.55 + score / 200)
    elif score >= 60 and abs(momentum) <= 8 and volatility < 8:
        stage = "成熟期"
        confidence = min(0.9, 0.5 + score / 220)
    elif change_pct < -3 or momentum < -8:
        stage = "衰退期"
        confidence = min(0.9, 0.55 + abs(momentum) / 50)
    else:
        stage = "导入期"
        confidence = 0.55

    return {
        "stage": stage,
        "confidence": round(float(confidence), 3),
        "drivers": {
            "score": round(score, 3),
            "momentum": round(momentum, 3),
            "change_pct": round(change_pct, 3),
            "money_flow": round(flow, 3),
            "volatility": round(volatility, 3),
        },
    }


def _build_industry_events(industry_name: str) -> List[Dict[str, Any]]:
    now = datetime.now()
    base_events = [
        {"name": "财报密集披露窗口", "offset_days": 14, "type": "earnings", "impact": "fundamental"},
        {"name": "月度宏观/行业数据窗口", "offset_days": 20, "type": "macro_data", "impact": "demand"},
        {"name": "政策/监管观察窗口", "offset_days": 35, "type": "policy", "impact": "valuation"},
    ]
    if any(keyword in industry_name for keyword in ("新能源", "光伏", "电池", "汽车")):
        base_events.append({"name": "新能源产业链价格与装机数据", "offset_days": 10, "type": "industry_data", "impact": "margin"})
    if any(keyword in industry_name for keyword in ("半导体", "芯片", "人工智能", "软件")):
        base_events.append({"name": "科技产品发布/供应链景气跟踪", "offset_days": 21, "type": "product_cycle", "impact": "growth"})
    return [
        {
            "date": (now + timedelta(days=item["offset_days"])).strftime("%Y-%m-%d"),
            "title": item["name"],
            "event_type": item["type"],
            "expected_impact": item["impact"],
            "industry_name": industry_name,
        }
        for item in base_events
    ]


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return model


def _format_storage_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def _trim_heatmap_history_payload(payload: list[dict]) -> list[dict]:
    trimmed = list(payload[:_HEATMAP_HISTORY_MAX_ITEMS])
    while trimmed:
        encoded = json.dumps(trimmed, ensure_ascii=False, indent=2).encode("utf-8")
        if len(encoded) <= _HEATMAP_HISTORY_MAX_FILE_BYTES:
            break
        trimmed = trimmed[:-1]
    return trimmed


def _resolve_industry_profile(request: Request | None) -> str:
    if request is None:
        return "default"
    return request.headers.get("X-Industry-Profile", "default")


def _get_stock_status_key(industry_name: str, top_n: int) -> str:
    return f"{industry_name}:{top_n}"


def _set_stock_build_status(industry_name: str, top_n: int, status: str, rows: int = 0, message: Optional[str] = None) -> None:
    _stocks_full_build_status[_get_stock_status_key(industry_name, top_n)] = {
        "industry_name": industry_name,
        "top_n": top_n,
        "status": status,
        "rows": int(rows or 0),
        "message": message,
        "updated_at": datetime.now().isoformat(),
    }


def _get_stock_build_status(industry_name: str, top_n: int) -> dict:
    _, full_cache_key = _get_stock_cache_keys(industry_name, top_n)
    cached = _get_endpoint_cache(full_cache_key)
    if cached is not None:
        return {
            "industry_name": industry_name,
            "top_n": top_n,
            "status": "ready",
            "rows": len(cached),
            "message": "完整版成分股缓存已就绪",
            "updated_at": datetime.now().isoformat(),
        }
    return _stocks_full_build_status.get(
        _get_stock_status_key(industry_name, top_n),
        {
            "industry_name": industry_name,
            "top_n": top_n,
            "status": "idle",
            "rows": 0,
            "message": "当前尚未开始构建完整版成分股缓存",
            "updated_at": datetime.now().isoformat(),
        },
    )


def _load_heatmap_history_from_disk() -> None:
    global _heatmap_history_loaded
    with _heatmap_history_lock:
        if _heatmap_history_loaded:
            return
        try:
            if _HEATMAP_HISTORY_FILE.exists():
                file_size = _HEATMAP_HISTORY_FILE.stat().st_size
                with open(_HEATMAP_HISTORY_FILE, "r", encoding="utf-8") as file:
                    payload = json.load(file)
                    if isinstance(payload, list):
                        _heatmap_history[:] = _trim_heatmap_history_payload(payload)
                logger.info(
                    "Loaded heatmap history snapshots from disk (%s, snapshots=%s)",
                    _format_storage_size(file_size),
                    len(_heatmap_history),
                )
        except Exception as exc:
            logger.warning("Failed to load heatmap history from disk: %s", exc)
        _heatmap_history_loaded = True


def _persist_heatmap_history_to_disk() -> None:
    try:
        _HEATMAP_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = _trim_heatmap_history_payload(_heatmap_history)
        _heatmap_history[:] = payload
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        with open(_HEATMAP_HISTORY_FILE, "w", encoding="utf-8") as file:
            file.write(serialized)
        logger.info(
            "Persisted heatmap history snapshots (%s, snapshots=%s)",
            _format_storage_size(len(serialized.encode('utf-8'))),
            len(payload),
        )
    except Exception as exc:
        logger.warning("Failed to persist heatmap history: %s", exc)


def _append_heatmap_history(days: int, result: HeatmapResponse):
    if not result or not getattr(result, "industries", None):
        return
    _load_heatmap_history_from_disk()

    entry = {
        "snapshot_id": f"{days}:{result.update_time}",
        "days": days,
        "captured_at": datetime.now().isoformat(),
        "update_time": result.update_time,
        "max_value": result.max_value,
        "min_value": result.min_value,
        "industries": [_model_to_dict(item) for item in result.industries],
    }

    with _heatmap_history_lock:
        existing_index = next(
            (
                index for index, item in enumerate(_heatmap_history)
                if item.get("days") == days and item.get("update_time") == result.update_time
            ),
            -1,
        )
        if existing_index >= 0:
            _heatmap_history[existing_index] = entry
        else:
            _heatmap_history.insert(0, entry)
            del _heatmap_history[_HEATMAP_HISTORY_MAX_ITEMS:]
        _persist_heatmap_history_to_disk()

def _resolve_symbol_with_provider(symbol_or_name: str) -> str:
    """允许详情接口和龙头列表同时接受代码或股票名。"""
    normalized = normalize_symbol(symbol_or_name)
    if re.fullmatch(r"\d{6}", normalized):
        return normalized

    provider = _get_or_create_provider()
    if hasattr(provider, "get_symbol_by_name"):
        try:
            resolved = normalize_symbol(provider.get_symbol_by_name(symbol_or_name))
            if re.fullmatch(r"\d{6}", resolved):
                return resolved
        except Exception as e:
            logger.warning(f"Failed to resolve symbol '{symbol_or_name}': {e}")

    return normalized


def _build_stock_responses(
    stocks: List[dict],
    industry_name: str,
    top_n: int,
    score_stage: Optional[str] = None,
) -> List[StockResponse]:
    """将 provider 返回的原始成分股标准化为接口响应。"""
    normalized_stocks = []
    for idx, stock in enumerate(stocks[:top_n], 1):
        symbol = normalize_symbol(stock.get("symbol") or stock.get("code") or "")
        if not symbol:
            continue
        detail_fields = extract_stock_detail_fields(stock)

        normalized_stocks.append(
            StockResponse(
                symbol=symbol,
                name=stock.get("name", ""),
                rank=int(stock.get("rank") or idx),
                total_score=float(stock.get("total_score") or 0),
                scoreStage=score_stage,
                market_cap=detail_fields.get("market_cap"),
                pe_ratio=detail_fields.get("pe_ratio"),
                change_pct=detail_fields.get("change_pct"),
                money_flow=detail_fields.get("money_flow"),
                turnover_rate=detail_fields.get("turnover_rate") or detail_fields.get("turnover"),
                industry=industry_name,
            )
        )

    return normalized_stocks


def _count_quick_stock_detail_fields(stock: Dict[str, Any]) -> int:
    detail_fields = extract_stock_detail_fields(stock)
    return sum([
        1 if has_meaningful_numeric(detail_fields.get("market_cap")) else 0,
        1 if has_meaningful_numeric(detail_fields.get("pe_ratio")) else 0,
        1 if detail_fields.get("money_flow") is not None else 0,
        1 if has_meaningful_numeric(detail_fields.get("turnover_rate")) else 0,
    ])


def _promote_detail_ready_quick_rows(
    stocks: List[Dict[str, Any]],
    visible_top_n: int = 5,
    detail_target: int = 2,
) -> List[Dict[str, Any]]:
    """在 quick 阶段尽量让首屏先出现有真实明细的成分股。"""
    if not stocks:
        return stocks

    front_size = min(len(stocks), visible_top_n)
    target_count = min(detail_target, front_size)
    front_rows = list(stocks[:front_size])
    back_rows = list(stocks[front_size:])

    front_detail_indexes = [
        index for index, stock in enumerate(front_rows)
        if _count_quick_stock_detail_fields(stock) > 0
    ]
    if len(front_detail_indexes) >= target_count:
        return stocks

    promoted_rows: List[Dict[str, Any]] = []
    remaining_back_rows: List[Dict[str, Any]] = []
    needed_promotions = target_count - len(front_detail_indexes)

    for stock in back_rows:
        if len(promoted_rows) < needed_promotions and _count_quick_stock_detail_fields(stock) > 0:
            promoted_rows.append(stock)
            continue
        remaining_back_rows.append(stock)

    if not promoted_rows:
        return stocks

    replacement_positions = [
        index for index, stock in reversed(list(enumerate(front_rows)))
        if _count_quick_stock_detail_fields(stock) == 0
    ][:len(promoted_rows)]
    if not replacement_positions:
        return stocks

    replacement_positions_set = set(replacement_positions)
    kept_front_rows = [
        stock for index, stock in enumerate(front_rows)
        if index not in replacement_positions_set
    ]
    displaced_front_rows = [
        stock for index, stock in enumerate(front_rows)
        if index in replacement_positions_set
    ]
    return kept_front_rows + promoted_rows + displaced_front_rows + remaining_back_rows


def _build_full_industry_stock_response(
    industry_name: str,
    top_n: int,
    provider=None,
) -> List[StockResponse]:
    """构造完整版行业成分股结果（评分排序 + 明细补齐 + 估值回填）。"""
    scorer = get_leader_scorer()
    provider = provider or _get_or_create_provider()

    ranked_stocks = scorer.rank_stocks_in_industry(industry_name, top_n=top_n)
    provider_stocks = provider.get_stock_list_by_industry(industry_name)

    if ranked_stocks:
        enriched_stocks = build_enriched_industry_stocks(
            provider,
            industry_name,
            ranked_stocks=ranked_stocks,
            provider_stocks=provider_stocks,
        )
        return _build_stock_responses(enriched_stocks, industry_name, top_n, score_stage="full")

    if provider_stocks:
        fallback_stocks = build_enriched_industry_stocks(
            provider,
            industry_name,
            provider_stocks=provider_stocks,
        )
        return _build_stock_responses(fallback_stocks, industry_name, top_n, score_stage="full")

    return []


def _build_quick_industry_stock_response(
    industry_name: str,
    top_n: int,
    provider_stocks: List[dict],
    provider=None,
    enable_valuation_backfill: bool = True,
) -> List[StockResponse]:
    """构造快速版行业成分股结果（仅用现有行情做轻量评分，不做估值回填）。"""
    if not provider_stocks:
        return []

    try:
        scorer = get_leader_scorer()
        provider = provider or getattr(scorer, "provider", None) or _get_or_create_provider()
        industry_stats = scorer.calculate_industry_stats(provider_stocks)
        quick_scored_stocks = []
        for stock in provider_stocks:
            quick_score = scorer.score_stock_from_industry_snapshot(
                stock,
                industry_stats,
                score_type="core",
            )
            quick_scored_stocks.append({
                **stock,
                "symbol": quick_score.get("symbol") or stock.get("symbol"),
                "name": quick_score.get("name") or stock.get("name"),
                "total_score": quick_score.get("total_score"),
            })
        quick_scored_stocks.sort(
            key=lambda item: float(item.get("total_score") or 0),
            reverse=True,
        )

        quick_display_stocks = quick_scored_stocks[:top_n]
        if provider is not None:
            # 本地快照首屏优先保证尽快可渲染，避免首次请求重新被估值回填拖回远端冷启动。
            if enable_valuation_backfill:
                quick_display_stocks = backfill_stock_details_with_valuation(quick_display_stocks, provider)
            quick_display_stocks = _promote_detail_ready_quick_rows(quick_display_stocks)

        for idx, stock in enumerate(quick_display_stocks, 1):
            stock["rank"] = idx
        return _build_stock_responses(quick_display_stocks, industry_name, top_n, score_stage="quick")
    except Exception as e:
        logger.warning(f"Failed to build quick stock scores for {industry_name}: {e}")
        return _build_stock_responses(provider_stocks, industry_name, top_n, score_stage="quick")


def _coerce_trend_alignment_stock_rows(stocks: List[Any]) -> List[Dict[str, Any]]:
    """将 StockResponse / dict 统一转成趋势面板可复用的成分股字典。"""
    rows: List[Dict[str, Any]] = []
    for stock in stocks or []:
        payload = _model_to_dict(stock)
        symbol = normalize_symbol(payload.get("symbol") or payload.get("code") or "")
        if not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "code": symbol,
                "name": payload.get("name", ""),
                "market_cap": payload.get("market_cap"),
                "pe_ratio": payload.get("pe_ratio"),
                "change_pct": payload.get("change_pct"),
                "money_flow": payload.get("money_flow"),
                "turnover_rate": payload.get("turnover_rate"),
                "turnover": payload.get("turnover_rate"),
                "total_score": payload.get("total_score"),
            }
        )
    return rows


def _load_trend_alignment_stock_rows(
    industry_name: str,
    expected_count: int,
    provider=None,
) -> List[Dict[str, Any]]:
    """
    为趋势详情加载一组与弹窗成分股列表更一致的股票行。

    这里优先复用 stocks 接口缓存；若没有缓存，再走 quick 构建，避免趋势接口被完整评分阻塞。
    """
    provider = provider or _get_or_create_provider()
    target_top_n = min(max(int(expected_count or 0), 12), 30) if expected_count else 20
    quick_cache_key, full_cache_key = _get_stock_cache_keys(industry_name, target_top_n)

    cached_rows = _get_endpoint_cache(full_cache_key)
    if cached_rows is None:
        cached_rows = _get_endpoint_cache(quick_cache_key)
    if cached_rows is not None:
        return _coerce_trend_alignment_stock_rows(cached_rows)

    provider_rows: List[Dict[str, Any]] = []
    cached_stock_loader = getattr(provider, "get_cached_stock_list_by_industry", None)
    if callable(cached_stock_loader):
        try:
            provider_rows = cached_stock_loader(industry_name) or []
        except Exception as exc:
            logger.warning("Failed to load cached trend-alignment stocks for %s: %s", industry_name, exc)

    if not provider_rows:
        try:
            provider_rows = provider.get_stock_list_by_industry(industry_name) or []
        except Exception as exc:
            logger.warning("Failed to load provider trend-alignment stocks for %s: %s", industry_name, exc)
            provider_rows = []

    if provider_rows:
        quick_rows = _build_quick_industry_stock_response(
            industry_name,
            target_top_n,
            provider_rows,
            provider=provider,
            enable_valuation_backfill=False,
        )
        if quick_rows:
            return _coerce_trend_alignment_stock_rows(quick_rows)

    full_rows = _build_full_industry_stock_response(
        industry_name,
        target_top_n,
        provider=provider,
    )
    return _coerce_trend_alignment_stock_rows(full_rows)


def _build_trend_summary_from_stock_rows(
    stocks: List[Dict[str, Any]],
    expected_count: int,
    fallback_total_market_cap: float = 0.0,
    fallback_avg_pe: float = 0.0,
) -> Dict[str, Any]:
    """根据统一股票列表重建趋势面板的成分股摘要字段。"""
    expected_count = max(int(expected_count or 0), 0)
    expected_count_base = max(expected_count, 1)

    detailed_stocks = []
    valid_change_stocks = []
    for stock in stocks or []:
        detail = extract_stock_detail_fields(stock)
        enriched_stock = {**stock, **detail}
        detailed_stocks.append(enriched_stock)
        if detail.get("change_pct") is not None:
            valid_change_stocks.append(enriched_stock)

    valid_market_caps = [
        stock["market_cap"]
        for stock in detailed_stocks
        if has_meaningful_numeric(stock.get("market_cap"))
    ]
    valid_pe_ratios = [
        stock["pe_ratio"]
        for stock in detailed_stocks
        if stock.get("pe_ratio") is not None and 0 < stock["pe_ratio"] < 500
    ]
    valid_pe_weighted_pairs = [
        (stock["market_cap"], stock["pe_ratio"])
        for stock in detailed_stocks
        if has_meaningful_numeric(stock.get("market_cap"))
        and stock.get("pe_ratio") is not None
        and 0 < stock["pe_ratio"] < 500
    ]

    total_market_cap = sum(float(value) for value in valid_market_caps)
    total_market_cap_fallback = False
    if not total_market_cap and fallback_total_market_cap > 0:
        total_market_cap = float(fallback_total_market_cap)
        total_market_cap_fallback = True

    if valid_pe_weighted_pairs:
        total_pe_market_cap = sum(float(market_cap) for market_cap, _ in valid_pe_weighted_pairs)
        total_earnings_proxy = sum(
            float(market_cap) / float(pe_ratio)
            for market_cap, pe_ratio in valid_pe_weighted_pairs
            if float(pe_ratio) > 0
        )
        avg_pe = (total_pe_market_cap / total_earnings_proxy) if total_pe_market_cap > 0 and total_earnings_proxy > 0 else None
    elif valid_pe_ratios:
        avg_pe = sum(float(value) for value in valid_pe_ratios) / len(valid_pe_ratios)
    else:
        avg_pe = None

    avg_pe_fallback = False
    if avg_pe is None and fallback_avg_pe > 0:
        avg_pe = float(fallback_avg_pe)
        avg_pe_fallback = True

    stock_coverage_ratio = min(len(stocks) / expected_count_base, 1.0) if expected_count > 0 else (1.0 if stocks else 0.0)
    change_coverage_ratio = min(len(valid_change_stocks) / expected_count_base, 1.0) if expected_count > 0 else (1.0 if valid_change_stocks else 0.0)
    market_cap_coverage_ratio = min(len(valid_market_caps) / expected_count_base, 1.0) if expected_count > 0 else (1.0 if valid_market_caps else 0.0)
    pe_coverage_base = len(valid_pe_weighted_pairs) if valid_pe_weighted_pairs else len(valid_pe_ratios)
    pe_coverage_ratio = min(pe_coverage_base / expected_count_base, 1.0) if expected_count > 0 else (1.0 if pe_coverage_base > 0 else 0.0)

    top_gainers = sorted(valid_change_stocks, key=lambda item: item.get("change_pct", 0), reverse=True)[:5]
    top_losers = sorted(valid_change_stocks, key=lambda item: item.get("change_pct", 0))[:5]
    rise_count = sum(1 for item in valid_change_stocks if item.get("change_pct", 0) > 0)
    fall_count = sum(1 for item in valid_change_stocks if item.get("change_pct", 0) < 0)
    flat_count = sum(1 for item in valid_change_stocks if item.get("change_pct", 0) == 0)

    note = None
    degraded = False
    if len(stocks) <= 3 and expected_count > 10:
        degraded = True
        note = f"成分股列表可能不完整（获取到 {len(stocks)} 只，预期约 {expected_count} 只）。当前展示可能存在偏差。"
    elif len(stocks) == 1:
        note = "该行业目前仅获取到单只成分股明细，分布数据仅供参考。"

    return {
        "stock_count": len(stocks),
        "expected_stock_count": expected_count,
        "total_market_cap": total_market_cap,
        "avg_pe": round(avg_pe, 2) if avg_pe is not None and not (isinstance(avg_pe, float) and math.isnan(avg_pe)) else 0,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "rise_count": rise_count,
        "fall_count": fall_count,
        "flat_count": flat_count,
        "stock_coverage_ratio": round(stock_coverage_ratio, 4),
        "change_coverage_ratio": round(change_coverage_ratio, 4),
        "market_cap_coverage_ratio": round(market_cap_coverage_ratio, 4),
        "pe_coverage_ratio": round(pe_coverage_ratio, 4),
        "total_market_cap_fallback": total_market_cap_fallback,
        "avg_pe_fallback": avg_pe_fallback,
        "degraded": degraded,
        "note": note,
    }


def _should_align_trend_with_stock_rows(
    trend_data: Dict[str, Any],
    stock_rows: List[Dict[str, Any]],
) -> bool:
    """判断趋势摘要是否应该回收成分股列表口径。"""
    if not stock_rows:
        return False

    trend_count = int(trend_data.get("stock_count", 0) or 0)
    expected_count = int(trend_data.get("expected_stock_count", 0) or 0)
    aligned_count = len(stock_rows)

    if trend_data.get("degraded") and aligned_count > trend_count:
        return True
    if trend_count <= 3 and aligned_count >= 5:
        return True
    if expected_count > 0 and trend_count > max(expected_count * 2, expected_count + 15):
        return aligned_count >= min(max(expected_count // 3, 4), 30)
    return False


def _schedule_full_stock_cache_build(
    industry_name: str,
    top_n: int,
) -> None:
    """异步构建完整版行业成分股缓存。"""
    _, full_cache_key = _get_stock_cache_keys(industry_name, top_n)
    if _get_endpoint_cache(full_cache_key) is not None:
        return

    with _stocks_full_build_lock:
        if full_cache_key in _stocks_full_build_inflight:
            return
        _stocks_full_build_inflight.add(full_cache_key)
        _set_stock_build_status(industry_name, top_n, "building", rows=0, message="完整版成分股缓存构建中")

    def _task():
        started_at = time.time()
        try:
            logger.info(
                "Building full stock cache for %s (top_n=%s)",
                industry_name,
                top_n,
            )
            result = _build_full_industry_stock_response(industry_name, top_n)
            if result:
                _set_endpoint_cache(full_cache_key, result)
                _set_stock_build_status(
                    industry_name,
                    top_n,
                    "ready",
                    rows=len(result),
                    message="完整版成分股缓存构建完成",
                )
                logger.info(
                    "Built full stock cache for %s (top_n=%s, rows=%s, elapsed=%.2fs)",
                    industry_name,
                    top_n,
                    len(result),
                    time.time() - started_at,
                )
            else:
                _set_stock_build_status(
                    industry_name,
                    top_n,
                    "failed",
                    rows=0,
                    message="完整版成分股缓存构建返回空结果",
                )
                logger.warning(
                    "Full stock cache build returned empty for %s (top_n=%s, elapsed=%.2fs)",
                    industry_name,
                    top_n,
                    time.time() - started_at,
                )
        except Exception as e:
            _set_stock_build_status(
                industry_name,
                top_n,
                "failed",
                rows=0,
                message=f"构建失败: {e}",
            )
            logger.warning(f"Failed to build full stock cache for {industry_name}: {e}")
        finally:
            with _stocks_full_build_lock:
                _stocks_full_build_inflight.discard(full_cache_key)

    _stocks_full_build_executor.submit(_task)


def _dedupe_leader_responses(leaders: List[LeaderStockResponse]) -> List[LeaderStockResponse]:
    """按 symbol 去重，保留总分更高、信息更完整的记录。"""
    best_by_symbol: dict[str, LeaderStockResponse] = {}

    for leader in leaders:
        symbol = normalize_symbol(getattr(leader, "symbol", ""))
        if not re.fullmatch(r"\d{6}", symbol):
            continue

        leader.symbol = symbol
        current = best_by_symbol.get(symbol)
        if current is None:
            best_by_symbol[symbol] = leader
            continue

        current_score = float(getattr(current, "total_score", 0) or 0)
        next_score = float(getattr(leader, "total_score", 0) or 0)
        current_cap = float(getattr(current, "market_cap", 0) or 0)
        next_cap = float(getattr(leader, "market_cap", 0) or 0)

        if (next_score, next_cap) > (current_score, current_cap):
            best_by_symbol[symbol] = leader

    deduped = list(best_by_symbol.values())
    deduped.sort(key=lambda item: float(getattr(item, "total_score", 0) or 0), reverse=True)
    for idx, leader in enumerate(deduped, 1):
        leader.global_rank = idx
    return deduped


def _get_or_create_provider():
    """获取或创建数据提供器实例（共用逻辑）"""
    global _akshare_provider
    if _akshare_provider is None:
        try:
            from src.data.providers.sina_ths_adapter import create_industry_provider
            _akshare_provider = create_industry_provider()
        except Exception as e:
            logger.warning(f"Failed to create provider via factory: {e}")
            from src.data.providers.sina_ths_adapter import SinaIndustryAdapter
            _akshare_provider = SinaIndustryAdapter()
    return _akshare_provider


def get_industry_analyzer():
    """获取行业分析器实例（延迟初始化，自动选择数据源）"""
    global _industry_analyzer
    
    if _industry_analyzer is None:
        try:
            from src.analytics.industry_analyzer import IndustryAnalyzer
            provider = _get_or_create_provider()
            _industry_analyzer = IndustryAnalyzer(provider)
            logger.info(f"Industry analyzer initialized with {type(provider).__name__}")
        except Exception as e:
            logger.error(f"Failed to initialize industry analyzer: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Industry analyzer initialization failed: {str(e)}"
            )
    
    return _industry_analyzer


def get_leader_scorer():
    """获取龙头股评分器实例（延迟初始化）"""
    global _leader_scorer
    
    if _leader_scorer is None:
        try:
            from src.analytics.leader_stock_scorer import LeaderStockScorer
            provider = _get_or_create_provider()
            _leader_scorer = LeaderStockScorer(provider)
            logger.info(f"Leader stock scorer initialized with {type(provider).__name__}")
        except Exception as e:
            logger.error(f"Failed to initialize leader scorer: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Leader scorer initialization failed: {str(e)}"
            )
    
    return _leader_scorer


@router.get("/industries/hot", response_model=List[IndustryRankResponse])
def get_hot_industries(
    top_n: int = Query(10, ge=1, le=50, description="返回前N个热门行业"),
    lookback_days: int = Query(5, ge=1, le=30, description="回看周期（天）"),
    sort_by: str = Query("total_score", description="排序字段: total_score, change_pct, money_flow, industry_volatility"),
    order: str = Query("desc", description="排序顺序: desc, asc")
) -> List[IndustryRankResponse]:
    """
    获取热门行业排名
    
    基于动量、资金流向和成交量变化综合评分，识别当前市场关注度高的行业。
    
    - **top_n**: 返回排名前 N 的行业
    - **lookback_days**: 用于计算动量和资金流向的回看周期
    - **sort_by**: 排序字段 (total_score, change_pct, money_flow, industry_volatility)
    - **order**: 排序顺序 (desc, asc)
    """
    try:
        # 端点级缓存
        cache_key = f"hot:v3:{top_n}:{lookback_days}:{sort_by}:{order}"
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

        analyzer = get_industry_analyzer()
        ascending = (order.lower() == "asc")
        hot_industries = analyzer.rank_industries(
            top_n=top_n,
            sort_by=sort_by,
            ascending=ascending,
            lookback_days=lookback_days
        )
        
        result = [
            IndustryRankResponse(
                rank=ind.get("rank", 0),
                industry_name=ind.get("industry_name", ""),
                score=ind.get("score", 0),
                momentum=ind.get("momentum", 0),
                change_pct=ind.get("change_pct", 0),
                money_flow=ind.get("money_flow", 0),
                flow_strength=ind.get("flow_strength", 0),
                industryVolatility=ind.get("industry_volatility", 0),
                industryVolatilitySource=ind.get("industry_volatility_source", "unavailable"),
                stock_count=ind.get("stock_count", 0),
                total_market_cap=ind.get("total_market_cap", 0),
                marketCapSource=ind.get("market_cap_source", "unknown"),
                mini_trend=ind.get("mini_trend", []),
                score_breakdown=analyzer.build_rank_score_breakdown(ind),
            )
            for ind in hot_industries
        ]
        _set_endpoint_cache(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting hot industries: {e}")
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning(f"Using stale cache for hot industries: {cache_key}")
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/{industry_name}/stocks", response_model=List[StockResponse])
def get_industry_stocks(
    industry_name: str,
    top_n: int = Query(20, ge=1, le=100, description="返回前N只股票")
) -> List[StockResponse]:
    """
    获取行业成分股及排名
    
    返回指定行业内按综合得分排名的股票列表。
    
    - **industry_name**: 行业名称（如 "电子"、"医药生物"）
    - **top_n**: 返回排名前 N 的股票
    """
    quick_cache_key, full_cache_key = _get_stock_cache_keys(industry_name, top_n)
    try:
        full_cached = _get_endpoint_cache(full_cache_key)
        if full_cached is not None:
            return full_cached

        quick_cached = _get_endpoint_cache(quick_cache_key)
        if quick_cached is not None:
            _schedule_full_stock_cache_build(industry_name, top_n)
            return quick_cached

        provider = _get_or_create_provider()
        cached_provider_rows = []
        cached_stock_loader = getattr(provider, "get_cached_stock_list_by_industry", None)
        if callable(cached_stock_loader):
            try:
                cached_provider_rows = cached_stock_loader(industry_name)
            except Exception as e:
                logger.warning(f"Failed to load cached industry stocks for {industry_name}: {e}")

        if cached_provider_rows:
            quick_result = _build_quick_industry_stock_response(
                industry_name,
                top_n,
                cached_provider_rows,
                provider=provider,
                enable_valuation_backfill=False,
            )
            _set_endpoint_cache(quick_cache_key, quick_result)
            _schedule_full_stock_cache_build(industry_name, top_n)
            return quick_result

        provider_stocks = provider.get_stock_list_by_industry(industry_name)

        # 首次请求优先返回 provider 的原始行业成分股，避免评分排序和估值回填阻塞首屏。
        if provider_stocks:
            quick_result = _build_quick_industry_stock_response(
                industry_name,
                top_n,
                provider_stocks,
                provider=provider,
            )
            _set_endpoint_cache(quick_cache_key, quick_result)
            _schedule_full_stock_cache_build(industry_name, top_n)
            return quick_result

        # provider 明细为空时，同步退回完整版构建逻辑，避免接口直接空掉。
        full_result = _build_full_industry_stock_response(industry_name, top_n, provider=provider)
        _set_endpoint_cache(full_cache_key, full_result)
        return full_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry stocks: {e}")
        stale = _get_stale_endpoint_cache(full_cache_key)
        if stale is None:
            stale = _get_stale_endpoint_cache(quick_cache_key)
        if stale is not None:
            logger.warning(
                f"Using stale cache for industry stocks: {full_cache_key} / {quick_cache_key}"
            )
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/{industry_name}/stocks/status", response_model=IndustryStockBuildStatusResponse)
def get_industry_stock_build_status(
    industry_name: str,
    top_n: int = Query(20, ge=1, le=100, description="返回前N只股票"),
) -> IndustryStockBuildStatusResponse:
    status = _get_stock_build_status(industry_name, top_n)
    return IndustryStockBuildStatusResponse(**status)


@router.get("/industries/{industry_name}/stocks/stream")
async def stream_industry_stock_build_status(
    industry_name: str,
    top_n: int = Query(20, ge=1, le=100, description="返回前N只股票"),
):
    async def event_generator():
        emitted = None
        started_at = time.time()
        while True:
            status = _get_stock_build_status(industry_name, top_n)
            payload = json.dumps(status, ensure_ascii=False)
            if payload != emitted:
                emitted = payload
                yield f"data: {payload}\n\n"

            if status.get("status") in {"ready", "failed"}:
                break
            if (time.time() - started_at) > 30:
                break
            await __import__("asyncio").sleep(0.75)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/industries/heatmap", response_model=HeatmapResponse)
def get_industry_heatmap(
    days: int = Query(5, ge=1, le=90, description="分析周期（天）")
) -> HeatmapResponse:
    """
    获取行业热力图数据
    
    返回所有行业的涨跌幅和市值数据，用于渲染热力图可视化。
    """
    try:
        # 端点级缓存
        cache_key = f"heatmap:v2:{days}"
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

        analyzer = get_industry_analyzer()
        heatmap_data = analyzer.get_industry_heatmap_data(days=days)
        
        result = HeatmapResponse(
            industries=[
                HeatmapDataItem(
                    name=ind.get("name", ""),
                    value=ind.get("value", 0),
                    total_score=ind.get("total_score", 0),
                    size=ind.get("size", 0),
                    stockCount=ind.get("stockCount", 0),
                    moneyFlow=ind.get("moneyFlow", 0),
                    turnoverRate=ind.get("turnoverRate", 0),
                    industryVolatility=ind.get("industryVolatility", 0),
                    industryVolatilitySource=ind.get("industryVolatilitySource", "unavailable"),
                    netInflowRatio=ind.get("netInflowRatio", 0),
                    leadingStock=str(ind["leadingStock"]) if ind.get("leadingStock") and ind["leadingStock"] != 0 else None,
                    sizeSource=ind.get("sizeSource", "estimated"),
                    marketCapSource=ind.get("marketCapSource", "unknown"),
                    marketCapSnapshotAgeHours=ind.get("marketCapSnapshotAgeHours"),
                    marketCapSnapshotIsStale=ind.get("marketCapSnapshotIsStale", False),
                    valuationSource=ind.get("valuationSource", "unavailable"),
                    valuationQuality=ind.get("valuationQuality", "unavailable"),
                    dataSources=ind.get("dataSources", []),
                    # THS 增强字段
                    industryIndex=ind.get("industryIndex", 0),
                    totalInflow=ind.get("totalInflow", 0),
                    totalOutflow=ind.get("totalOutflow", 0),
                    leadingStockChange=ind.get("leadingStockChange", 0),
                    leadingStockPrice=ind.get("leadingStockPrice", 0),
                    # AKShare 估值增强字段
                    pe_ttm=ind.get("pe_ttm"),
                    pb=ind.get("pb"),
                    dividend_yield=ind.get("dividend_yield"),
                )

                for ind in heatmap_data.get("industries", [])
            ],
            max_value=heatmap_data.get("max_value", 0),
            min_value=heatmap_data.get("min_value", 0),
            update_time=heatmap_data.get("update_time", ""),
        )
        # 不缓存空结果，避免 API 临时故障导致持续返回空数据
        if result.industries:
            _set_endpoint_cache(cache_key, result)
            _append_heatmap_history(days, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry heatmap: {e}")
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning(f"Using stale cache for heatmap: {cache_key}")
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/heatmap/history", response_model=HeatmapHistoryResponse)
def get_industry_heatmap_history(
    limit: int = Query(10, ge=1, le=50, description="返回快照数量"),
    days: Optional[int] = Query(None, ge=1, le=90, description="按周期过滤"),
) -> HeatmapHistoryResponse:
    """
    获取行业热力图历史快照。

    用于行业热度模块的历史回放。当前返回服务端近期保留的快照窗口。
    """
    _load_heatmap_history_from_disk()
    with _heatmap_history_lock:
        items = list(_heatmap_history)

    if days is not None:
        items = [item for item in items if int(item.get("days", 0) or 0) == days]

    history_items = [
        HeatmapHistoryItem(
            snapshot_id=item.get("snapshot_id", ""),
            days=item.get("days", 0),
            captured_at=item.get("captured_at", ""),
            update_time=item.get("update_time", ""),
            max_value=item.get("max_value", 0),
            min_value=item.get("min_value", 0),
            industries=[
                HeatmapDataItem(**industry_item)
                for industry_item in item.get("industries", [])
            ],
        )
        for item in items[:limit]
    ]
    return HeatmapHistoryResponse(items=history_items)


@router.get("/preferences", response_model=IndustryPreferencesResponse)
def get_industry_preferences(request: Request) -> IndustryPreferencesResponse:
    profile_id = _resolve_industry_profile(request)
    return IndustryPreferencesResponse(**industry_preferences_store.get_preferences(profile_id=profile_id))


@router.put("/preferences", response_model=IndustryPreferencesResponse)
def update_industry_preferences(payload: IndustryPreferencesResponse, request: Request) -> IndustryPreferencesResponse:
    profile_id = _resolve_industry_profile(request)
    data = industry_preferences_store.update_preferences(payload.model_dump(), profile_id=profile_id)
    return IndustryPreferencesResponse(**data)


@router.get("/preferences/export")
def export_industry_preferences(request: Request):
    profile_id = _resolve_industry_profile(request)
    return JSONResponse(content=industry_preferences_store.get_preferences(profile_id=profile_id))


@router.post("/preferences/import", response_model=IndustryPreferencesResponse)
def import_industry_preferences(payload: IndustryPreferencesResponse, request: Request) -> IndustryPreferencesResponse:
    profile_id = _resolve_industry_profile(request)
    data = industry_preferences_store.update_preferences(payload.model_dump(), profile_id=profile_id)
    return IndustryPreferencesResponse(**data)


@router.get("/industries/{industry_name}/trend", response_model=IndustryTrendResponse)
def get_industry_trend(
    industry_name: str,
    days: int = Query(30, ge=1, le=90, description="分析周期（天）")
) -> IndustryTrendResponse:
    """
    获取行业趋势分析
    
    返回指定行业的详细趋势分析，包括涨幅/跌幅前5的股票。
    """
    cache_key = f"trend:v5:{industry_name}:{days}"
    try:
        # 1. 检查有效缓存
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

        analyzer = get_industry_analyzer()
        trend_data = analyzer.get_industry_trend(industry_name, days=days)
        
        if "error" in trend_data:
            raise HTTPException(status_code=404, detail=trend_data["error"])
        
        result = IndustryTrendResponse(
            industry_name=trend_data.get("industry_name", ""),
            stock_count=trend_data.get("stock_count", 0),
            expected_stock_count=trend_data.get("expected_stock_count", 0),
            total_market_cap=trend_data.get("total_market_cap", 0),
            avg_pe=trend_data.get("avg_pe", 0),
            industry_volatility=trend_data.get("industry_volatility", 0),
            industry_volatility_source=trend_data.get("industry_volatility_source", "unavailable"),
            period_days=trend_data.get("period_days", days),
            period_change_pct=trend_data.get("period_change_pct", 0),
            period_money_flow=trend_data.get("period_money_flow", 0),
            top_gainers=trend_data.get("top_gainers", []),
            top_losers=trend_data.get("top_losers", []),
            rise_count=trend_data.get("rise_count", 0),
            fall_count=trend_data.get("fall_count", 0),
            flat_count=trend_data.get("flat_count", 0),
            stock_coverage_ratio=trend_data.get("stock_coverage_ratio", 0),
            change_coverage_ratio=trend_data.get("change_coverage_ratio", 0),
            market_cap_coverage_ratio=trend_data.get("market_cap_coverage_ratio", 0),
            pe_coverage_ratio=trend_data.get("pe_coverage_ratio", 0),
            total_market_cap_fallback=trend_data.get("total_market_cap_fallback", False),
            avg_pe_fallback=trend_data.get("avg_pe_fallback", False),
            market_cap_source=trend_data.get("market_cap_source", "unknown"),
            valuation_source=trend_data.get("valuation_source", "unavailable"),
            valuation_quality=trend_data.get("valuation_quality", "unavailable"),
            trend_series=trend_data.get("trend_series", []),
            degraded=trend_data.get("degraded", False),
            note=trend_data.get("note"),
            update_time=trend_data.get("update_time", ""),
        )

        should_attempt_alignment = (
            result.degraded
            or (
                result.expected_stock_count > 0
                and result.stock_count > max(result.expected_stock_count * 2, result.expected_stock_count + 15)
            )
        )
        if should_attempt_alignment:
            provider = getattr(analyzer, "provider", None) or _get_or_create_provider()
            aligned_stock_rows = _load_trend_alignment_stock_rows(
                industry_name,
                result.expected_stock_count,
                provider=provider,
            )
            if _should_align_trend_with_stock_rows(result.model_dump(), aligned_stock_rows):
                aligned_summary = _build_trend_summary_from_stock_rows(
                    aligned_stock_rows,
                    expected_count=result.expected_stock_count,
                    fallback_total_market_cap=result.total_market_cap,
                    fallback_avg_pe=result.avg_pe,
                )
                aligned_payload = result.model_dump()
                aligned_payload.update(aligned_summary)
                result = IndustryTrendResponse(**aligned_payload)
        
        # 2. 如果当前数据降级，尝试使用健康的过期缓存兜底
        if result.degraded:
            stale = _get_stale_endpoint_cache(cache_key)
            if stale is not None and not getattr(stale, "degraded", True):
                logger.warning(f"Trend data degraded for {industry_name}, returning healthy stale cache")
                return stale
                
        # 3. 更新缓存（包含健康数据或只能接受的降级数据）
        _set_endpoint_cache(cache_key, result)
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry trend: {e}")
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning(f"Using stale cache for trend: {cache_key}")
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/clusters", response_model=ClusterResponse)
def get_industry_clusters(
    n_clusters: int = Query(4, ge=2, le=10, description="聚类数量")
) -> ClusterResponse:
    """
    获取行业聚类分析
    
    使用 K-Means 算法将行业聚类为热门组和非热门组。
    """
    try:
        analyzer = get_industry_analyzer()
        cluster_data = analyzer.cluster_hot_industries(n_clusters=n_clusters)
        
        return ClusterResponse(
            clusters=cluster_data.get("clusters", {}),
            hot_cluster=cluster_data.get("hot_cluster", -1),
            cluster_stats=cluster_data.get("cluster_stats", {}),
            points=cluster_data.get("points", []),
            selected_cluster_count=cluster_data.get("selected_cluster_count", n_clusters),
            silhouette_score=cluster_data.get("silhouette_score"),
            cluster_candidates=cluster_data.get("cluster_candidates", {}),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry clusters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/rotation", response_model=IndustryRotationResponse)
def get_industry_rotation(
    industries: str = Query(..., description="行业名称列表，逗号分隔"),
    periods: Optional[str] = Query(None, description="统计周期列表，逗号分隔，如 1,5,20"),
) -> IndustryRotationResponse:
    """
    获取行业轮动对比数据
    
    比较多个行业在不同时间周期的涨跌幅表现。
    
    - **industries**: 行业名称列表，用逗号分隔（如2-5个）
    """
    try:
        industry_list = [i.strip() for i in industries.split(",") if i.strip()]
        if len(industry_list) < 2:
            raise HTTPException(status_code=400, detail="至少需要选择 2 个行业进行对比")
        if len(industry_list) > 5:
            industry_list = industry_list[:5]
        
        requested_periods = None
        if periods:
            requested_periods = []
            for raw in periods.split(","):
                raw_value = raw.strip()
                if not raw_value:
                    continue
                try:
                    requested_periods.append(max(int(raw_value), 1))
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=f"非法周期参数: {raw_value}") from exc

        analyzer = get_industry_analyzer()
        rotation_data = analyzer.get_industry_rotation(industry_list, requested_periods)
        
        if "error" in rotation_data:
            raise HTTPException(status_code=500, detail=rotation_data["error"])
        
        return IndustryRotationResponse(
            industries=rotation_data.get("industries", []),
            periods=rotation_data.get("periods", []),
            data=rotation_data.get("data", []),
            update_time=rotation_data.get("update_time", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry rotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/intelligence", summary="行业生命周期、ETF 映射与事件日历")
def get_industry_intelligence(
    top_n: int = Query(12, ge=1, le=30, description="分析前 N 个热门行业"),
    lookback_days: int = Query(5, ge=1, le=30, description="热度回看周期"),
):
    cache_key = f"industry_intelligence:v1:{top_n}:{lookback_days}"
    cached = _get_endpoint_cache(cache_key)
    if cached is not None:
        return cached
    try:
        analyzer = get_industry_analyzer()
        rows = analyzer.rank_industries(
            top_n=top_n,
            sort_by="total_score",
            ascending=False,
            lookback_days=lookback_days,
        )
        industries = []
        for row in rows:
            industry_name = row.get("industry_name", "")
            industries.append(
                {
                    "industry_name": industry_name,
                    "rank": row.get("rank", 0),
                    "score": row.get("score", row.get("total_score", 0)),
                    "change_pct": row.get("change_pct", 0),
                    "money_flow": row.get("money_flow", 0),
                    "lifecycle": _classify_industry_lifecycle(row),
                    "etf_mapping": _map_industry_etfs(industry_name),
                    "event_calendar": _build_industry_events(industry_name),
                }
            )
        result = {
            "success": True,
            "data": {
                "lookback_days": lookback_days,
                "industries": industries,
                "generated_at": datetime.now().isoformat(),
            },
        }
        _set_endpoint_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Error building industry intelligence: {e}", exc_info=True)
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/network", summary="行业相关性网络图")
def get_industry_network(
    top_n: int = Query(18, ge=4, le=50, description="网络节点数量"),
    lookback_days: int = Query(5, ge=1, le=30, description="热度回看周期"),
    min_similarity: float = Query(0.92, ge=0.0, le=1.0, description="最小相似度"),
):
    cache_key = f"industry_network:v1:{top_n}:{lookback_days}:{min_similarity}"
    cached = _get_endpoint_cache(cache_key)
    if cached is not None:
        return cached
    try:
        analyzer = get_industry_analyzer()
        rows = analyzer.rank_industries(
            top_n=top_n,
            sort_by="total_score",
            ascending=False,
            lookback_days=lookback_days,
        )
        nodes = []
        vectors = {}
        for row in rows:
            name = row.get("industry_name", "")
            score = float(row.get("score", row.get("total_score", 0)) or 0)
            momentum = float(row.get("momentum", 0) or 0)
            change_pct = float(row.get("change_pct", 0) or 0)
            flow = float(row.get("money_flow", row.get("flow_strength", 0)) or 0)
            volatility = float(row.get("industry_volatility", 0) or 0)
            vectors[name] = [
                score / 100,
                momentum / 100,
                change_pct / 20,
                flow / max(abs(flow), 1_000_000_000),
                volatility / 20,
            ]
            nodes.append(
                {
                    "id": name,
                    "label": name,
                    "score": round(score, 3),
                    "stage": _classify_industry_lifecycle(row)["stage"],
                    "etfs": _map_industry_etfs(name)[:2],
                }
            )

        edges = []
        names = list(vectors.keys())
        for left_index, left_name in enumerate(names):
            for right_name in names[left_index + 1 :]:
                similarity = _cosine_similarity(vectors[left_name], vectors[right_name])
                if similarity >= min_similarity:
                    edges.append(
                        {
                            "source": left_name,
                            "target": right_name,
                            "weight": round(float(similarity), 4),
                            "relationship": "factor_similarity",
                        }
                    )
        edges.sort(key=lambda item: item["weight"], reverse=True)
        result = {
            "success": True,
            "data": {
                "nodes": nodes,
                "edges": edges[:120],
                "metadata": {
                    "top_n": top_n,
                    "lookback_days": lookback_days,
                    "min_similarity": min_similarity,
                    "generated_at": datetime.now().isoformat(),
                },
            },
        }
        _set_endpoint_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Error building industry network: {e}", exc_info=True)
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaders", response_model=List[LeaderStockResponse])
def get_leader_stocks(
    top_n: int = Query(20, ge=1, le=100, description="返回龙头股数量"),
    top_industries: int = Query(5, ge=1, le=20, description="从前N个热门行业中选取"),
    per_industry: int = Query(5, ge=1, le=20, description="每个行业选取的龙头数量"),
    list_type: Literal["hot", "core"] = Query("hot", description="榜单类型：hot(热点先锋) 或 core(核心资产)")
) -> List[LeaderStockResponse]:
    """
    获取龙头股推荐列表
    
    - hot (热点先锋): 使用独立的 0-100 动量评分，聚焦短期涨势与资金关注度。
    - core (核心资产): 使用 0-100 综合评分，侧重长线基本面与流动性。
    """
    try:
        # 端点级缓存
        cache_key = f"leaders:v3:{list_type}:{top_n}:{top_industries}:{per_industry}"
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

        analyzer = get_industry_analyzer()

        # 获取热门行业排名（用于筛选行业）
        hot_industries = analyzer.rank_industries(top_n=top_industries)
        top_industry_names = set(ind.get("industry_name") for ind in hot_industries)

        # ========== 核心资产 (Core Leaders) 逻辑 ==========
        if list_type == "core":
            import concurrent.futures
            scorer = get_leader_scorer()
            provider = analyzer.provider

            def _process_core_industry(industry):
                """处理单个行业的核心资产遴选（可并行）"""
                ind_name = industry.get("industry_name")
                if not ind_name:
                    return []
                try:
                    stocks = provider.get_stock_list_by_industry(ind_name)
                    if not stocks:
                        return []

                    candidate_pool = []
                    for stock in stocks:
                        sym = normalize_symbol(stock.get("symbol") or stock.get("code") or "")
                        if not re.fullmatch(r"\d{6}", sym):
                            continue
                        candidate_pool.append({
                            "symbol": sym,
                            "name": stock.get("name", ""),
                            "market_cap": float(stock.get("market_cap") or 0),
                            "pe_ratio": float(stock.get("pe_ratio") or 0),
                            "change_pct": float(stock.get("change_pct") or 0),
                            "amount": float(stock.get("amount") or 0),
                        })

                    if not candidate_pool:
                        return []

                    candidate_pool.sort(
                        key=lambda item: (
                            item["market_cap"] > 0,
                            item["market_cap"],
                            item["amount"],
                            abs(item["change_pct"]),
                        ),
                        reverse=True,
                    )

                    valid_stocks = []
                    for item in candidate_pool[: max(5, per_industry * 2)]:
                        mkt_cap = item["market_cap"]
                        pe = item["pe_ratio"]
                        if mkt_cap > 0 and mkt_cap < 3000000000:
                            continue
                        if pe != 0 and (pe < 0 or pe > 150):
                            continue
                        valid_stocks.append(item["symbol"])

                    if not valid_stocks:
                        valid_stocks = [item["symbol"] for item in candidate_pool[: min(5, len(candidate_pool))]]

                    logger.info(f"For {ind_name}, selected {len(valid_stocks)} valid core candidates.")
                    candidate_map = {item["symbol"]: item for item in candidate_pool}
                    industry_stats = scorer.calculate_industry_stats(candidate_pool)

                    # 阶段一：无网络 I/O 的快速本地评分（筛选候选）
                    fast_results = []
                    for sym in valid_stocks[:max(5, int(per_industry * 1.5))]:
                        snapshot = candidate_map.get(sym, {"symbol": sym, "name": sym})
                        sd = scorer.score_stock_from_snapshot(snapshot, industry_stats=industry_stats, enrich_financial=False)
                        ds = sd.get("dimension_scores", {})
                        roe = sd.get("raw_data", {}).get("roe")
                        if roe is not None and roe < 0:
                            continue
                        fast_score = sd.get("total_score", 0)
                        fast_results.append((sym, fast_score, sd))

                    fast_results.sort(key=lambda x: x[1], reverse=True)
                    top_syms = [sym for sym, _, _ in fast_results[:per_industry]]

                    # 阶段二：仅复用已有财务缓存，榜单请求不主动触发新的财务网络 I/O
                    ind_core_list = []
                    for sym in top_syms:
                        snapshot = candidate_map.get(sym, {"symbol": sym, "name": sym})
                        sd = None
                        try:
                            sd = scorer.score_stock_from_snapshot(
                                snapshot,
                                industry_stats=industry_stats,
                                enrich_financial=True,
                                cached_only=True,
                            )
                        except Exception:
                            pass
                        if not sd or "error" in sd:
                            sd = scorer.score_stock_from_snapshot(snapshot, industry_stats=industry_stats, enrich_financial=False)
                        ds = sd.get("dimension_scores", {})
                        roe = sd.get("raw_data", {}).get("roe")
                        if roe is not None and roe < 0:
                            continue
                        total_score = round(sd.get("total_score", 0), 2)
                        ind_core_list.append(LeaderStockResponse(
                            symbol=sym,
                            name=sd.get("name", sym),
                            industry=ind_name,
                            score_type="core",
                            global_rank=0,
                            industry_rank=0,
                            total_score=total_score,
                            market_cap=sd.get("raw_data", {}).get("market_cap", snapshot.get("market_cap", 0)),
                            pe_ratio=sd.get("raw_data", {}).get("pe_ttm", snapshot.get("pe_ratio", 0)),
                            change_pct=sd.get("raw_data", {}).get("change_pct", snapshot.get("change_pct", 0)),
                            dimension_scores=ds,
                            mini_trend=[],
                        ))

                    ind_core_list.sort(key=lambda x: x.total_score, reverse=True)
                    for rank_idx, stock in enumerate(ind_core_list[:per_industry], 1):
                        stock.industry_rank = rank_idx
                    return ind_core_list[:per_industry]
                except Exception as e:
                    logger.error(f"Error fetching core stocks for {ind_name}: {e}")
                    return []

            # [性能优化] 5 个行业并行处理，大幅缩短总耗时
            core_leaders = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                industry_results = list(executor.map(
                    _process_core_industry, hot_industries[:top_industries]
                ))
            for result in industry_results:
                core_leaders.extend(result)

            # 批量持久化财务缓存（一次性写入，避免逐股写磁盘）
            try:
                from src.analytics.leader_stock_scorer import LeaderStockScorer
                LeaderStockScorer._persist_financial_cache()
            except Exception:
                pass

            # 全局排名截断
            core_leaders = _dedupe_leader_responses(core_leaders)[:top_n]
            
            if core_leaders:
                _set_endpoint_cache(cache_key, core_leaders)
                # 保存快照状态到独立 parity 缓存（30分钟 TTL）
                for l in core_leaders:
                    _set_parity_cache(l.symbol, "core", l)
            else:
                stale = _get_stale_endpoint_cache(cache_key)
                if stale is not None:
                    logger.warning("Core leaders empty, using stale cache: %s", cache_key)
                    return stale
            return core_leaders

        # ========== 热点先锋 (Hot Movers) 逻辑 ==========
        # 优先路径：从热力图数据中提取 leading_stock（THS 已有领涨股信息）
        heatmap_df = analyzer.analyze_money_flow(days=1)
        leaders_from_heatmap = []
        scorer = get_leader_scorer()
        valuation_provider = getattr(analyzer, "provider", None)

        if not heatmap_df.empty and "leading_stock" in heatmap_df.columns:
            sort_col = "main_net_inflow" if "main_net_inflow" in heatmap_df.columns else "change_pct"
            sorted_df = heatmap_df.sort_values(sort_col, ascending=False)

            seen_stocks = set()
            hot_candidates = []
            for _, row in sorted_df.iterrows():
                industry_name = row.get("industry_name", "")
                leading_stock = row.get("leading_stock")
                if not leading_stock or not isinstance(leading_stock, str):
                    continue
                if top_industry_names and industry_name not in top_industry_names:
                    continue
                if leading_stock in seen_stocks:
                    continue
                seen_stocks.add(leading_stock)
                hot_candidates.append(row)
                if len(hot_candidates) >= int(top_n * 1.2):
                    break

            def _score_hot_stock(row):
                industry_name = row.get("industry_name", "")
                leading_stock = row.get("leading_stock")
                change_pct = float(row.get("leading_stock_change", row.get("change_pct", 0)) or 0)
                net_inflow_ratio = float(row.get("main_net_ratio", 0) or 0)
                
                # [性能优化] 先尝试直接提取6位代码，避免不必要的网络反查
                quick_symbol = normalize_symbol(leading_stock)
                if re.fullmatch(r"\d{6}", quick_symbol):
                    real_symbol = quick_symbol
                else:
                    real_symbol = _resolve_symbol_with_provider(leading_stock)

                valuation_snapshot = {}
                if re.fullmatch(r"\d{6}", real_symbol) and valuation_provider and hasattr(valuation_provider, "get_stock_valuation"):
                    try:
                        candidate = valuation_provider.get_stock_valuation(real_symbol)
                        if isinstance(candidate, dict) and "error" not in candidate:
                            valuation_snapshot = candidate
                    except Exception as exc:
                        logger.warning("Failed to hydrate hot leader valuation for %s: %s", real_symbol, exc)

                snapshot_data = {
                    "symbol": real_symbol,
                    "name": leading_stock,
                    "market_cap": float(valuation_snapshot.get("market_cap") or 0),
                    "pe_ratio": float(valuation_snapshot.get("pe_ttm") or valuation_snapshot.get("pe_ratio") or 0),
                    "change_pct": change_pct,
                    "amount": float(valuation_snapshot.get("amount") or abs(float(row.get("main_net_inflow", 0) or 0))),
                    "turnover": float(valuation_snapshot.get("turnover") or 0),
                    "net_inflow_ratio": net_inflow_ratio,
                }

                # [性能优化] 使用 snapshot 快速评分，避免逐股请求 AKShare 财务接口
                score_detail = scorer.score_stock_from_snapshot(snapshot_data, score_type="hot")

                if "error" not in score_detail:
                    scored_symbol = normalize_symbol(score_detail.get("symbol", real_symbol))
                    market_cap = score_detail.get("raw_data", {}).get("market_cap", 0)
                    pe_ratio = score_detail.get("raw_data", {}).get("pe_ttm", 0)
                    dimension_scores = score_detail.get("dimension_scores", {})
                    total_score = score_detail.get("total_score", 0)
                else:
                    scored_symbol = real_symbol
                    total_score = round(min(100, max(0, (change_pct + 15) / 30 * 50 + max(0, min(50, net_inflow_ratio * 5 + 25)))), 2)
                    market_cap = 0
                    pe_ratio = 0
                    dimension_scores = {
                        "momentum": min(1.0, max(0.0, (change_pct + 15) / 30)),
                        "money_flow": min(1.0, max(0.0, (net_inflow_ratio + 10) / 20)),
                        "valuation": 0.5,
                        "profitability": 0.5,
                        "growth": 0.5,
                        "activity": 0.5,
                        "score_type": "hot"
                    }

                # 龙头股详情接口要求 symbol 最终是可识别代码；无法解析的候选直接跳过。
                if not re.fullmatch(r"\d{6}", scored_symbol):
                    logger.warning(f"Skipping leader '{leading_stock}' because symbol could not be resolved: {scored_symbol}")
                    return None

                return LeaderStockResponse(
                    symbol=scored_symbol,
                    name=leading_stock,
                    industry=industry_name,
                    score_type="hot",
                    global_rank=0,
                    industry_rank=1,
                    total_score=total_score,
                    market_cap=market_cap,
                    pe_ratio=pe_ratio,
                    change_pct=change_pct,
                    dimension_scores=dimension_scores,
                    mini_trend=[],
                )

            import concurrent.futures
            # 优化：降低线程池防止代理报错
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(_score_hot_stock, hot_candidates))
                
            for res in results:
                if res: leaders_from_heatmap.append(res)

            leaders_from_heatmap = _dedupe_leader_responses(leaders_from_heatmap)[:top_n]

        if leaders_from_heatmap and len(leaders_from_heatmap) < top_n:
            logger.info(
                "Heatmap hot leaders underfilled (%s/%s), backfilling from LeaderStockScorer",
                len(leaders_from_heatmap),
                top_n,
            )
            scorer = get_leader_scorer()
            industry_names = [ind.get("industry_name") for ind in hot_industries]
            needed_count = max(0, top_n - len(leaders_from_heatmap))
            supplemental_per_industry = max(
                1,
                (needed_count + max(len(industry_names), 1) - 1) // max(len(industry_names), 1),
            )
            supplemental = scorer.get_leader_stocks(
                industry_names,
                top_per_industry=supplemental_per_industry,
                score_type="hot",
            )
            leaders_from_heatmap.extend(
                [
                    LeaderStockResponse(
                        symbol=l.get("symbol", ""),
                        name=l.get("name", ""),
                        industry=l.get("industry", ""),
                        score_type="hot",
                        global_rank=l.get("global_rank", 0),
                        industry_rank=l.get("rank", 0),
                        total_score=l.get("total_score", 0),
                        market_cap=l.get("market_cap", 0),
                        pe_ratio=l.get("pe_ratio", 0),
                        change_pct=l.get("change_pct", 0),
                        dimension_scores=l.get("dimension_scores", {}),
                        mini_trend=l.get("mini_trend", []),
                    )
                    for l in supplemental
                ]
            )
            leaders_from_heatmap = _dedupe_leader_responses(leaders_from_heatmap)[:top_n]

        if leaders_from_heatmap:
            _set_endpoint_cache(cache_key, leaders_from_heatmap)
            for l in leaders_from_heatmap:
                _set_parity_cache(l.symbol, "hot", l)
            return leaders_from_heatmap

        # ⬇️ 降级路径：尝试原始成分股评分器（成功概率低，但保留备用）
        logger.warning("Heatmap leading_stock unavailable, falling back to LeaderStockScorer")
        scorer = get_leader_scorer()
        industry_names = [ind.get("industry_name") for ind in hot_industries]
        leaders = scorer.get_leader_stocks(industry_names, top_per_industry=per_industry, score_type="hot")
        leaders = leaders[:top_n]

        result = [
            LeaderStockResponse(
                symbol=l.get("symbol", ""),
                name=l.get("name", ""),
                industry=l.get("industry", ""),
                score_type="hot",
                global_rank=l.get("global_rank", 0),
                industry_rank=l.get("rank", 0),
                total_score=l.get("total_score", 0),
                market_cap=l.get("market_cap", 0),
                pe_ratio=l.get("pe_ratio", 0),
                change_pct=l.get("change_pct", 0),
                dimension_scores=l.get("dimension_scores", {}),
                mini_trend=l.get("mini_trend", []),
            )
            for l in leaders
        ]
        result = _dedupe_leader_responses(result)[:top_n]
        if result:
            _set_endpoint_cache(cache_key, result)
            for l in result:
                _set_parity_cache(l.symbol, "hot", l)
        else:
            stale = _get_stale_endpoint_cache(cache_key)
            if stale is not None:
                logger.warning("Hot leaders empty, using stale cache: %s", cache_key)
                return stale
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting leader stocks: {e}")
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning(f"Using stale cache for leaders: {cache_key}")
            return stale
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/leaders/{symbol}/detail", response_model=LeaderDetailResponse)
def get_leader_detail(
    symbol: str,
    score_type: Literal["core", "hot"] = Query("core", description="评分类型: core 或 hot")
) -> LeaderDetailResponse:
    """
    获取龙头股详细分析
    
    返回指定股票的完整分析报告，包括评分详情、技术分析和历史价格。
    
    - **symbol**: 股票代码（如 "000001"、"600519"）
    """
    try:
        resolved_symbol = _resolve_symbol_with_provider(symbol)

        # 端点级缓存
        cache_key = f"leader_detail:v2:{resolved_symbol}:{score_type}"
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

        scorer = get_leader_scorer()
        detail = scorer.get_leader_detail(resolved_symbol, score_type=score_type)
        
        if "error" in detail:
            raise HTTPException(status_code=404, detail=detail["error"])
            
        # 尝试使用列表端点计算的快照得分来保证前端展示完全一致 (Score Parity)
        # 优先使用独立 parity 缓存（30分钟 TTL），过期后仍作为兜底
        parity = _get_parity_cache(resolved_symbol, score_type)
        if parity is None:
            parity = _get_stale_parity_cache(resolved_symbol, score_type)
            if parity:
                logger.info(f"Using stale parity cache for {resolved_symbol}:{score_type}")

        if parity:
            detail["total_score"] = parity.total_score
            if hasattr(parity, "dimension_scores") and parity.dimension_scores:
                detail["dimension_scores"] = parity.dimension_scores
            raw_data = detail.setdefault("raw_data", {})
            if hasattr(parity, "change_pct") and not has_meaningful_numeric(raw_data.get("change_pct")):
                raw_data["change_pct"] = parity.change_pct
            if hasattr(parity, "market_cap") and has_meaningful_numeric(parity.market_cap) and not has_meaningful_numeric(raw_data.get("market_cap")):
                raw_data["market_cap"] = parity.market_cap
            if hasattr(parity, "pe_ratio") and has_meaningful_numeric(parity.pe_ratio) and not has_meaningful_numeric(raw_data.get("pe_ttm")):
                raw_data["pe_ttm"] = parity.pe_ratio
        
        result = LeaderDetailResponse(
            symbol=normalize_symbol(detail.get("symbol", resolved_symbol)),
            name=detail.get("name", ""),
            total_score=detail.get("total_score", 0),
            score_type=score_type,
            dimension_scores=detail.get("dimension_scores", {}),
            raw_data=detail.get("raw_data", {}),
            technical_analysis=detail.get("technical_analysis", {}),
            price_data=detail.get("price_data", []),
        )
        _set_endpoint_cache(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting leader detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
def health_check():
    """
    行业分析模块健康检查 + 数据源状态
    
    返回当前活跃数据源、能力、连接状态等详细信息
    """
    import time
    
    try:
        from src.data.providers.akshare_provider import AKSHARE_AVAILABLE
    except Exception:
        AKSHARE_AVAILABLE = False
    
    # 判断当前活跃的 provider
    provider = _akshare_provider
    provider_name = "未初始化"
    provider_type = "none"
    
    if provider is not None:
        class_name = type(provider).__name__
        if "Sina" in class_name:
            provider_name = "新浪财经 (Sina Finance)"
            provider_type = "sina"
        elif "AKShare" in class_name:
            provider_name = "AKShare (东方财富)"
            provider_type = "akshare"
        else:
            provider_name = class_name
            provider_type = "unknown"
    
    # 数据源能力矩阵
    capabilities = {
        "akshare": {
            "name": "AKShare (东方财富)",
            "installed": AKSHARE_AVAILABLE,
            "has_market_cap": True,
            "has_multi_day": True,
            "has_real_money_flow": True,
            "day_options": ["1日", "5日", "10日"],
            "status": "unavailable",
            "status_detail": "",
        },
        "sina": {
            "name": "新浪财经 (Sina Finance)",
            "installed": True,
            "has_market_cap": True,  # 通过成分股汇总
            "has_multi_day": False,
            "has_real_money_flow": False,
            "day_options": ["当日"],
            "status": "unknown",
            "status_detail": "市值通过成分股数据汇总计算",
        },
        "ths": {
            "name": "同花顺 (THS)",
            "installed": True,
            "has_market_cap": False,
            "has_multi_day": True,
            "has_real_money_flow": True,
            "day_options": ["当日", "5日", "10日", "20日"],
            "status": "unknown",
            "status_detail": "多日涨跌与主力资金流向增强",
        },
    }
    
    # 检查 AKShare 实际连接
    if AKSHARE_AVAILABLE:
        try:
            import akshare as ak
            start = time.time()
            df = ak.stock_sector_fund_flow_rank(indicator="今日")
            elapsed = time.time() - start
            if df is not None and not df.empty:
                capabilities["akshare"]["status"] = "connected"
                capabilities["akshare"]["status_detail"] = f"响应 {elapsed:.1f}s, {len(df)} 行业"
            else:
                capabilities["akshare"]["status"] = "empty"
                capabilities["akshare"]["status_detail"] = "API 返回空数据"
        except Exception as e:
            err_msg = str(e)
            if "proxy" in err_msg.lower() or "connection" in err_msg.lower():
                capabilities["akshare"]["status"] = "blocked"
                capabilities["akshare"]["status_detail"] = "网络代理拦截"
            else:
                capabilities["akshare"]["status"] = "error"
                capabilities["akshare"]["status_detail"] = err_msg[:80]
    else:
        capabilities["akshare"]["status"] = "not_installed"
        capabilities["akshare"]["status_detail"] = "akshare 未安装"
    
    # 检查 Sina 连接
    try:
        from src.data.providers.sina_provider import SinaFinanceProvider
        sina = SinaFinanceProvider()
        start = time.time()
        industries = sina.get_industry_list()
        elapsed = time.time() - start
        
        # 兼容 DataFrame 判断和 None 判断
        is_success = False
        data_len = 0
        
        if industries is not None:
            if hasattr(industries, 'empty'):
                is_success = not industries.empty
                data_len = len(industries)
            else:
                is_success = len(industries) > 0
                data_len = len(industries)
                
        if is_success:
            capabilities["sina"]["status"] = "connected"
            capabilities["sina"]["status_detail"] = f"响应 {elapsed:.1f}s, {data_len} 行业"
        else:
            capabilities["sina"]["status"] = "empty"
            capabilities["sina"]["status_detail"] = "API 返回空数据"
    except Exception as e:
        capabilities["sina"]["status"] = "error"
        capabilities["sina"]["status_detail"] = str(e)[:80]
        
    # 检查 THS 连接
    try:
        from src.data.providers.sina_ths_adapter import SinaIndustryAdapter
        adapter = SinaIndustryAdapter()
        start = time.time()
        ths_df = adapter._get_ths_flow_data(days=1)
        elapsed = time.time() - start
        
        if not ths_df.empty:
            capabilities["ths"]["status"] = "connected"
            capabilities["ths"]["status_detail"] = f"响应 {elapsed:.1f}s, {len(ths_df)} 行业"
        else:
            capabilities["ths"]["status"] = "empty"
            capabilities["ths"]["status_detail"] = "API 返回空数据"
    except Exception as e:
        capabilities["ths"]["status"] = "error"
        capabilities["ths"]["status_detail"] = str(e)[:80]
    
    # Sina fallback 状态
    has_sina_fallback = False
    if _industry_analyzer and hasattr(_industry_analyzer, '_sina_fallback'):
        has_sina_fallback = True
    
    # 数据来源透出：当前生效的数据源组合
    data_sources_contributing = []
    if capabilities.get("ths", {}).get("status") == "connected":
        data_sources_contributing.append("ths")
    if capabilities.get("sina", {}).get("status") == "connected":
        data_sources_contributing.append("sina")
    if capabilities.get("akshare", {}).get("status") == "connected":
        data_sources_contributing.append("akshare")
    if not data_sources_contributing:
        data_sources_contributing = ["unknown"]
    
    data_source_mode = "sina_fallback" if has_sina_fallback else "ths_primary"
    
    return {
        "status": "healthy" if provider is not None else "degraded",
        "active_provider": {
            "name": provider_name,
            "type": provider_type,
        },
        "data_sources": capabilities,
        "sina_fallback_active": has_sina_fallback,
        "akshare_available": AKSHARE_AVAILABLE,
        "data_sources_contributing": data_sources_contributing,
        "data_source_mode": data_source_mode,
        "message": f"当前数据源: {provider_name}",
    }
