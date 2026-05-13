#!/usr/bin/env python3
"""Daily ETF rotation manual trade plan.

This script combines:

* ``src.strategy.etf_rotation_strategy`` — produces raw target weights from
  a price matrix.
* ``src.risk.etf_portfolio_rules`` — applies portfolio-level guardrails.
* ``src.data.etf_rotation`` — sizes the manual buy/sell/hold suggestions.

It is intentionally **broker-agnostic and non-trading**. The output is a
plan a human reviews and executes manually — no order is submitted, no
broker API is touched.

Default invocation seeds the plan from the screenshot portfolio
(豆粕/有色/沪深300/黄金/恒生科技) so the script is hermetic and produces
deterministic output without any external data file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_rotation import (  # noqa: E402
    EtfHolding,
    EtfQuote,
    build_trade_suggestions,
    calculate_current_weights,
)
from src.risk.etf_portfolio_rules import (  # noqa: E402
    EtfRiskRuleConfig,
    apply_etf_portfolio_risk_rules,
)
from src.strategy.etf_rotation_strategy import (  # noqa: E402
    EtfAssetConfig,
    EtfRotationConfig,
    EtfRotationStrategy,
)


MANUAL_BANNER = (
    "Manual trade plan — review and execute manually. "
    "No broker API is called and no auto-ordering occurs."
)


# ---------------------------------------------------------------------------
# Default seed (Leonard's current ETF portfolio screenshot)
# ---------------------------------------------------------------------------


def load_default_holdings() -> List[EtfHolding]:
    """Return the five-ETF screenshot seed used for examples and tests."""

    return [
        EtfHolding(
            code="159985", name="豆粕ETF华夏", shares=1100,
            cost_price=2.118, current_price=2.161,
        ),
        EtfHolding(
            code="512400", name="有色金属ETF南方", shares=4700,
            cost_price=2.227, current_price=2.209,
        ),
        EtfHolding(
            code="510300", name="沪深300ETF华泰柏瑞", shares=1400,
            cost_price=4.674, current_price=5.017,
        ),
        EtfHolding(
            code="518680", name="金ETF富国", shares=1000,
            cost_price=11.007, current_price=10.259,
        ),
        EtfHolding(
            code="513130", name="恒生科技ETF华泰柏瑞", shares=3100,
            cost_price=0.731, current_price=0.636,
        ),
    ]


def load_default_quotes(holdings: Sequence[EtfHolding]) -> Dict[str, EtfQuote]:
    """Synthesize quotes from holdings when no quote file is supplied."""

    return {
        h.code: EtfQuote(
            code=h.code,
            name=h.name,
            current_price=h.current_price,
            prev_close=h.current_price,
        )
        for h in holdings
    }


# Per-asset configuration: caps mirror the plan's default ceilings, base
# weights mirror the planned long-run targets. The strategy still scales
# these by the price-momentum score, so a weak asset never gets its base.
DEFAULT_ASSET_CONFIG: Dict[str, Dict[str, Any]] = {
    "159985": {"name": "豆粕ETF华夏", "category": "commodity_event",
               "max_weight": 0.08, "base_weight": 0.05},
    "512400": {"name": "有色金属ETF南方", "category": "nonferrous",
               "max_weight": 0.25, "base_weight": 0.22},
    "510300": {"name": "沪深300ETF华泰柏瑞", "category": "a_share_core",
               "max_weight": 0.35, "base_weight": 0.28},
    "518680": {"name": "金ETF富国", "category": "gold_hedge",
               "max_weight": 0.25, "base_weight": 0.20},
    "513130": {"name": "恒生科技ETF华泰柏瑞", "category": "hk_tech_satellite",
               "max_weight": 0.12, "base_weight": 0.07},
}


# Metadata for the portfolio-level risk rules. The bucket/tag values are
# what the rule engine inspects when applying commodity / QDII vetoes.
DEFAULT_RISK_METADATA: Dict[str, Dict[str, Any]] = {
    "159985": {"category": "commodity", "bucket": "commodity",
               "tags": ("commodity", "agri")},
    "512400": {"category": "metals", "bucket": "commodity",
               "tags": ("metals", "commodity")},
    "510300": {"category": "broad_equity", "bucket": "domestic_equity"},
    "518680": {"category": "gold", "bucket": "commodity",
               "tags": ("gold", "commodity")},
    "513130": {"category": "overseas", "bucket": "qdii", "is_qdii": True},
    "CASH": {"category": "cash"},
}


# ---------------------------------------------------------------------------
# Strategy + risk plumbing
# ---------------------------------------------------------------------------


def build_strategy_config(holdings: Sequence[EtfHolding]) -> EtfRotationConfig:
    """Build an ``EtfRotationConfig`` covering every holding's symbol."""

    assets: List[EtfAssetConfig] = []
    for holding in holdings:
        spec = DEFAULT_ASSET_CONFIG.get(holding.code, {})
        assets.append(
            EtfAssetConfig(
                symbol=holding.code,
                name=spec.get("name", holding.name),
                category=spec.get("category", ""),
                min_weight=0.0,
                max_weight=float(spec.get("max_weight", 0.30)),
                base_weight=float(spec.get("base_weight", 0.10)),
            )
        )
    return EtfRotationConfig(assets=assets, gross_cap=0.90)


def synthesize_price_matrix(
    quotes: Mapping[str, EtfQuote],
    *,
    days: int = 120,
    seed: int = 20260513,
) -> pd.DataFrame:
    """Build a deterministic price history when no live history is supplied.

    Each ETF receives a gentle uptrend from ``current_price * 0.90`` to
    ``current_price`` plus a low-amplitude noise component seeded per code.
    This is enough to make the strategy emit a sensible non-zero target
    weight on the last day while keeping the script's output deterministic.
    """

    if days < 60:
        raise ValueError("days must be >= 60 so the 60-day warmup fires")

    dates = pd.bdate_range(end=pd.Timestamp("2026-05-13"), periods=days)
    matrix: Dict[str, pd.Series] = {}

    for offset, (code, quote) in enumerate(quotes.items()):
        end_price = quote.current_price or 1.0
        start_price = end_price * 0.90
        baseline = np.linspace(start_price, end_price, days)
        rng = np.random.default_rng(seed + offset)
        noise = rng.normal(0.0, end_price * 0.002, days)
        series = baseline + np.cumsum(noise) * 0.05
        matrix[code] = pd.Series(series, index=dates)

    return pd.DataFrame(matrix)


def _quotes_to_premium_map(quotes: Mapping[str, EtfQuote]) -> Dict[str, float]:
    """Extract premium percentages from quotes where NAV is known."""

    premiums: Dict[str, float] = {}
    for code, quote in quotes.items():
        premium = quote.premium
        if premium is not None:
            premiums[code] = premium
    return premiums


def generate_plan(
    holdings: Optional[Sequence[EtfHolding]] = None,
    quotes: Optional[Mapping[str, EtfQuote]] = None,
    *,
    price_matrix: Optional[pd.DataFrame] = None,
    risk_config: Optional[EtfRiskRuleConfig] = None,
    threshold_weight: float = 0.03,
    lot_size: int = 100,
) -> Dict[str, Any]:
    """Produce a full manual trade plan for the supplied holdings."""

    holdings = list(holdings) if holdings is not None else load_default_holdings()
    quote_map = dict(quotes) if quotes is not None else load_default_quotes(holdings)

    total_asset = sum(h.market_value for h in holdings)
    current_weights = calculate_current_weights(holdings, total_asset)

    strategy = EtfRotationStrategy(build_strategy_config(holdings))
    if price_matrix is None:
        price_matrix = synthesize_price_matrix(quote_map)

    signals = strategy.evaluate(
        price_matrix,
        current_weights=current_weights,
    )
    target_weights = {sig.symbol: sig.target_weight for sig in signals}
    # Make sure every held symbol appears in the target map (zero if the
    # strategy refused to score it — keeps the rule engine consistent).
    for holding in holdings:
        target_weights.setdefault(holding.code, 0.0)

    decision = apply_etf_portfolio_risk_rules(
        proposed_weights=target_weights,
        current_weights=current_weights,
        asset_metadata=DEFAULT_RISK_METADATA,
        premium_percentages=_quotes_to_premium_map(quote_map),
        config=risk_config,
    )

    # ``adjusted_weights`` may contain a synthesised CASH entry — exclude
    # it from the ETF-level sizing pass, but keep it in the JSON payload.
    adjusted_for_trades = {
        code: weight
        for code, weight in decision.adjusted_weights.items()
        if code != "CASH"
    }

    suggestions = build_trade_suggestions(
        current_holdings=holdings,
        target_weights=adjusted_for_trades,
        quotes=quote_map,
        total_asset=total_asset,
        lot_size=lot_size,
        threshold_weight=threshold_weight,
    )

    return {
        "manual_only": True,
        "auto_ordering": False,
        "banner": MANUAL_BANNER,
        "total_asset": float(total_asset),
        "current_weights": {k: float(v) for k, v in current_weights.items()},
        "target_weights": {k: float(v) for k, v in target_weights.items()},
        "adjusted_weights": {k: float(v) for k, v in decision.adjusted_weights.items()},
        "suggestions": [
            {
                "code": s.code,
                "name": s.name,
                "action": s.action,
                "shares": int(s.shares),
                "estimated_amount": float(s.estimated_amount),
                "current_weight": float(s.current_weight),
                "target_weight": float(s.target_weight),
                "reason": s.reason,
            }
            for s in suggestions
        ],
        "risk_reasons": list(decision.reasons),
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_output(plan: Mapping[str, Any], *, output: str = "text") -> str:
    """Render the plan as JSON or human-readable text."""

    if output == "json":
        return json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
    if output == "text":
        return _render_text(plan)
    raise ValueError(f"Unsupported output format: {output!r}")


def _render_text(plan: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append(MANUAL_BANNER)
    lines.append("(No auto-ordering. No broker API calls.)")
    lines.append("")
    lines.append(f"Total asset value: ¥{plan.get('total_asset', 0.0):,.2f}")
    lines.append("")

    lines.append("Current weights:")
    for code, weight in sorted(plan.get("current_weights", {}).items()):
        lines.append(f"  {code:>6}: {weight * 100:6.2f}%")

    lines.append("")
    lines.append("Strategy target weights (before risk rules):")
    for code, weight in sorted(plan.get("target_weights", {}).items()):
        lines.append(f"  {code:>6}: {weight * 100:6.2f}%")

    lines.append("")
    lines.append("Adjusted weights (after risk rules):")
    for code, weight in sorted(plan.get("adjusted_weights", {}).items()):
        lines.append(f"  {code:>6}: {weight * 100:6.2f}%")

    lines.append("")
    lines.append("Manual trade suggestions:")
    suggestions = plan.get("suggestions") or []
    if not suggestions:
        lines.append("  (none)")
    for suggestion in suggestions:
        action = suggestion["action"].upper()
        lines.append(
            f"  {suggestion['code']:>6} {suggestion['name']:<18} "
            f"{action:<4} {suggestion['shares']:>7} 股  "
            f"≈¥{suggestion['estimated_amount']:>10,.2f}  "
            f"({suggestion['current_weight'] * 100:5.2f}% → "
            f"{suggestion['target_weight'] * 100:5.2f}%)  "
            f"[{suggestion['reason']}]"
        )

    lines.append("")
    lines.append("Risk reasons:")
    reasons = plan.get("risk_reasons") or []
    if not reasons:
        lines.append("  (no portfolio-level adjustments triggered)")
    for reason in reasons:
        lines.append(f"  - {reason}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON loaders
# ---------------------------------------------------------------------------


def load_holdings_from_json(path: Path) -> List[EtfHolding]:
    """Load holdings from a JSON file produced manually or by upstream tools."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = payload.get("holdings") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise ValueError("holdings JSON must contain a list of holdings")

    holdings: List[EtfHolding] = []
    for item in raw:
        holdings.append(
            EtfHolding(
                code=str(item["code"]),
                name=str(item.get("name", item["code"])),
                shares=int(item.get("shares", 0)),
                cost_price=float(item.get("cost_price", 0.0)),
                current_price=float(item.get("current_price", 0.0)),
            )
        )
    return holdings


def load_quotes_from_json(path: Path) -> Dict[str, EtfQuote]:
    """Load real-time quotes from a JSON file keyed by code."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("quotes JSON must be a {code: quote-object} mapping")

    quotes: Dict[str, EtfQuote] = {}
    for code, item in payload.items():
        quotes[str(code)] = EtfQuote(
            code=str(code),
            name=str(item.get("name", code)),
            current_price=_maybe_float(item.get("current_price")),
            prev_close=_maybe_float(item.get("prev_close")),
            open_price=_maybe_float(item.get("open_price")),
            high=_maybe_float(item.get("high")),
            low=_maybe_float(item.get("low")),
            volume=_maybe_float(item.get("volume")),
            amount=_maybe_float(item.get("amount")),
            estimated_nav=_maybe_float(item.get("estimated_nav")),
            prev_nav=_maybe_float(item.get("prev_nav")),
        )
    return quotes


def _maybe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a daily manual ETF rotation trade plan. "
            "No broker API is contacted; this script only suggests trades."
        )
    )
    parser.add_argument(
        "--holdings-json",
        type=Path,
        default=None,
        help="Optional JSON file with current holdings. Defaults to the "
             "screenshot seed when omitted.",
    )
    parser.add_argument(
        "--quotes-json",
        type=Path,
        default=None,
        help="Optional JSON file with current quotes keyed by code. Defaults "
             "to synthetic quotes derived from holdings.",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format. 'text' prints a human readable plan; 'json' "
             "emits a machine-readable payload.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.holdings_json is not None:
        holdings = load_holdings_from_json(args.holdings_json)
    else:
        holdings = load_default_holdings()

    if args.quotes_json is not None:
        quotes = load_quotes_from_json(args.quotes_json)
    else:
        quotes = load_default_quotes(holdings)

    plan = generate_plan(holdings, quotes)
    print(format_output(plan, output=args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
