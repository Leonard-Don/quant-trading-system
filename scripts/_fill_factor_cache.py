"""Throttle-aware filler for the survivorship-free factor panel cache.

Warms the per-symbol pickle cache (price/fundamental/moneyflow) for the FULL
survivorship-free CSI300 union in batches that stay under the per-minute budget,
sleeping between batches so the sliding-window throttle never short-circuits a
symbol to an empty frame. Resumable: already-cached symbols are skipped.

Not part of the test surface — a one-shot research driver. Run:
    TUSHARE_TOKEN=... PYTHONPATH=. python scripts/_fill_factor_cache.py
"""

from __future__ import annotations

import pathlib
import sys
import time

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CSI300_CODE = "000300.SH"
START, END = "20180101", "20240101"
CACHE = PROJECT_ROOT / "data/_factor_cache"
BATCH = 55  # 55 symbols * 3 endpoints = 165 calls < 200/min budget
SLEEP_S = 62


def main() -> int:
    from src.data.factor_panel import build_panel, build_survivorship_free_universe
    from src.data.providers.tushare_provider import TushareProvider

    provider = TushareProvider()
    universe = build_survivorship_free_universe(
        provider, CSI300_CODE, START, END, sample_freq_days=90
    )
    print(f"union universe: {len(universe)} symbols", flush=True)

    # Skip symbols whose price pickle already exists (resumable).
    todo = [s for s in universe if not (CACHE / f"{s}_px.pkl").exists()]
    print(f"to fetch: {len(todo)} (already cached: {len(universe) - len(todo)})", flush=True)

    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        provider.reset_throttle()
        build_panel(batch, START, END, provider, cache_dir=CACHE)
        got = sum(1 for s in batch if (CACHE / f"{s}_px.pkl").exists())
        print(
            f"batch {i // BATCH + 1}: requested {len(batch)}, "
            f"px-cached {got}; cumulative {i + len(batch)}/{len(todo)}",
            flush=True,
        )
        if i + BATCH < len(todo):
            time.sleep(SLEEP_S)

    cached = sum(1 for s in universe if (CACHE / f"{s}_px.pkl").exists())
    print(f"DONE: {cached}/{len(universe)} union symbols have a price cache", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
