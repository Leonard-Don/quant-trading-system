"""Limit-order price suggestions for ETF rotation trade plans.

The rotation pipeline produces ``buy`` / ``sell`` actions sized to a
target weight, but it stops at "what shares to trade". For real-money
manual execution on a CN A-share broker the next question is **at what
price**: a passive limit at the touch may not fill, a market order
crosses the spread for no reason, and large batches against thin books
move the price against you.

This module turns each suggestion into three concrete limit prices
(passive / neutral / aggressive) plus an execution playbook (best
intraday window, recommended batch count). The output is intentionally
opinionated — the dashboard surfaces a default recommendation but the
operator can override.

Design choices
--------------
* **Pure functions, no I/O.** Takes the trade suggestion + quote
  snapshot and emits a ``PricingHints`` payload. Easy to unit-test,
  reusable from the live API and from CLI / audit replays.
* **Tick-aware.** CN A-share ETFs all trade on a 0.001 RMB minimum
  tick. We snap every suggested price to the nearest tick so the
  output is always a valid broker order.
* **Sensible defaults you can tune.** ``PricingConfig`` carries every
  knob (tick size, aggression levels, batch breakpoints) so the user
  can override via strategy.json without touching code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class PricingConfig:
    """Tunable parameters for :func:`build_pricing_hints`.

    Defaults are calibrated for CN A-share ETFs (0.001 RMB tick) and
    typical retail order sizes. Override via ``strategy.json`` →
    ``order_pricing`` if needed.
    """

    # Minimum price tick for CN A-share ETFs — uniform 0.001 RMB.
    tick_size: float = 0.001
    # How many ticks each aggression level moves away from / toward the
    # reference (current) price.
    aggressive_ticks: int = 2   # cross the spread harder for faster fills
    neutral_ticks: int = 1      # one tick into the spread — typical default
    passive_ticks: int = 1      # one tick away from market — try for better fill
    # Default recommendation among the three. Switching to "passive" makes
    # the strategy try for better fills at the risk of partial / no fills.
    default_recommendation: str = "neutral"
    # Order-batching breakpoints — split orders larger than these into
    # multiple batches so the operator can stagger them through the
    # session and reduce visible footprint.
    batch_breakpoint_shares: int = 5000
    batch_breakpoint_notional: float = 30000.0  # ¥30k
    # Time-of-day execution windows (informational). Avoid the volatile
    # first-30-min open and the last-30-min closing print; favour the
    # liquid middle of each session.
    preferred_windows: tuple = (
        "10:00-11:00 (上午盘中段，流动性最好)",
        "13:30-14:30 (下午盘中段，避开 14:55+ 收盘冲击)",
    )


@dataclass(frozen=True)
class PricingHints:
    """One trade suggestion's limit prices + execution playbook."""

    action: str  # "buy" | "sell" | "hold"
    reference_price: float
    tick_size: float
    limit_prices: dict[str, float]  # {passive, neutral, aggressive}
    recommended_level: str
    recommended_price: float
    batches: int
    shares_per_batch: list[int]
    preferred_windows: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reference_price": float(self.reference_price),
            "tick_size": float(self.tick_size),
            "limit_prices": {k: float(v) for k, v in self.limit_prices.items()},
            "recommended_level": self.recommended_level,
            "recommended_price": float(self.recommended_price),
            "batches": int(self.batches),
            "shares_per_batch": list(self.shares_per_batch),
            "preferred_windows": list(self.preferred_windows),
            "notes": list(self.notes),
        }


def _positive_float(value: Any, default: float) -> float:
    """Return a finite positive float or the safe default."""

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) and numeric > 0 else default


def _non_negative_int(value: Any, default: int) -> int:
    """Return a finite non-negative integer or the safe default."""

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        return default
    return int(numeric)


def _positive_int(value: Any, default: int) -> int:
    """Return a finite positive integer or the safe default."""

    numeric = _non_negative_int(value, default)
    return numeric if numeric > 0 else default


def _string_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    """Return a tuple of non-empty strings or the safe default."""

    if not isinstance(value, (list, tuple)):
        return default
    out = tuple(str(v).strip() for v in value if str(v).strip())
    return out or default


def _snap_to_tick(price: float, tick: float) -> float:
    """Snap ``price`` to the nearest multiple of ``tick`` (>= 0)."""

    if tick <= 0:
        return float(price)
    rounded = round(price / tick) * tick
    # Floating-point cleanup — round to the same decimal places as the tick
    # so 0.0010000000000000002 doesn't appear in JSON outputs.
    decimals = max(0, -round(math.log10(tick))) + 1
    return round(rounded, decimals)


def _split_shares(total: int, batches: int) -> list[int]:
    """Split ``total`` shares into ``batches`` lots, lot-size rounded.

    For CN ETFs we lot-size to 100 shares per order. The last batch
    absorbs any remainder so the sum still equals ``total``.
    """

    if batches <= 1 or total <= 0:
        return [int(total)] if total > 0 else []
    lot = 100
    # Per-batch target rounded down to the lot, last batch takes the rest.
    per = (total // batches // lot) * lot
    if per <= 0:
        per = lot
    out = [per] * (batches - 1)
    out.append(total - sum(out))
    # Defensive: guarantee the split sums to total.
    if sum(out) != total:
        out[-1] = total - sum(out[:-1])
    return [int(x) for x in out if x > 0]


def _decide_batches(
    shares: int, notional: float, config: PricingConfig
) -> int:
    """Pick a batch count based on the larger of (share, notional) signal."""

    by_shares = max(1, (shares + config.batch_breakpoint_shares - 1) // config.batch_breakpoint_shares)
    by_notional = max(
        1,
        int((notional + config.batch_breakpoint_notional - 1) // config.batch_breakpoint_notional),
    )
    return min(3, max(by_shares, by_notional))  # cap at 3 — beyond is overkill for retail


def build_pricing_hints(
    *,
    action: str,
    reference_price: Optional[float],
    shares: int,
    estimated_amount: float,
    config: Optional[PricingConfig] = None,
) -> Optional[PricingHints]:
    """Return three limit-price levels + batching plan for one suggestion.

    Returns ``None`` for hold actions or when no usable reference price
    is available (e.g. when the quote feed didn't deliver a price for
    this code — the dashboard then surfaces "—" instead of a fake number).
    """

    if action not in {"buy", "sell"}:
        return None
    if reference_price is None or reference_price <= 0 or shares <= 0:
        return None

    cfg = config or PricingConfig()
    tick = float(cfg.tick_size)
    ref = float(reference_price)

    # Direction convention:
    #   buy: aggressive = pay up to fill, passive = bid below market
    #   sell: aggressive = sell down to fill, passive = ask above market
    if action == "buy":
        aggressive = ref + cfg.aggressive_ticks * tick
        neutral = ref + cfg.neutral_ticks * tick
        passive = ref - cfg.passive_ticks * tick
    else:  # sell
        aggressive = ref - cfg.aggressive_ticks * tick
        neutral = ref - cfg.neutral_ticks * tick
        passive = ref + cfg.passive_ticks * tick

    levels = {
        "aggressive": max(_snap_to_tick(aggressive, tick), tick),
        "neutral": max(_snap_to_tick(neutral, tick), tick),
        "passive": max(_snap_to_tick(passive, tick), tick),
    }

    recommended = cfg.default_recommendation
    if recommended not in levels:
        recommended = "neutral"

    batches = _decide_batches(shares, estimated_amount, cfg)
    per_batch = _split_shares(shares, batches)

    notes: list[str] = []
    notes.append(
        f"参考价 ¥{ref:.3f}，最小变动单位 ¥{tick:.3f}，方向：{'买入' if action == 'buy' else '卖出'}"
    )
    if batches > 1:
        notes.append(
            f"建议分 {batches} 笔下单，每笔约 {per_batch[0]:,} 股，避免一次性冲击盘口"
        )
    else:
        notes.append("订单规模适中，一笔即可")
    if levels["passive"] != levels["aggressive"]:
        if action == "sell":
            notes.append(
                f"积极价 ¥{levels['aggressive']:.3f}（成交快）；"
                f"中性价 ¥{levels['neutral']:.3f}（约市价）；"
                f"保守价 ¥{levels['passive']:.3f}（挂在卖一上方等更好价格）"
            )
        else:
            notes.append(
                f"积极价 ¥{levels['aggressive']:.3f}（快买入）；"
                f"中性价 ¥{levels['neutral']:.3f}（约市价）；"
                f"保守价 ¥{levels['passive']:.3f}（挂在买一下方等更好价格）"
            )

    return PricingHints(
        action=action,
        reference_price=ref,
        tick_size=tick,
        limit_prices=levels,
        recommended_level=recommended,
        recommended_price=levels[recommended],
        batches=batches,
        shares_per_batch=per_batch,
        preferred_windows=list(cfg.preferred_windows),
        notes=notes,
    )


def build_config_from_strategy_json(raw: Optional[dict[str, Any]]) -> PricingConfig:
    """Construct :class:`PricingConfig` from the ``order_pricing`` config block."""

    if not raw:
        return PricingConfig()
    defaults = PricingConfig()
    kwargs: dict[str, Any] = {}
    if "tick_size" in raw:
        kwargs["tick_size"] = _positive_float(raw["tick_size"], defaults.tick_size)
    for field_name in ("aggressive_ticks", "neutral_ticks", "passive_ticks"):
        if field_name in raw:
            kwargs[field_name] = _non_negative_int(raw[field_name], getattr(defaults, field_name))
    if "default_recommendation" in raw:
        recommendation = str(raw["default_recommendation"])
        kwargs["default_recommendation"] = (
            recommendation if recommendation in {"aggressive", "neutral", "passive"}
            else defaults.default_recommendation
        )
    if "batch_breakpoint_shares" in raw:
        kwargs["batch_breakpoint_shares"] = _positive_int(
            raw["batch_breakpoint_shares"], defaults.batch_breakpoint_shares
        )
    if "batch_breakpoint_notional" in raw:
        kwargs["batch_breakpoint_notional"] = _positive_float(
            raw["batch_breakpoint_notional"], defaults.batch_breakpoint_notional
        )
    if "preferred_windows" in raw:
        kwargs["preferred_windows"] = _string_tuple(
            raw["preferred_windows"], defaults.preferred_windows
        )
    return PricingConfig(**kwargs)


__all__ = [
    "PricingConfig",
    "PricingHints",
    "build_config_from_strategy_json",
    "build_pricing_hints",
]
