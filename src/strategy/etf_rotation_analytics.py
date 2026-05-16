"""Strategy edge analytics — Information Coefficient + hit rate.

Once the audit log carries per-ETF scores + decision-time prices, this
module back-fills forward returns by *looking up* the closest later
audit entry that satisfies the horizon and computes:

* **Information Coefficient (IC)**: Spearman rank correlation between
  the strategy's score and the realised forward return. A 60+ day
  rolling IC above ~0.05 is the conventional threshold for "this
  strategy has measurable edge".
* **Hit rate**: among all (score, forward-return) pairs, the fraction
  where ``sign(score - 50) == sign(forward_return)`` (i.e. the
  strategy's bullish predictions were positive, bearish were negative).
* **Per-code metrics**: same numbers split by ETF, so you can see
  whether the edge is concentrated in one sleeve or broad-based.

The analytics is **offline / on-demand**: no background loop. The API
endpoint computes everything from the audit JSONL file each time it is
hit. With <2k entries the full sweep takes milliseconds.

Methodology choices
-------------------
* **Horizon**: forward-return horizon is configurable; we default to
  5 *audit-bar* days because the audit log refreshes during trading
  hours, so 5 bars ≈ 1 hour of intraday data. For meaningful daily
  IC use 20+ bars.
* **Forward price lookup**: we find the *earliest* audit entry whose
  ``run_at - entry.run_at >= horizon_days``. If no such entry exists
  (current entry is too recent), the pair is skipped.
* **Score normalisation**: we centre the score around 50 (the
  cross-sectional baseline) for hit-rate sign comparison. Spearman IC
  is rank-based so doesn't care about the centre.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


def _parse_iso(value: object) -> Optional[datetime]:
    """Tolerant ISO-8601 parser that always returns tz-aware datetimes."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    try:
        # Python 3.11+ supports trailing 'Z' but older syntax uses +00:00
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _spearman_rank(values: Sequence[float]) -> List[float]:
    """Average-rank (ties get the mean of their slot range)."""

    indexed = sorted(enumerate(values), key=lambda kv: kv[1])
    ranks: List[float] = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-indexed
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def spearman_correlation(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Compute Spearman rank correlation. Returns None on insufficient data."""

    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    rx = _spearman_rank(xs)
    ry = _spearman_rank(ys)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    num = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
    denom_x = sum((r - mean_x) ** 2 for r in rx)
    denom_y = sum((r - mean_y) ** 2 for r in ry)
    if denom_x <= 0 or denom_y <= 0:
        return None
    return num / (denom_x ** 0.5 * denom_y ** 0.5)


# ---------------------------------------------------------------------------
# Forward-return joining
# ---------------------------------------------------------------------------


def build_score_return_pairs(
    entries: Sequence[Mapping[str, object]],
    *,
    horizon_minutes: float,
) -> List[Dict[str, object]]:
    """Pair each (entry, code, score) with the realised forward return.

    For each audit entry E at time T(E), for each code C with a
    ``score_breakdown[C]`` and a decision price ``prices_at_decision[C]``,
    find the earliest later entry E' whose ``run_at >= T(E) + horizon``
    and that also has a decision price for C. The forward return is
    ``E'.prices_at_decision[C] / E.prices_at_decision[C] - 1``.

    Returns a list of dicts with fields::

        {code, run_at, forward_run_at, score, price, forward_price,
         forward_return, horizon_minutes}

    Skips:
    * entries with missing score or price
    * code/entry combos with no future entry past the horizon
    """

    if not entries:
        return []

    # Sort once; the audit log is appended chronologically but we don't
    # trust the input ordering.
    parsed: List[Tuple[datetime, Mapping[str, object]]] = []
    for entry in entries:
        ts = _parse_iso(entry.get("run_at"))
        if ts is None:
            continue
        parsed.append((ts, entry))
    parsed.sort(key=lambda kv: kv[0])

    horizon = timedelta(minutes=horizon_minutes)
    pairs: List[Dict[str, object]] = []

    for i, (t_i, entry_i) in enumerate(parsed):
        scores = entry_i.get("score_breakdown") or {}
        prices = entry_i.get("prices_at_decision") or {}
        if not isinstance(scores, Mapping) or not isinstance(prices, Mapping):
            continue
        for code, sb in scores.items():
            if not isinstance(sb, Mapping):
                continue
            score_value = sb.get("score")
            try:
                score = float(score_value) if score_value is not None else None
            except (TypeError, ValueError):
                score = None
            decision_price = prices.get(code)
            try:
                decision_price_f = (
                    float(decision_price) if decision_price is not None else None
                )
            except (TypeError, ValueError):
                decision_price_f = None
            if score is None or decision_price_f is None or decision_price_f <= 0:
                continue
            # Find the earliest forward entry beyond the horizon.
            forward = None
            for j in range(i + 1, len(parsed)):
                t_j, entry_j = parsed[j]
                if t_j - t_i < horizon:
                    continue
                fwd_prices = entry_j.get("prices_at_decision") or {}
                if not isinstance(fwd_prices, Mapping):
                    continue
                forward_price = fwd_prices.get(code)
                try:
                    forward_price_f = (
                        float(forward_price) if forward_price is not None else None
                    )
                except (TypeError, ValueError):
                    forward_price_f = None
                if forward_price_f is None or forward_price_f <= 0:
                    continue
                forward = (t_j, forward_price_f)
                break
            if forward is None:
                continue
            t_j, forward_price_f = forward
            forward_return = forward_price_f / decision_price_f - 1.0
            pairs.append(
                {
                    "code": code,
                    "run_at": t_i.isoformat(),
                    "forward_run_at": t_j.isoformat(),
                    "score": float(score),
                    "price": float(decision_price_f),
                    "forward_price": float(forward_price_f),
                    "forward_return": float(forward_return),
                    "horizon_minutes": horizon_minutes,
                }
            )
    return pairs


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------


def compute_information_coefficient(pairs: Sequence[Mapping[str, object]]) -> Optional[float]:
    """Overall IC: Spearman across all (score, forward_return) pairs."""

    if not pairs:
        return None
    scores = [float(p["score"]) for p in pairs]
    returns = [float(p["forward_return"]) for p in pairs]
    return spearman_correlation(scores, returns)


def compute_hit_rate(pairs: Sequence[Mapping[str, object]], *, neutral_score: float = 50.0) -> Optional[float]:
    """Fraction of pairs where score sign vs ``neutral_score`` matches return sign."""

    hits = 0
    total = 0
    for pair in pairs:
        score = float(pair["score"])
        ret = float(pair["forward_return"])
        if abs(score - neutral_score) < 1e-9 or abs(ret) < 1e-9:
            continue
        expected_positive = score > neutral_score
        realised_positive = ret > 0
        if expected_positive == realised_positive:
            hits += 1
        total += 1
    if total == 0:
        return None
    return hits / total


def compute_per_code_metrics(
    pairs: Sequence[Mapping[str, object]],
) -> Dict[str, Dict[str, Optional[float]]]:
    by_code: Dict[str, List[Mapping[str, object]]] = {}
    for pair in pairs:
        by_code.setdefault(str(pair["code"]), []).append(pair)
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for code, code_pairs in by_code.items():
        scores = [float(p["score"]) for p in code_pairs]
        returns = [float(p["forward_return"]) for p in code_pairs]
        ic = spearman_correlation(scores, returns)
        hit = compute_hit_rate(code_pairs)
        mean_score = float(statistics.fmean(scores)) if scores else None
        mean_return = float(statistics.fmean(returns)) if returns else None
        out[code] = {
            "n_pairs": len(code_pairs),
            "ic": ic,
            "hit_rate": hit,
            "mean_score": mean_score,
            "mean_forward_return": mean_return,
        }
    return out


def summarise_edge(
    entries: Sequence[Mapping[str, object]],
    *,
    horizons_minutes: Sequence[float] = (60.0, 240.0, 1440.0),
) -> Dict[str, object]:
    """Top-level edge report — pair counts + IC + hit-rate per horizon."""

    horizons: Dict[str, object] = {}
    for horizon in horizons_minutes:
        pairs = build_score_return_pairs(entries, horizon_minutes=horizon)
        horizons[f"horizon_{int(horizon)}min"] = {
            "horizon_minutes": horizon,
            "n_pairs": len(pairs),
            "information_coefficient": compute_information_coefficient(pairs),
            "hit_rate": compute_hit_rate(pairs),
            "per_code": compute_per_code_metrics(pairs),
        }
    return {
        "n_audit_entries": len(entries),
        "horizons": horizons,
    }


__all__ = [
    "build_score_return_pairs",
    "compute_hit_rate",
    "compute_information_coefficient",
    "compute_per_code_metrics",
    "spearman_correlation",
    "summarise_edge",
]
