"""Empirical attribution for the opt-in ``policy_signal_factor``.

This module answers one question: **"when ``policy_signal_factor`` was on,
did it actually add return, or was it noise?"**.

It reads the ETF rotation audit log (JSON Lines at
``~/.config/etf-rotation/audit.jsonl`` by default) and, for each rebalance
where the factor fired, reconstructs both:

* ``factor_on_weights`` — the final weights actually emitted by the
  strategy after risk/cash overlays (``adjusted_weights`` from the audit row).
* ``factor_off_weights`` — a proportional post-overlay counterfactual:
  for each ETF touched by ``policy_adjustment``, scale its final weight by
  ``weight_before / weight_after``. This preserves downstream proportional
  risk/cash scaling when present, while avoiding any network or broker reads.
  Weights that the factor never touched flow through unchanged.

Both weight vectors are then held until the next audit-log rebalance row and
marked to market using ETF close prices (from ``nav_history`` — a wide
DataFrame indexed by date, columns = 6-digit ETF codes). The arithmetic is the
familiar discrete portfolio return:

    period_return = sum_i  w_i * (P_{t+1} / P_t - 1)

with the unallocated remainder held in cash (zero return). No transaction
costs and no rebalance lag — see the **Caveats** docstring below.

Determinism
-----------
The engine is **pure**: given the same audit log and price matrix the
output is bit-for-bit identical. It never reads the network and never
mutates its inputs.

Caveats (the honest ones)
-------------------------
* **Transaction costs ignored.** Switching weights frees up trading
  costs that the live execution does pay. If the factor is small (±10%)
  the net is dominated by mark-to-market drift, but pathological
  high-turnover regimes could shift the sign by a few bps.
* **Rebalance lag assumed zero.** We mark to market between the run_at
  timestamps of consecutive audit rows. In reality the user might place
  the order T+1; that delay is identical for the on/off legs so the
  *difference* (factor contribution) is unaffected, but the *absolute*
  return numbers are off by one bar of slippage.
* **Cash earns zero.** Pessimistic by ~1.5%/yr; same hit on both legs
  so the *difference* is preserved.
* **Post-overlay counterfactual is proportional.** The audit log stores the
  final executed weights and the policy layer's before/after ratio, not a full
  second pass through premium vetoes, stop-loss, and cash-floor rules. Scaling
  final weights by ``weight_before / weight_after`` is exact for proportional
  downstream scaling and an honest approximation for hard per-code overrides.
* **Survivorship.** We only attribute over the window the audit log
  covers. Pre-factor-on history is ignored by construction — this is
  attribution, not back-testing.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from numbers import Real
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerRebalanceAttribution:
    """One row in the per-rebalance breakdown."""

    run_at: str
    period_start: str
    period_end: str
    n_days: int
    factor_on_return_pct: float
    factor_off_return_pct: float
    factor_contribution_pct: float
    applied_codes: list[str] = field(default_factory=list)
    per_code_contribution_pct: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AttributionReport:
    """Aggregate attribution over the requested window."""

    period_start: str
    period_end: str
    period_days: int
    n_rebalances: int
    n_factor_on_rebalances: int
    factor_on_return_pct: float
    factor_off_return_pct: float
    factor_contribution_pct: float
    hit_rate_pct: float
    top_winner_etfs: list[dict[str, Any]] = field(default_factory=list)
    top_loser_etfs: list[dict[str, Any]] = field(default_factory=list)
    per_rebalance_attribution: list[PerRebalanceAttribution] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Convert nested dataclass list explicitly so json serialisation works
        data["per_rebalance_attribution"] = [
            row.to_dict() if isinstance(row, PerRebalanceAttribution) else row
            for row in self.per_rebalance_attribution
        ]
        return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _finite_float(value: object, *, allow_numeric_strings: bool = False) -> Optional[float]:
    """Return a finite float for attribution math, otherwise ``None``."""

    if isinstance(value, bool):
        return None
    if not isinstance(value, Real):
        if not allow_numeric_strings or not isinstance(value, str):
            return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _parse_iso(value: object) -> Optional[datetime]:
    """Tolerant ISO-8601 parser that always returns tz-aware datetimes."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read_audit_log(path: Path) -> list[dict[str, Any]]:
    """Return the audit log JSON-Lines file as a chronologically sorted list."""

    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed audit line %d in %s: %s", line_no, path, exc)
            continue
        if not isinstance(row, Mapping):
            logger.warning(
                "Skipping non-object audit line %d in %s: decoded %s",
                line_no,
                path,
                type(row).__name__,
            )
            continue
        rows.append(dict(row))
    rows.sort(key=lambda r: str(r.get("run_at", "")))
    return rows


def _filter_window(
    entries: Sequence[Mapping[str, Any]],
    *,
    period_days: int,
    now: Optional[datetime] = None,
) -> tuple[list[dict[str, Any]], datetime, datetime]:
    """Keep only entries whose ``run_at`` falls in [now - period_days, now]."""

    if period_days <= 0:
        raise ValueError("period_days must be > 0")
    if not entries:
        end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        start = end - timedelta(days=period_days)
        return [], start, end

    # Use the actual current time as the upper bound so the "still in flight"
    # last rebalance still has hold-window prices to mark to market. The audit
    # log can carry future-dated rows only via test fixtures, but for tests
    # callers should pass ``now=`` explicitly.
    parsed_end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    parsed_start = parsed_end - timedelta(days=period_days)

    filtered: list[dict[str, Any]] = []
    for entry in entries:
        run_at = _parse_iso(entry.get("run_at"))
        if run_at is None:
            continue
        if parsed_start <= run_at <= parsed_end:
            filtered.append(dict(entry))
    return filtered, parsed_start, parsed_end


def _factor_on_weights(entry: Mapping[str, Any]) -> dict[str, float]:
    """Extract the actually-executed weights from an audit row.

    ``adjusted_weights`` is the post-everything number the strategy
    actually targets after risk overlays, premium veto, drawdown cuts,
    etc. We use ``target_weights`` as a fallback if (an older audit
    schema) didn't populate ``adjusted_weights``.
    """

    raw = entry.get("adjusted_weights") or entry.get("target_weights") or {}
    if not isinstance(raw, Mapping):
        return {}
    weights: dict[str, float] = {}
    for code, weight in raw.items():
        if code == "CASH":
            continue
        numeric = _finite_float(weight)
        if numeric is None:
            continue
        weights[str(code)] = numeric
    return weights


def _factor_off_weights(entry: Mapping[str, Any]) -> tuple[dict[str, float], list[str]]:
    """Reconstruct a post-overlay counterfactual with policy impact removed.

    The audit row has two layers of information:

    * ``adjusted_weights`` — the final emitted weights after risk/cash rules.
    * ``score_breakdown[code].policy_adjustment`` — the policy layer's
      ``weight_before`` / ``weight_after`` ratio before later overlays.

    We cannot replay every downstream rule from an audit row alone, so the
    counterfactual preserves the recorded final overlay by scaling each final
    touched weight by ``weight_before / weight_after``. If downstream rules only
    scaled weights proportionally, this is exact; if a hard stop/cap dominated,
    it is still a conservative attribution proxy and is labelled as such in the
    rendered report/API copy.
    """

    weights = _factor_on_weights(entry)
    breakdown = entry.get("score_breakdown") or {}
    applied: list[str] = []
    if not isinstance(breakdown, Mapping):
        return weights, applied

    for code, meta in breakdown.items():
        code_s = str(code)
        if not isinstance(meta, Mapping):
            continue
        adj = meta.get("policy_adjustment")
        if not isinstance(adj, Mapping):
            continue
        if not adj.get("applied"):
            continue
        if code_s not in weights:
            continue
        before_raw = adj.get("weight_before")
        after_raw = adj.get("weight_after")
        before = _finite_float(before_raw, allow_numeric_strings=True)
        after = _finite_float(after_raw, allow_numeric_strings=True)
        final_on = _finite_float(weights.get(code_s))
        if before is None or after is None or final_on is None:
            continue
        if final_on < 0:
            continue
        if after > 0:
            weights[code_s] = max(0.0, final_on * before / after)
        else:
            weights[code_s] = max(0.0, before)
        applied.append(code_s)
    return weights, applied


def _policy_factor_enabled(entry: Mapping[str, Any]) -> bool:
    summary = entry.get("policy_signal_factor") or {}
    if not isinstance(summary, Mapping):
        return False
    return bool(summary.get("enabled"))


def _slice_prices(
    nav_history: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Inclusive daily-date slice of the price matrix.

    ETF history is daily close data, usually indexed at midnight. Audit rows are
    timestamped intraday/UTC (for example ``02:00``), so timestamp comparison
    would skip the rebalance date's close. Compare calendar dates instead.
    """

    if nav_history is None or nav_history.empty:
        return pd.DataFrame()
    idx = pd.DatetimeIndex(pd.to_datetime(nav_history.index))
    start_date = start.date()
    end_date = end.date()
    mask = [(start_date <= ts.date() <= end_date) for ts in idx]
    return nav_history.loc[mask]


def _weighted_period_return(
    weights: Mapping[str, float],
    prices: pd.DataFrame,
) -> tuple[float, dict[str, float]]:
    """Return ``(total_return, per_code_return)`` for a held-flat portfolio.

    ``total_return`` is the sum over assets of ``w_i * (P_end / P_start - 1)``.
    ``per_code_return`` is each ETF's contribution to the total — useful
    for the winner/loser ranking.
    """

    if prices.empty or len(prices) < 2:
        return 0.0, {}
    start_row = prices.iloc[0]
    end_row = prices.iloc[-1]
    total = 0.0
    per_code: dict[str, float] = {}
    for code, weight in weights.items():
        if code not in prices.columns:
            continue
        p_start = _finite_float(start_row[code], allow_numeric_strings=True)
        p_end = _finite_float(end_row[code], allow_numeric_strings=True)
        weight_value = _finite_float(weight)
        if p_start is None or p_end is None or weight_value is None:
            continue
        if not (p_start > 0 and p_end > 0):
            continue
        asset_return = p_end / p_start - 1.0
        contrib = weight_value * asset_return
        total += contrib
        per_code[code] = contrib
    return total, per_code


def _aggregate_per_code(
    rows: Sequence[PerRebalanceAttribution],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Sum per-code contributions across rebalances → top winners/losers."""

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in rows:
        for code, contrib in row.per_code_contribution_pct.items():
            totals[code] = totals.get(code, 0.0) + float(contrib)
            counts[code] = counts.get(code, 0) + 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    winners = [
        {
            "code": code,
            "contribution_pct": round(value, 6),
            "n_rebalances": counts.get(code, 0),
        }
        for code, value in ranked
        if value > 0
    ][:5]
    losers = [
        {
            "code": code,
            "contribution_pct": round(value, 6),
            "n_rebalances": counts.get(code, 0),
        }
        for code, value in reversed(ranked)
        if value < 0
    ][:5]
    return winners, losers


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_attribution(
    audit_log_path: Path | str,
    nav_history: pd.DataFrame,
    *,
    period_days: int = 30,
    now: Optional[datetime] = None,
) -> AttributionReport:
    """Compute the empirical contribution of ``policy_signal_factor`` to P&L.

    Parameters
    ----------
    audit_log_path:
        Path to the audit JSONL file (``~/.config/etf-rotation/audit.jsonl``
        in production). May not exist — that returns an empty report.
    nav_history:
        Wide DataFrame indexed by trading date, columns = 6-digit ETF
        codes, values = close prices (any adjusted convention is fine as
        long as it's the same for the on/off legs).
    period_days:
        Window length in calendar days, anchored on ``now`` (or the
        latest audit row when ``now`` is None).
    now:
        Override for the upper bound of the window. Used in tests; in
        production callers leave it ``None``.

    Returns
    -------
    AttributionReport — fully populated dataclass; safe to ``.to_dict()``
    for JSON serialisation.
    """

    path = Path(audit_log_path).expanduser()
    raw_entries = _read_audit_log(path)
    filtered, period_start, period_end = _filter_window(
        raw_entries, period_days=period_days, now=now,
    )

    notes: list[str] = []
    if not filtered:
        notes.append("Audit log empty within the requested window.")
        return AttributionReport(
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            period_days=period_days,
            n_rebalances=0,
            n_factor_on_rebalances=0,
            factor_on_return_pct=0.0,
            factor_off_return_pct=0.0,
            factor_contribution_pct=0.0,
            hit_rate_pct=0.0,
            notes=notes,
        )

    factor_on_rows = [e for e in filtered if _policy_factor_enabled(e)]
    if not factor_on_rows:
        notes.append(
            "No audit rows in the window had ``policy_signal_factor.enabled=True``. "
            "Run with the factor enabled (CLI: --enable-policy-signal) to populate.",
        )
        return AttributionReport(
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            period_days=period_days,
            n_rebalances=len(filtered),
            n_factor_on_rebalances=0,
            factor_on_return_pct=0.0,
            factor_off_return_pct=0.0,
            factor_contribution_pct=0.0,
            hit_rate_pct=0.0,
            notes=notes,
        )

    per_rebalance: list[PerRebalanceAttribution] = []
    hits = 0
    growth_on = 1.0
    growth_off = 1.0

    for idx, entry in enumerate(filtered):
        if not _policy_factor_enabled(entry):
            continue
        run_at = _parse_iso(entry.get("run_at"))
        if run_at is None:
            continue
        # Hold period ends at the next audit-log rebalance, regardless of
        # whether that later row had policy_signal_factor enabled. A factor-off
        # row is still a real rebalance and should stop the previous weights.
        hold_end = period_end
        for future_entry in filtered[idx + 1:]:
            next_run = _parse_iso(future_entry.get("run_at"))
            if next_run is not None and next_run > run_at:
                hold_end = next_run
                break
        if hold_end <= run_at:
            continue

        prices = _slice_prices(nav_history, run_at, hold_end)
        if prices.empty or len(prices) < 2:
            continue

        weights_on = _factor_on_weights(entry)
        weights_off, applied = _factor_off_weights(entry)

        on_total, on_per_code = _weighted_period_return(weights_on, prices)
        off_total, _ = _weighted_period_return(weights_off, prices)
        contribution = on_total - off_total

        # Per-code contribution = on-leg-contribution minus the off-leg
        # contribution from the same ETF at its ``weight_before``.
        per_code_attr: dict[str, float] = {}
        for code in applied:
            if code not in prices.columns:
                per_code_attr[code] = 0.0
                continue
            on_c = on_per_code.get(code, 0.0)
            start_p = _finite_float(prices.iloc[0][code], allow_numeric_strings=True)
            end_p = _finite_float(prices.iloc[-1][code], allow_numeric_strings=True)
            off_w = _finite_float(weights_off.get(code, 0.0))
            if (
                start_p is not None
                and end_p is not None
                and off_w is not None
                and start_p > 0
                and end_p > 0
            ):
                off_c = off_w * (end_p / start_p - 1.0)
            else:
                off_c = 0.0
            per_code_attr[code] = round(on_c - off_c, 6)

        per_rebalance.append(
            PerRebalanceAttribution(
                run_at=run_at.isoformat(),
                period_start=run_at.isoformat(),
                period_end=hold_end.isoformat(),
                n_days=max(1, (hold_end - run_at).days),
                factor_on_return_pct=round(on_total * 100, 6),
                factor_off_return_pct=round(off_total * 100, 6),
                factor_contribution_pct=round(contribution * 100, 6),
                applied_codes=applied,
                per_code_contribution_pct={
                    k: round(v * 100, 6) for k, v in per_code_attr.items()
                },
            )
        )
        growth_on *= 1.0 + on_total
        growth_off *= 1.0 + off_total
        if contribution > 0:
            hits += 1

    if not per_rebalance:
        notes.append(
            "Factor-on rebalances exist but the price matrix has no rows in "
            "any hold window. Check ``nav_history`` coverage.",
        )

    winners, losers = _aggregate_per_code(per_rebalance)
    hit_rate = (hits / len(per_rebalance) * 100.0) if per_rebalance else 0.0

    return AttributionReport(
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        period_days=period_days,
        n_rebalances=len(filtered),
        n_factor_on_rebalances=len(factor_on_rows),
        factor_on_return_pct=round((growth_on - 1.0) * 100, 6),
        factor_off_return_pct=round((growth_off - 1.0) * 100, 6),
        factor_contribution_pct=round((growth_on - growth_off) * 100, 6),
        hit_rate_pct=round(hit_rate, 4),
        top_winner_etfs=winners,
        top_loser_etfs=losers,
        per_rebalance_attribution=per_rebalance,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Markdown rendering — used by the CLI and the sample report
# ---------------------------------------------------------------------------


def render_markdown(report: AttributionReport, *, title: Optional[str] = None) -> str:
    """Render an attribution report as a human-readable Markdown document."""

    title = title or "Policy Signal Factor — Attribution Report"
    sign_total = "+" if report.factor_contribution_pct >= 0 else ""
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- **Window**: `{report.period_start}` → `{report.period_end}`"
                 f" ({report.period_days} days)")
    lines.append(f"- **Rebalances in window**: {report.n_rebalances} "
                 f"(factor ON: {report.n_factor_on_rebalances})")
    lines.append(
        f"- **Factor-ON compounded return**: {report.factor_on_return_pct:+.4f}% "
        f"(proportional factor-OFF proxy: {report.factor_off_return_pct:+.4f}%)"
    )
    lines.append(
        f"- **Factor contribution**: "
        f"**{sign_total}{report.factor_contribution_pct:.4f}%** "
        f"(hit rate: {report.hit_rate_pct:.2f}%)"
    )
    lines.append("")

    if report.notes:
        lines.append("### Notes")
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")

    if report.top_winner_etfs:
        lines.append("### Top winner ETFs (factor added P&L)")
        lines.append("| ETF | Contribution % | # rebalances |")
        lines.append("|---|---:|---:|")
        for row in report.top_winner_etfs:
            lines.append(
                f"| `{row['code']}` | "
                f"{row['contribution_pct']:+.4f}% | "
                f"{row['n_rebalances']} |"
            )
        lines.append("")

    if report.top_loser_etfs:
        lines.append("### Top loser ETFs (factor subtracted P&L)")
        lines.append("| ETF | Contribution % | # rebalances |")
        lines.append("|---|---:|---:|")
        for row in report.top_loser_etfs:
            lines.append(
                f"| `{row['code']}` | "
                f"{row['contribution_pct']:+.4f}% | "
                f"{row['n_rebalances']} |"
            )
        lines.append("")

    if report.per_rebalance_attribution:
        lines.append("### Per-rebalance breakdown")
        lines.append(
            "| Run at | Hold days | ON % | OFF % | Contribution % | Applied codes |"
        )
        lines.append("|---|---:|---:|---:|---:|---|")
        for attribution_row in report.per_rebalance_attribution:
            applied = ", ".join(attribution_row.applied_codes) or "—"
            lines.append(
                f"| `{attribution_row.run_at}` | {attribution_row.n_days} | "
                f"{attribution_row.factor_on_return_pct:+.4f}% | "
                f"{attribution_row.factor_off_return_pct:+.4f}% | "
                f"{attribution_row.factor_contribution_pct:+.4f}% | "
                f"{applied} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("### How to read this")
    lines.append(
        "- **Factor contribution = compounded ON return − proportional OFF proxy.** "
        "Positive means enabling the factor outperformed a post-overlay proxy "
        "where each touched ETF's final weight is scaled by weight_before / "
        "weight_after."
    )
    lines.append(
        "- **Hit rate** is the % of rebalances where the factor improved "
        "return that period. 50% is coin-flip; >55% over 20+ rebalances "
        "starts to look like signal."
    )
    lines.append(
        "- **Per-code contribution** sums the marginal P&L from the "
        "policy adjustment on each ETF after the same proportional final-weight "
        "scaling used by the report-level proxy."
    )
    lines.append(
        "- This is **attribution, not back-testing**: no transaction costs, "
        "no rebalance lag, cash assumed to earn zero, and the off leg is a "
        "proportional post-overlay proxy rather than a full second strategy run."
    )

    return "\n".join(lines) + "\n"
