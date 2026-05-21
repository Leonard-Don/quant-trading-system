"""Tests for the live-refreshing EtfRotationService.

These tests stay hermetic: a fake holdings loader / quote fetcher / history
fetcher are injected, plus a deterministic clock so the trading-hours branch
is testable without sleeping or mocking system time.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import pytest

from src.data.etf_rotation import EtfHolding, EtfQuote
from src.strategy.etf_rotation_config_loader import StrategyConfig, load_strategy_config
from src.strategy.etf_rotation_service import (
    EtfRotationService,
    audit_state_signature,
    is_within_trading_hours,
    max_weight_delta,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_holdings() -> List[EtfHolding]:
    return [
        EtfHolding(code="510300", name="沪深300ETF", shares=1000,
                   cost_price=5.0, current_price=5.0),
        EtfHolding(code="159985", name="豆粕ETF", shares=1000,
                   cost_price=2.0, current_price=2.0),
    ]


def _fake_holdings_loader():
    return _build_holdings(), True


def _empty_quotes(codes: Sequence[str], use_cache: bool) -> Tuple[Dict[str, EtfQuote], Dict[str, Any]]:
    return {}, {
        "requested": len(codes), "resolved": 0,
        "missing": len(codes), "use_cache": use_cache,
    }


def _build_price_matrix(codes: Sequence[str], days: int = 120, seed: int = 0) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=days)
    rng = np.random.default_rng(seed)
    data = {}
    for offset, code in enumerate(codes):
        drift = np.linspace(0, 0.10 + 0.05 * offset, days)
        noise = np.cumsum(rng.normal(0, 0.003, days))
        data[code] = 5.0 * np.exp(drift + noise)
    return pd.DataFrame(data, index=dates)


def _config_with_refresh_enabled(tmp_path: Path) -> StrategyConfig:
    import json

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "refresh": {
            "enabled": True,
            "interval_seconds": 60,
            "rebalance_debounce_weight": 0.01,
            "trading_hours": [["09:30", "11:30"], ["13:00", "15:00"]],
            "timezone": "Asia/Shanghai",
        }
    }))
    return load_strategy_config(path)


# ---------------------------------------------------------------------------
# Trading-hours helper
# ---------------------------------------------------------------------------


def test_is_within_trading_hours_monday_open() -> None:
    # Monday 2026-05-11 10:00 Shanghai time = 02:00 UTC.
    when = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)
    sessions = [["09:30", "11:30"], ["13:00", "15:00"]]
    assert is_within_trading_hours(when, sessions, "Asia/Shanghai") is True


def test_is_within_trading_hours_weekend_closed() -> None:
    # Saturday 2026-05-09 10:00 Shanghai time → closed.
    when = datetime(2026, 5, 9, 2, 0, tzinfo=timezone.utc)
    sessions = [["09:30", "11:30"], ["13:00", "15:00"]]
    assert is_within_trading_hours(when, sessions, "Asia/Shanghai") is False


def test_is_within_trading_hours_lunch_break() -> None:
    # Monday 12:00 Shanghai time → between sessions.
    when = datetime(2026, 5, 11, 4, 0, tzinfo=timezone.utc)
    sessions = [["09:30", "11:30"], ["13:00", "15:00"]]
    assert is_within_trading_hours(when, sessions, "Asia/Shanghai") is False


def test_max_weight_delta_returns_l_infinity_norm() -> None:
    a = {"X": 0.30, "Y": 0.50, "Z": 0.20}
    b = {"X": 0.32, "Y": 0.45, "W": 0.10}
    # Per-key deltas: X 0.02, Y 0.05, Z 0.20 (dropped from b), W 0.10 (new in b).
    assert max_weight_delta(a, b) == 0.20
    assert max_weight_delta({}, {}) == 0.0


def test_audit_state_signature_ignores_market_noise() -> None:
    base = {
        "adjusted_weights": {"510300": 0.5004, "159985": 0.4996},
        "score_breakdown": {"510300": {"latest_price": 4.01}},
        "total_asset": 123456.0,
        "prices_at_decision": {"510300": 4.01},
        "risk_reasons": ["premium_block_active"],
        "overlays": {"510300": {"block_new_buys": True}},
    }
    noisy = {
        **base,
        "score_breakdown": {"510300": {"latest_price": 4.09}},
        "total_asset": 999999.0,
        "prices_at_decision": {"510300": 4.09},
        "run_at": "2026-05-19T10:00:00Z",
        "quote_source": "service:live",
    }

    assert audit_state_signature(base) == audit_state_signature(noisy)


def test_audit_state_signature_tracks_actionable_changes() -> None:
    base = {"adjusted_weights": {"510300": 0.5}, "risk_reasons": []}
    changed = {
        **base,
        "stop_loss_triggered": {"510300": {"reason": "drawdown"}},
    }

    assert audit_state_signature(base) != audit_state_signature(changed)


# ---------------------------------------------------------------------------
# Service: refresh / debounce / trading-hours
# ---------------------------------------------------------------------------


def test_service_refresh_during_trading_hours_caches_plan(tmp_path) -> None:
    cfg = _config_with_refresh_enabled(tmp_path)
    # Monday 10:00 SH = 02:00 UTC
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    def history_fetcher(codes, **_kw):
        return _build_price_matrix(list(codes), seed=1)

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=history_fetcher,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    outcome = service.refresh()
    assert outcome.refreshed is True
    assert outcome.cached is not None
    assert outcome.cached.refreshed_at == fixed_now
    assert outcome.cached.debounced is False
    plan = outcome.cached.plan
    assert "adjusted_weights" in plan


def test_service_refresh_outside_trading_hours_returns_cached(tmp_path) -> None:
    cfg = _config_with_refresh_enabled(tmp_path)
    monday_open = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)
    monday_after_close = datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc)  # 16:00 SH
    timeline = iter([monday_open, monday_after_close])

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes)),
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: next(timeline),
    )

    first = service.refresh()
    second = service.refresh()
    assert first.refreshed is True
    assert second.refreshed is False
    assert second.skipped_reason == "outside_trading_hours"


def test_service_refresh_debounces_when_weights_barely_change(tmp_path) -> None:
    cfg = _config_with_refresh_enabled(tmp_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    base = _build_price_matrix(["510300", "159985"], seed=2)

    def history_fetcher(codes, **_kw):
        return base.copy()

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=history_fetcher,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    first = service.refresh()
    second = service.refresh()
    assert first.refreshed is True
    # Identical history → weights identical → debounce kicks in.
    assert second.refreshed is False
    assert second.skipped_reason == "below_debounce_threshold"
    assert second.cached.debounced is True
    audit_lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 1


def test_service_force_refresh_skips_trading_hours_check(tmp_path) -> None:
    cfg = _config_with_refresh_enabled(tmp_path)
    after_close = datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc)  # 16:00 SH

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes)),
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: after_close,
    )

    outcome = service.refresh(force=True)
    assert outcome.refreshed is True


def test_service_invalidate_drops_cache(tmp_path) -> None:
    cfg = _config_with_refresh_enabled(tmp_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes)),
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    service.refresh()
    assert service.get_cached_plan() is not None
    service.invalidate()
    assert service.get_cached_plan() is None


def test_service_quote_source_reflects_inputs(tmp_path) -> None:
    cfg = _config_with_refresh_enabled(tmp_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    # Pure synthetic (no live quotes, no live history).
    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: pd.DataFrame(),
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )
    outcome = service.refresh(use_live_history=True, use_live_quotes=True)
    assert outcome.cached.plan["quote_source"] == "synthetic"


# ---------------------------------------------------------------------------
# Adaptive scoring smoke (delegates to strategy but exercised via service)
# ---------------------------------------------------------------------------


def test_service_premium_monitor_injects_overlays_into_plan(tmp_path) -> None:
    """When a premium monitor reports a fresh +6% premium for 512400,
    the service must enrich the quote with NAV and emit an overlay so
    both the risk-rule veto and the scoring penalty fire."""

    import asyncio

    from src.data.etf_premium_monitor import EtfPremiumMonitor

    cfg = _config_with_refresh_enabled(tmp_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    async def fake_fetcher(code: str):
        if code != "512400":
            return None
        payload = (
            'jsonpgz({"fundcode":"512400","name":"有色金属ETF",'
            '"jzrq":"2026-05-14","dwjz":"2.0000","gsz":"2.0000",'
            '"gszzl":"0.00","gztime":"2026-05-15 10:30"});'
        )
        return payload

    monitor = EtfPremiumMonitor(["510300", "512400"], fetcher=fake_fetcher)
    asyncio.run(monitor.refresh_async())

    # Live quote fetcher returns a 512400 market price 6% above NAV.
    def quotes_fetcher(codes, use_cache):
        from src.data.etf_rotation import EtfQuote
        return {
            "512400": EtfQuote(
                code="512400", name="有色",
                current_price=2.12, prev_close=2.00, source="fake-live",
                timestamp="2026-05-15T02:00:00+00:00",
            ),
        }, {"requested": len(codes), "resolved": 1, "missing": len(codes) - 1}

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=quotes_fetcher,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes)),
        premium_monitor=monitor,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    outcome = service.refresh(force=True)
    plan = outcome.cached.plan

    # Overlay surfaced in the plan output (6% > 5% hard premium veto).
    assert "overlays" in plan
    assert "512400" in plan["overlays"]
    assert plan["overlays"]["512400"]["premium"] == pytest.approx(0.06, abs=1e-6)
    # Quote enrichment: estimated_nav populated and the snapshot reflects it.
    snapshot = plan["quote_snapshot"]["512400"]
    assert snapshot.get("premium") == pytest.approx(0.06, abs=1e-6)
    # Premium-monitor status is also surfaced for dashboards.
    assert "premium_monitor_status" in plan


def test_service_premium_monitor_none_keeps_legacy_behaviour(tmp_path) -> None:
    cfg = _config_with_refresh_enabled(tmp_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes)),
        premium_monitor=None,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )
    outcome = service.refresh(force=True)
    plan = outcome.cached.plan
    assert plan.get("overlays") == {}
    assert "premium_monitor_status" not in plan


def test_service_applies_regime_derate_to_gross_cap(tmp_path) -> None:
    """A bear-regime price matrix must derate the strategy's gross_cap."""

    import json
    cfg_path = tmp_path / "strategy.json"
    cfg_path.write_text(json.dumps({
        "refresh": {"enabled": True, "interval_seconds": 60},
        "regime": {"enabled": True, "ma_long_window": 200},
    }))
    cfg = load_strategy_config(cfg_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    # Build a long down-trending 510300 series that ends below MA200.
    rng = np.random.default_rng(13)
    dates = pd.bdate_range("2024-01-02", periods=400)
    drift = np.linspace(0, np.log(0.7), 400)
    noise = np.cumsum(rng.normal(0, 0.003, 400))
    bear_series = 5.0 * np.exp(drift + noise)
    bear_matrix = pd.DataFrame(
        {"510300": bear_series, "159985": bear_series * 0.95},
        index=dates,
    )

    def fake_holdings():
        return [
            EtfHolding(code="510300", name="沪深300", shares=1000,
                       cost_price=5.0, current_price=float(bear_series[-1])),
            EtfHolding(code="159985", name="豆粕", shares=1000,
                       cost_price=2.0, current_price=2.0),
        ], True

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=fake_holdings,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: bear_matrix,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    outcome = service.refresh(force=True)
    plan = outcome.cached.plan

    assert "regime" in plan
    assert plan["regime"]["regime"] in {"bear", "crisis"}
    assert plan["regime"]["gross_cap_multiplier"] < 1.0
    # Derated gross cap: total non-cash <= base_gross_cap * multiplier
    base_cap = float(cfg.strategy.get("gross_cap", 0.90))
    multiplier = plan["regime"]["gross_cap_multiplier"]
    non_cash = sum(v for k, v in plan["adjusted_weights"].items() if k != "CASH")
    assert non_cash <= base_cap * multiplier + 1e-6


def test_service_applies_regime_scoring_overrides_in_bear(tmp_path) -> None:
    """In a bear regime, the scoring overrides for momentum/risk must
    be merged into the strategy_config that generate_plan sees."""

    import json
    cfg_path = tmp_path / "strategy.json"
    cfg_path.write_text(json.dumps({
        "refresh": {"enabled": True, "interval_seconds": 60},
        "regime": {
            "enabled": True,
            "ma_long_window": 200,
            "scoring_overrides": {
                "bear": {
                    "momentum_return20_multiplier": 50.0,
                    "risk_volatility_multiplier": 70.0,
                },
            },
        },
    }))
    cfg = load_strategy_config(cfg_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    # Forced bear: 400-day downtrend that ends below MA200.
    rng = np.random.default_rng(99)
    dates = pd.bdate_range("2024-01-02", periods=400)
    drift = np.linspace(0, np.log(0.7), 400)
    noise = np.cumsum(rng.normal(0, 0.003, 400))
    bear_series = 5.0 * np.exp(drift + noise)
    bear_matrix = pd.DataFrame(
        {"510300": bear_series, "159985": bear_series * 0.95}, index=dates,
    )

    def fake_holdings():
        return [
            EtfHolding(code="510300", name="沪深300", shares=1000,
                       cost_price=5.0, current_price=float(bear_series[-1])),
            EtfHolding(code="159985", name="豆粕", shares=1000,
                       cost_price=2.0, current_price=2.0),
        ], True

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=fake_holdings,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: bear_matrix,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    outcome = service.refresh(force=True)
    plan = outcome.cached.plan

    # Regime should classify as bear (or crisis) — both should trigger overrides
    assert plan["regime"]["regime"] in {"bear", "crisis"}
    overrides = plan["regime"]["scoring_overrides_applied"]
    if plan["regime"]["regime"] == "bear":
        # The bear overrides we configured should appear
        assert overrides.get("momentum_return20_multiplier") == pytest.approx(50.0)
        assert overrides.get("risk_volatility_multiplier") == pytest.approx(70.0)


def test_service_with_ensemble_disabled_uses_trend_only(tmp_path) -> None:
    """With ensemble.enabled=False (the default) plan must NOT contain blend metadata."""

    cfg = _config_with_refresh_enabled(tmp_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)
    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes)),
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )
    outcome = service.refresh(force=True)
    plan = outcome.cached.plan
    assert plan.get("ensemble", {}).get("enabled") is False


def test_service_policy_factor_override_rebuilds_live_strategy(
    tmp_path,
    monkeypatch,
) -> None:
    """A per-call policy override must affect the service-built strategy."""

    import json

    from scripts import daily_etf_signal

    cfg_path = tmp_path / "strategy.json"
    cfg_path.write_text(json.dumps({
        "refresh": {"enabled": True, "interval_seconds": 60},
        "regime": {"enabled": False},
        "strategy": {
            "policy_signal_factor_enabled": False,
            "min_score_to_hold": 0.0,
            "min_score_full_hold": 1.0,
        },
        "etf_industry_map": {"510300": "metals"},
    }))
    cfg = load_strategy_config(cfg_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)
    policy_snapshot = {"metals": {"avg_impact": 0.50, "mentions": 3, "signal": "bullish"}}
    monkeypatch.setattr(
        daily_etf_signal,
        "load_policy_industry_signals",
        lambda: (policy_snapshot, "2026-05-11T01:55:00+00:00"),
    )

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes)),
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    off_plan = service.refresh(
        force=True,
        enable_policy_signal_factor=False,
    ).cached.plan
    on_plan = service.refresh(
        force=True,
        enable_policy_signal_factor=True,
    ).cached.plan

    assert off_plan["policy_signal_factor"]["enabled"] is False
    assert off_plan["score_breakdown"]["510300"]["policy_adjustment"] is None
    assert on_plan["policy_signal_factor"]["enabled"] is True
    assert on_plan["policy_signal_factor"]["applied_count"] == 1
    meta = on_plan["score_breakdown"]["510300"]["policy_adjustment"]
    assert meta["applied"] is True
    assert meta["signal"] == "bullish"
    assert meta["weight_after"] == pytest.approx(
        on_plan["score_breakdown"]["510300"]["raw_target_weight"]
    )


def test_service_with_ensemble_enabled_blends_strategies(tmp_path) -> None:
    """Enabling ensemble in strategy.json must surface blend metadata in plan."""

    import json
    cfg_path = tmp_path / "strategy.json"
    cfg_path.write_text(json.dumps({
        "refresh": {"enabled": True, "interval_seconds": 60},
        "ensemble": {
            "enabled": True,
            "regime_blend_weights": {
                "bull": 0.70,
                "sideways": 0.50,
                "unknown": 0.80,
            },
        },
    }))
    cfg = load_strategy_config(cfg_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    # Long uptrend → regime should be bull
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2024-01-02", periods=400)
    bull_series = 5.0 * np.exp(np.linspace(0, np.log(1.30), 400) + np.cumsum(rng.normal(0, 0.003, 400)))
    bull_matrix = pd.DataFrame(
        {"510300": bull_series, "159985": bull_series * 0.95}, index=dates,
    )

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=lambda: ([
            EtfHolding(code="510300", name="沪深300", shares=1000,
                       cost_price=5.0, current_price=float(bull_series[-1])),
            EtfHolding(code="159985", name="豆粕", shares=1000,
                       cost_price=2.0, current_price=2.0),
        ], True),
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: bull_matrix,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    outcome = service.refresh(force=True)
    plan = outcome.cached.plan
    ensemble = plan["ensemble"]
    assert ensemble["enabled"] is True
    assert ensemble["regime"] == "bull"
    assert ensemble["alpha_trend"] == pytest.approx(0.70)
    assert ensemble["alpha_mean_reversion"] == pytest.approx(0.30)


def test_service_no_scoring_overrides_for_bull_regime(tmp_path) -> None:
    """A bull regime should leave the scoring at its defaults (or whatever
    default scoring overrides config provides — currently empty for bull)."""

    import json
    cfg_path = tmp_path / "strategy.json"
    cfg_path.write_text(json.dumps({
        "refresh": {"enabled": True, "interval_seconds": 60},
        "regime": {
            "enabled": True,
            "scoring_overrides": {
                "bear": {"momentum_return20_multiplier": 50.0},
                # No "bull" key → bull keeps defaults
            },
        },
    }))
    cfg = load_strategy_config(cfg_path)
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2024-01-02", periods=400)
    bull_series = 5.0 * np.exp(np.linspace(0, np.log(1.3), 400) + np.cumsum(rng.normal(0, 0.003, 400)))
    bull_matrix = pd.DataFrame(
        {"510300": bull_series, "159985": bull_series * 0.95}, index=dates,
    )

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=lambda: ([
            EtfHolding(code="510300", name="沪深300", shares=1000,
                       cost_price=5.0, current_price=float(bull_series[-1])),
        ], True),
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: bull_matrix,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    outcome = service.refresh(force=True)
    plan = outcome.cached.plan
    assert plan["regime"]["regime"] == "bull"
    # No bull override → empty dict
    assert plan["regime"]["scoring_overrides_applied"] == {}


def test_service_premium_auto_block_disables_new_buys_above_threshold(tmp_path) -> None:
    """Premium >= 5% must produce overlay with block_new_buys=True."""

    import asyncio

    from src.data.etf_premium_monitor import EtfPremiumMonitor

    cfg = _config_with_refresh_enabled(tmp_path)
    # Force the auto_block_threshold to 0.05.
    cfg = type(cfg)(  # rebuild with overridden premium config
        universe=cfg.universe, risk_rules=cfg.risk_rules,
        strategy=cfg.strategy, scoring=cfg.scoring,
        refresh=cfg.refresh, regime=cfg.regime,
        premium={"auto_block_threshold": 0.05},
        source_path=cfg.source_path, source_mtime=cfg.source_mtime,
    )
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    async def fake_fetcher(code: str):
        if code != "510300":
            return None
        # NAV 5.0, market will be 5.30 → 6% premium → auto-block fires.
        return (
            'jsonpgz({"fundcode":"510300","name":"沪深300ETF",'
            '"jzrq":"2026-05-14","dwjz":"5.0000","gsz":"5.0000",'
            '"gszzl":"0.00","gztime":"2026-05-15 10:30"});'
        )

    monitor = EtfPremiumMonitor(["510300", "159985"], fetcher=fake_fetcher)
    asyncio.run(monitor.refresh_async())

    def quotes_fetcher(codes, use_cache):
        return {
            "510300": EtfQuote(
                code="510300", name="沪深300ETF",
                current_price=5.30, prev_close=5.00, source="fake-live",
                timestamp="2026-05-15T02:00:00+00:00",
            ),
        }, {"requested": len(codes), "resolved": 1}

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=quotes_fetcher,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes)),
        premium_monitor=monitor,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    outcome = service.refresh(force=True)
    plan = outcome.cached.plan
    assert "510300" in plan["overlays"]
    overlay = plan["overlays"]["510300"]
    assert overlay["block_new_buys"] is True
    assert "auto_block_new_buys" in (overlay.get("reason") or "")


def test_service_premium_auto_block_inactive_below_threshold(tmp_path) -> None:
    """Premium below the threshold leaves block_new_buys False."""

    import asyncio

    from src.data.etf_premium_monitor import EtfPremiumMonitor

    cfg = _config_with_refresh_enabled(tmp_path)
    cfg = type(cfg)(
        universe=cfg.universe, risk_rules=cfg.risk_rules,
        strategy=cfg.strategy, scoring=cfg.scoring,
        refresh=cfg.refresh, regime=cfg.regime,
        premium={"auto_block_threshold": 0.05},
        source_path=cfg.source_path, source_mtime=cfg.source_mtime,
    )
    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    async def fake_fetcher(code: str):
        return (
            f'jsonpgz({{"fundcode":"{code}","name":"x","jzrq":"2026-05-14",'
            '"dwjz":"5.0000","gsz":"5.0000","gszzl":"0.00","gztime":"2026-05-15 10:30"});'
        )

    monitor = EtfPremiumMonitor(["510300"], fetcher=fake_fetcher)
    asyncio.run(monitor.refresh_async())

    def quotes_fetcher(codes, use_cache):
        return {
            "510300": EtfQuote(
                code="510300", name="沪深300ETF",
                current_price=5.05, prev_close=5.00, source="fake-live",  # only 1% premium
                timestamp="2026-05-15T02:00:00+00:00",
            ),
        }, {"requested": len(codes), "resolved": 1}

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=quotes_fetcher,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes)),
        premium_monitor=monitor,
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )
    outcome = service.refresh(force=True)
    plan = outcome.cached.plan
    assert plan["overlays"]["510300"]["block_new_buys"] is False


def test_service_reload_strategy_config_picks_up_file_edits(tmp_path, monkeypatch) -> None:
    """Editing strategy.json + calling reload_strategy_config must surface
    the new values without restarting the process."""

    import json
    cfg_path = tmp_path / "strategy.json"
    cfg_path.write_text(json.dumps({"strategy": {"gross_cap": 0.80}}))
    monkeypatch.setenv("ETF_STRATEGY_CONFIG_PATH", str(cfg_path))

    service = EtfRotationService()
    assert service._strategy_config.strategy["gross_cap"] == pytest.approx(0.80)

    cfg_path.write_text(json.dumps({"strategy": {"gross_cap": 0.65}}))
    new_cfg = service.reload_strategy_config()
    assert new_cfg.strategy["gross_cap"] == pytest.approx(0.65)
    assert service._strategy_config.strategy["gross_cap"] == pytest.approx(0.65)


def test_service_reload_strategy_config_propagates_universe_to_monitor(tmp_path, monkeypatch) -> None:
    import json

    from src.data.etf_premium_monitor import EtfPremiumMonitor

    cfg_path = tmp_path / "strategy.json"
    cfg_path.write_text(json.dumps({}))
    monkeypatch.setenv("ETF_STRATEGY_CONFIG_PATH", str(cfg_path))

    async def fetcher(code: str):
        return None
    monitor = EtfPremiumMonitor(["159985", "512400", "510300", "518680", "513130"], fetcher=fetcher)
    service = EtfRotationService(premium_monitor=monitor)

    # Replace universe with a single new code via reload.
    cfg_path.write_text(json.dumps({
        "universe": [
            {"code": "511260", "name": "10年国债ETF", "exchange": "sh",
             "max_weight": 0.20, "base_weight": 0.10,
             "risk_metadata": {"bucket": "fixed_income"}}
        ]
    }))
    service.reload_strategy_config()
    # set_codes is invoked → monitor's universe now is the user override
    # appended onto the built-in defaults.
    assert "511260" in monitor.codes


def test_service_propagates_cross_sectional_scoring(tmp_path) -> None:
    import json

    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({
        "strategy": {"scoring_mode": "cross_sectional"},
        "refresh": {"enabled": True, "interval_seconds": 60},
    }))
    cfg = load_strategy_config(path)

    fixed_now = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)

    service = EtfRotationService(
        strategy_config=cfg,
        holdings_loader=_fake_holdings_loader,
        quotes_fetcher=_empty_quotes,
        history_fetcher=lambda codes, **_kw: _build_price_matrix(list(codes), seed=4),
        audit_log_path=tmp_path / "audit.jsonl",
        clock=lambda: fixed_now,
    )

    outcome = service.refresh()
    plan = outcome.cached.plan
    # Cross-sectional mode must still produce a valid plan with adjusted weights.
    assert "adjusted_weights" in plan
    assert "CASH" in plan["adjusted_weights"]
