"""ETF rotation — read-only HTTP surface for the daily manual trade plan.

This wraps :func:`scripts.daily_etf_signal.generate_plan` so the frontend can
render the same manual-only suggestions the CLI prints. The endpoint remains
broker-agnostic: it may read market quotes, but it never contacts a broker and
never submits orders.

Quote and history fetching live in :mod:`scripts.daily_etf_signal` so the CLI
and this endpoint share identical semantics — no duplicated realtime logic.

Endpoints
---------
* ``GET /daily-signal`` — one-shot computation against live quotes (for the
  legacy dashboard tile).
* ``GET /live-target`` — returns the latest cached plan from the
  ``EtfRotationService`` background refresh loop, with explicit freshness
  metadata. Use this when the dashboard polls every few seconds.
* ``POST /refresh`` — force a refresh outside trading hours.
* ``POST /backtest`` — replay the strategy on a committed historical price
  matrix and return a BacktestReport.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace as dataclass_replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Body, HTTPException, Query

from scripts import daily_etf_signal
from src.backtest.etf_rotation_backtest import (
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_REBALANCE_FREQ_DAYS,
    EtfRotationBacktester,
)
from src.backtest.etf_rotation_walkforward import (
    DEFAULT_STEP_MONTHS,
    DEFAULT_WINDOW_MONTHS,
    EtfRotationWalkforwardAnalyzer,
)
from src.backtest.strategy_comparison import (
    DEFAULT_STRATEGY_LABELS,
    StrategyComparator,
    build_default_strategy_specs,
)
from src.backtest.transaction_costs import TransactionCostModel
from src.research.policy_factor_attribution import (
    AttributionReport,
    compute_attribution,
)
from src.strategy.etf_rotation_analytics import summarise_edge
from src.strategy.etf_rotation_config_loader import load_strategy_config
from src.strategy.etf_rotation_preferences import (
    EtfRotationPreferences,
    get_preferences_store,
)
from src.strategy.etf_rotation_service import EtfRotationService
from src.strategy.market_regime_classifier import (
    ClassifierConfig,
    MarketRegimeClassifier,
)
from src.strategy.strategy_recommender import recommend_strategy

logger = logging.getLogger(__name__)

# Committed historical price matrix shipped in ``data/etf_backtest/``. The
# backtest endpoint defaults to this file so the dashboard / CLI don't need
# to remember a path — and so the endpoint stays hermetic (no live data).
_PROJECT_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_BACKTEST_PRICE_CSV = (
    _PROJECT_ROOT / "data" / "etf_backtest" / "etf_prices_4y.csv"
)

router = APIRouter()

# Singleton service shared by all requests. Built lazily so test setups
# (and the conftest isolation fixture) can monkeypatch the constructor or
# inject a fake before the first call.
_service: Optional[EtfRotationService] = None
_service_lock_module_init = False


def _get_service() -> EtfRotationService:
    global _service
    if _service is None:
        _service = EtfRotationService()
    return _service


def reset_service_for_tests() -> None:
    """Drop the cached service singleton — used by the test fixture."""

    global _service
    _service = None


def install_service(service: EtfRotationService) -> None:
    """Replace the module-level service (used by the FastAPI lifespan hook)."""

    global _service
    _service = service


# ---------------------------------------------------------------------------
# Preference store wiring
#
# The preferences module ships its own singleton, but the endpoint layer
# accepts an injected override (used by tests + the FastAPI lifespan hook
# when the operator wants a non-default storage path). When the override
# is ``None`` we fall through to ``get_preferences_store`` so production
# code keeps a single source of truth.
# ---------------------------------------------------------------------------

_preferences_override: Optional[EtfRotationPreferences] = None


def _get_preferences() -> EtfRotationPreferences:
    if _preferences_override is not None:
        return _preferences_override
    return get_preferences_store()


def install_preferences(store: EtfRotationPreferences) -> None:
    """Wire a non-default preferences store for tests / advanced setups."""

    global _preferences_override
    _preferences_override = store


def reset_preferences_for_tests() -> None:
    """Drop any preferences override — paired with ``install_preferences``."""

    global _preferences_override
    _preferences_override = None


def _resolve_policy_factor_flag(
    *, query_param: Optional[bool]
) -> tuple[Optional[bool], bool, str]:
    """Return ``(effective_for_call, effective_bool, source_label)``.

    * ``effective_for_call`` is what we pass into ``generate_plan`` /
      ``service.refresh`` — preserves ``None`` when neither the caller nor
      the UI preference has expressed an opinion, so the downstream code
      keeps its existing "honour config" path.
    * ``effective_bool`` is the *resolved* enabled-or-not value (after the
      config default has been folded in) for the UI to display.
    * ``source_label`` is one of ``"query"`` / ``"preference"`` /
      ``"config"`` so the dashboard / docs can explain who won.
    """

    if query_param is not None:
        cfg = load_strategy_config()
        config_default = bool(cfg.strategy.get("policy_signal_factor_enabled", False))
        store = _get_preferences()
        effective = store.resolve_policy_signal_factor_enabled(
            explicit=query_param, config_default=config_default
        )
        return query_param, effective, "query"

    store = _get_preferences()
    snapshot = store.snapshot()
    cfg = load_strategy_config()
    config_default = bool(cfg.strategy.get("policy_signal_factor_enabled", False))
    if snapshot.policy_signal_factor_enabled is not None:
        return (
            bool(snapshot.policy_signal_factor_enabled),
            bool(snapshot.policy_signal_factor_enabled),
            "preference",
        )
    return None, config_default, "config"


def resolve_policy_factor_refresh_override() -> Optional[bool]:
    """Return the persisted UI preference override for service refresh calls.

    Background refreshes have no query parameter, but they still need to
    honor the dashboard preference. ``None`` means no stored preference is
    set, so ``EtfRotationService.refresh`` should keep honoring strategy.json.
    """

    effective_for_call, _, _ = _resolve_policy_factor_flag(query_param=None)
    return effective_for_call


@router.get(
    "/daily-signal",
    summary="获取每日 ETF 轮动手动调仓建议",
    description=(
        "返回 ``scripts.daily_etf_signal.generate_plan`` 的完整计划字段："
        "current_weights / target_weights / adjusted_weights / suggestions / "
        "risk_reasons。该接口只读、默认使用实时行情更新持仓现价，但不调用任何券商或下单接口。"
    ),
)
def get_daily_signal(
    threshold_weight: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "低于该权重差异的标的不会触发买卖建议（仅生成 hold）。"
            "未传时使用 strategy.json -> strategy.rebalance_threshold 的配置值。"
        ),
    ),
    quote_source: str = Query(
        default="live",
        pattern="^(live|synthetic)$",
        description="live=用实时行情刷新持仓现价；synthetic=使用截图种子的确定性行情。",
    ),
    use_cache: bool = Query(
        default=True,
        description="live 模式下是否允许使用实时行情缓存；手动刷新可传 false。",
    ),
    enable_policy_signal_factor: Optional[bool] = Query(
        default=None,
        description=(
            "可选：覆盖 strategy.json -> strategy.policy_signal_factor_enabled。"
            "true=本次调用启用 policy_radar 影响 ETF 权重；"
            "false=本次关闭；省略=沿用配置值（默认关闭）。"
        ),
    ),
) -> dict[str, Any]:
    base_holdings, holdings_is_configured = daily_etf_signal.load_configured_holdings()

    # Resolve the three-layer precedence (query > preference > config) once
    # per request and stamp the result on the response so the UI can keep
    # its toggle in sync without a separate round-trip.
    effective_for_call, effective_bool, source_label = _resolve_policy_factor_flag(
        query_param=enable_policy_signal_factor,
    )

    if quote_source == "synthetic":
        plan = daily_etf_signal.generate_plan(
            holdings=base_holdings if holdings_is_configured else None,
            threshold_weight=threshold_weight,
            enable_policy_signal_factor=effective_for_call,
        )
        plan["quote_source"] = "synthetic"
        plan["live_quote_status"] = {
            "requested": 0,
            "resolved": 0,
            "missing": 0,
            "use_cache": use_cache,
        }
        _stamp_policy_factor_source(plan, effective_bool, source_label)
        daily_etf_signal.append_audit_entry(plan, quote_source="api:synthetic")
        return {"success": True, "data": plan}

    codes = [h.code for h in base_holdings]
    live_quotes, live_status = daily_etf_signal.fetch_live_quotes(
        codes, use_cache=use_cache
    )
    if live_quotes:
        holdings = daily_etf_signal.apply_quotes_to_holdings(base_holdings, live_quotes)
        quote_map = daily_etf_signal.load_default_quotes(holdings)
        quote_map.update(live_quotes)
        plan = daily_etf_signal.generate_plan(
            holdings=holdings,
            quotes=quote_map,
            threshold_weight=threshold_weight,
            quotes_as_of=max(
                (quote.timestamp for quote in live_quotes.values() if quote.timestamp),
                default=None,
            ),
            enable_policy_signal_factor=effective_for_call,
        )
        plan["quote_source"] = "live"
    else:
        plan = daily_etf_signal.generate_plan(
            holdings=base_holdings if holdings_is_configured else None,
            threshold_weight=threshold_weight,
            enable_policy_signal_factor=effective_for_call,
        )
        plan["quote_source"] = "fallback_synthetic"
    plan["live_quote_status"] = live_status
    _stamp_policy_factor_source(plan, effective_bool, source_label)
    daily_etf_signal.append_audit_entry(plan, quote_source=f"api:{plan['quote_source']}")
    return {"success": True, "data": plan}


def _stamp_policy_factor_source(
    plan: dict[str, Any], effective: bool, source_label: str
) -> None:
    """Attach the effective enabled-state and its source onto the plan.

    ``generate_plan`` already writes ``policy_signal_factor.enabled``; we
    just add the ``source`` discriminator alongside it, and surface the
    boolean at top-level for the UI's convenience (``policy_signal_factor_enabled``).
    The top-level field is a UI ergonomics shortcut — the canonical
    record is still under ``policy_signal_factor`` in case the caller wants
    the rich summary (boosted/penalised lists, last_refresh, etc).
    """

    summary = plan.get("policy_signal_factor")
    if not isinstance(summary, dict):
        summary = {}
        plan["policy_signal_factor"] = summary
    summary.setdefault("enabled", effective)
    summary["enabled"] = bool(effective)
    summary["source"] = source_label
    plan["policy_signal_factor_enabled"] = bool(effective)


def _serialise_cached(cached: Any) -> dict[str, Any]:
    return {
        "plan": cached.plan,
        "refreshed_at": cached.refreshed_at.isoformat() if cached.refreshed_at else None,
        "quote_source": cached.quote_source,
        "debounced": cached.debounced,
        "debounce_max_delta": cached.debounce_max_delta,
        "reasons": list(cached.reasons or []),
    }


@router.get(
    "/live-target",
    summary="读取最近一次后台刷新的 ETF 轮动目标仓位",
    description=(
        "返回 EtfRotationService 缓存的最新计划与刷新元数据。前端可"
        "高频轮询此端点而不触发底层数据拉取——后台刷新循环负责保持缓存常新。"
        "trigger_refresh=true 时即使非交易时段也会强制刷新一次。"
    ),
)
def get_live_target(
    trigger_refresh: bool = Query(
        default=False,
        description="true=阻塞触发一次刷新（即使非交易时段）；false=仅读缓存。",
    ),
    enable_policy_signal_factor: Optional[bool] = Query(
        default=None,
        description=(
            "可选：trigger_refresh=true 时覆盖 "
            "strategy.policy_signal_factor_enabled；省略=沿用配置。"
        ),
    ),
) -> dict[str, Any]:
    service = _get_service()
    effective_for_call, effective_bool, source_label = _resolve_policy_factor_flag(
        query_param=enable_policy_signal_factor,
    )
    if trigger_refresh:
        outcome = service.refresh(
            force=True,
            enable_policy_signal_factor=effective_for_call,
        )
        serialised = _serialise_cached(outcome.cached)
        if isinstance(serialised.get("plan"), dict):
            _stamp_policy_factor_source(serialised["plan"], effective_bool, source_label)
        return {
            "success": True,
            "data": serialised,
            "refresh": {
                "refreshed": outcome.refreshed,
                "skipped_reason": outcome.skipped_reason,
            },
        }

    cached = service.get_cached_plan()
    if cached is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "ETF rotation service has not produced a plan yet. "
                "Call /live-target?trigger_refresh=true or wait for the "
                "next scheduled refresh."
            ),
        )
    serialised = _serialise_cached(cached)
    # The cached plan was built before the (possibly more recent) preference
    # change. Re-stamp the effective field so the UI always sees the
    # current resolution — the underlying weights themselves only refresh
    # on the next service.refresh tick, but the "is the toggle on?" status
    # should track the user's last click immediately.
    if isinstance(serialised.get("plan"), dict):
        _stamp_policy_factor_source(serialised["plan"], effective_bool, source_label)
    return {
        "success": True,
        "data": serialised,
        "refresh": {
            "is_trading_hours": service.is_trading_hours(),
        },
    }


@router.post(
    "/refresh",
    summary="强制刷新 ETF 轮动信号缓存",
    description="即使在非交易时段也立即重新计算一次 plan，并写入审计日志。",
)
def post_refresh(
    use_cache: bool = Query(default=True),
    enable_policy_signal_factor: Optional[bool] = Query(
        default=None,
        description=(
            "可选：覆盖 strategy.policy_signal_factor_enabled；"
            "true=本次启用；false=本次关闭；省略=沿用配置。"
        ),
    ),
) -> dict[str, Any]:
    service = _get_service()
    effective_for_call, effective_bool, source_label = _resolve_policy_factor_flag(
        query_param=enable_policy_signal_factor,
    )
    outcome = service.refresh(
        force=True,
        use_cache=use_cache,
        enable_policy_signal_factor=effective_for_call,
    )
    serialised = _serialise_cached(outcome.cached)
    if isinstance(serialised.get("plan"), dict):
        _stamp_policy_factor_source(serialised["plan"], effective_bool, source_label)
    return {
        "success": True,
        "data": serialised,
        "refresh": {
            "refreshed": outcome.refreshed,
            "skipped_reason": outcome.skipped_reason,
        },
    }


@router.get(
    "/analytics",
    summary="策略 Edge 度量：IC + 命中率 + 每标的拆解",
    description=(
        "从审计日志计算策略的信息系数（Spearman 相关）和命中率，"
        "用于回答 “策略到底有没有 alpha” 这个问题。"
        "默认三档前瞻期：1 小时 / 4 小时 / 1 个交易日。"
        "60 日滚动 IC > 0.05 是行业经验上 “有可测量 edge” 的门槛。"
    ),
)
def get_analytics(
    horizons: Optional[str] = Query(
        default=None,
        description="逗号分隔的前瞻分钟数列表，默认 60,240,1440",
    ),
) -> dict[str, Any]:
    entries = daily_etf_signal.read_audit_log()
    if horizons:
        try:
            horizon_values = [float(h.strip()) for h in horizons.split(",") if h.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid horizons: {exc}")
        if not horizon_values:
            horizon_values = [60.0, 240.0, 1440.0]
    else:
        horizon_values = [60.0, 240.0, 1440.0]

    report = summarise_edge(entries, horizons_minutes=horizon_values)
    return {"success": True, "data": report}


@router.get(
    "/audit-log",
    summary="读取 ETF 轮动信号审计日志",
    description=(
        "返回 JSON Lines 审计日志的最近 N 行（默认 200）。"
        "可选 ``since`` 参数（ISO timestamp）过滤更新时间。"
        "完全只读；日志位置 = ``ETF_AUDIT_LOG_PATH`` env / "
        "``~/.config/etf-rotation/audit.jsonl``。"
    ),
)
def get_audit_log(
    limit: int = Query(default=200, ge=1, le=2000),
    since: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    entries = daily_etf_signal.read_audit_log()
    if since:
        entries = [e for e in entries if str(e.get("run_at", "")) >= since]
    total = len(entries)
    tail = entries[-limit:]
    return {
        "success": True,
        "data": {
            "entries": tail,
            "total": total,
            "returned": len(tail),
        },
    }


def _summarise_strategy_config(cfg: Any) -> dict[str, Any]:
    """Compact view of the loaded strategy config (returned by /reload-config)."""

    return {
        "source_path": str(cfg.source_path) if cfg.source_path else None,
        "source_mtime": cfg.source_mtime,
        "universe": [
            {
                "code": asset.get("code"),
                "name": asset.get("name", ""),
                "max_weight": asset.get("max_weight"),
                "base_weight": asset.get("base_weight"),
            }
            for asset in cfg.universe
        ],
        "risk_rules": dict(cfg.risk_rules),
        "strategy": dict(cfg.strategy),
        "refresh": dict(cfg.refresh),
        "regime": dict(cfg.regime),
        "premium": dict(cfg.premium),
    }


@router.post(
    "/reload-config",
    summary="重载 strategy.json，不重启 backend 即可应用",
    description=(
        "重新读取 ``ETF_STRATEGY_CONFIG_PATH`` / ``~/.config/etf-rotation/strategy.json``"
        "，同步到 EtfRotationService 与 EtfPremiumMonitor，下次刷新自动生效。"
        "返回值是重载后的完整配置摘要（universe / risk_rules / strategy / refresh / regime / premium）。"
    ),
)
def post_reload_config(refresh_after: bool = Query(default=True)) -> dict[str, Any]:
    service = _get_service()
    cfg = service.reload_strategy_config()
    summary = _summarise_strategy_config(cfg)
    refresh_outcome = None
    if refresh_after:
        outcome = service.refresh(
            force=True,
            enable_policy_signal_factor=resolve_policy_factor_refresh_override(),
        )
        refresh_outcome = {
            "refreshed": outcome.refreshed,
            "skipped_reason": outcome.skipped_reason,
            "refreshed_at": (
                outcome.cached.refreshed_at.isoformat() if outcome.cached else None
            ),
        }
    return {
        "success": True,
        "data": summary,
        "refresh": refresh_outcome,
    }


def _build_preferences_envelope() -> dict[str, Any]:
    """Compose the GET/POST preferences response.

    Pairs the user's stored preference with the resolved effective state
    (so the UI can show *what's actually in effect* when no preference is
    set) plus the config default that would otherwise win — useful when
    the dashboard wants to explain "off because the config says so".
    """

    store = _get_preferences()
    snapshot = store.snapshot()
    cfg = load_strategy_config()
    config_default = bool(cfg.strategy.get("policy_signal_factor_enabled", False))
    if snapshot.policy_signal_factor_enabled is None:
        effective = config_default
        source = "config"
    else:
        effective = bool(snapshot.policy_signal_factor_enabled)
        source = "preference"
    return {
        "preference": snapshot.to_dict(),
        "effective": {
            "policy_signal_factor_enabled": effective,
            "source": source,
        },
        "config_default": {
            "policy_signal_factor_enabled": config_default,
        },
    }


@router.get(
    "/preferences",
    summary="读取 ETF 轮动 UI 偏好（per-installation, 持久化到 JSON 文件）",
    description=(
        "返回当前用户在仪表盘里设置的偏好，目前只包含 ``policy_signal_factor_enabled``。"
        "``preference`` 反映文件里的原值（``null`` = 未设置），"
        "``effective`` 是把 config 默认折算进去之后“现在到底开没开”的真实状态。"
        "``source`` ∈ {{config, preference}} 解释 effective 是哪一档赢了。"
    ),
)
def get_preferences() -> dict[str, Any]:
    return {"success": True, "data": _build_preferences_envelope()}


@router.post(
    "/preferences",
    summary="更新 ETF 轮动 UI 偏好",
    description=(
        "POST 一个 JSON ``{policy_signal_factor_enabled: bool | null}``——"
        "``true``/``false`` 持久化（覆盖 config 默认），``null`` 清除该偏好"
        "（回退到 config 默认）。"
        "写入采用 temp-file + rename 原子模式，保证并发读不会读到半截 JSON。"
    ),
)
def post_preferences(
    payload: Optional[dict[str, Any]] = Body(default=None),
) -> dict[str, Any]:
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=422,
            detail="Request body must be a JSON object.",
        )

    patch: dict[str, Any] = {}
    if "policy_signal_factor_enabled" in payload:
        raw = payload["policy_signal_factor_enabled"]
        if raw is None:
            patch["policy_signal_factor_enabled"] = None
        elif isinstance(raw, bool):
            patch["policy_signal_factor_enabled"] = raw
        else:
            raise HTTPException(
                status_code=422,
                detail=(
                    "policy_signal_factor_enabled must be a JSON boolean "
                    "or null (got "
                    f"{type(raw).__name__})."
                ),
            )

    if patch:
        _get_preferences().update(patch)

    return {"success": True, "data": _build_preferences_envelope()}


# ---------------------------------------------------------------------------
# Policy factor attribution
#
# Computes the empirical contribution of ``policy_signal_factor`` over the
# last N days by comparing actually-emitted final weights against a proportional
# post-overlay proxy with the policy multiplier removed. Cached for
# ``_ATTRIBUTION_CACHE_TTL`` so the (~50ms) attribution sweep doesn't fire on
# every UI poll; cache keys include audit-log size/mtime so new rows invalidate.
# ---------------------------------------------------------------------------


_ATTRIBUTION_CACHE_TTL = 300.0  # 5 minutes
_attribution_cache: dict[tuple[int, str, int, int], tuple[float, dict[str, Any]]] = {}


def reset_attribution_cache_for_tests() -> None:
    """Drop the attribution cache — tests call this between scenarios."""

    _attribution_cache.clear()


def _fetch_attribution_prices(
    audit_path: Path, period_days: int,
) -> Any:
    """Look up close history for every ETF referenced in the audit window.

    Wrapped in its own helper so tests can monkeypatch it without going through
    the (network-bound) akshare client.
    """

    try:
        from src.data.etf_price_history import fetch_etf_history
    except ImportError:  # pragma: no cover - akshare missing in CI
        return None

    entries = daily_etf_signal.read_audit_log(audit_path)
    codes: set[str] = set()
    for entry in entries:
        for code in (entry.get("adjusted_weights") or {}):
            if code != "CASH":
                codes.add(str(code))
    if not codes:
        return None
    end = datetime.now()
    start = end - timedelta(days=max(period_days + 10, 60))
    try:
        return fetch_etf_history(sorted(codes), start_date=start, end_date=end)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("ETF price fetch for attribution failed: %s", exc)
        return None


@router.get(
    "/policy-factor-attribution",
    summary="读取 policy_signal_factor 的 30 日实证归因报告",
    description=(
        "对启用了 policy_signal_factor 的历史调仓做归因回放："
        "保留审计日志里的最终 ``adjusted_weights`` 作为 *factor-on*，"
        "并按每个 ETF 的 ``policy_adjustment.weight_before / weight_after`` "
        "比例缩放最终权重，得到一个 post-overlay 的 *factor-off* proxy。"
        "两条权重路径在下一条审计 rebalance 之前持有（按 ETF 收盘价计算 mark-to-market），"
        "差值即 policy_signal_factor 对该窗口 P&L 的边际贡献。"
        "\n\n"
        "返回结构（``AttributionReport.to_dict()``）包含："
        "聚合 on/off/contribution（逐窗口复利）、命中率、top winner/loser ETF、"
        "以及逐次调仓的拆解。结果按 ``period_days`` 缓存 5 分钟；"
        "审计日志 size/mtime 变化会自动打破缓存。"
        "\n\n"
        "**注意**：不计交易成本、不计调仓滞后；off leg 是比例 proxy，"
        "不是重新跑一遍完整策略 —— 详见模块顶部 docstring。"
    ),
)
def get_policy_factor_attribution(
    period_days: int = Query(
        default=30, ge=1, le=365,
        description="窗口长度（天），默认 30。",
    ),
    refresh: bool = Query(
        default=False,
        description="true=绕过 5 分钟缓存强制重算。",
    ),
) -> dict[str, Any]:
    audit_path = daily_etf_signal._resolve_audit_log_path()
    audit_file = Path(audit_path) if audit_path is not None else None
    if audit_file is not None and audit_file.is_file():
        stat = audit_file.stat()
        cache_key = (
            int(period_days), str(audit_file), int(stat.st_mtime_ns), int(stat.st_size),
        )
    else:
        cache_key = (int(period_days), str(audit_file) if audit_file else "", 0, 0)
    now = time.monotonic()
    if not refresh and cache_key in _attribution_cache:
        cached_at, cached_payload = _attribution_cache[cache_key]
        if now - cached_at < _ATTRIBUTION_CACHE_TTL:
            return {
                "success": True,
                "data": cached_payload,
                "cached": True,
                "cache_age_seconds": round(now - cached_at, 3),
            }

    if audit_file is None or not audit_file.is_file():
        empty = {
            "period_start": None,
            "period_end": None,
            "period_days": period_days,
            "n_rebalances": 0,
            "n_factor_on_rebalances": 0,
            "factor_on_return_pct": 0.0,
            "factor_off_return_pct": 0.0,
            "factor_contribution_pct": 0.0,
            "hit_rate_pct": 0.0,
            "top_winner_etfs": [],
            "top_loser_etfs": [],
            "per_rebalance_attribution": [],
            "notes": ["Audit log not configured — set ETF_AUDIT_LOG_PATH."],
        }
        _attribution_cache[cache_key] = (now, empty)
        return {"success": True, "data": empty, "cached": False}

    nav = _fetch_attribution_prices(audit_file, period_days)
    if nav is None:
        # Even with no prices the engine returns a structured "zero" report,
        # which the UI can render with a "data unavailable" hint.
        nav = pd.DataFrame()
    report: AttributionReport = compute_attribution(
        audit_file, nav, period_days=period_days,
    )
    payload = report.to_dict()
    _attribution_cache[cache_key] = (now, payload)
    return {"success": True, "data": payload, "cached": False}


# ---------------------------------------------------------------------------
# Historical backtest harness
#
# Replays ``EtfRotationStrategy`` over a closed historical window and returns
# a structured ``BacktestReport``. The endpoint is intentionally synchronous —
# 3-month windows take ~5s on the committed 4-year price matrix; longer
# windows degrade gracefully but the caller should expect at most ~30s for a
# year-long span. No live data is fetched.
# ---------------------------------------------------------------------------


def _parse_tc_model(payload: dict[str, Any]) -> Optional[TransactionCostModel]:
    """Translate the optional ``tc_model`` body slot into a model instance.

    Body shape accepted (all fields optional except presence of the key):

        {"tc_model": {"commission_bps": 3.0, "bid_ask_spread_bps": 5.0, ...}}

    Or simply ``{"tc_model": true}`` to enable the model with all defaults.
    ``{"tc_model": false}`` or ``{"tc_model": null}`` / absence → opt-out
    (the report stays gross-of-fees, matching pre-TC behaviour). Raises
    ``HTTPException(422)`` on malformed inputs so the caller can surface
    the error directly.
    """

    raw = payload.get("tc_model")
    if raw is None or raw is False:
        return None
    if raw is True:
        return TransactionCostModel()
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=422,
            detail=(
                "tc_model must be either a bool (true=defaults, "
                "false/null=disabled) or a JSON object with override fields."
            ),
        )
    try:
        return TransactionCostModel.from_overrides(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"tc_model: {exc}") from exc


def _load_backtest_price_matrix(prices_csv_path: Optional[Path]) -> pd.DataFrame:
    """Load the wide price matrix used by the backtest endpoint.

    Defaults to ``DEFAULT_BACKTEST_PRICE_CSV`` when ``prices_csv_path`` is
    ``None``. Raises ``FileNotFoundError`` when the file is missing — the
    handler converts that into a 503 so the frontend can surface
    "historical data unavailable" without crashing.
    """

    csv_path = prices_csv_path or DEFAULT_BACKTEST_PRICE_CSV
    if not csv_path.is_file():
        raise FileNotFoundError(str(csv_path))
    frame = pd.read_csv(csv_path, index_col=0)
    frame.index = pd.to_datetime(frame.index)
    return (
        frame.apply(pd.to_numeric, errors="coerce")
        .sort_index()
        .ffill()
        .dropna(how="all")
    )


@router.post(
    "/backtest",
    summary="历史回放 ETF 轮动策略并返回业绩指标",
    description=(
        "在已提交的历史价格矩阵（默认 ``data/etf_backtest/etf_prices_4y.csv``）上"
        "回放 ``EtfRotationStrategy``：根据指定的 ``period_start`` / ``period_end`` "
        "窗口逐周（默认）调仓，输出 ``BacktestReport`` —— 总收益 / Sharpe / 最大回撤 / "
        "Calmar / 平均换手 / 命中率 / 等权 buy-and-hold 对照。"
        "\n\n"
        "``enable_policy_signal_factor`` 用于 A/B 测试因子开关；"
        "``strategy_config_overrides`` 接受一个 partial 的 strategy 块（如 ``min_score_to_hold``）。"
        "**不计算交易成本、不模拟买卖价差、不建模冲击成本** —— 详见 BacktestReport.caveats。"
        "调用预期同步，3 个月窗口 < 30s。"
    ),
)
def post_backtest(
    payload: dict[str, Any] = Body(default_factory=dict),  # type: ignore[assignment]
) -> dict[str, Any]:
    period_start = payload.get("period_start")
    period_end = payload.get("period_end")
    enable_policy_signal_factor = bool(
        payload.get("enable_policy_signal_factor", False)
    )
    rebalance_freq_days = int(
        payload.get("rebalance_freq_days", DEFAULT_REBALANCE_FREQ_DAYS) or 1
    )
    initial_capital = float(
        payload.get("initial_capital", DEFAULT_INITIAL_CAPITAL) or DEFAULT_INITIAL_CAPITAL
    )
    overrides = payload.get("strategy_config_overrides") or {}
    if not isinstance(overrides, dict):
        raise HTTPException(
            status_code=422,
            detail="strategy_config_overrides must be a JSON object.",
        )
    if rebalance_freq_days < 1:
        raise HTTPException(
            status_code=422,
            detail="rebalance_freq_days must be >= 1.",
        )
    if initial_capital <= 0:
        raise HTTPException(
            status_code=422,
            detail="initial_capital must be > 0.",
        )

    try:
        prices = _load_backtest_price_matrix(None)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Backtest price matrix not found at {exc}. Run the data "
                "pipeline (`scripts/refresh_*`) before calling /backtest."
            ),
        )

    strategy_cfg = load_strategy_config()
    if overrides:
        merged_strategy = {**strategy_cfg.strategy, **overrides}
        strategy_cfg = dataclass_replace(strategy_cfg, strategy=merged_strategy)

    holdings = [
        h for h in daily_etf_signal.load_default_holdings() if h.code in prices.columns
    ] or daily_etf_signal.load_default_holdings()
    config = daily_etf_signal.build_strategy_config(holdings, strategy_cfg)

    industry_signals: Optional[dict[str, Any]] = None
    etf_industry_map: Optional[dict[str, str]] = (
        dict(strategy_cfg.etf_industry_map) if strategy_cfg.etf_industry_map else None
    )
    if enable_policy_signal_factor:
        loaded, _last_refresh = daily_etf_signal.load_policy_industry_signals()
        if loaded:
            industry_signals = dict(loaded)

    tc_model = _parse_tc_model(payload)
    backtester = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start=period_start,
        period_end=period_end,
        policy_signal_factor_enabled=enable_policy_signal_factor,
        industry_signals=industry_signals,
        etf_industry_map=etf_industry_map,
        rebalance_freq_days=rebalance_freq_days,
        initial_capital=initial_capital,
        tc_model=tc_model,
    )
    report = backtester.run()
    return {"success": True, "data": report.to_dict()}


# ---------------------------------------------------------------------------
# Walkforward stability analyzer
#
# Rolls ``EtfRotationBacktester`` across overlapping windows of the committed
# 4-year price matrix and returns the aggregate ``WalkforwardReport``. The
# expensive bit is the per-window backtest; for 15 months / 3-month windows /
# 1-month step we generate ~13 windows ≈ ~13 backtests. Each takes a few
# seconds, so the full run is on the order of 30-60s. We cache the JSON
# payload for ``_WALKFORWARD_CACHE_TTL`` seconds keyed on every parameter
# that materially affects the result, so a follow-up poll from the UI returns
# instantly without re-running the windows.
# ---------------------------------------------------------------------------


_WALKFORWARD_CACHE_TTL = 3600.0  # 1 hour
# Cache key is the full set of params the analyzer reads + the price-matrix
# mtime/size so a new CSV invalidates everything in-flight.
_walkforward_cache: dict[
    tuple[
        str, str, int, int, int, bool, int, float, str, int, int,
    ],
    tuple[float, dict[str, Any]],
] = {}


def reset_walkforward_cache_for_tests() -> None:
    """Drop the walkforward cache — tests call this between scenarios."""

    _walkforward_cache.clear()


@router.post(
    "/walkforward",
    summary="多窗口滚动回放 ETF 轮动策略并返回稳定性报告",
    description=(
        "把 ``EtfRotationBacktester`` 在已提交的历史价格矩阵（默认 "
        "``data/etf_backtest/etf_prices_4y.csv``）上滚动多次，每次切一个 "
        "``window_months`` 长的子窗口（默认 3 个月），按 ``step_months`` 步进 "
        "（默认 1 个月）。返回 ``WalkforwardReport`` —— 每个窗口的 BacktestReport "
        "原样保留，并汇总：median/mean/std 窗口收益、正收益窗口比例、平均与最差 "
        "MaxDD、平均 Sharpe、平均 buy-hold 对照、0-1 的 ``consistency_score``。"
        "\n\n"
        "请求体（全部可选除明确标注）："
        "``{period_start: ISO 日期, period_end: ISO 日期, window_months: int=3, "
        "step_months: int=1, enable_policy_signal_factor: bool=false, "
        "rebalance_freq_days: int=5, initial_capital: float=100000, "
        "strategy_config_overrides: object}``。"
        "``period_start`` / ``period_end`` 必填 —— 没有外层边界 walkforward 无从滚动。"
        "\n\n"
        "缓存 1 小时；缓存 key 包含所有窗口参数 + 价格 CSV 的 mtime/size，"
        "新 CSV 自动让全部 in-flight 缓存失效。同步执行，~13 个窗口实测 ~60s。"
        "**全部继承 v0.1 backtest 的简化**：无交易成本 / 无买卖价差 / 无冲击 / "
        "next-bar close 全额成交 / 无幸存者偏差；额外 walkforward 警示：重叠窗口在 "
        "``aggregate_return_pct`` 上会双计重叠部分，看 ``median_window_return_pct`` 更稳。"
    ),
)
def post_walkforward(
    payload: dict[str, Any] = Body(default_factory=dict),  # type: ignore[assignment]
) -> dict[str, Any]:
    period_start = payload.get("period_start")
    period_end = payload.get("period_end")
    if not period_start or not period_end:
        raise HTTPException(
            status_code=422,
            detail="period_start and period_end are required for walkforward.",
        )

    # Explicit None-check rather than ``or`` so a deliberate ``0`` reaches the
    # validation block below and returns 422 instead of being silently coerced
    # back to the default.
    window_months_raw = payload.get("window_months")
    window_months = int(
        window_months_raw if window_months_raw is not None else DEFAULT_WINDOW_MONTHS
    )
    step_months_raw = payload.get("step_months")
    step_months = int(
        step_months_raw if step_months_raw is not None else DEFAULT_STEP_MONTHS
    )
    enable_policy_signal_factor = bool(
        payload.get("enable_policy_signal_factor", False)
    )
    rebalance_freq_days = int(
        payload.get("rebalance_freq_days", DEFAULT_REBALANCE_FREQ_DAYS) or 1
    )
    initial_capital = float(
        payload.get("initial_capital", DEFAULT_INITIAL_CAPITAL) or DEFAULT_INITIAL_CAPITAL
    )
    overrides = payload.get("strategy_config_overrides") or {}
    refresh = bool(payload.get("refresh", False))

    if not isinstance(overrides, dict):
        raise HTTPException(
            status_code=422,
            detail="strategy_config_overrides must be a JSON object.",
        )
    if window_months < 1:
        raise HTTPException(status_code=422, detail="window_months must be >= 1.")
    if step_months < 1:
        raise HTTPException(status_code=422, detail="step_months must be >= 1.")
    if rebalance_freq_days < 1:
        raise HTTPException(status_code=422, detail="rebalance_freq_days must be >= 1.")
    if initial_capital <= 0:
        raise HTTPException(status_code=422, detail="initial_capital must be > 0.")

    csv_path = DEFAULT_BACKTEST_PRICE_CSV
    if not csv_path.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Backtest price matrix not found at {csv_path}. Run the data "
                "pipeline (`scripts/refresh_*`) before calling /walkforward."
            ),
        )
    stat = csv_path.stat()

    # Cache key — including overrides via repr() so the hash distinguishes
    # parameter variations without needing each field broken out. The
    # reserved slot stores a stable repr of the TC model so toggling the
    # cost layer (or tweaking its params) invalidates the cache.
    overrides_key = repr(sorted(overrides.items())) if overrides else ""
    tc_payload = payload.get("tc_model")
    tc_key = repr(tc_payload) if tc_payload is not None else ""
    cache_key = (
        str(period_start),
        str(period_end),
        window_months,
        step_months,
        rebalance_freq_days,
        enable_policy_signal_factor,
        int(initial_capital * 100),  # cents-precision key so floats key cleanly
        float(0),  # reserved slot — keep cache_key shape stable for future params
        overrides_key + "|tc=" + tc_key,
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )
    now = time.monotonic()
    if not refresh and cache_key in _walkforward_cache:
        cached_at, cached_payload = _walkforward_cache[cache_key]
        if now - cached_at < _WALKFORWARD_CACHE_TTL:
            return {
                "success": True,
                "data": cached_payload,
                "cached": True,
                "cache_age_seconds": round(now - cached_at, 3),
            }

    try:
        prices = _load_backtest_price_matrix(None)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Backtest price matrix not found at {exc}. Run the data "
                "pipeline (`scripts/refresh_*`) before calling /walkforward."
            ),
        )

    strategy_cfg = load_strategy_config()
    if overrides:
        merged_strategy = {**strategy_cfg.strategy, **overrides}
        strategy_cfg = dataclass_replace(strategy_cfg, strategy=merged_strategy)

    holdings = [
        h for h in daily_etf_signal.load_default_holdings() if h.code in prices.columns
    ] or daily_etf_signal.load_default_holdings()
    config = daily_etf_signal.build_strategy_config(holdings, strategy_cfg)

    industry_signals: Optional[dict[str, Any]] = None
    etf_industry_map: Optional[dict[str, str]] = (
        dict(strategy_cfg.etf_industry_map) if strategy_cfg.etf_industry_map else None
    )
    if enable_policy_signal_factor:
        loaded, _last_refresh = daily_etf_signal.load_policy_industry_signals()
        if loaded:
            industry_signals = dict(loaded)

    tc_model = _parse_tc_model(payload)
    analyzer = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=window_months,
        step_months=step_months,
        period_start=period_start,
        period_end=period_end,
        policy_signal_factor_enabled=enable_policy_signal_factor,
        industry_signals=industry_signals,
        etf_industry_map=etf_industry_map,
        rebalance_freq_days=rebalance_freq_days,
        initial_capital=initial_capital,
        tc_model=tc_model,
    )
    report = analyzer.run()
    response_payload = report.to_dict()
    _walkforward_cache[cache_key] = (now, response_payload)
    return {"success": True, "data": response_payload, "cached": False}


# ---------------------------------------------------------------------------
# Multi-strategy head-to-head comparison endpoint
#
# Runs ``EtfRotationStrategy``, ``EtfMeanReversionStrategy``, and
# ``EtfStrategyBlend`` (any subset) on the **same** historical window using
# the shared ``EtfRotationBacktester`` engine, then surfaces winner-by-metric,
# pairwise spreads, and a regime breakdown. Cached for 1 hour, keyed on every
# parameter that materially affects the result + the price CSV mtime/size.
# ---------------------------------------------------------------------------


_STRATEGY_COMPARISON_CACHE_TTL = 3600.0  # 1 hour
_strategy_comparison_cache: dict[
    tuple[
        str, str, str, int, bool, int, float, str, str, int, int,
    ],
    tuple[float, dict[str, Any]],
] = {}


def reset_strategy_comparison_cache_for_tests() -> None:
    """Drop the comparison cache — tests call this between scenarios."""

    _strategy_comparison_cache.clear()


@router.post(
    "/strategy-comparison",
    summary="同窗口对照回放 rotation / mean_reversion / blend 三大 ETF 策略",
    description=(
        "在已提交的历史价格矩阵（默认 ``data/etf_backtest/etf_prices_4y.csv``）上，"
        "让 ``EtfRotationStrategy`` / ``EtfMeanReversionStrategy`` / "
        "``EtfStrategyBlend``（或任意子集，通过 ``strategies`` 字段筛选）"
        "在 **同一个** 窗口 / 同一份价格 / 同一个 rebalance 节奏下回放，"
        "返回 ``ComparisonReport``：每个策略的完整 ``BacktestReport`` + "
        "Sharpe / 总收益 / Calmar / MaxDD / 换手 单项冠军 + trending/choppy "
        "区间分析（哪个策略在哪种 regime 占优）+ 全部有序两两的 return / sharpe / "
        "MaxDD 差值（A vs B = A 减 B，两个方向都返回）。"
        "\n\n"
        "请求体（全部可选除明确标注）："
        "``{period_start: ISO 日期 (必填), period_end: ISO 日期 (必填), "
        "strategies: list[str] 或逗号分隔 str，默认全 3 个；"
        "enable_policy_signal_factor: bool=false（仅 rotation + blend 的 trend leg 消费，"
        "mean_reversion 按约定忽略 —— 避免反趋势策略对政策利好做二次叠加），"
        "rebalance_freq_days: int=5, initial_capital: float=100000, "
        "blend_regime: str=unknown (bull/correction/sideways/bear/crisis/unknown), "
        "strategy_config_overrides: object, refresh: bool=false}``。"
        "\n\n"
        "缓存 1 小时；缓存 key 包含所有比较参数 + 价格 CSV 的 mtime/size，"
        "新 CSV 自动让 in-flight 缓存失效；响应里带 ``cached: bool`` + "
        "``cache_age_seconds``。同步执行，3 策略 × 15 个月窗口实测 ~10s。"
        "**全部继承 v0.1 backtest 简化**：无交易成本 / 无买卖价差 / 无冲击 / "
        "next-bar close 全额成交 / 无幸存者偏差 —— 比较是内部 apples-to-apples，"
        "但绝对收益不是 cost-adjusted 的活盘预测。"
    ),
)
def post_strategy_comparison(
    payload: dict[str, Any] = Body(default_factory=dict),  # type: ignore[assignment]
) -> dict[str, Any]:
    period_start = payload.get("period_start")
    period_end = payload.get("period_end")
    if not period_start or not period_end:
        raise HTTPException(
            status_code=422,
            detail="period_start and period_end are required for strategy-comparison.",
        )

    raw_strategies = payload.get("strategies")
    if raw_strategies is None:
        strategy_labels = list(DEFAULT_STRATEGY_LABELS)
    elif isinstance(raw_strategies, str):
        strategy_labels = [
            item.strip() for item in raw_strategies.split(",") if item.strip()
        ]
    elif isinstance(raw_strategies, (list, tuple)):
        strategy_labels = [str(item).strip() for item in raw_strategies if str(item).strip()]
    else:
        raise HTTPException(
            status_code=422,
            detail="strategies must be a list[str] or a comma-separated string.",
        )

    unknown = [label for label in strategy_labels if label not in DEFAULT_STRATEGY_LABELS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown strategies {unknown}; valid options are "
                f"{list(DEFAULT_STRATEGY_LABELS)}."
            ),
        )
    if not strategy_labels:
        raise HTTPException(
            status_code=422,
            detail="strategies must select at least one label.",
        )
    # Dedupe while preserving the caller-supplied order.
    deduped_labels: list[str] = []
    for label in strategy_labels:
        if label not in deduped_labels:
            deduped_labels.append(label)
    strategy_labels = deduped_labels

    enable_policy_signal_factor = bool(
        payload.get("enable_policy_signal_factor", False)
    )
    blend_regime = str(payload.get("blend_regime", "unknown") or "unknown")
    allowed_regimes = {"bull", "correction", "sideways", "bear", "crisis", "unknown"}
    if blend_regime not in allowed_regimes:
        raise HTTPException(
            status_code=422,
            detail=(
                f"blend_regime={blend_regime!r} is not valid; "
                f"choose one of {sorted(allowed_regimes)}."
            ),
        )

    rebalance_freq_days = int(
        payload.get("rebalance_freq_days", DEFAULT_REBALANCE_FREQ_DAYS) or 1
    )
    initial_capital = float(
        payload.get("initial_capital", DEFAULT_INITIAL_CAPITAL) or DEFAULT_INITIAL_CAPITAL
    )
    overrides = payload.get("strategy_config_overrides") or {}
    refresh = bool(payload.get("refresh", False))

    if not isinstance(overrides, dict):
        raise HTTPException(
            status_code=422,
            detail="strategy_config_overrides must be a JSON object.",
        )
    if rebalance_freq_days < 1:
        raise HTTPException(status_code=422, detail="rebalance_freq_days must be >= 1.")
    if initial_capital <= 0:
        raise HTTPException(status_code=422, detail="initial_capital must be > 0.")

    csv_path = DEFAULT_BACKTEST_PRICE_CSV
    if not csv_path.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Backtest price matrix not found at {csv_path}. Run the data "
                "pipeline (`scripts/refresh_*`) before calling /strategy-comparison."
            ),
        )
    stat = csv_path.stat()

    overrides_key = repr(sorted(overrides.items())) if overrides else ""
    tc_payload = payload.get("tc_model")
    tc_key = repr(tc_payload) if tc_payload is not None else ""
    cache_key = (
        str(period_start),
        str(period_end),
        ",".join(strategy_labels),
        rebalance_freq_days,
        enable_policy_signal_factor,
        int(initial_capital * 100),
        float(0),  # reserved slot — keep cache_key shape stable for future params
        blend_regime,
        overrides_key + "|tc=" + tc_key,
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )
    now = time.monotonic()
    if not refresh and cache_key in _strategy_comparison_cache:
        cached_at, cached_payload = _strategy_comparison_cache[cache_key]
        if now - cached_at < _STRATEGY_COMPARISON_CACHE_TTL:
            return {
                "success": True,
                "data": cached_payload,
                "cached": True,
                "cache_age_seconds": round(now - cached_at, 3),
            }

    try:
        prices = _load_backtest_price_matrix(None)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Backtest price matrix not found at {exc}. Run the data "
                "pipeline (`scripts/refresh_*`) before calling /strategy-comparison."
            ),
        )

    strategy_cfg = load_strategy_config()
    if overrides:
        merged_strategy = {**strategy_cfg.strategy, **overrides}
        strategy_cfg = dataclass_replace(strategy_cfg, strategy=merged_strategy)

    holdings = [
        h for h in daily_etf_signal.load_default_holdings() if h.code in prices.columns
    ] or daily_etf_signal.load_default_holdings()
    rotation_config = daily_etf_signal.build_strategy_config(holdings, strategy_cfg)

    industry_signals: Optional[dict[str, Any]] = None
    etf_industry_map: Optional[dict[str, str]] = (
        dict(strategy_cfg.etf_industry_map) if strategy_cfg.etf_industry_map else None
    )
    if enable_policy_signal_factor:
        loaded, _last_refresh = daily_etf_signal.load_policy_industry_signals()
        if loaded:
            industry_signals = dict(loaded)

    all_specs = build_default_strategy_specs(
        rotation_config, blend_regime=blend_regime,
    )
    chosen_specs = [all_specs[label] for label in strategy_labels]

    tc_model = _parse_tc_model(payload)
    comparator = StrategyComparator(
        strategies=chosen_specs,
        price_history=prices,
        period_start=period_start,
        period_end=period_end,
        industry_signals=industry_signals,
        etf_industry_map=etf_industry_map,
        rebalance_freq_days=rebalance_freq_days,
        initial_capital=initial_capital,
        tc_model=tc_model,
    )
    report = comparator.run()
    response_payload = report.to_dict()
    _strategy_comparison_cache[cache_key] = (now, response_payload)
    return {"success": True, "data": response_payload, "cached": False}


# ---------------------------------------------------------------------------
# Regime classifier + strategy recommender
#
# Productises commit ``a54b986``'s empirical finding (rotation wins choppy,
# mean_reversion wins trending). Reads the committed historical price
# matrix, classifies the trailing ``lookback_days`` window, and returns a
# typed recommendation the dashboard tile renders without any second
# round-trip.
# ---------------------------------------------------------------------------


@router.get(
    "/regime-recommendation",
    summary="基于市场状态分类返回推荐策略",
    description=(
        "对 ``data/etf_backtest/etf_prices_4y.csv`` 的最近 lookback_days 行做"
        "5 特征分类（trend R² / 波动率 / 偏度 / 回撤比 / 跨资产相关性）；"
        "每只 ETF 先在 lookback 起点归一化为 1.0，再构造等权市场代理，"
        "避免高价格基金支配信号。"
        "映射到 6 个 regime 之一，并返回对应的推荐策略 + config 覆盖。"
        "确定性、无 ML 模型；同样输入永远同样输出。"
        "\n\n"
        "实证锚点（commit ``a54b986`` 多策略比较）：2024-01-01 → 2025-04-30 窗口下，"
        "choppy 上半场 (R²=0.370) 是 rotation 胜出 (+5.48%)，"
        "trending 下半场 (R²=0.792) 是 mean_reversion 胜出 (+6.17%)。"
        "本端点把那张表落地成运行时建议。"
    ),
)
def get_regime_recommendation(
    lookback_days: int = Query(
        default=90,
        ge=10,
        le=500,
        description="计算窗口长度（交易日，默认 90）。",
    ),
    trend_r2_threshold: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="可选：覆盖 trending 判定的 R² 阈值（默认 0.55）。",
    ),
    vol_high_threshold: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=2.0,
        description="可选：覆盖 high-vol 阈值（年化波动率，默认 0.25）。",
    ),
) -> dict[str, Any]:
    try:
        prices = _load_backtest_price_matrix(None)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Backtest price matrix not found at {exc}. Run the data "
                "pipeline (`scripts/refresh_*`) before calling "
                "/regime-recommendation."
            ),
        )

    cfg_kwargs: dict[str, Any] = {}
    if trend_r2_threshold is not None:
        cfg_kwargs["trend_r2_threshold"] = float(trend_r2_threshold)
    if vol_high_threshold is not None:
        cfg_kwargs["vol_high_threshold"] = float(vol_high_threshold)
    config = ClassifierConfig(**cfg_kwargs) if cfg_kwargs else ClassifierConfig()

    classifier = MarketRegimeClassifier(config=config)
    regime = classifier.classify(prices, lookback_days=int(lookback_days))
    recommendation = recommend_strategy(regime)
    return {
        "success": True,
        "data": {
            "regime": regime.to_dict(),
            "recommendation": recommendation.to_dict(),
            "config": {
                "trend_r2_threshold": float(config.trend_r2_threshold),
                "vol_high_threshold": float(config.vol_high_threshold),
                "bear_slope_threshold": float(config.bear_slope_threshold),
                "skew_negative_threshold": float(config.skew_negative_threshold),
                "drawdown_ratio_high": float(config.drawdown_ratio_high),
                "correlation_high_threshold": float(
                    config.correlation_high_threshold
                ),
            },
        },
    }
