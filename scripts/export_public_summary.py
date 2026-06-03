#!/usr/bin/env python3
"""
导出 quant-trading-system 公开摘要 (Phase F1).

把 runtime 私有缓存（``cache/alt_data/providers/*.json``、
``data/paper_trading/*.json``、``data/industry/heatmap_history.json``）蒸馏为
一份小而稳定、可安全提交到版本库的 ``data/public/quant_summary.json``。

下游消费者
==========

sibling 项目 ``cn-altdata-brief`` 在 GitHub Actions 里直接 ``git clone``
本仓库，只读 ``data/public/quant_summary.json`` 就能拿到：

- policy_radar 当前 industry 信号 top-N（已按 |avg_impact| 排序）
- 行业热度榜单（top-10 行业的最新 score / change% / 关联政策信号）
- paper_trading 已激活的 profile 列表

它不需要直接访问 ``cache/``（被 ``.gitignore`` 排除），也不需要拉起后端
FastAPI 进程。

设计要点
========

1. **schema 稳定**：顶层 ``schema_version`` 控制破坏性变更；同输入同
   输出（除了 ``generated_at`` 是当前运行时刻），方便 ``git diff`` 看出
   真实数据变化而不是元数据噪音。
2. **安全过滤**：永远不写入文件路径、原始 RSS 正文、debug 字段、用户
   现金 / 持仓金额、broker 凭据等内部 metadata。
3. **大小可控**：每个 section 都有 top-N cap，预期 5–15 KB。
4. **graceful degrade**：缺 cache 时对应 key 直接缺席，不写入合成数据。

脚本自包含：可在不启动 FastAPI 的情况下直接
``python scripts/export_public_summary.py``。Sibling 项目 super-pricing-system
有 Celery beat 触发等价导出；本项目 Celery 只用于回测任务卸载（参考
``CLAUDE.md``），所以这里通过 ``docs/MAINTENANCE_GUIDE.md`` 推荐的 cron
条目周期触发。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROVIDERS_DIR = PROJECT_ROOT / "cache" / "alt_data" / "providers"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "public" / "quant_summary.json"
DEFAULT_VERSION_PATH = PROJECT_ROOT / "VERSION"
DEFAULT_HEATMAP_HISTORY_PATH = PROJECT_ROOT / "data" / "industry" / "heatmap_history.json"
DEFAULT_PAPER_TRADING_DIR = PROJECT_ROOT / "data" / "paper_trading"
# Ensure ``src.*`` imports resolve when invoked via ``python scripts/...``.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Stable schema version. Bumps when the *shape* of any output field
# changes in a breaking way. Additive fields do NOT bump.
SCHEMA_VERSION = 1

# Cap how many industries we publish from policy_radar.industry_signals
# (sorted by |avg_impact|, ties broken by mentions). Keeps the file
# bounded if upstream coverage grows.
MAX_POLICY_INDUSTRIES = 5

# Cap how many top-scoring industries we surface in industry_heat.
MAX_INDUSTRY_HEAT_ROWS = 10

# Cap how many paper_trading profile names we list (only names — no
# cash / positions). Anonymises a workstation with hundreds of profiles.
MAX_PAPER_TRADING_PROFILES = 50

# Policy-radar signals are thematic (for example ``电网`` / ``风电``),
# while the industry heatmap uses finer Shenwan-style names (``电网设备`` /
# ``风电设备``).  Keep a tiny, explicit alias map so the public summary can
# publish canonical cross-source names when both sources are present instead
# of reporting a degenerate "no shared industries" result downstream.
POLICY_HEAT_CANONICAL_ALIASES: dict[str, str] = {
    "电网设备": "电网",
    "风电设备": "风电",
    "电池": "新能源汽车",
    "汽车整车": "新能源汽车",
    "汽车零部件": "新能源汽车",
}

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    """Stable, microsecond-stripped UTC ISO timestamp."""
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def _read_version(version_path: Path) -> str:
    try:
        return version_path.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def _read_json_or_none(path: Path) -> Any | None:
    """Return ``json.load(path)`` or ``None`` (with warning) on any error."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return None
    # Reject NaN / inf — they break JSON encoding and aren't useful here.
    if coerced != coerced or coerced in (float("inf"), float("-inf")):
        return None
    return coerced


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round_optional_float(value: Any, *, digits: int = 4) -> float | None:
    coerced = _coerce_float(value)
    return round(coerced, digits) if coerced is not None else None


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_policy_radar_section(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Distil ``policy_radar.json`` into the top-N industry signals.

    Drops every per-record raw_value, link, excerpt, source_health detail.
    Only publishes the aggregated industry signals plus a record-count
    headline and a refresh timestamp.
    """
    signal = snapshot.get("signal") or {}
    industry_signals_raw = signal.get("industry_signals") or {}

    rows: list[dict[str, Any]] = []
    for industry, payload in industry_signals_raw.items():
        if not isinstance(payload, dict):
            continue
        avg_impact = _coerce_float(payload.get("avg_impact"))
        mentions = _coerce_int(payload.get("mentions"))
        rows.append(
            {
                "industry": str(industry),
                "avg_impact": round(avg_impact, 4) if avg_impact is not None else 0.0,
                "mentions": mentions,
                "signal": str(payload.get("signal", "neutral")),
            }
        )
    # Sort by |avg_impact| desc, ties by mentions desc, ties by industry name
    # for deterministic git diffs.
    rows.sort(
        key=lambda r: (abs(float(r["avg_impact"])), int(r["mentions"]), r["industry"]),
        reverse=True,
    )
    top_industries = rows[:MAX_POLICY_INDUSTRIES]

    last_refresh = signal.get("timestamp")
    return {
        "last_refresh_at": str(last_refresh) if isinstance(last_refresh, str) else None,
        "total_records": _coerce_int(signal.get("record_count")),
        "policy_count": _coerce_int(signal.get("policy_count")),
        "top_industries": top_industries,
    }


def _is_test_fixture_snapshot(snapshot: dict[str, Any]) -> bool:
    """True iff every industry name in the snapshot looks like a fixture.

    Guards against historical heatmap snapshots that accidentally include
    rows like ``测试行业`` / ``测试龙头`` / ``test_industry`` / ``demo_*``.
    A real production snapshot has 40+ industries with canonical Chinese
    names (新能源汽车, 电网, 煤炭开采加工, ...). If *every* row in the
    snapshot is recognisably a test fixture, the snapshot is rejected
    upstream of being picked as ``latest``.

    Heuristics (all-of-the-above on any individual row qualifies it as a
    fixture, then we require ALL rows to be fixtures to drop the
    snapshot — single-row fixture snapshots are the common shape):

    * row name contains the substring ``测试`` (Chinese "test"); or
    * row name starts with ``test_`` / ``demo_`` / ``old_`` / ``fixture_``
      (ASCII fixture prefixes used by unit tests).
    """
    rows = snapshot.get("industries")
    if not isinstance(rows, list) or not rows:
        return False
    fixture_prefixes = ("test_", "demo_", "old_", "fixture_")
    for entry in rows:
        if not isinstance(entry, dict):
            return False
        name = str(entry.get("name") or "").strip()
        if not name:
            return False
        looks_fixture = "测试" in name or name.startswith(fixture_prefixes)
        if not looks_fixture:
            return False
    return True


def _canonical_heat_industry_name(
    raw_name: str,
    *,
    preferred_industry_names: set[str],
) -> str:
    """Return the cross-source canonical name for a heatmap industry.

    Aliasing is only applied when the policy-radar section actually
    contains the thematic name.  This preserves heatmap-native names for
    standalone exports, while making strict cross-source validation useful
    when both policy and heat data are present.
    """
    alias = POLICY_HEAT_CANONICAL_ALIASES.get(raw_name)
    if alias and alias in preferred_industry_names:
        return alias
    return raw_name


def _build_industry_heat_section(
    history_path: Path,
    *,
    preferred_industry_names: set[str] | None = None,
) -> dict[str, Any] | None:
    """Distil ``data/industry/heatmap_history.json`` into top-N rows.

    The history file is an array of snapshots; we pick the most recent
    (by ``captured_at``) NON-FIXTURE snapshot and publish the top-N
    industries by ``total_score``. Snapshots that consist entirely of
    test-fixture rows (e.g. ``{"name": "测试行业"}``) are filtered out
    so a stray developer fixture in the history file cannot poison the
    committed public summary that downstream sibling projects consume.
    """
    history = _read_json_or_none(history_path)
    if not isinstance(history, list) or not history:
        return None

    def _captured_at(snapshot: Any) -> str:
        if not isinstance(snapshot, dict):
            return ""
        return str(snapshot.get("captured_at") or snapshot.get("update_time") or "")

    real_snapshots = [
        snap
        for snap in history
        if isinstance(snap, dict) and not _is_test_fixture_snapshot(snap)
    ]
    if not real_snapshots:
        return None

    latest = max(real_snapshots, key=_captured_at)
    if not isinstance(latest, dict):
        return None

    industries = latest.get("industries")
    if not isinstance(industries, list) or not industries:
        return None

    preferred_industry_names = preferred_industry_names or set()
    rows: list[dict[str, Any]] = []
    for entry in industries:
        if not isinstance(entry, dict):
            continue
        raw_name = str(entry.get("name") or "")
        if not raw_name:
            continue
        industry_name = _canonical_heat_industry_name(
            raw_name,
            preferred_industry_names=preferred_industry_names,
        )
        score = _coerce_float(entry.get("total_score")) or 0.0
        change_pct = _coerce_float(entry.get("value")) or 0.0
        row = {
            "industry_name": industry_name,
            "score": round(score, 2),
            "change_pct": round(change_pct, 2),
            "stock_count": _coerce_int(entry.get("stockCount")),
        }
        if industry_name != raw_name:
            row["source_industry_name"] = raw_name
        rows.append(row)

    # Sort by score desc, ties by change_pct desc, ties by name asc.
    rows.sort(key=lambda r: (-float(r["score"]), -float(r["change_pct"]), r["industry_name"]))

    # Canonical aliases can map several heatmap leaves to one policy theme
    # (e.g. 电池 / 汽车整车 → 新能源汽车). Keep the strongest row per
    # canonical name so downstream consumers see a stable one-row signal.
    deduped_rows: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for row in rows:
        name = str(row["industry_name"])
        if name in seen_names:
            continue
        seen_names.add(name)
        deduped_rows.append(row)

    selected = list(deduped_rows[:MAX_INDUSTRY_HEAT_ROWS])
    if preferred_industry_names and selected:
        selected_names = {str(row["industry_name"]) for row in selected}
        if not (selected_names & preferred_industry_names):
            preferred_candidates = [
                row
                for row in deduped_rows
                if str(row["industry_name"]) in preferred_industry_names
            ]
            if preferred_candidates:
                # Reserve the last slot for the highest-scoring cross-source
                # overlap. This intentionally trades one tail heat row for a
                # row that makes policy-vs-heat consistency measurable.
                forced = preferred_candidates[0]
                if len(selected) >= MAX_INDUSTRY_HEAT_ROWS:
                    selected[-1] = forced
                else:
                    selected.append(forced)

    top_rows: list[dict[str, Any]] = []
    for rank, row in enumerate(selected, start=1):
        top_rows.append({"rank": rank, **row})

    captured_at = latest.get("captured_at") or latest.get("update_time")
    return {
        "snapshot_captured_at": str(captured_at) if captured_at else None,
        "days": _coerce_int(latest.get("days"), default=5),
        "top_industries_by_score": top_rows,
    }


def _enrich_industry_heat_with_policy_signal(
    industry_heat: dict[str, Any],
    policy_radar: dict[str, Any],
) -> dict[str, Any]:
    """Attach the matching policy_radar signal to each industry_heat row.

    If the policy_radar top_industries list contains the same industry
    name (exact match), inline the avg_impact / mentions / signal under
    ``policy_signal``. No match means the field is absent — never invent
    a signal.
    """
    policy_by_name: dict[str, dict[str, Any]] = {
        str(row.get("industry")): {
            "avg_impact": row.get("avg_impact"),
            "mentions": row.get("mentions"),
            "signal": row.get("signal"),
        }
        for row in policy_radar.get("top_industries", [])
        if isinstance(row, dict) and row.get("industry")
    }
    enriched_rows: list[dict[str, Any]] = []
    for row in industry_heat.get("top_industries_by_score", []):
        if not isinstance(row, dict):
            continue
        name = row.get("industry_name")
        match = policy_by_name.get(str(name)) if name else None
        new_row = dict(row)
        if match is not None:
            new_row["policy_signal"] = match
        enriched_rows.append(new_row)
    new_block = dict(industry_heat)
    new_block["top_industries_by_score"] = enriched_rows
    return new_block


def _build_paper_trading_section(profiles_dir: Path) -> dict[str, Any]:
    """List active paper_trading profile names (no cash/position detail).

    Profile names are the filenames (sans ``.json``) under
    ``data/paper_trading/``. We never read the account body — file presence
    alone is the signal.
    """
    profile_names: list[str] = []
    if profiles_dir.exists():
        for entry in sorted(profiles_dir.iterdir()):
            if entry.is_file() and entry.suffix == ".json":
                profile_names.append(entry.stem)
    profile_names = profile_names[:MAX_PAPER_TRADING_PROFILES]
    return {
        "active_profiles": profile_names,
        "profile_count": len(profile_names),
        "available": bool(profile_names),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_public_summary(
    providers_dir: Path = DEFAULT_PROVIDERS_DIR,
    *,
    version_path: Path = DEFAULT_VERSION_PATH,
    heatmap_history_path: Path = DEFAULT_HEATMAP_HISTORY_PATH,
    paper_trading_dir: Path = DEFAULT_PAPER_TRADING_DIR,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the public quant summary dict from on-disk runtime artifacts.

    Every input has a sensible default rooted at ``PROJECT_ROOT`` (or the
    user's home for the audit log). Tests pass synthetic paths to
    exercise specific branches.

    Parameters
    ----------
    generated_at:
        Override for the ``generated_at`` field. Defaults to current UTC.
        Tests pass a fixed value for deterministic assertions.
    """
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or _now_utc_iso(),
        "source_codebase_version": _read_version(version_path),
    }

    # --- policy_radar
    policy_radar_snapshot = _read_json_or_none(providers_dir / "policy_radar.json")
    policy_radar_section: dict[str, Any] | None = None
    if isinstance(policy_radar_snapshot, dict):
        policy_radar_section = _build_policy_radar_section(policy_radar_snapshot)
        payload["policy_radar"] = policy_radar_section

    # --- industry_heat (enriched with matching policy_radar signal when present)
    preferred_industry_names: set[str] = set()
    if policy_radar_section is not None:
        preferred_industry_names = {
            str(row.get("industry"))
            for row in policy_radar_section.get("top_industries", [])
            if isinstance(row, dict) and row.get("industry")
        }
    industry_heat_section = _build_industry_heat_section(
        heatmap_history_path,
        preferred_industry_names=preferred_industry_names,
    )
    if industry_heat_section is not None:
        if policy_radar_section is not None:
            industry_heat_section = _enrich_industry_heat_with_policy_signal(
                industry_heat_section, policy_radar_section
            )
        payload["industry_heat"] = industry_heat_section

    # --- paper_trading (always present — file-presence based)
    payload["paper_trading"] = _build_paper_trading_section(paper_trading_dir)

    # --- providers envelope (sibling-project contract, additive)
    #
    # cn-altdata-brief's ``QuantTradingAdapter`` (and the sibling
    # super-pricing-system summary) reads everything under a top-level
    # ``providers`` key with canonical field names (``industry``,
    # ``heat_score``, ``policy_signal``, ``policy_impact``, ``mentions``).
    # The flat ``policy_radar`` / ``industry_heat`` blocks above are kept
    # for backward compatibility (same schema_version=1, purely additive).
    payload["providers"] = _build_providers_envelope(
        policy_radar_section=policy_radar_section,
        industry_heat_section=industry_heat_section,
        paper_trading_section=payload["paper_trading"],
    )

    return payload


def _build_providers_envelope(
    *,
    policy_radar_section: dict[str, Any] | None,
    industry_heat_section: dict[str, Any] | None,
    paper_trading_section: dict[str, Any],
) -> dict[str, Any]:
    """Build the ``providers`` envelope matching the sibling-project contract.

    Sibling project ``cn-altdata-brief`` (and the symmetric
    ``super-pricing-system`` exporter) expect a top-level ``providers``
    block whose children use canonical field names:

    * ``policy_radar.top_industries[]`` rows: ``industry``, ``avg_impact``,
      ``mentions``, ``signal`` (already canonical in our flat block — we
      just nest it).
    * ``industry_heat.top_industries_by_score[]`` rows: ``industry``,
      ``heat_score``, ``policy_signal`` (string: bullish/bearish/neutral),
      ``policy_impact`` (float), ``mentions`` (int).

    The flat per-section blocks above keep their richer / source-shape
    fields (``industry_name``, ``score``, ``change_pct``, ``stock_count``,
    nested ``policy_signal: {avg_impact, mentions, signal}``) — both
    shapes coexist for additive backward compatibility.
    """
    envelope: dict[str, Any] = {}

    if policy_radar_section is not None:
        envelope["policy_radar"] = {
            "policy_count": policy_radar_section.get("policy_count", 0),
            "last_refresh_at": policy_radar_section.get("last_refresh_at"),
            "top_industries": [
                {
                    "industry": row.get("industry"),
                    "avg_impact": row.get("avg_impact"),
                    "mentions": row.get("mentions"),
                    "signal": row.get("signal"),
                }
                for row in policy_radar_section.get("top_industries", [])
                if isinstance(row, dict)
            ],
        }

    if industry_heat_section is not None:
        # Build a name -> {avg_impact, mentions, signal} lookup so heat rows
        # carry the canonical policy_signal string + policy_impact float
        # (not the nested dict the flat block uses).
        policy_lookup: dict[str, dict[str, Any]] = {}
        if policy_radar_section is not None:
            for row in policy_radar_section.get("top_industries", []):
                if not isinstance(row, dict):
                    continue
                name = row.get("industry")
                if not name:
                    continue
                policy_lookup[str(name)] = {
                    "avg_impact": row.get("avg_impact"),
                    "signal": row.get("signal"),
                    "mentions": row.get("mentions"),
                }
        heat_rows: list[dict[str, Any]] = []
        for row in industry_heat_section.get("top_industries_by_score", []):
            if not isinstance(row, dict):
                continue
            name = str(row.get("industry_name") or "")
            if not name:
                continue
            match = policy_lookup.get(name)
            heat_rows.append(
                {
                    "industry": name,
                    # heat_score is the same total_score we publish in the
                    # flat block — keep as float, downstream sorts on it.
                    "heat_score": _coerce_float(row.get("score")) or 0.0,
                    "policy_signal": (
                        str(match.get("signal") or "neutral")
                        if match is not None
                        else "neutral"
                    ),
                    "policy_impact": (
                        _coerce_float(match.get("avg_impact")) or 0.0
                        if match is not None
                        else 0.0
                    ),
                    "mentions": (
                        _coerce_int(match.get("mentions"))
                        if match is not None
                        else 0
                    ),
                }
            )
        envelope["industry_heat"] = {
            "last_refresh_at": industry_heat_section.get("snapshot_captured_at"),
            "top_industries_by_score": heat_rows,
        }

    # paper_trading: just lift the existing section — no rename needed.
    envelope["paper_trading"] = paper_trading_section

    return envelope


def write_public_summary_atomic(payload: dict[str, Any], output_path: Path) -> None:
    """Atomic-write the payload to ``output_path`` using the tempfile pattern.

    Writes to a tempfile in the same directory, then ``rename`` swaps it in
    so a reader never sees a half-written file. JSON is sorted + indented
    so ``git diff`` is human-readable.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f"{output_path.stem}-",
        suffix=f"{output_path.suffix}.tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")  # POSIX-friendly trailing newline
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)


def export_public_summary(
    providers_dir: Path = DEFAULT_PROVIDERS_DIR,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    *,
    version_path: Path = DEFAULT_VERSION_PATH,
    heatmap_history_path: Path = DEFAULT_HEATMAP_HISTORY_PATH,
    paper_trading_dir: Path = DEFAULT_PAPER_TRADING_DIR,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """One-shot: build the summary and atomic-write it to disk."""
    payload = build_public_summary(
        providers_dir,
        version_path=version_path,
        heatmap_history_path=heatmap_history_path,
        paper_trading_dir=paper_trading_dir,
        generated_at=generated_at,
    )
    write_public_summary_atomic(payload, output_path)
    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Distill cache/alt_data/providers/*.json + data/industry/* + "
            "data/paper_trading/* into the small, sanitized, committable "
            "data/public/quant_summary.json."
        )
    )
    parser.add_argument(
        "--providers-dir",
        type=Path,
        default=DEFAULT_PROVIDERS_DIR,
        help=f"Source providers directory (default: {DEFAULT_PROVIDERS_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Destination JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--heatmap-history",
        type=Path,
        default=DEFAULT_HEATMAP_HISTORY_PATH,
        help="Industry heatmap history file (default: data/industry/heatmap_history.json)",
    )
    parser.add_argument(
        "--paper-trading-dir",
        type=Path,
        default=DEFAULT_PAPER_TRADING_DIR,
        help="Paper trading profiles directory (default: data/paper_trading/)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the JSON to stdout instead of writing to disk.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    payload = build_public_summary(
        args.providers_dir,
        heatmap_history_path=args.heatmap_history,
        paper_trading_dir=args.paper_trading_dir,
    )
    if args.print:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    write_public_summary_atomic(payload, args.output)
    logger.info(
        "Wrote public summary to %s (sections=%s)",
        args.output,
        sorted(k for k in payload if k not in {"schema_version", "generated_at"}),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
