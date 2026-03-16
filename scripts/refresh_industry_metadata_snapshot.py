#!/usr/bin/env python3
"""
刷新 AKShare 行业元数据快照。

用途：
- 主动拉取 `stock_board_industry_name_em` 行业元数据
- 触发 `AKShareProvider` 的持久化快照写入
- 在上游偶发抖动时可反复执行，直到生成首份可用快照
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.providers.akshare_provider import AKShareProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh persistent AKShare industry metadata snapshot")
    parser.add_argument("--attempts", type=int, default=5, help="Maximum refresh attempts")
    parser.add_argument("--sleep", type=float, default=2.0, help="Seconds between attempts")
    args = parser.parse_args()

    provider = AKShareProvider()
    cache_path = provider._industry_meta_cache_path

    print(f"Snapshot target: {cache_path}")
    for attempt in range(1, args.attempts + 1):
        print(f"[{attempt}/{args.attempts}] Fetching industry metadata...")
        df = provider._get_industry_metadata()
        if not df.empty and cache_path.exists():
            print(f"Success: fetched {len(df)} industries")
            print(f"Snapshot written: {cache_path}")
            preview_cols = [c for c in ["industry_name", "original_name", "total_market_cap", "turnover_rate"] if c in df.columns]
            if preview_cols:
                print(df[preview_cols].head(5).to_string())
            return 0

        if attempt < args.attempts:
            time.sleep(args.sleep)

    print("Failed: snapshot was not created")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
