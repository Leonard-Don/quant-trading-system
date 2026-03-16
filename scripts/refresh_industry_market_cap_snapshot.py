#!/usr/bin/env python3
"""
刷新行业市值快照。

用途：
- 主动执行行业热度链路，尽可能拿到实时行业市值
- 将真实市值来源持久化到 `industry_market_cap_snapshot.json`
- 在外部源抖动时，也能单独维护一份可复用的行业市值快照
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.providers.sina_ths_adapter import SinaIndustryAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh persistent industry market cap snapshot")
    parser.add_argument("--days", type=int, default=5, help="Money-flow lookback window")
    parser.add_argument("--preview", type=int, default=10, help="How many snapshot rows to preview")
    parser.add_argument("--min-entries", type=int, default=60, help="Minimum snapshot entries before forcing a refresh")
    parser.add_argument("--max-age-hours", type=float, default=24.0, help="Refresh when any snapshot row is older than this")
    parser.add_argument("--force", action="store_true", help="Refresh even if the existing snapshot is still healthy")
    parser.add_argument("--inspect-only", action="store_true", help="Only inspect the current snapshot state without refreshing")
    args = parser.parse_args()

    provider = SinaIndustryAdapter()
    snapshot_path = provider._industry_market_cap_snapshot_path
    before_status = provider.get_persistent_market_cap_snapshot_status()

    print(f"Snapshot target: {snapshot_path}")
    print(
        "Current snapshot status: "
        f"entries={before_status['entries']}, "
        f"fresh={before_status['fresh_entries']}, "
        f"stale={before_status['stale_entries']}, "
        f"oldest={_format_age(before_status['max_age_hours'])}, "
        f"sources={before_status['source_counts']}"
    )

    if args.inspect_only:
        _print_snapshot_preview(snapshot_path, args.preview)
        return 0

    oldest_age = before_status["max_age_hours"]
    snapshot_healthy = (
        before_status["entries"] >= args.min_entries
        and before_status["stale_entries"] == 0
        and oldest_age is not None
        and oldest_age <= args.max_age_hours
    )
    if snapshot_healthy and not args.force:
        print(
            "Skipping refresh: "
            f"entries >= {args.min_entries} and oldest snapshot <= {args.max_age_hours:.1f}h"
        )
        _print_snapshot_preview(snapshot_path, args.preview)
        return 0

    print(f"Refreshing market-cap data with days={args.days} ...")
    df = provider.get_industry_money_flow(days=args.days)
    if df.empty:
        print("Failed: provider returned no industry rows")
        return 1

    source_counts = Counter(df.get("market_cap_source", []).astype(str))
    print(f"Industry rows: {len(df)}")
    print(f"Market cap sources: {dict(source_counts)}")

    if not snapshot_path.exists():
        print("Failed: snapshot file was not created")
        return 1

    after_status = provider.get_persistent_market_cap_snapshot_status()
    print(
        "Updated snapshot status: "
        f"entries={after_status['entries']}, "
        f"fresh={after_status['fresh_entries']}, "
        f"stale={after_status['stale_entries']}, "
        f"oldest={_format_age(after_status['max_age_hours'])}, "
        f"sources={after_status['source_counts']}"
    )
    print(f"Snapshot delta: {after_status['entries'] - before_status['entries']:+d} entries")
    _print_snapshot_preview(snapshot_path, args.preview)

    return 0 if after_status["entries"] else 1


def _format_age(age_hours: float | None) -> str:
    if age_hours is None:
        return "n/a"
    return f"{age_hours:.1f}h"


def _print_snapshot_preview(snapshot_path: Path, preview: int) -> None:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else {}
    data = payload.get("data", {})
    print(f"Snapshot entries: {len(data)}")

    preview_rows = sorted(
        data.items(),
        key=lambda item: float(item[1].get("updated_at", 0) or 0),
        reverse=True,
    )[: preview]

    if not preview_rows:
        return

    print("Latest snapshot rows:")
    for industry_code, item in preview_rows:
        print(
            f"- {item.get('industry_name', '')} {industry_code}: "
            f"{item.get('market_cap_source', 'unknown')} "
            f"{float(item.get('total_market_cap', 0) or 0):.2f}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
