"""ETF rotation data models and pure portfolio helpers.

This module is intentionally **side-effect free**:

* No network calls — callers fetch the raw Sina/Eastmoney payloads and feed
  them into the pure parsers in this module.
* No global state — every helper either returns a value or constructs a new
  dataclass instance.

The public surface is:

* Dataclasses describing universe items, real-time quotes, current holdings
  and manual trade suggestions.
* ``DEFAULT_UNIVERSE`` — the five-ETF rotation seed used by the screenshot
  workflow (豆粕 / 有色 / 沪深300 / 黄金 / 恒生科技).
* ``parse_sina_quotes`` / ``parse_fundgz`` / ``parse_fundgz_to_nav`` for
  decoding upstream payloads.
* ``calculate_current_weights`` and ``build_trade_suggestions`` for portfolio
  arithmetic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EtfUniverseItem:
    """Static description of an ETF tracked by the rotation strategy."""

    code: str
    name: str
    category: str
    exchange: str  # "sh" or "sz" — used to build Sina symbols (sh510300 etc.)

    @property
    def sina_symbol(self) -> str:
        return f"{self.exchange}{self.code}"


@dataclass
class EtfQuote:
    """Real-time quote for an ETF.

    Combines the Sina hq_str fields (open / high / low / current / volume)
    with the optional Eastmoney fundgz estimated NAV so callers can read
    the premium/discount in one place.
    """

    code: str
    name: str
    current_price: Optional[float] = None
    prev_close: Optional[float] = None
    open_price: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    time: Optional[str] = None
    estimated_nav: Optional[float] = None
    prev_nav: Optional[float] = None
    source: Optional[str] = None
    timestamp: Optional[str] = None

    @property
    def change_pct(self) -> Optional[float]:
        if self.current_price is None or not self.prev_close:
            return None
        return (self.current_price - self.prev_close) / self.prev_close

    @property
    def premium(self) -> Optional[float]:
        if self.current_price is None or not self.estimated_nav:
            return None
        return (self.current_price - self.estimated_nav) / self.estimated_nav


@dataclass
class EtfHolding:
    """A position currently held in the rotation portfolio."""

    code: str
    name: str
    shares: int
    cost_price: float
    current_price: float

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def cost_value(self) -> float:
        return self.shares * self.cost_price

    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_value

    @property
    def pnl_pct(self) -> Optional[float]:
        if self.cost_value == 0:
            return None
        return self.pnl / self.cost_value


@dataclass
class EtfTradeSuggestion:
    """Manual trade suggestion produced by ``build_trade_suggestions``."""

    code: str
    name: str
    action: str  # "buy" | "sell" | "hold"
    shares: int
    estimated_amount: float
    current_weight: float
    target_weight: float
    reason: str
    extras: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Default universe
# ---------------------------------------------------------------------------


DEFAULT_UNIVERSE: List[EtfUniverseItem] = [
    EtfUniverseItem(code="159985", name="豆粕ETF",
                    category="commodity_agri", exchange="sz"),
    EtfUniverseItem(code="512400", name="有色金属ETF",
                    category="sector_metals", exchange="sh"),
    EtfUniverseItem(code="510300", name="沪深300ETF",
                    category="broad_index", exchange="sh"),
    EtfUniverseItem(code="518680", name="黄金ETF基金",
                    category="commodity_gold", exchange="sh"),
    EtfUniverseItem(code="513130", name="恒生科技ETF",
                    category="hk_tech", exchange="sh"),
]


# ---------------------------------------------------------------------------
# Sina quote parsing
# ---------------------------------------------------------------------------

# Matches `var hq_str_sh510300="..."` (also sz / bj). Captures the exchange,
# the 6-digit code, and the comma-separated payload between the quotes.
_SINA_PATTERN = re.compile(
    r"""var\s+hq_str_(?P<exchange>sh|sz|bj)(?P<code>\d{6})\s*=\s*"(?P<body>[^"]*)"\s*;?""",
    re.VERBOSE,
)


def _maybe_float(raw: str) -> Optional[float]:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_sina_quotes(raw: str) -> Dict[str, EtfQuote]:
    """Decode one or more Sina ``hq_str_*`` declarations.

    The Sina layout for stocks/ETFs is:

    ``name, open, prev_close, current, high, low, bid, ask, volume, amount,
    [bid/ask depth × 10], date, time, ...``

    Returns an empty dict if the input is not recognisable or every payload
    is empty (e.g. delisted symbol).
    """

    if not raw:
        return {}

    out: Dict[str, EtfQuote] = {}
    for match in _SINA_PATTERN.finditer(raw):
        body = match.group("body").strip()
        if not body:
            continue
        parts = body.split(",")
        if len(parts) < 6:
            continue

        code = match.group("code")
        out[code] = EtfQuote(
            code=code,
            name=parts[0],
            open_price=_maybe_float(parts[1]),
            prev_close=_maybe_float(parts[2]),
            current_price=_maybe_float(parts[3]),
            high=_maybe_float(parts[4]),
            low=_maybe_float(parts[5]),
            volume=_maybe_float(parts[8]) if len(parts) > 8 else None,
            amount=_maybe_float(parts[9]) if len(parts) > 9 else None,
            date=parts[30] if len(parts) > 30 and parts[30] else None,
            time=parts[31] if len(parts) > 31 and parts[31] else None,
        )
    return out


# ---------------------------------------------------------------------------
# fundgz parsing
# ---------------------------------------------------------------------------


_FUNDGZ_PATTERN = re.compile(r"^\s*jsonpgz\(\s*(?P<body>.*?)\s*\)\s*;?\s*$",
                             re.DOTALL)


def parse_fundgz(raw: str) -> Optional[Dict[str, Any]]:
    """Decode a single ``jsonpgz({...});`` Eastmoney response.

    Returns ``None`` for anything that doesn't look like a populated
    ``jsonpgz(...)`` envelope.
    """

    if not raw:
        return None
    match = _FUNDGZ_PATTERN.match(raw)
    if not match:
        return None
    body = match.group("body").strip()
    if not body or body in {"{}", "[]"}:
        return None
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def parse_fundgz_to_nav(raw: str) -> Optional[Dict[str, Any]]:
    """Project ``parse_fundgz`` into a typed NAV record.

    Returned keys: ``code``, ``name``, ``estimated_nav``, ``prev_nav``,
    ``change_pct``, ``estimate_time``. Any field missing in the upstream
    payload is left out (``code`` and ``estimated_nav`` are required for the
    record to be returned at all).
    """

    payload = parse_fundgz(raw)
    if payload is None:
        return None

    code = payload.get("fundcode")
    estimated = _maybe_float(payload.get("gsz"))
    if not code or estimated is None:
        return None

    pct = _maybe_float(payload.get("gszzl"))
    record: Dict[str, Any] = {
        "code": code,
        "name": payload.get("name"),
        "estimated_nav": estimated,
        "prev_nav": _maybe_float(payload.get("dwjz")),
        "change_pct": (pct / 100.0) if pct is not None else None,
        "estimate_time": payload.get("gztime"),
    }
    return record


# ---------------------------------------------------------------------------
# Portfolio helpers
# ---------------------------------------------------------------------------


def calculate_current_weights(
    holdings: Iterable[EtfHolding],
    total_asset: float,
) -> Dict[str, float]:
    """Return ``{code: weight}`` where ``weight = market_value / total_asset``.

    A zero (or negative) ``total_asset`` yields zero weights instead of
    raising — the rebalancer should still be able to render a snapshot.
    """

    holdings = list(holdings)
    if total_asset <= 0:
        return {h.code: 0.0 for h in holdings}
    return {h.code: h.market_value / total_asset for h in holdings}


def _floor_to_lot(shares: float, lot_size: int) -> int:
    if lot_size <= 0:
        return int(shares)
    # Tiny epsilon absorbs FP jitter — e.g. 0.20 - 0.35 yields 7499.999…
    # for a 15% sell on a 100k portfolio @ ¥2.00, which would otherwise
    # floor to 7400 instead of the obvious 7500.
    return int((shares + 1e-6) // lot_size) * lot_size


def build_trade_suggestions(
    current_holdings: Iterable[EtfHolding],
    target_weights: Dict[str, float],
    quotes: Dict[str, EtfQuote],
    total_asset: float,
    lot_size: int = 100,
    threshold_weight: float = 0.03,
) -> List[EtfTradeSuggestion]:
    """Generate manual buy/sell/hold suggestions for a target allocation.

    Algorithm (per code present in either ``current_holdings`` or
    ``target_weights``):

    1. Compute ``delta = target_weight - current_weight``.
    2. If ``|delta| < threshold_weight`` → ``hold`` (reason
       ``within_threshold``).
    3. Otherwise size the order from ``|delta| * total_asset / price`` and
       floor to ``lot_size``. If that floors to zero shares the suggestion
       falls back to ``hold`` (reason ``below_lot_size``).
    4. Missing or zero quote price → ``hold`` (reason ``missing_quote``).
    """

    holdings_list = list(current_holdings)
    holdings_by_code = {h.code: h for h in holdings_list}
    weights = calculate_current_weights(holdings_list, total_asset)

    all_codes = set(holdings_by_code) | set(target_weights)
    suggestions: List[EtfTradeSuggestion] = []
    for code in sorted(all_codes):
        current_weight = weights.get(code, 0.0)
        target_weight = float(target_weights.get(code, 0.0))
        delta = target_weight - current_weight

        holding = holdings_by_code.get(code)
        quote = quotes.get(code)
        name = (
            (holding.name if holding else None)
            or (quote.name if quote else None)
            or code
        )

        # Step 2: within threshold → hold.
        if abs(delta) < threshold_weight:
            suggestions.append(EtfTradeSuggestion(
                code=code, name=name, action="hold", shares=0,
                estimated_amount=0.0,
                current_weight=current_weight, target_weight=target_weight,
                reason="within_threshold",
            ))
            continue

        # Step 4 (handled before sizing): need a price to size the order.
        price = quote.current_price if quote else None
        if not price or price <= 0:
            suggestions.append(EtfTradeSuggestion(
                code=code, name=name, action="hold", shares=0,
                estimated_amount=0.0,
                current_weight=current_weight, target_weight=target_weight,
                reason="missing_quote",
            ))
            continue

        # Step 3: size the order and round to a lot.
        delta_value = abs(delta) * total_asset
        raw_shares = delta_value / price
        rounded = _floor_to_lot(raw_shares, lot_size)
        # Cap sells at the holding's lot-floored share count so the
        # suggestion remains physically executable in the manual workflow
        # when the live quote drifts below the position snapshot price.
        if delta < 0 and holding is not None:
            rounded = min(rounded, _floor_to_lot(holding.shares, lot_size))
        if rounded <= 0:
            suggestions.append(EtfTradeSuggestion(
                code=code, name=name, action="hold", shares=0,
                estimated_amount=0.0,
                current_weight=current_weight, target_weight=target_weight,
                reason="below_lot_size",
            ))
            continue

        action = "buy" if delta > 0 else "sell"
        suggestions.append(EtfTradeSuggestion(
            code=code, name=name, action=action, shares=rounded,
            estimated_amount=rounded * price,
            current_weight=current_weight, target_weight=target_weight,
            reason=f"delta_{delta:+.4f}",
        ))

    return suggestions


__all__ = [
    "DEFAULT_UNIVERSE",
    "EtfHolding",
    "EtfQuote",
    "EtfTradeSuggestion",
    "EtfUniverseItem",
    "build_trade_suggestions",
    "calculate_current_weights",
    "parse_fundgz",
    "parse_fundgz_to_nav",
    "parse_sina_quotes",
]
