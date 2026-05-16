"""Intraday ETF premium / discount monitor.

Pulls per-minute estimated NAV from Eastmoney's ``fundgz`` endpoint (the
same JSONP feed the public 1234567.com.cn site uses) and exposes a cached
view that the rotation service can consult on each refresh. The strategy's
*scoring* core stays daily-grain — premium overlays only kick in as a
short-circuit when intraday arbitrage windows materially distort an ETF's
market price relative to its underlying basket.

Architecture
------------
* The monitor is a thread-safe cache. It does not impose a fetch cadence
  on its own; callers (the FastAPI lifespan loop) call
  :meth:`refresh_async` on whatever schedule they want (60s is typical).
* Tests inject a fake fetcher via ``fetcher`` — no real HTTP. The
  default fetcher uses ``httpx`` with explicit ``trust_env=False`` to
  bypass macOS scutil-injected system proxies that block the endpoint
  in some environments.
* Cached entries carry a wall-clock timestamp. Consumers ask for
  overlays with a ``max_age_seconds`` window so stale data silently
  drops out of the signal instead of zombie-vetoing positions.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, Iterable, List, Mapping, Optional

from src.data.etf_rotation import parse_fundgz_to_nav
from src.strategy.etf_rotation_strategy import EtfOverlay

logger = logging.getLogger(__name__)


EASTMONEY_FUNDGZ_URL = "https://fundgz.1234567.com.cn/js/{code}.js"

# Trade source label exposed on enriched quotes so the dashboard can
# distinguish "premium from intraday monitor" vs "premium from a Sina
# pull" or other sources.
PREMIUM_SOURCE = "eastmoney_fundgz"


@dataclass
class PremiumSnapshot:
    """One in-cache NAV/premium entry."""

    code: str
    estimated_nav: float
    prev_nav: Optional[float]
    nav_change_pct: Optional[float]
    estimate_time: Optional[str]
    fetched_at: datetime
    raw: Optional[Dict[str, str]] = None

    def premium(self, market_price: Optional[float]) -> Optional[float]:
        """Compute (market - nav) / nav. Returns ``None`` when inputs invalid."""

        if market_price is None or not self.estimated_nav:
            return None
        try:
            return (float(market_price) - self.estimated_nav) / self.estimated_nav
        except (TypeError, ValueError, ZeroDivisionError):
            return None


AsyncFetcher = Callable[[str], Awaitable[Optional[str]]]


async def _httpx_fetcher(code: str) -> Optional[str]:
    """Default ``fetcher`` — uses httpx with system proxies disabled.

    Lazily imported so test environments that lack httpx still load this
    module (they'd inject a fake ``fetcher`` anyway).
    """

    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError as exc:
        logger.warning("httpx unavailable; premium monitor disabled: %s", exc)
        return None

    url = EASTMONEY_FUNDGZ_URL.format(code=code)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Referer": "https://fund.eastmoney.com/",
    }
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except Exception as exc:  # noqa: BLE001 — monitor must survive transient errors
        logger.debug("fundgz fetch failed for %s: %s", code, exc)
        return None


class EtfPremiumMonitor:
    """Thread-safe cache for intraday ETF NAV/premium snapshots."""

    def __init__(
        self,
        codes: Iterable[str],
        *,
        fetcher: Optional[AsyncFetcher] = None,
        max_age_seconds: int = 300,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._codes: List[str] = [c.strip() for c in codes if c]
        self._fetcher: AsyncFetcher = fetcher or _httpx_fetcher
        self._max_age_seconds = max_age_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache: Dict[str, PremiumSnapshot] = {}
        self._lock = threading.Lock()
        self._last_run_at: Optional[datetime] = None
        self._last_outcome: Dict[str, str] = {}  # code -> "ok" / error label

    @property
    def codes(self) -> List[str]:
        return list(self._codes)

    def set_codes(self, codes: Iterable[str]) -> None:
        """Replace the watched universe. Drops cache entries for removed codes."""

        with self._lock:
            self._codes = [c.strip() for c in codes if c]
            allowed = set(self._codes)
            self._cache = {k: v for k, v in self._cache.items() if k in allowed}

    async def refresh_async(self) -> Dict[str, str]:
        """Pull NAV for every watched code; returns ``{code: outcome}``.

        Outcomes: ``ok`` (cached), ``no_payload`` (empty response),
        ``parse_failed`` (couldn't decode), ``fetch_error`` (exception
        bubbled up from the fetcher). The monitor caches whatever it can
        and reports failures so dashboards can surface stale spots.
        """

        outcomes: Dict[str, str] = {}
        for code in list(self._codes):
            try:
                raw = await self._fetcher(code)
            except Exception as exc:  # noqa: BLE001
                logger.debug("premium fetcher raised for %s: %s", code, exc)
                outcomes[code] = "fetch_error"
                continue
            if raw is None:
                outcomes[code] = "fetch_error"
                continue
            nav_record = parse_fundgz_to_nav(raw)
            if nav_record is None:
                outcomes[code] = "parse_failed"
                continue
            try:
                snapshot = PremiumSnapshot(
                    code=nav_record["code"],
                    estimated_nav=float(nav_record["estimated_nav"]),
                    prev_nav=(
                        float(nav_record["prev_nav"])
                        if nav_record.get("prev_nav") is not None
                        else None
                    ),
                    nav_change_pct=nav_record.get("change_pct"),
                    estimate_time=nav_record.get("estimate_time"),
                    fetched_at=self._clock(),
                    raw=None,  # don't keep raw blob in memory
                )
            except (KeyError, TypeError, ValueError):
                outcomes[code] = "parse_failed"
                continue
            with self._lock:
                self._cache[snapshot.code] = snapshot
            outcomes[snapshot.code] = "ok"
        with self._lock:
            self._last_run_at = self._clock()
            self._last_outcome = outcomes
        return outcomes

    def get_snapshot(self, code: str) -> Optional[PremiumSnapshot]:
        """Thread-safe lookup. Returns ``None`` when missing or stale."""

        with self._lock:
            snapshot = self._cache.get(code)
        if snapshot is None:
            return None
        age = (self._clock() - snapshot.fetched_at).total_seconds()
        if age > self._max_age_seconds:
            return None
        return snapshot

    def build_overlays(
        self,
        market_prices: Mapping[str, Optional[float]],
        *,
        reason_label: str = "intraday_premium_monitor",
        auto_block_threshold: Optional[float] = None,
    ) -> Dict[str, EtfOverlay]:
        """Return ``{code: EtfOverlay(...)}`` for fresh entries.

        The strategy's ``_score_premium`` consumes ``EtfOverlay.premium``
        (numeric penalty) and ``_apply_asset_constraints`` consumes
        ``EtfOverlay.block_new_buys`` (hard cap at current weight).
        Risk rules separately read the premium via ``EtfQuote.premium``
        — so we return overlays here and *separately* enrich the quotes
        via :meth:`enrichment_for_quote` so all three paths see the same
        intraday number.

        When ``auto_block_threshold`` is supplied and a code's premium
        meets or exceeds it (in absolute value, for positive premiums
        only — discounts are not a risk reason to refuse new buys),
        the overlay also carries ``block_new_buys=True``. The reason
        field is augmented so the audit log/dashboard can explain why.
        """

        overlays: Dict[str, EtfOverlay] = {}
        for code, price in market_prices.items():
            snapshot = self.get_snapshot(code)
            if snapshot is None:
                continue
            premium = snapshot.premium(price)
            if premium is None:
                continue
            block_new_buys = (
                auto_block_threshold is not None
                and premium >= auto_block_threshold - 1e-12
            )
            reason = reason_label
            if block_new_buys:
                reason = (
                    f"{reason_label}:premium_{premium:+.2%}_>=_"
                    f"{auto_block_threshold:.2%}_auto_block_new_buys"
                )
            overlays[code] = EtfOverlay(
                premium=premium,
                block_new_buys=block_new_buys,
                reason=reason,
            )
        return overlays

    def enrichment_for_quote(self, code: str) -> Optional[Dict[str, object]]:
        """Return a dict of fields to splice into an EtfQuote."""

        snapshot = self.get_snapshot(code)
        if snapshot is None:
            return None
        return {
            "estimated_nav": snapshot.estimated_nav,
            "prev_nav": snapshot.prev_nav,
        }

    def status(self) -> Dict[str, object]:
        """Diagnostic snapshot — last run time + per-code outcome."""

        with self._lock:
            return {
                "watched_codes": list(self._codes),
                "cached_codes": list(self._cache.keys()),
                "last_run_at": (
                    self._last_run_at.isoformat() if self._last_run_at else None
                ),
                "last_outcome": dict(self._last_outcome),
            }


async def run_premium_refresh_loop(
    monitor: EtfPremiumMonitor,
    *,
    interval_seconds: int = 60,
    initial_delay_seconds: float = 1.0,
) -> None:
    """Background task that keeps the monitor's cache fresh.

    Designed to be plugged into a FastAPI lifespan. Sleeps between
    fetches and survives any per-iteration exception so the loop never
    dies on a transient network hiccup. Exits cleanly when its
    asyncio task is cancelled.
    """

    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)
    interval = max(int(interval_seconds), 10)
    logger.info(
        "Starting ETF premium refresh loop (codes=%s, interval=%ss)",
        monitor.codes, interval,
    )
    try:
        while True:
            try:
                outcomes = await monitor.refresh_async()
                ok = sum(1 for v in outcomes.values() if v == "ok")
                logger.debug(
                    "premium monitor refresh: %d/%d ok",
                    ok, len(outcomes),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("premium monitor refresh failed: %s", exc)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("ETF premium refresh loop stopped")
        raise


__all__ = [
    "EASTMONEY_FUNDGZ_URL",
    "PREMIUM_SOURCE",
    "EtfPremiumMonitor",
    "PremiumSnapshot",
    "run_premium_refresh_loop",
]
