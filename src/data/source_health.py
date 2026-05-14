"""Cross-domain provider / source-health registry.

The quant-trading-system already carries domain-specific health shapes:

* ``src.data.providers.provider_factory`` — per-provider entries for market
  data with ``id`` / ``ok`` / ``status`` / ``reason`` / ``required`` / etc.
* ``src.data.alternative.policy_radar.policy_signals`` — per-source ingest
  quality (``record_count`` / ``avg_text_length`` / ``level``).

Each domain re-invents the field names and rendering, which makes it hard for
new consumers (ETF rotation, future Qlib/rqalpha/vectorbt adapters) to share
dashboards or API helpers.

This module exposes one normalized contract:

``SourceHealthEntry``
    Frozen dataclass with: ``source_id``, ``display_name``, ``status``,
    ``ok``, ``required``, ``fallback``, ``as_of`` (ISO Z string),
    ``age_seconds``, ``freshness`` (label), ``reason``, ``capabilities``.

``build_source_registry``
    Takes a list of spec dicts and returns ordered ``SourceHealthEntry``
    objects with status / freshness / required / fallback normalized.
    Ordering: required first, then ok=True, then alphabetical display_name.

``freshness_label``
    Pure helper mapping an age in seconds (or ``None``) to one of
    ``fresh`` / ``recent`` / ``stale`` / ``expired`` / ``missing``. Daily-data
    defaults: ≤1 h fresh, ≤1 d recent, ≤7 d stale, otherwise expired.

The module is deliberately import-light (stdlib only) so it can be reused
from API responses, CLI scripts, and analytical notebooks without pulling
in pandas / numpy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple, Union


# ---------------------------------------------------------------------------
# Freshness thresholds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreshnessThresholds:
    """Boundary times (in seconds) for the freshness label buckets.

    Defaults are tuned for **daily-cadence** data sources (the ETF rotation
    use-case). Real-time sources can pass a tighter set, e.g.
    ``FreshnessThresholds(60, 300, 1800)`` for ≤1 min / ≤5 min / ≤30 min.
    """

    fresh_max_seconds: float = 60 * 60                 # ≤ 1 hour  → "fresh"
    recent_max_seconds: float = 24 * 60 * 60           # ≤ 1 day   → "recent"
    stale_max_seconds: float = 7 * 24 * 60 * 60        # ≤ 1 week  → "stale"


DEFAULT_FRESHNESS = FreshnessThresholds()


FRESHNESS_FRESH = "fresh"
FRESHNESS_RECENT = "recent"
FRESHNESS_STALE = "stale"
FRESHNESS_EXPIRED = "expired"
FRESHNESS_MISSING = "missing"


def freshness_label(
    age_seconds: Optional[float],
    *,
    thresholds: FreshnessThresholds = DEFAULT_FRESHNESS,
) -> str:
    """Bucket an age into ``fresh`` / ``recent`` / ``stale`` / ``expired``.

    ``None`` ages map to ``missing`` so callers can distinguish "no data
    available" from "data is old". Slightly negative ages (clock skew where
    ``as_of`` lands marginally in the future) are still ``fresh``.
    """
    if age_seconds is None:
        return FRESHNESS_MISSING
    if age_seconds < 0:
        return FRESHNESS_FRESH
    if age_seconds <= thresholds.fresh_max_seconds:
        return FRESHNESS_FRESH
    if age_seconds <= thresholds.recent_max_seconds:
        return FRESHNESS_RECENT
    if age_seconds <= thresholds.stale_max_seconds:
        return FRESHNESS_STALE
    return FRESHNESS_EXPIRED


# ---------------------------------------------------------------------------
# Entry dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceHealthEntry:
    """Normalized health/freshness record for a single data source.

    Field semantics:

    * ``source_id`` — canonical id (lowercase / snake_case is encouraged).
    * ``display_name`` — human-readable label for UIs.
    * ``status`` — short token: ``ready`` / ``synthetic`` / ``stale`` /
      ``skipped`` / ``error`` / ``empty`` / ``unavailable`` / ``unknown``.
      ``synthetic`` means the value was usable (``ok=True``) but was produced
      by a deterministic substitute (seed / random walk / derivation), not by
      a real upstream sample — pair with ``fallback=True`` and a ``reason``
      so consumers can distinguish synthetic frames from live data.
    * ``ok`` — whether the source contributed usable data this round.
    * ``required`` — failing this source breaks the consumer.
    * ``fallback`` — eligible as a substitute when a higher-priority source
      fails. ``ok=True`` entries default to ``False``; failing entries
      default to ``True``.
    * ``as_of`` — ISO-8601 UTC string ("…Z") of the data's **sample** time,
      or ``None`` when no sample timestamp was supplied / parseable. Callers
      must not set this to "now" just because the data was used recently —
      that conflates data freshness with plan-build time.
    * ``age_seconds`` — distance from ``as_of`` to ``now`` at build time.
    * ``freshness`` — label derived from ``age_seconds`` (see
      :func:`freshness_label`).
    * ``reason`` — short, redacted human string explaining a non-default
      state: why the source failed, why the data is synthetic, or why a
      sample timestamp is unavailable.
    * ``capabilities`` — tuple of capability tags (e.g. ``historical_data``,
      ``latest_quote``, ``order_book``).
    * ``observed_at`` — ISO-8601 UTC string ("…Z") of when the registry
      snapshot was assembled. Distinct from ``as_of`` (the data's sample
      time) — consumers use it to compute "how long ago was this plan
      built". Always present.
    """

    source_id: str
    display_name: str
    status: str
    ok: bool
    required: bool
    fallback: bool
    as_of: Optional[str]
    age_seconds: Optional[float]
    freshness: str
    reason: Optional[str]
    capabilities: Tuple[str, ...] = field(default_factory=tuple)
    observed_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Project to a JSON-safe dict (tuples → lists)."""
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "status": self.status,
            "ok": self.ok,
            "required": self.required,
            "fallback": self.fallback,
            "as_of": self.as_of,
            "age_seconds": self.age_seconds,
            "freshness": self.freshness,
            "reason": self.reason,
            "capabilities": list(self.capabilities),
            "observed_at": self.observed_at,
        }


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


_AsOfInput = Optional[Union[str, datetime]]


def _coerce_capabilities(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        # A bare string is treated as a single capability tag.
        return (value,)
    if isinstance(value, Mapping):
        # ``{"order_book": True, "fundamental_data": False}`` →
        # keep only the truthy ones, preserving insertion order.
        return tuple(str(key) for key, enabled in value.items() if enabled)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value)
    return ()


def _parse_as_of(value: _AsOfInput) -> Optional[datetime]:
    """Best-effort parse to an aware ``datetime`` in UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    # ``datetime.fromisoformat`` accepts ``"+00:00"`` but not ``"Z"`` (pre-3.11).
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _format_as_of(parsed: Optional[datetime]) -> Optional[str]:
    """Re-render a parsed timestamp as ISO with a ``Z`` UTC suffix."""
    if parsed is None:
        return None
    utc = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return utc.isoformat().replace("+00:00", "Z")


def _coerce_status(value: Any, *, ok: bool) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "ready" if ok else "unknown"


def _coerce_reason(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_required(
    value: Any, *, source_id: str, default_required: Optional[str]
) -> bool:
    if value is None:
        return source_id == default_required
    return bool(value)


def _coerce_fallback(value: Any, *, ok: bool, status: str) -> bool:
    if value is None:
        # Unknown/minimal specs have not declared fallback semantics yet.
        # Once a source reports a concrete failing status (for example
        # "skipped" or "error"), it is eligible as a fallback candidate by
        # default. currently-ok sources are not "in fallback role".
        return (not ok) and status != "unknown"
    return bool(value)


def build_source_registry(
    specs: Iterable[Mapping[str, Any]],
    *,
    default_required: Optional[str] = None,
    now: Optional[datetime] = None,
    thresholds: FreshnessThresholds = DEFAULT_FRESHNESS,
) -> List[SourceHealthEntry]:
    """Normalize a list of source-health specs into ordered entries.

    Specs are arbitrary mappings; recognized keys: ``source_id`` (required),
    ``display_name``, ``status``, ``ok``, ``required``, ``fallback``,
    ``as_of`` (str / datetime), ``reason``, ``capabilities`` (iterable or
    dict of feature → bool).

    Ordering: required first, then ``ok=True``, then alphabetical by
    ``display_name``. Specs missing a non-empty ``source_id`` are silently
    skipped — callers can pass a heterogeneous mix without pre-filtering.
    """
    reference_now = (now or datetime.now(timezone.utc))
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)
    observed_at = _format_as_of(reference_now)

    entries: List[SourceHealthEntry] = []
    for spec in specs:
        if not isinstance(spec, Mapping):
            continue
        raw_id = spec.get("source_id")
        if not isinstance(raw_id, str):
            continue
        source_id = raw_id.strip()
        if not source_id:
            continue

        ok_value = bool(spec.get("ok", False))
        status = _coerce_status(spec.get("status"), ok=ok_value)
        display_name_raw = spec.get("display_name")
        display_name = (
            display_name_raw.strip()
            if isinstance(display_name_raw, str) and display_name_raw.strip()
            else source_id
        )

        parsed_as_of = _parse_as_of(spec.get("as_of"))
        as_of_str = _format_as_of(parsed_as_of)
        age_seconds: Optional[float]
        if parsed_as_of is None:
            age_seconds = None
        else:
            age_seconds = float(
                (reference_now - parsed_as_of).total_seconds()
            )
        freshness = freshness_label(age_seconds, thresholds=thresholds)

        entries.append(
            SourceHealthEntry(
                source_id=source_id,
                display_name=display_name,
                status=status,
                ok=ok_value,
                required=_coerce_required(
                    spec.get("required"),
                    source_id=source_id,
                    default_required=default_required,
                ),
                fallback=_coerce_fallback(
                    spec.get("fallback"), ok=ok_value, status=status
                ),
                as_of=as_of_str,
                age_seconds=age_seconds,
                freshness=freshness,
                reason=_coerce_reason(spec.get("reason")),
                capabilities=_coerce_capabilities(spec.get("capabilities")),
                observed_at=observed_at,
            )
        )

    entries.sort(key=_ordering_key)
    return entries


def _ordering_key(entry: SourceHealthEntry) -> Tuple[int, int, str, str]:
    """Sort key: required first, then ok=True, then display name, then id."""
    return (
        0 if entry.required else 1,
        0 if entry.ok else 1,
        entry.display_name.lower(),
        entry.source_id.lower(),
    )


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------


__all__: Sequence[str] = (
    "DEFAULT_FRESHNESS",
    "FRESHNESS_EXPIRED",
    "FRESHNESS_FRESH",
    "FRESHNESS_MISSING",
    "FRESHNESS_RECENT",
    "FRESHNESS_STALE",
    "FreshnessThresholds",
    "SourceHealthEntry",
    "build_source_registry",
    "freshness_label",
)
