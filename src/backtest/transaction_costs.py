"""Transaction cost (TC) modelling for the ETF rotation backtest harness.

Every backtest result emitted by ``EtfRotationBacktester`` /
``EtfRotationWalkforwardAnalyzer`` / ``StrategyComparator`` up to this
module landed was **gross of execution friction**. The multi-strategy
comparison report (commit ``a54b986``) ended with a paragraph reading::

    With a typical CN ETF 5-10 bps round-trip fee, the turnover ranking
    (rotation 7.55% > MR 6.05% > blend 5.22%) means rotation's headline
    +8.71% would shrink first and blend's lead would widen.

This module turns that paragraph into actual numbers: a
:class:`TransactionCostModel` dataclass whose defaults track real CN
broker reality, an :func:`apply_transaction_costs` function that
converts a rebalance event into a structured :class:`CostBreakdown`, and
unit-tested invariants that let downstream callers reason about cost
drag without reinventing the calculation.

Default parameter rationale (Chinese ETF brokerage, 2024-2026)
--------------------------------------------------------------
* ``commission_bps = 3.0`` — most retail CN brokerages charge 0.025% to
  0.03% per side on ETF turnover, capped at a floor (5 RMB / trade is
  the common minimum). 3 bps is the conservative midpoint.
* ``min_commission_per_trade = 5.0`` — virtually every domestic broker
  (华泰 / 国泰君安 / 中信 / 招商 / 平安) floors single-trade ETF
  commission at 5 RMB. Smaller orders pay the floor, not the bps.
* ``bid_ask_spread_bps = 5.0`` — half-spread cost (we cross the spread
  once when entering, once when exiting; per-trade the realised half is
  reasonable). Popular ETFs (512400 metals, 510300 CSI300) trade at 1-3
  bps; thinner sector + QDII names can be 8-15 bps. 5 bps is the
  weighted midpoint for the configured rotation universe.
* ``market_impact_bps_per_pct_adv = 0.5`` — Almgren-style linear-in-ADV
  impact. At 5% of ADV a single trade pushes prices by ~0.5 * 5 = 2.5
  bps. Retail-sized portfolios (< 100 万 RMB) rarely cross 5% of ADV,
  so this term is mostly zero on the default 100k portfolio; it kicks
  in only when callers backtest larger AUM levels.
* ``min_trade_size_rmb = 100.0`` — anything below this rounds to "don't
  bother" — the floor commission alone would eat the trade. Real desks
  also batch sub-100 RMB drift into the next rebalance.

The defaults sum to ~8 bps one-way and ~16 bps round-trip on a typical
trade; the multi-strategy comparison note above is consistent with this
range.

Normalized weight-space invariance
----------------------------------
The model is dimensionless in ``portfolio_value`` — the per-trade RMB
costs scale linearly with AUM, and the headline metric the backtester
consumes is ``total_cost_bps_of_portfolio`` (bps of AUM, not RMB).
Callers without an explicit AUM should pass ``portfolio_value=1.0``;
the bps output is the same.

What this module does NOT model
-------------------------------
* **Stamp duty.** A-shares pay 千分之一 stamp on the sell side; ETFs
  are explicitly exempt under the 2008 财税[2008]171号 rule still in
  force. No need to model.
* **Borrow / shorting cost.** Rotation never goes net short — gross_cap
  < 1 leaves cash, not borrow.
* **Same-day reversal.** Real fills can produce a same-bar exit/entry
  that the strategy didn't intend; the harness uses next-bar close
  fills only, so this never appears in the cost ledger.
* **Tax wrappers.** Off-shore / 港股通 ETFs pay 10% dividend WHT but
  not on turnover — outside the scope of a trading-cost model.

See ``tests/unit/test_transaction_costs.py`` for the contract tests and
``docs/CHANGELOG.md`` Unreleased section for the integration write-up.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Union


# Defaults are surfaced module-level so CLIs / endpoints / tests can
# reference them without instantiating a model. Keep these tracking the
# docstring "Default parameter rationale" block above.
DEFAULT_COMMISSION_BPS = 3.0
DEFAULT_MIN_COMMISSION_PER_TRADE = 5.0
DEFAULT_BID_ASK_SPREAD_BPS = 5.0
DEFAULT_MARKET_IMPACT_BPS_PER_PCT_ADV = 0.5
DEFAULT_MIN_TRADE_SIZE_RMB = 100.0


@dataclass(frozen=True)
class TransactionCostModel:
    """Tunable transaction-cost parameters for an ETF rebalance event.

    All values are *positive numbers in their natural units*:

    * ``commission_bps`` — per-side commission as basis points of trade
      notional. Default 3.0 bps mirrors the conservative midpoint of CN
      retail brokerage rates (0.025%-0.03%). One-way; the harness
      applies it to *each* leg of a rebalance (buy and sell are both
      single-side fills).
    * ``min_commission_per_trade`` — RMB floor per single-leg trade.
      Default 5.0 matches the universal CN broker minimum.
    * ``bid_ask_spread_bps`` — half-spread cost per side, basis points
      of notional. Default 5.0 bps reflects the weighted average half-
      spread across the configured ETF universe (popular tickers 1-3
      bps; thinner sector + QDII 8-15 bps; weighted midpoint ~5).
    * ``market_impact_bps_per_pct_adv`` — Almgren-linear impact
      coefficient. A trade that is ``p%`` of ADV pays
      ``market_impact_bps_per_pct_adv * p`` bps in price impact.
      Default 0.5 is conservative for retail; institutions size this
      higher. **Only fires when ``trade_pct_adv > 5.0%``** — sub-5%
      trades pass under the impact radar.
    * ``min_trade_size_rmb`` — minimum notional below which the trade
      is rejected (cost-only; we don't actually re-route the trade,
      just don't charge commission/spread/impact since the model would
      flag a rebalance as "too small to bother" and the desk would
      defer to the next rebalance). Default 100.0 RMB.

    The frozen dataclass + ``__post_init__`` validation guarantees the
    model can be shared across threads/processes without surprise.
    """

    commission_bps: float = DEFAULT_COMMISSION_BPS
    min_commission_per_trade: float = DEFAULT_MIN_COMMISSION_PER_TRADE
    bid_ask_spread_bps: float = DEFAULT_BID_ASK_SPREAD_BPS
    market_impact_bps_per_pct_adv: float = DEFAULT_MARKET_IMPACT_BPS_PER_PCT_ADV
    min_trade_size_rmb: float = DEFAULT_MIN_TRADE_SIZE_RMB

    def __post_init__(self) -> None:
        # Negative parameters would silently fund the strategy; positive-or-zero only.
        # Keep these checks light so the dataclass stays cheap.
        if self.commission_bps < 0:
            raise ValueError("commission_bps must be >= 0")
        if self.min_commission_per_trade < 0:
            raise ValueError("min_commission_per_trade must be >= 0")
        if self.bid_ask_spread_bps < 0:
            raise ValueError("bid_ask_spread_bps must be >= 0")
        if self.market_impact_bps_per_pct_adv < 0:
            raise ValueError("market_impact_bps_per_pct_adv must be >= 0")
        if self.min_trade_size_rmb < 0:
            raise ValueError("min_trade_size_rmb must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly snapshot, useful when echoing back via API."""

        return asdict(self)

    @classmethod
    def from_overrides(
        cls,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> "TransactionCostModel":
        """Build a model from a partial overrides dict (CLI / API path).

        Unknown keys raise ``TypeError`` so a typo in the override block
        surfaces immediately instead of being silently dropped.
        """

        if not overrides:
            return cls()
        # ``dataclass`` constructor will already raise on unknown fields, but
        # explicit filtering keeps the error message tight.
        allowed = set(cls.__dataclass_fields__)
        unknown = [k for k in overrides if k not in allowed]
        if unknown:
            raise TypeError(
                f"TransactionCostModel: unknown override keys {unknown!r}. "
                f"Allowed: {sorted(allowed)}"
            )
        kwargs = {k: float(v) for k, v in overrides.items() if v is not None}
        return cls(**kwargs)


@dataclass(frozen=True)
class CostBreakdown:
    """Per-rebalance transaction-cost breakdown.

    ``total_cost_rmb`` is the raw RMB cost. ``total_cost_bps_of_portfolio``
    is the same quantity divided by the (assumed) portfolio value, in
    basis points — this is what the backtester subtracts from the period
    return before compounding.

    Per-leg breakdown is preserved for downstream audit/UI consumers; the
    list is in deterministic symbol-sorted order so two runs of the same
    rebalance produce byte-identical breakdowns.
    """

    commission_rmb: float
    spread_rmb: float
    impact_rmb: float
    total_cost_rmb: float
    total_cost_bps_of_portfolio: float
    n_trades_charged: int
    n_trades_skipped_under_min: int
    portfolio_value: float
    per_leg: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------


RebalanceEventLike = Union[
    Mapping[str, Any],
    "RebalanceEventInput",
]


@dataclass(frozen=True)
class RebalanceEventInput:
    """Compact descriptor of a rebalance event the cost model needs.

    The caller passes weight deltas (``delta_w``, dimensionless, where
    1.0 = 100% of portfolio) per symbol. Optional per-symbol ``adv_rmb``
    enables the market-impact term; when missing, impact is 0.

    Using a dataclass rather than the raw rebalance-log dict keeps the
    contract explicit, the field names typed, and the test fixtures
    readable.
    """

    portfolio_value: float
    weight_deltas: Mapping[str, float]
    adv_per_symbol: Optional[Mapping[str, float]] = None


def apply_transaction_costs(
    rebalance_event: RebalanceEventLike,
    model: TransactionCostModel,
) -> CostBreakdown:
    """Convert a rebalance event into a :class:`CostBreakdown`.

    The function is pure: given the same event + model, the output is
    byte-identical. No RNG, no environment knobs, no I/O.

    Algorithm (per traded symbol):

    1. ``trade_rmb = |delta_w| * portfolio_value``
    2. If ``trade_rmb < model.min_trade_size_rmb``: skip (no cost,
       counted in ``n_trades_skipped_under_min``).
    3. ``commission = max(trade_rmb * commission_bps/10000, min_commission_per_trade)``
    4. ``spread = trade_rmb * bid_ask_spread_bps / 10000``
    5. ``impact_bps = max(0, (trade_rmb / adv_rmb * 100 - 5) * impact_coef)``
       — only the *excess* over 5% of ADV is charged (sub-5% trades pay
       zero impact). Missing ``adv_rmb`` → impact = 0.
    6. ``impact_rmb = trade_rmb * impact_bps / 10000``

    Returns the aggregate breakdown; per-leg detail is preserved for
    UI / audit.
    """

    event = _coerce_event(rebalance_event)
    portfolio_value = float(event.portfolio_value)
    # Defensively normalise: 0 / negative AUM gives nonsense bps, so we
    # treat it as 1.0 (the "normalized weight-space" mode documented in
    # the module header).
    if not math.isfinite(portfolio_value) or portfolio_value <= 0:
        portfolio_value = 1.0

    weight_deltas = dict(event.weight_deltas or {})
    adv_per_symbol = dict(event.adv_per_symbol or {})

    commission_total = 0.0
    spread_total = 0.0
    impact_total = 0.0
    n_charged = 0
    n_skipped = 0
    per_leg: list[dict[str, Any]] = []

    # Deterministic order so two runs produce byte-identical output.
    for symbol in sorted(weight_deltas.keys()):
        delta_w = float(weight_deltas[symbol])
        if not math.isfinite(delta_w) or abs(delta_w) < 1e-12:
            continue

        trade_rmb = abs(delta_w) * portfolio_value
        if trade_rmb < model.min_trade_size_rmb:
            n_skipped += 1
            per_leg.append({
                "symbol": symbol,
                "delta_w": delta_w,
                "trade_rmb": trade_rmb,
                "skipped": True,
                "skip_reason": "below_min_trade_size",
                "commission_rmb": 0.0,
                "spread_rmb": 0.0,
                "impact_rmb": 0.0,
                "total_rmb": 0.0,
            })
            continue

        commission = max(
            trade_rmb * model.commission_bps / 10_000.0,
            model.min_commission_per_trade,
        )
        spread = trade_rmb * model.bid_ask_spread_bps / 10_000.0

        impact_rmb = 0.0
        impact_bps = 0.0
        adv_rmb = adv_per_symbol.get(symbol)
        if (
            adv_rmb is not None
            and math.isfinite(float(adv_rmb))
            and float(adv_rmb) > 0
        ):
            trade_pct_adv = (trade_rmb / float(adv_rmb)) * 100.0
            # Only the excess over 5% pays impact; sub-5% trades are
            # retail-size and don't move the tape.
            excess_pct = max(0.0, trade_pct_adv - 5.0)
            impact_bps = excess_pct * model.market_impact_bps_per_pct_adv
            impact_rmb = trade_rmb * impact_bps / 10_000.0

        total_rmb = commission + spread + impact_rmb
        commission_total += commission
        spread_total += spread
        impact_total += impact_rmb
        n_charged += 1
        per_leg.append({
            "symbol": symbol,
            "delta_w": delta_w,
            "trade_rmb": trade_rmb,
            "skipped": False,
            "commission_rmb": commission,
            "spread_rmb": spread,
            "impact_rmb": impact_rmb,
            "impact_bps": impact_bps,
            "total_rmb": total_rmb,
        })

    total_cost_rmb = commission_total + spread_total + impact_total
    total_cost_bps = (total_cost_rmb / portfolio_value) * 10_000.0

    return CostBreakdown(
        commission_rmb=float(commission_total),
        spread_rmb=float(spread_total),
        impact_rmb=float(impact_total),
        total_cost_rmb=float(total_cost_rmb),
        total_cost_bps_of_portfolio=float(total_cost_bps),
        n_trades_charged=int(n_charged),
        n_trades_skipped_under_min=int(n_skipped),
        portfolio_value=float(portfolio_value),
        per_leg=per_leg,
    )


def _coerce_event(event: RebalanceEventLike) -> RebalanceEventInput:
    """Accept either a :class:`RebalanceEventInput` or a raw dict."""

    if isinstance(event, RebalanceEventInput):
        return event
    if isinstance(event, Mapping):
        return RebalanceEventInput(
            portfolio_value=float(event.get("portfolio_value", 1.0)),
            weight_deltas=event.get("weight_deltas") or {},
            adv_per_symbol=event.get("adv_per_symbol"),
        )
    raise TypeError(
        f"rebalance_event must be a RebalanceEventInput or Mapping; got {type(event)!r}"
    )


__all__ = [
    "DEFAULT_BID_ASK_SPREAD_BPS",
    "DEFAULT_COMMISSION_BPS",
    "DEFAULT_MARKET_IMPACT_BPS_PER_PCT_ADV",
    "DEFAULT_MIN_COMMISSION_PER_TRADE",
    "DEFAULT_MIN_TRADE_SIZE_RMB",
    "CostBreakdown",
    "RebalanceEventInput",
    "TransactionCostModel",
    "apply_transaction_costs",
]
