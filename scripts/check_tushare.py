#!/usr/bin/env python
"""Self-check: is Tushare actually usable (token valid + reachable)?

Run this after changing ``TUSHARE_TOKEN``. It exits non-zero when Tushare can't
be used, so a *configured-but-dead* token (or a per-minute rate limit) surfaces
loudly instead of silently degrading A-share data — 行业详情 / valuation /
history — to the slow AKShare/EastMoney scrape.

    python scripts/check_tushare.py

Note: reads the token via ``load_dotenv`` (strips surrounding quotes, exactly
like the backend). A raw ``.strip()`` read would keep the quotes and falsely
report ``token_invalid``.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

# Import after dotenv + path setup so the provider sees TUSHARE_TOKEN.
from src.data.providers.tushare_provider import TushareProvider  # noqa: E402


def main() -> int:
    hc = TushareProvider().health_check()
    if hc.get("ok"):
        print(f"✅ Tushare OK — {hc.get('detail')}")
        return 0

    print(f"❌ Tushare NOT usable [{hc.get('reason')}]: {hc.get('detail')}")
    print(
        "   -> A-share detail / valuation / history will silently fall back to the "
        "slow AKShare scrape."
    )
    if hc.get("reason") == "rate_limited":
        print("   -> Looks like a per-minute rate limit; wait ~45s and retry.")
    elif hc.get("reason") in {"token_missing", "token_invalid"}:
        print("   -> Fix TUSHARE_TOKEN in .env (a valid Tushare Pro token).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
