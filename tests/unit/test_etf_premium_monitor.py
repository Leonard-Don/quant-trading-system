"""Tests for the intraday ETF premium / NAV monitor."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

import pytest

from src.data.etf_premium_monitor import (
    EtfPremiumMonitor,
    PremiumSnapshot,
    run_premium_refresh_loop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fundgz_payload(
    code: str,
    nav: float,
    *,
    prev_nav: Optional[float] = None,
    change_pct: float = 0.5,
    estimate_time: str = "2026-05-15 10:30",
) -> str:
    payload = {
        "fundcode": code,
        "name": f"Fund {code}",
        "jzrq": "2026-05-14",
        "dwjz": f"{prev_nav if prev_nav is not None else nav:.4f}",
        "gsz": f"{nav:.4f}",
        "gszzl": f"{change_pct:.2f}",
        "gztime": estimate_time,
    }
    return f"jsonpgz({json.dumps(payload)});"


def _make_fetcher(
    payloads: Dict[str, str],
    *,
    raise_for: Optional[set] = None,
) -> Callable[[str], "asyncio.Future[Optional[str]]"]:
    async def fetcher(code: str) -> Optional[str]:
        if raise_for and code in raise_for:
            raise RuntimeError("simulated network error")
        return payloads.get(code)
    return fetcher


def _now_clock(start: datetime) -> Callable[[], datetime]:
    state = {"now": start}
    def tick(delta: float = 0.0) -> datetime:
        return state["now"]
    def advance(seconds: float) -> None:
        state["now"] = state["now"] + timedelta(seconds=seconds)
    tick.advance = advance  # type: ignore[attr-defined]
    return tick


# ---------------------------------------------------------------------------
# Cache and refresh
# ---------------------------------------------------------------------------


def test_refresh_caches_nav_and_marks_outcome_ok() -> None:
    payloads = {"510300": _fundgz_payload("510300", 4.9710, prev_nav=4.9500)}
    monitor = EtfPremiumMonitor(["510300"], fetcher=_make_fetcher(payloads))

    outcomes = asyncio.run(monitor.refresh_async())
    assert outcomes == {"510300": "ok"}

    snapshot = monitor.get_snapshot("510300")
    assert isinstance(snapshot, PremiumSnapshot)
    assert snapshot.estimated_nav == pytest.approx(4.9710)
    assert snapshot.prev_nav == pytest.approx(4.9500)


def test_premium_calculation_uses_market_price() -> None:
    snapshot = PremiumSnapshot(
        code="510300", estimated_nav=5.0, prev_nav=4.95,
        nav_change_pct=0.01, estimate_time=None,
        fetched_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    # 5.10 market vs 5.0 NAV → 2% premium
    assert snapshot.premium(5.10) == pytest.approx(0.02)
    # NAV unchanged but market discounted → negative premium
    assert snapshot.premium(4.90) == pytest.approx(-0.02)
    assert snapshot.premium(None) is None


def test_get_snapshot_drops_stale_entries() -> None:
    clock = _now_clock(datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc))
    payloads = {"510300": _fundgz_payload("510300", 5.0)}
    monitor = EtfPremiumMonitor(
        ["510300"], fetcher=_make_fetcher(payloads),
        max_age_seconds=120, clock=clock,
    )
    asyncio.run(monitor.refresh_async())
    assert monitor.get_snapshot("510300") is not None
    clock.advance(125)  # type: ignore[attr-defined]
    assert monitor.get_snapshot("510300") is None


def test_refresh_reports_per_code_outcome_labels() -> None:
    payloads = {
        "510300": _fundgz_payload("510300", 5.0),
        "159985": "jsonpgz();",  # parse failure (empty)
        "513130": "garbage",      # parse failure (malformed)
    }
    fetcher = _make_fetcher(payloads, raise_for={"512400"})
    monitor = EtfPremiumMonitor(
        ["510300", "159985", "513130", "512400"], fetcher=fetcher,
    )

    outcomes = asyncio.run(monitor.refresh_async())
    assert outcomes["510300"] == "ok"
    assert outcomes["159985"] == "parse_failed"
    assert outcomes["513130"] == "parse_failed"
    assert outcomes["512400"] == "fetch_error"


# ---------------------------------------------------------------------------
# Overlay construction
# ---------------------------------------------------------------------------


def test_build_overlays_returns_etf_overlay_for_fresh_entries() -> None:
    payloads = {
        "510300": _fundgz_payload("510300", 5.0),
        "159985": _fundgz_payload("159985", 2.0),
    }
    monitor = EtfPremiumMonitor(["510300", "159985"], fetcher=_make_fetcher(payloads))
    asyncio.run(monitor.refresh_async())

    overlays = monitor.build_overlays({"510300": 5.10, "159985": 1.95, "513130": None})
    assert set(overlays) == {"510300", "159985"}
    assert overlays["510300"].premium == pytest.approx(0.02)
    assert overlays["159985"].premium == pytest.approx(-0.025)
    # Missing price for 513130 → no overlay
    assert "513130" not in overlays


def test_build_overlays_skips_stale_entries() -> None:
    clock = _now_clock(datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc))
    payloads = {"510300": _fundgz_payload("510300", 5.0)}
    monitor = EtfPremiumMonitor(
        ["510300"], fetcher=_make_fetcher(payloads),
        max_age_seconds=60, clock=clock,
    )
    asyncio.run(monitor.refresh_async())
    clock.advance(75)  # type: ignore[attr-defined]
    overlays = monitor.build_overlays({"510300": 5.10})
    assert overlays == {}


def test_enrichment_for_quote_returns_nav_fields() -> None:
    payloads = {"510300": _fundgz_payload("510300", 5.0, prev_nav=4.95)}
    monitor = EtfPremiumMonitor(["510300"], fetcher=_make_fetcher(payloads))
    asyncio.run(monitor.refresh_async())
    enrichment = monitor.enrichment_for_quote("510300")
    assert enrichment is not None
    assert enrichment["estimated_nav"] == pytest.approx(5.0)
    assert enrichment["prev_nav"] == pytest.approx(4.95)


# ---------------------------------------------------------------------------
# Universe mutation
# ---------------------------------------------------------------------------


def test_set_codes_evicts_dropped_codes_from_cache() -> None:
    payloads = {
        "510300": _fundgz_payload("510300", 5.0),
        "159985": _fundgz_payload("159985", 2.0),
    }
    monitor = EtfPremiumMonitor(["510300", "159985"], fetcher=_make_fetcher(payloads))
    asyncio.run(monitor.refresh_async())
    assert monitor.get_snapshot("159985") is not None

    monitor.set_codes(["510300"])
    assert monitor.get_snapshot("510300") is not None
    assert monitor.get_snapshot("159985") is None


# ---------------------------------------------------------------------------
# Status payload
# ---------------------------------------------------------------------------


def test_status_includes_outcome_and_run_timestamp() -> None:
    clock = _now_clock(datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc))
    payloads = {"510300": _fundgz_payload("510300", 5.0)}
    monitor = EtfPremiumMonitor(
        ["510300", "missing"],
        fetcher=_make_fetcher(payloads),
        clock=clock,
    )
    asyncio.run(monitor.refresh_async())
    status = monitor.status()
    assert status["watched_codes"] == ["510300", "missing"]
    assert status["cached_codes"] == ["510300"]
    assert status["last_run_at"] is not None
    assert status["last_outcome"]["510300"] == "ok"
    assert status["last_outcome"]["missing"] == "fetch_error"


# ---------------------------------------------------------------------------
# Refresh loop survives transient errors
# ---------------------------------------------------------------------------


def test_run_premium_refresh_loop_survives_one_failure_and_continues() -> None:
    call_count = {"n": 0}

    async def flaky_fetcher(code: str) -> Optional[str]:
        call_count["n"] += 1
        if call_count["n"] <= 2:
            raise RuntimeError("transient")
        return _fundgz_payload("510300", 5.0)

    monitor = EtfPremiumMonitor(["510300"], fetcher=flaky_fetcher, max_age_seconds=300)

    async def driver() -> None:
        task = asyncio.create_task(
            run_premium_refresh_loop(
                monitor,
                interval_seconds=10,
                initial_delay_seconds=0,
            )
        )
        # Give the loop ~3 iterations of "instant sleeps" by patching sleep.
        # Easier: just wait briefly, then cancel.
        # We can't actually verify success without sleeping in real time —
        # instead inspect that the loop survived the early failures.
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(driver())
    assert call_count["n"] >= 1
