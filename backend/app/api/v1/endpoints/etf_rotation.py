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
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from scripts import daily_etf_signal
from src.strategy.etf_rotation_analytics import summarise_edge
from src.strategy.etf_rotation_config_loader import load_strategy_config
from src.strategy.etf_rotation_preferences import (
    EtfRotationPreferences,
    get_preferences_store,
)
from src.strategy.etf_rotation_service import EtfRotationService

logger = logging.getLogger(__name__)

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
        outcome = service.refresh(force=True)
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
