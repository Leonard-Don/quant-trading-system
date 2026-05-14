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
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

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
from src.data.source_health import build_source_registry  # noqa: E402
from src.risk.etf_portfolio_rules import (  # noqa: E402
    EtfRiskRuleConfig,
    apply_etf_portfolio_risk_rules,
)
from src.strategy.etf_rotation_strategy import (  # noqa: E402
    EtfAssetConfig,
    EtfRotationConfig,
    EtfRotationStrategy,
)

MANUAL_BANNER = "手动调仓计划：请人工复核后执行；不连接券商接口，也不会自动下单。"


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


def apply_quotes_to_holdings(
    holdings: Sequence[EtfHolding],
    quotes: Mapping[str, EtfQuote],
) -> List[EtfHolding]:
    """Return holdings repriced with any positive live quote prices.

    Share counts and cost basis remain unchanged; only ``current_price`` is
    refreshed so current weights / total asset / trade sizing reflect the
    latest quote snapshot.
    """

    updated: List[EtfHolding] = []
    for holding in holdings:
        quote = quotes.get(holding.code)
        live_price = quote.current_price if quote else None
        current_price = (
            float(live_price)
            if live_price is not None and live_price > 0
            else holding.current_price
        )
        updated.append(
            EtfHolding(
                code=holding.code,
                name=holding.name,
                shares=holding.shares,
                cost_price=holding.cost_price,
                current_price=current_price,
            )
        )
    return updated


def _quotes_to_snapshot(quotes: Mapping[str, EtfQuote]) -> Dict[str, Dict[str, Any]]:
    """Expose quote fields used by dashboards without broker/order data."""

    snapshot: Dict[str, Dict[str, Any]] = {}
    for code, quote in sorted(quotes.items()):
        snapshot[code] = {
            "code": quote.code,
            "name": quote.name,
            "current_price": quote.current_price,
            "prev_close": quote.prev_close,
            "change_pct": quote.change_pct,
            "premium": quote.premium,
            "open_price": quote.open_price,
            "high": quote.high,
            "low": quote.low,
            "volume": quote.volume,
            "amount": quote.amount,
            "date": quote.date,
            "time": quote.time,
            "timestamp": quote.timestamp,
            "source": quote.source,
        }
    return snapshot


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


_AsOf = Optional[Union[str, datetime]]


def generate_plan(
    holdings: Optional[Sequence[EtfHolding]] = None,
    quotes: Optional[Mapping[str, EtfQuote]] = None,
    *,
    price_matrix: Optional[pd.DataFrame] = None,
    risk_config: Optional[EtfRiskRuleConfig] = None,
    threshold_weight: float = 0.03,
    lot_size: int = 100,
    holdings_as_of: _AsOf = None,
    quotes_as_of: _AsOf = None,
    price_matrix_as_of: _AsOf = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Produce a full manual trade plan for the supplied holdings.

    The ``*_as_of`` parameters communicate the **sample** time of each input,
    distinct from the plan-build time. Pass them when you know the upstream
    snapshot timestamp (broker query time, quote feed tick time, history end
    date) so the source-health registry can report accurate freshness instead
    of stamping every supplied frame with ``datetime.now()``.
    """

    holdings_supplied = holdings is not None
    quotes_supplied = quotes is not None
    price_matrix_supplied = price_matrix is not None

    holdings = list(holdings) if holdings_supplied else load_default_holdings()
    quote_map = dict(quotes) if quotes_supplied else load_default_quotes(holdings)

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

    source_health = _build_source_health_payload(
        holdings_supplied=holdings_supplied,
        quotes_supplied=quotes_supplied,
        price_matrix_supplied=price_matrix_supplied,
        holdings_as_of=holdings_as_of,
        quotes_as_of=quotes_as_of,
        price_matrix_as_of=price_matrix_as_of,
        now=now,
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
        "source_health": source_health,
        "quote_snapshot": _quotes_to_snapshot(quote_map),
    }


def _build_source_health_payload(
    *,
    holdings_supplied: bool,
    quotes_supplied: bool,
    price_matrix_supplied: bool,
    holdings_as_of: _AsOf = None,
    quotes_as_of: _AsOf = None,
    price_matrix_as_of: _AsOf = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Describe where the ETF rotation inputs came from.

    The plan's three inputs (holdings, quotes, price matrix) can each be
    supplied externally or filled by the deterministic screenshot seed. The
    registry exposes that provenance so dashboards / API consumers can show
    whether they're looking at live data or the fallback synthetic frame.

    Contract for ``as_of``:

    * Supplied data + ``*_as_of`` known → ``status='ready'``, ``as_of`` is
      that timestamp, ``reason`` is empty. Freshness reflects reality.
    * Supplied data + ``*_as_of`` unknown → ``status='ready'``,
      ``as_of=None``, ``reason='sample_timestamp_unknown'``. We don't fake
      freshness from the plan-build clock.
    * Synthetic (no upstream data) → ``status='synthetic'``, ``ok=True``,
      ``as_of=None``, ``fallback=True``, ``reason`` names the substitute
      ("screenshot_seed" / "derived_from_holdings" /
      "deterministic_random_walk").
    """
    reference_now = now or datetime.now(timezone.utc)

    def _spec(
        *,
        source_id: str,
        display_name: str,
        capabilities: Tuple[str, ...],
        supplied: bool,
        sample_as_of: _AsOf,
        synthetic_reason: str,
    ) -> Dict[str, Any]:
        if not supplied:
            return {
                "source_id": source_id,
                "display_name": display_name,
                "status": "synthetic",
                "ok": True,
                "as_of": None,
                "reason": synthetic_reason,
                "capabilities": capabilities,
                "fallback": True,
            }
        if sample_as_of is None:
            return {
                "source_id": source_id,
                "display_name": display_name,
                "status": "ready",
                "ok": True,
                "as_of": None,
                "reason": "sample_timestamp_unknown",
                "capabilities": capabilities,
                "fallback": False,
            }
        return {
            "source_id": source_id,
            "display_name": display_name,
            "status": "ready",
            "ok": True,
            "as_of": sample_as_of,
            "reason": None,
            "capabilities": capabilities,
            "fallback": False,
        }

    specs = [
        _spec(
            source_id="etf_holdings",
            display_name="ETF 持仓快照",
            capabilities=("holdings",),
            supplied=holdings_supplied,
            sample_as_of=holdings_as_of,
            synthetic_reason="screenshot_seed",
        ),
        _spec(
            source_id="etf_quotes",
            display_name="ETF 实时行情",
            capabilities=("latest_quote",),
            supplied=quotes_supplied,
            sample_as_of=quotes_as_of,
            synthetic_reason="derived_from_holdings",
        ),
        _spec(
            source_id="price_matrix",
            display_name="ETF 价格历史",
            capabilities=("historical_data",),
            supplied=price_matrix_supplied,
            sample_as_of=price_matrix_as_of,
            synthetic_reason="deterministic_random_walk",
        ),
    ]
    return [
        entry.to_dict()
        for entry in build_source_registry(
            specs,
            default_required="etf_holdings",
            now=reference_now,
        )
    ]


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


def _format_trade_reason_zh(reason: Any) -> str:
    text = str(reason or "").strip()
    if not text:
        return "—"
    labels = {
        "within_threshold": "无需调仓（偏离低于阈值）",
        "missing_quote": "缺少可用行情，暂不操作",
        "below_lot_size": "调整量不足一手，暂不操作",
    }
    if text in labels:
        return labels[text]
    delta_match = re.match(r"^delta_([+-]?\d+(?:\.\d+)?)$", text)
    if delta_match:
        return f"目标偏离 {float(delta_match.group(1)) * 100:.2f}%"
    return text


def _format_risk_reason_zh(reason: Any) -> str:
    text = str(reason or "").strip()
    if not text:
        return "—"
    labels = {
        "Cash floor target maintained": "现金底线已保留",
        "Manual-only ETF rotation signal": "手动 ETF 轮动信号",
    }
    if text in labels:
        return labels[text]

    patterns = [
        (
            r"^Cash floor: raised cash from ([\d.]+%) to ([\d.]+%)\.$",
            lambda m: f"现金底线：现金仓位从 {m.group(1)} 提高到 {m.group(2)}。",
        ),
        (
            r"^Commodity/resource bucket cap: reduced combined bucket "
            r"from ([\d.]+%) to ([\d.]+%)\.$",
            lambda m: f"商品/资源类仓位上限：合计仓位从 {m.group(1)} 降至 {m.group(2)}。",
        ),
        (
            r"^Single ETF cap for ([^:]+): reduced from ([\d.]+%) to ([\d.]+%)\.$",
            lambda m: f"单只 ETF 上限：{m.group(1)} 从 {m.group(2)} 降至 {m.group(3)}。",
        ),
        (
            r"^Premium veto for ([^:]+): premium ([\d.]+%) "
            r"exceeds ([\d.]+%); target increase capped at current weight\.$",
            lambda m: (
                f"溢价风控：{m.group(1)} 溢价 {m.group(2)} 超过 {m.group(3)}，"
                "目标增仓限制在当前权重。"
            ),
        ),
        (
            r"^Drawdown cut: portfolio drawdown ([\d.]+%) exceeds ([\d.]+%); "
            r"gross ETF exposure reduced from ([\d.]+%) to ([\d.]+%)\.$",
            lambda m: (
                f"回撤风控：组合回撤 {m.group(1)} 超过 {m.group(2)}，"
                f"ETF 总敞口从 {m.group(3)} 降至 {m.group(4)}。"
            ),
        ),
    ]
    for pattern, formatter in patterns:
        match = re.match(pattern, text)
        if match:
            return formatter(match)
    return text


def _render_text(plan: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append(MANUAL_BANNER)
    lines.append("（无自动下单；不调用券商 API。）")
    lines.append("")
    lines.append(f"组合资产：¥{plan.get('total_asset', 0.0):,.2f}")
    lines.append("")

    lines.append("当前权重：")
    for code, weight in sorted(plan.get("current_weights", {}).items()):
        lines.append(f"  {code:>6}: {weight * 100:6.2f}%")

    lines.append("")
    lines.append("策略目标权重（风控前）：")
    for code, weight in sorted(plan.get("target_weights", {}).items()):
        lines.append(f"  {code:>6}: {weight * 100:6.2f}%")

    lines.append("")
    lines.append("风控后目标权重：")
    for code, weight in sorted(plan.get("adjusted_weights", {}).items()):
        lines.append(f"  {code:>6}: {weight * 100:6.2f}%")

    lines.append("")
    lines.append("手动交易建议：")
    suggestions = plan.get("suggestions") or []
    if not suggestions:
        lines.append("  （暂无）")
    action_labels = {"buy": "买入", "sell": "卖出", "hold": "持有"}
    for suggestion in suggestions:
        action = action_labels.get(str(suggestion["action"]).lower(), str(suggestion["action"]))
        reason = _format_trade_reason_zh(suggestion["reason"])
        lines.append(
            f"  {suggestion['code']:>6} {suggestion['name']:<18} "
            f"{action:<4} {suggestion['shares']:>7} 股  "
            f"≈¥{suggestion['estimated_amount']:>10,.2f}  "
            f"({suggestion['current_weight'] * 100:5.2f}% → "
            f"{suggestion['target_weight'] * 100:5.2f}%)  "
            f"[{reason}]"
        )

    lines.append("")
    lines.append("风控原因：")
    reasons = plan.get("risk_reasons") or []
    if not reasons:
        lines.append("  （未触发组合级风控调整）")
    for reason in reasons:
        lines.append(f"  - {_format_risk_reason_zh(reason)}")

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
            source=str(item.get("source")) if item.get("source") else None,
            timestamp=str(item.get("timestamp")) if item.get("timestamp") else None,
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


class ChineseArgumentParser(argparse.ArgumentParser):
    """Argparse with localized default help chrome for user-facing CLI output."""

    def format_help(self) -> str:
        text = super().format_help()
        replacements = {
            "usage: ": "用法：",
            "options:": "选项：",
            "optional arguments:": "选项：",
            "show this help message and exit": "显示此帮助信息并退出",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def format_usage(self) -> str:
        return super().format_usage().replace("usage: ", "用法：")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = ChineseArgumentParser(
        description="生成每日 ETF 轮动手动调仓计划；不连接券商接口，只给出人工复核建议。"
    )
    parser.add_argument(
        "--holdings-json",
        type=Path,
        default=None,
        help="可选：当前持仓 JSON 文件；未提供时使用截图种子。",
    )
    parser.add_argument(
        "--quotes-json",
        type=Path,
        default=None,
        help="可选：按代码索引的当前行情 JSON 文件；未提供时使用持仓推导的模拟行情。",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="输出格式：text 打印易读计划；json 输出机器可读载荷。",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    # Pass ``None`` when the user didn't supply a file so ``generate_plan``
    # can record the source-health provenance as ``synthetic`` instead of
    # ``ready`` (loading the screenshot seed here would hide that fact).
    holdings = (
        load_holdings_from_json(args.holdings_json)
        if args.holdings_json is not None
        else None
    )
    quotes = (
        load_quotes_from_json(args.quotes_json)
        if args.quotes_json is not None
        else None
    )

    plan = generate_plan(holdings=holdings, quotes=quotes)
    print(format_output(plan, output=args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
