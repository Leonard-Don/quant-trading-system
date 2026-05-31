"""Pure helper functions extracted from ``endpoints/etf_rotation.py``.

These are stateless utilities (plan field-stamping / contract guards,
cached-plan serialisation, strategy-config summarisation, and the optional
transaction-cost-model parser). They have **no** module-level state and
**no** dependency on the endpoint module's service / preferences / cache
singletons, so they split cleanly out of the large endpoint module.

The functions remain underscore-prefixed and are re-imported by
``endpoints/etf_rotation.py`` so callsite paths (and ``etf_rotation.<name>``
access used by tests) are unchanged.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from scripts import daily_etf_signal
from src.backtest.transaction_costs import TransactionCostModel


def _ensure_actionable_fields(plan: dict[str, Any]) -> None:
    """Guarantee ``actionable`` and ``non_actionable_reasons`` are present and typed.

    ``generate_plan`` and ``EtfRotationService`` always emit these keys, but
    this function makes the API contract explicit rather than relying on the
    caller remembering to pass them through.  Calling it on every plan-bearing
    response ensures a client can rely on::

        response["data"]["actionable"]           → bool
        response["data"]["non_actionable_reasons"] → list[str]

    For a plan built on synthetic or stale price data ``actionable`` will be
    ``False`` and ``non_actionable_reasons`` will contain a human-readable
    explanation.  Live plans with fresh data will carry ``actionable=True`` and
    an empty list.

    The function is idempotent and never overrides a value already set by
    ``generate_plan`` — it only fills in safe defaults when a key is absent
    (which should not happen in production but guards against future refactors).
    """
    if not isinstance(plan.get("actionable"), bool):
        plan["actionable"] = True
    if not isinstance(plan.get("non_actionable_reasons"), list):
        plan["non_actionable_reasons"] = []


def _ensure_manual_execution_contract(plan: dict[str, Any]) -> None:
    """Guarantee every ETF plan-bearing response is manual-only.

    Generated plans include this field, but cached legacy/stubbed plans may not.
    The endpoint layer is the final HTTP guardrail: it restates the manual-only
    top-level booleans and exposes a stable nested contract for consumers.
    """

    existing = plan.get("execution_contract")
    contract = dict(existing) if isinstance(existing, dict) else {}
    contract.update(daily_etf_signal.manual_execution_contract())
    plan["manual_only"] = True
    plan["auto_ordering"] = False
    plan["execution_contract"] = contract


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
