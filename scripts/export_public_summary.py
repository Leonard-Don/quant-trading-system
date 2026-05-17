#!/usr/bin/env python3
"""
导出 quant-trading-system 公开摘要 (Phase F1).

把 runtime 私有缓存（``cache/alt_data/providers/*.json``、
``~/.config/etf-rotation/audit.jsonl``、``data/paper_trading/*.json``、
``data/industry/heatmap_history.json``）蒸馏为一份小而稳定、可安全提交到
版本库的 ``data/public/quant_summary.json``。

下游消费者
==========

sibling 项目 ``cn-altdata-brief`` 在 GitHub Actions 里直接 ``git clone``
本仓库，只读 ``data/public/quant_summary.json`` 就能拿到：

- policy_radar 当前 industry 信号 top-N（已按 |avg_impact| 排序）
- 行业热度榜单（top-10 行业的最新 score / change% / 关联政策信号）
- ETF rotation 默认开关 / universe 大小 / 最近一次审计条目数
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
DEFAULT_AUDIT_LOG_PATH = Path.home() / ".config" / "etf-rotation" / "audit.jsonl"
DEFAULT_BACKTEST_PRICE_CSV = PROJECT_ROOT / "data" / "etf_backtest" / "etf_prices_4y.csv"

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


def _build_industry_heat_section(history_path: Path) -> dict[str, Any] | None:
    """Distil ``data/industry/heatmap_history.json`` into top-N rows.

    The history file is an array of snapshots; we pick the most recent
    (by ``captured_at``) and publish the top-N industries by ``total_score``.
    """
    history = _read_json_or_none(history_path)
    if not isinstance(history, list) or not history:
        return None

    def _captured_at(snapshot: Any) -> str:
        if not isinstance(snapshot, dict):
            return ""
        return str(snapshot.get("captured_at") or snapshot.get("update_time") or "")

    latest = max(history, key=_captured_at)
    if not isinstance(latest, dict):
        return None

    industries = latest.get("industries")
    if not isinstance(industries, list) or not industries:
        return None

    rows: list[dict[str, Any]] = []
    for entry in industries:
        if not isinstance(entry, dict):
            continue
        score = _coerce_float(entry.get("total_score")) or 0.0
        change_pct = _coerce_float(entry.get("value")) or 0.0
        rows.append(
            {
                "industry_name": str(entry.get("name") or ""),
                "score": round(score, 2),
                "change_pct": round(change_pct, 2),
                "stock_count": _coerce_int(entry.get("stockCount")),
            }
        )

    # Sort by score desc, ties by change_pct desc, ties by name asc.
    rows.sort(key=lambda r: (-float(r["score"]), -float(r["change_pct"]), r["industry_name"]))
    top_rows: list[dict[str, Any]] = []
    for rank, row in enumerate(rows[:MAX_INDUSTRY_HEAT_ROWS], start=1):
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


def _build_etf_rotation_section(
    audit_log_path: Path,
    *,
    backtest_price_csv_path: Path = DEFAULT_BACKTEST_PRICE_CSV,
) -> dict[str, Any]:
    """Static config defaults + the most recent audit log line metadata.

    We only read the *last* line of the audit log so an unbounded log
    file doesn't blow up the script. The audit log line carries plenty
    of structured fields (score_breakdown, adjusted_weights, etc.) — we
    keep none of them; only the run timestamp surfaces.
    """
    # Pull config defaults lazily so the script is importable in test
    # environments that don't have the strategy chain installed.
    try:
        from src.strategy.etf_rotation_config_loader import (
            DEFAULT_STRATEGY_PARAMS,
            DEFAULT_UNIVERSE,
        )

        policy_signal_default = bool(
            DEFAULT_STRATEGY_PARAMS.get("policy_signal_factor_enabled", False)
        )
        universe_size = len(DEFAULT_UNIVERSE)
    except ImportError as exc:
        logger.warning("etf_rotation_config_loader import failed: %s", exc)
        policy_signal_default = False
        universe_size = 0

    # Count strategy classes (concrete BaseStrategy subclasses across the
    # strategy library). We import each module and inspect __mro__ to
    # avoid hard-coding a count that drifts when strategies are added.
    strategies_count = _count_strategy_classes()

    audit_line_count = 0
    latest_audit_at: str | None = None
    latest_audit_run_at: str | None = None
    if audit_log_path.exists():
        try:
            with audit_log_path.open("r", encoding="utf-8") as handle:
                last_payload: dict[str, Any] | None = None
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    audit_line_count += 1
                    try:
                        last_payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
            if isinstance(last_payload, dict):
                # The exporter publishes timestamps only — never the
                # weights / prices / risk reasons body.
                latest_audit_at = (
                    last_payload.get("recorded_at")
                    or last_payload.get("ts")
                )
                latest_audit_run_at = last_payload.get("run_at")
        except OSError as exc:
            logger.warning("Failed to read audit log %s: %s", audit_log_path, exc)

    return {
        "policy_signal_factor_enabled_default": policy_signal_default,
        "config_default_universe_size": universe_size,
        "available_strategies_count": strategies_count,
        "latest_audit_log_entry_count": audit_line_count,
        "latest_audit_at": str(latest_audit_at) if latest_audit_at else None,
        "latest_audit_run_at": str(latest_audit_run_at) if latest_audit_run_at else None,
        "regime_recommendation": _build_regime_recommendation_section(
            backtest_price_csv_path
        ),
    }


def _build_regime_recommendation_section(
    price_csv_path: Path,
    *,
    lookback_days: int = 90,
) -> dict[str, Any]:
    """Publish the current market-regime recommendation without raw prices.

    The sibling ``cn-altdata-brief`` project only needs the label,
    confidence, recommendation and a few rounded feature values. We never
    include the source CSV path or any raw price rows, so the committed public
    summary stays portable and does not leak workstation-local paths.
    """

    base: dict[str, Any] = {
        "available": False,
        "lookback_days": int(lookback_days),
    }
    if not price_csv_path.is_file():
        return {**base, "unavailable_reason": "price_matrix_missing"}

    try:
        import pandas as pd

        from src.strategy.market_regime_classifier import MarketRegimeClassifier
        from src.strategy.strategy_recommender import recommend_strategy
    except ImportError as exc:
        logger.warning("Cannot build regime recommendation: %s", exc)
        return {**base, "unavailable_reason": "classifier_unavailable"}

    try:
        frame = pd.read_csv(price_csv_path, index_col=0)
        frame.index = pd.to_datetime(frame.index)
        prices = (
            frame.apply(pd.to_numeric, errors="coerce")
            .sort_index()
            .ffill()
            .dropna(how="all")
        )
    except (OSError, ValueError) as exc:
        logger.warning("Cannot read regime price matrix: %s", exc)
        return {**base, "unavailable_reason": "price_matrix_unreadable"}

    regime = MarketRegimeClassifier().classify(prices, lookback_days=lookback_days)
    recommendation = recommend_strategy(regime)
    features = regime.features or {}
    return {
        "available": True,
        "lookback_days": int(regime.lookback_days),
        "as_of": regime.as_of,
        "regime_name": regime.regime_name,
        "confidence": _round_optional_float(regime.confidence, digits=3),
        "recommended_strategy": recommendation.strategy_name,
        "config_overrides": dict(recommendation.config_overrides),
        "n_assets_used": int(regime.n_assets_used),
        "features": {
            "trend_r2": _round_optional_float(features.get("trend_r2"), digits=4),
            "trend_slope": _round_optional_float(features.get("trend_slope"), digits=6),
            "realized_vol": _round_optional_float(features.get("realized_vol"), digits=4),
            "return_skew": _round_optional_float(features.get("return_skew"), digits=4),
            "drawdown_ratio": _round_optional_float(features.get("drawdown_ratio"), digits=4),
            "avg_pairwise_correlation": _round_optional_float(
                features.get("avg_pairwise_correlation"), digits=4
            ),
        },
        "rationale": recommendation.rationale,
    }


def _count_strategy_classes() -> int:
    """Count concrete BaseStrategy subclasses available in ``src.strategy``.

    Skipped gracefully (returns 0) if the strategy chain can't be imported
    in this environment (e.g. tests with stubbed deps). The count is a
    headline number for downstream consumers; precision matters less than
    determinism, so we exclude abstract bases (``BaseStrategy``, ``MLStrategy``)
    and any class with abstract methods.
    """
    import importlib
    import inspect

    strategy_modules = (
        "src.strategy.strategies",
        "src.strategy.advanced_strategies",
        "src.strategy.advanced_technical",
        "src.strategy.momentum_strategy",
        "src.strategy.pairs_trading",
        "src.strategy.sentiment_strategy",
        "src.strategy.ml_strategies",
        "src.strategy.lstm_strategy",
        "src.strategy.etf_mean_reversion_strategy",
        "src.strategy.etf_rotation_strategy",
    )
    seen: set[str] = set()
    try:
        base_module = importlib.import_module("src.strategy.strategies")
    except ImportError as exc:
        logger.warning("Cannot count strategies — base import failed: %s", exc)
        return 0
    base_cls = getattr(base_module, "BaseStrategy", None)
    if base_cls is None:
        return 0
    for module_name in strategy_modules:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            logger.warning("Skipping strategy module %s: %s", module_name, exc)
            continue
        for _name, member in inspect.getmembers(module, inspect.isclass):
            if not _name.endswith("Strategy"):
                continue
            # Concrete strategy: inherits from BaseStrategy (or is the ETF
            # rotation/blend wrapper class) AND has no remaining abstract
            # methods. We accept ``EtfMeanReversionStrategy`` /
            # ``EtfRotationStrategy`` even though they don't inherit from
            # ``BaseStrategy``; they're first-class strategies users invoke.
            is_strategy_subclass = base_cls is not None and issubclass(member, base_cls)
            is_etf_wrapper = _name in {
                "EtfMeanReversionStrategy",
                "EtfRotationStrategy",
            }
            if not (is_strategy_subclass or is_etf_wrapper):
                continue
            if _name in {"BaseStrategy", "MLStrategy"}:
                # Abstract; not a user-facing strategy.
                continue
            if getattr(member, "__abstractmethods__", None):
                continue
            seen.add(f"{module_name}.{_name}")
    return len(seen)


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
    audit_log_path: Path = DEFAULT_AUDIT_LOG_PATH,
    backtest_price_csv_path: Path = DEFAULT_BACKTEST_PRICE_CSV,
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
    industry_heat_section = _build_industry_heat_section(heatmap_history_path)
    if industry_heat_section is not None:
        if policy_radar_section is not None:
            industry_heat_section = _enrich_industry_heat_with_policy_signal(
                industry_heat_section, policy_radar_section
            )
        payload["industry_heat"] = industry_heat_section

    # --- etf_rotation (always present — has static defaults to publish)
    payload["etf_rotation"] = _build_etf_rotation_section(
        audit_log_path,
        backtest_price_csv_path=backtest_price_csv_path,
    )

    # --- paper_trading (always present — file-presence based)
    payload["paper_trading"] = _build_paper_trading_section(paper_trading_dir)

    return payload


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
    audit_log_path: Path = DEFAULT_AUDIT_LOG_PATH,
    backtest_price_csv_path: Path = DEFAULT_BACKTEST_PRICE_CSV,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """One-shot: build the summary and atomic-write it to disk."""
    payload = build_public_summary(
        providers_dir,
        version_path=version_path,
        heatmap_history_path=heatmap_history_path,
        paper_trading_dir=paper_trading_dir,
        audit_log_path=audit_log_path,
        backtest_price_csv_path=backtest_price_csv_path,
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
            "data/paper_trading/* + ~/.config/etf-rotation/audit.jsonl into "
            "the small, sanitized, committable data/public/quant_summary.json."
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
        "--audit-log",
        type=Path,
        default=DEFAULT_AUDIT_LOG_PATH,
        help=f"ETF rotation audit log (default: {DEFAULT_AUDIT_LOG_PATH})",
    )
    parser.add_argument(
        "--backtest-price-csv",
        type=Path,
        default=DEFAULT_BACKTEST_PRICE_CSV,
        help="ETF rotation historical price matrix for regime recommendation.",
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
        audit_log_path=args.audit_log,
        backtest_price_csv_path=args.backtest_price_csv,
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
