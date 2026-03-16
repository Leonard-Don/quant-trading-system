#!/usr/bin/env python3
"""
预热 Sina 行业目录与成分股缓存。

用途：
- 刷新行业目录缓存（可走备用目录端点）
- 尝试为若干或全部行业拉取成分股，并写入持久化缓存
- 适合在 Sina endpoint 间歇性可用时反复执行
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.providers.sina_provider import SinaFinanceProvider

KNOWN_NEW_INDUSTRY_CODES = [
    "new_blhy", "new_cbzz", "new_cmyl", "new_dlhy", "new_dqhy", "new_dzqj", "new_dzxx", "new_fdc",
    "new_fdsb", "new_fjzz", "new_fzhy", "new_fzjx", "new_fzxl", "new_glql", "new_gsgq", "new_gthy",
    "new_hbhy", "new_hghy", "new_hqhy", "new_jdhy", "new_jdly", "new_jjhy", "new_jrhy", "new_jtys",
    "new_jxhy", "new_jzjc", "new_kfq", "new_ljhy", "new_mtc", "new_mthy", "new_nlmy", "new_nyhf",
    "new_qczz", "new_qtxy", "new_slzp", "new_snhy", "new_sphy", "new_stock", "new_swzz", "new_sybh",
    "new_syhy", "new_tchy", "new_wzwm", "new_ylqx", "new_ysbz", "new_ysjs", "new_zhhy", "new_zzhy",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Warm Sina industry list and stock caches")
    parser.add_argument("--limit", type=int, default=10, help="How many industries to try")
    parser.add_argument("--sleep", type=float, default=0.5, help="Seconds between industry requests")
    parser.add_argument(
        "--mode",
        choices=["auto", "list", "known_new"],
        default="auto",
        help="Use live industry list, a built-in new_* node list, or auto-select built-in nodes when list lacks new_* codes",
    )
    args = parser.parse_args()

    provider = SinaFinanceProvider()
    industries = provider.get_industry_list()
    use_known_new_codes = args.mode == "known_new"
    if args.mode == "auto":
        use_known_new_codes = industries.empty or not provider._has_preferred_industry_codes(industries)

    if industries.empty and not use_known_new_codes:
        print("Failed: industry list unavailable")
        return 1

    if not industries.empty:
        print(f"Industry list ready: {len(industries)} rows")
    if use_known_new_codes:
        print(f"Using built-in new_* node list: {len(KNOWN_NEW_INDUSTRY_CODES)} codes")

    success = 0
    total = 0

    if use_known_new_codes:
        targets = [
            {"industry_code": code, "industry_name": code}
            for code in KNOWN_NEW_INDUSTRY_CODES[:args.limit]
        ]
    else:
        targets = industries.head(args.limit).to_dict(orient="records")

    for row in targets:
        total += 1
        code = str(row["industry_code"])
        name = str(row["industry_name"])
        stocks = provider.get_industry_stocks(code, fetch_all=True)
        if stocks:
            success += 1
            print(f"OK  {name} {code}: {len(stocks)} stocks")
        else:
            print(f"MISS {name} {code}")
        time.sleep(args.sleep)

    print(f"Done: {success}/{total} industries cached")
    print(f"List cache: {provider._industry_list_cache_path}")
    print(f"Stocks cache: {provider._industry_stocks_cache_path}")
    return 0 if success > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
