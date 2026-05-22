"""Tests for the synthetic / stale price-history hard gate.

The ETF rotation plan has REAL-MONEY stakes. A synthetic price matrix (a
fabricated deterministic uptrend) or a stale one (last bar long behind
the trading calendar) must NEVER silently produce a plan that *looks*
actionable. The gate adds a hard, structural ``actionable`` flag plus
``non_actionable_reasons`` — distinct from the soft, easy-to-miss
``source_health`` provenance field.

Contract under test:

* Synthetic price matrix (no ``price_matrix`` supplied) → ``actionable``
  is ``False`` unless an explicit override is passed.
* A real but stale matrix (last bar older than the staleness threshold)
  → ``actionable`` is ``False`` unless overridden.
* A fresh, supplied matrix → ``actionable`` is ``True``.
* The override (``allow_synthetic_or_stale=True``) flips ``actionable``
  back to ``True`` and records that the operator opted in.
* The manual-only contract holds regardless: ``manual_only`` stays
  ``True`` and ``auto_ordering`` stays ``False`` in every case.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import daily_etf_signal
from src.data.etf_rotation import EtfHolding, EtfQuote

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _holdings() -> list[EtfHolding]:
    return [
        EtfHolding(code="510300", name="沪深300ETF", shares=1000,
                   cost_price=5.0, current_price=5.0),
        EtfHolding(code="512400", name="有色金属ETF", shares=1000,
                   cost_price=2.0, current_price=2.0),
    ]


def _quotes() -> dict[str, EtfQuote]:
    return {
        "510300": EtfQuote(code="510300", name="沪深300ETF",
                           current_price=5.0, prev_close=5.0),
        "512400": EtfQuote(code="512400", name="有色金属ETF",
                           current_price=2.0, prev_close=2.0),
    }


def _real_price_matrix(*, end_date: pd.Timestamp, days: int = 260) -> pd.DataFrame:
    """A plausible 'real' wide-form close-price matrix ending at ``end_date``.

    Deterministic, but built as if it were fetched live — the gate keys
    off the *staleness of the last bar* and the *supplied* flag, not the
    numbers, so this stands in for genuine history.
    """

    dates = pd.bdate_range(end=end_date, periods=days)
    rng = np.random.default_rng(7)
    matrix: dict[str, pd.Series] = {}
    for code in ("510300", "512400"):
        drift = np.linspace(0.0, 0.15, days)
        noise = rng.normal(0.0, 0.004, days)
        matrix[code] = pd.Series(
            5.0 * np.exp(drift + np.cumsum(noise)), index=dates
        )
    return pd.DataFrame(matrix)


# ---------------------------------------------------------------------------
# Synthetic-fallback gate
# ---------------------------------------------------------------------------


def test_synthetic_price_matrix_plan_is_not_actionable_by_default() -> None:
    """No ``price_matrix`` → synthetic fallback → must be flagged
    NON-ACTIONABLE with a hard structural flag."""

    plan = daily_etf_signal.generate_plan(
        holdings=_holdings(),
        quotes=_quotes(),
    )

    assert plan["actionable"] is False
    reasons = plan.get("non_actionable_reasons") or []
    assert any("synthetic" in str(r) for r in reasons), (
        f"expected a synthetic reason, got {reasons!r}"
    )
    # Manual-only contract is independent of the gate and must still hold.
    assert plan["manual_only"] is True
    assert plan["auto_ordering"] is False


def test_synthetic_plan_actionable_when_override_passed() -> None:
    """The explicit override makes a synthetic plan actionable again — for
    tests / offline demos — and records the opt-in."""

    plan = daily_etf_signal.generate_plan(
        holdings=_holdings(),
        quotes=_quotes(),
        allow_synthetic_or_stale=True,
    )

    assert plan["actionable"] is True
    assert plan["data_safety"]["override_applied"] is True
    assert plan["manual_only"] is True
    assert plan["auto_ordering"] is False


# ---------------------------------------------------------------------------
# Stale-matrix gate
# ---------------------------------------------------------------------------


def test_stale_price_matrix_plan_is_not_actionable() -> None:
    """A supplied-but-stale matrix (last bar weeks old) must be flagged
    NON-ACTIONABLE even though it is 'real' data."""

    now = pd.Timestamp("2026-05-22T08:00:00Z")
    # Last bar 30 calendar days behind 'now' — well past any sane staleness
    # threshold.
    stale = _real_price_matrix(end_date=pd.Timestamp("2026-04-22"))

    plan = daily_etf_signal.generate_plan(
        holdings=_holdings(),
        quotes=_quotes(),
        price_matrix=stale,
        price_matrix_as_of="2026-04-22T00:00:00",
        now=now.to_pydatetime(),
    )

    assert plan["actionable"] is False
    reasons = plan.get("non_actionable_reasons") or []
    assert any("stale" in str(r) for r in reasons), (
        f"expected a staleness reason, got {reasons!r}"
    )
    assert plan["manual_only"] is True
    assert plan["auto_ordering"] is False


def test_stale_price_matrix_actionable_when_override_passed() -> None:
    now = pd.Timestamp("2026-05-22T08:00:00Z")
    stale = _real_price_matrix(end_date=pd.Timestamp("2026-04-22"))

    plan = daily_etf_signal.generate_plan(
        holdings=_holdings(),
        quotes=_quotes(),
        price_matrix=stale,
        price_matrix_as_of="2026-04-22T00:00:00",
        now=now.to_pydatetime(),
        allow_synthetic_or_stale=True,
    )

    assert plan["actionable"] is True
    assert plan["data_safety"]["override_applied"] is True


def test_fresh_price_matrix_plan_is_actionable() -> None:
    """A real, supplied matrix whose last bar is current → actionable
    with no override needed."""

    now = pd.Timestamp("2026-05-22T08:00:00Z")
    fresh = _real_price_matrix(end_date=pd.Timestamp("2026-05-22"))

    plan = daily_etf_signal.generate_plan(
        holdings=_holdings(),
        quotes=_quotes(),
        price_matrix=fresh,
        price_matrix_as_of="2026-05-22T00:00:00",
        now=now.to_pydatetime(),
    )

    assert plan["actionable"] is True
    reasons = plan.get("non_actionable_reasons") or []
    assert reasons == []
    assert plan["data_safety"]["price_matrix_synthetic"] is False
    assert plan["data_safety"]["price_matrix_stale"] is False


def test_data_safety_block_always_present() -> None:
    """Every plan carries a structural ``data_safety`` block + ``actionable``
    flag so consumers never have to guess."""

    plan = daily_etf_signal.generate_plan(holdings=_holdings(), quotes=_quotes())
    assert "actionable" in plan
    assert "data_safety" in plan
    ds = plan["data_safety"]
    assert "price_matrix_synthetic" in ds
    assert "price_matrix_stale" in ds
    assert "staleness_threshold_trading_days" in ds
    assert "override_applied" in ds
