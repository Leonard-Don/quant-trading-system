from __future__ import annotations

import argparse
import json
import pathlib
import sys

import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ~50 diversified, liquid A-share names across sectors. Uses the current
# liquidity list to approximate the historical pool (mild survivorship bias,
# flagged in the scorecard header).
DEFAULT_UNIVERSE = [
    # 金融 (banks / insurance / brokers)
    "601398.SH", "601318.SH", "600036.SH", "601288.SH", "601166.SH",
    "600000.SH", "601628.SH", "600030.SH", "300059.SZ", "601688.SH",
    # 消费 (consumer / liquor / appliances)
    "600519.SH", "000858.SZ", "600887.SH", "000333.SZ", "000651.SZ",
    "603288.SH", "600690.SH", "002304.SZ", "603501.SH", "600809.SH",
    # 医药 (healthcare)
    "600276.SH", "300760.SZ", "603259.SH", "300015.SZ", "002821.SZ",
    # 科技 / 电子 (tech / electronics)
    "002415.SZ", "000725.SZ", "002230.SZ", "300124.SZ", "688981.SH",
    "002714.SZ", "603986.SH", "300782.SZ",
    # 新能源 / 制造 (new energy / manufacturing)
    "300750.SZ", "601012.SH", "002594.SZ", "300274.SZ", "601127.SH",
    "002460.SZ", "603799.SH", "688599.SH",
    # 资源 / 周期 (resources / cyclicals)
    "601899.SH", "600900.SH", "601985.SH", "600028.SH", "601088.SH",
    "600585.SH", "601668.SH", "600009.SH", "601111.SH",
]


def monthly_rebalance_dates(trading_dates) -> list:
    s = pd.Series(1, index=pd.DatetimeIndex(trading_dates))
    return [pd.Timestamp(g.index[0]) for _, g in s.groupby([s.index.year, s.index.month])]


def build_scorecard_markdown(reports: list[dict]) -> str:
    lines = [
        "# 因子记分卡 (Phase 1)",
        "",
        "> Universe 用当前流动性名单近似历史池(轻微幸存者偏差)。点位时间;OOS = 后 30% 时序。",
        "",
        "| factor | n | mean IC | ICIR | OOS IC | sign-stable | verdict |",
        "|---|--:|--:|--:|--:|:--:|:--:|",
    ]
    for r in sorted(reports, key=lambda x: (x.get("oos_mean_ic") or -9), reverse=True):
        vals = {
            k: (r.get(k) if r.get(k) is not None else float("nan"))
            for k in ["name", "n_dates", "mean_ic", "icir", "oos_mean_ic"]
        }
        lines.append(
            "| {name} | {n_dates} | {mean_ic:.4f} | {icir:.3f} | {oos_mean_ic:.4f} | {ss} | {v} |".format(
                ss="✓" if r.get("sign_stable") else "✗",
                v="PASS" if r.get("passes") else "FAIL",
                **vals,
            )
        )
    passed = [r["name"] for r in reports if r.get("passes")]
    lines += ["", f"**过关因子:** {', '.join(passed) if passed else '无 —— 不启动 Phase 2(诚实门)'}"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20180101")
    ap.add_argument("--end", default="20240101")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    from src.analytics.factors.evaluation import evaluate_factor
    from src.analytics.factors.fundamental import ALL_FUNDAMENTAL_FACTORS
    from src.analytics.factors.moneyflow import ALL_MONEYFLOW_FACTORS
    from src.analytics.factors.price import ALL_PRICE_FACTORS
    from src.data.factor_panel import build_panel
    from src.data.providers.tushare_provider import TushareProvider

    panel = build_panel(
        DEFAULT_UNIVERSE,
        args.start,
        args.end,
        TushareProvider(),
        cache_dir=PROJECT_ROOT / "data/_factor_cache",
    )
    dates = monthly_rebalance_dates(panel.trading_dates)
    # Need >=252 bars of history at each rebalance, and drop the final date so a
    # forward bar exists.
    dates = [d for d in dates if len(panel.history(panel.symbols[0], d)) >= 252][:-1]
    factors = ALL_PRICE_FACTORS + ALL_FUNDAMENTAL_FACTORS + ALL_MONEYFLOW_FACTORS
    reports = [evaluate_factor(f, panel, dates, args.horizon, args.train_frac) for f in factors]
    (PROJECT_ROOT / "docs/factor_scorecard.md").write_text(
        build_scorecard_markdown(reports), encoding="utf-8"
    )
    (PROJECT_ROOT / "docs/factor_scorecard.json").write_text(
        json.dumps(reports, default=str, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(build_scorecard_markdown(reports))


if __name__ == "__main__":
    main()
