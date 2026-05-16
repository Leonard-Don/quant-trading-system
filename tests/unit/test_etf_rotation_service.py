"""Tests for the live-refreshing EtfRotationService.

These tests stay hermetic: a fake holdings loader / quote fetcher / history
fetcher are injected, plus a deterministic clock so the trading-hours branch
is testable without sleeping or mocking system time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd
import pytest

from src.data.etf_rotation import EtfHolding, EtfQuote
from src.strategy.etf_rotation_config_loader import StrategyConfig, load_strategy_config
from src.strategy.etf_rotation_service import (
    EtfRotationService,
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
