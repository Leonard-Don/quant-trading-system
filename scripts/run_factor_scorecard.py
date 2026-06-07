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

CSI300_CODE = "000300.SH"


def parse_horizons(text: str) -> list[int]:
    """Parse a comma list of holding horizons (e.g. ``"5,20,60"``) into ints.

    Trims whitespace, drops empties, and de-duplicates while preserving the
    first-seen order so the matrix columns stay in the order the user asked for.
    """
    out: list[int] = []
    for tok in str(text or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        h = int(tok)
        if h not in out:
            out.append(h)
    return out


def resolve_universe(name: str, provider) -> list[str]:
    """Resolve a universe name into a concrete symbol list.

    ``default`` -> the hardcoded ~50-name liquidity list (no network).
    ``csi300``  -> current CSI 300 constituents via the provider (network).
    """
    key = str(name or "default").strip().lower()
    if key == "csi300":
        return list(provider.get_index_constituents(CSI300_CODE))
    return list(DEFAULT_UNIVERSE)


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


def _factor_order(reports_by_horizon: dict[int, list[dict]]) -> list[str]:
    """Factor names in first-seen order across all horizon report lists."""
    order: list[str] = []
    for h in sorted(reports_by_horizon):
        for r in reports_by_horizon[h]:
            if r["name"] not in order:
                order.append(r["name"])
    return order


def _index_reports(reports: list[dict]) -> dict[str, dict]:
    return {r["name"]: r for r in reports}


def build_oos_ic_matrix_markdown(reports_by_horizon: dict[int, list[dict]]) -> str:
    """Compact **factor × horizon -> OOS IC** matrix (4dp, '-' if missing)."""
    horizons = sorted(reports_by_horizon)
    factors = _factor_order(reports_by_horizon)
    per_h = {h: _index_reports(reports_by_horizon[h]) for h in horizons}
    header = "| factor | " + " | ".join(f"h={h}" for h in horizons) + " |"
    sep = "|---|" + "|".join(["--:"] * len(horizons)) + "|"
    lines = [header, sep]
    for name in factors:
        cells = []
        for h in horizons:
            r = per_h[h].get(name)
            v = r.get("oos_mean_ic") if r else None
            cells.append(f"{v:.4f}" if isinstance(v, (int, float)) and v == v else "-")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_pass_fail_matrix_markdown(reports_by_horizon: dict[int, list[dict]]) -> str:
    """Compact **factor × horizon -> PASS/FAIL** matrix (✓ pass / ✗ fail)."""
    horizons = sorted(reports_by_horizon)
    factors = _factor_order(reports_by_horizon)
    per_h = {h: _index_reports(reports_by_horizon[h]) for h in horizons}
    header = "| factor | " + " | ".join(f"h={h}" for h in horizons) + " |"
    sep = "|---|" + "|".join([":--:"] * len(horizons)) + "|"
    lines = [header, sep]
    for name in factors:
        cells = []
        for h in horizons:
            r = per_h[h].get(name)
            cells.append("✓" if r and r.get("passes") else "✗")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _passing_pairs(reports_by_horizon: dict[int, list[dict]]) -> list[str]:
    """``factor@horizon`` labels for every (factor, horizon) that passes the gate."""
    pairs: list[str] = []
    for h in sorted(reports_by_horizon):
        for r in reports_by_horizon[h]:
            if r.get("passes"):
                pairs.append(f"{r['name']}@{h}")
    return pairs


def build_multi_horizon_markdown(
    reports_by_horizon: dict[int, list[dict]],
    *,
    universe_label: str,
    n_symbols: int,
) -> str:
    """Full multi-horizon scorecard document.

    Per-horizon detail sections + a factor×horizon OOS-IC matrix + a
    factor×horizon PASS/FAIL matrix + an honest pass summary.
    """
    horizons = sorted(reports_by_horizon)
    lines = [
        "# 因子记分卡 (Phase 1, multi-horizon)",
        "",
        f"> Universe: **{universe_label}** ({n_symbols} symbols usable). "
        "Universe 用当前成分/流动性名单近似历史池(轻微幸存者偏差)。"
        "点位时间;OOS = 后 30% 时序;门槛 OOS IC ≥ 0.03 且 ICIR>0 且 sign-stable。",
        f"> Horizons (持有天数): {', '.join(f'h={h}' for h in horizons)}",
        "",
        "## factor × horizon → OOS IC",
        "",
        build_oos_ic_matrix_markdown(reports_by_horizon),
        "",
        "## factor × horizon → PASS / FAIL",
        "",
        build_pass_fail_matrix_markdown(reports_by_horizon),
        "",
    ]
    passing = _passing_pairs(reports_by_horizon)
    lines += [
        "## 过关因子 (factor@horizon)",
        "",
        (", ".join(passing) if passing else "无 (none) —— 不启动 Phase 2(诚实门)"),
        "",
    ]
    for h in horizons:
        lines += [
            f"## 明细 h={h}",
            "",
            build_scorecard_markdown(reports_by_horizon[h]),
            "",
        ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20180101")
    ap.add_argument("--end", default="20240101")
    ap.add_argument("--universe", choices=["default", "csi300"], default="default")
    ap.add_argument(
        "--horizons",
        default="20",
        help="comma list of holding horizons in trading days, e.g. 5,20,60",
    )
    ap.add_argument(
        "--max-symbols",
        type=int,
        default=0,
        help="cap the universe to the first N symbols (0 = no cap); used for a bounded fallback",
    )
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

    horizons = parse_horizons(args.horizons)
    if not horizons:
        raise SystemExit("--horizons must contain at least one integer horizon")

    provider = TushareProvider()
    symbols = resolve_universe(args.universe, provider)
    if args.max_symbols and args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]
    print(f"universe={args.universe} requested={len(symbols)} symbols; building panel...")

    # Build the panel ONCE for the universe (resumable per-symbol pickle cache).
    panel = build_panel(
        symbols,
        args.start,
        args.end,
        provider,
        cache_dir=PROJECT_ROOT / "data/_factor_cache",
    )
    usable = len(panel.symbols)
    print(f"panel built: {usable} symbols usable (of {len(symbols)} requested)")
    if usable < 100:
        print(f"WARNING: only {usable} symbols usable (<100); IC estimates will be noisy")

    factors = ALL_PRICE_FACTORS + ALL_FUNDAMENTAL_FACTORS + ALL_MONEYFLOW_FACTORS

    # Rebalance dates need >=252 bars of history; drop the final date per horizon
    # so a forward bar exists (use the longest horizon for the trailing drop so
    # every horizon shares one date grid).
    base_dates = monthly_rebalance_dates(panel.trading_dates)
    ref_sym = panel.symbols[0]
    base_dates = [d for d in base_dates if len(panel.history(ref_sym, d)) >= 252]

    reports_by_horizon: dict[int, list[dict]] = {}
    for h in horizons:
        # Leave enough trailing dates so a forward bar exists for this horizon.
        dates_h = base_dates[:-1] if base_dates else []
        print(f"evaluating {len(factors)} factors @ h={h} over {len(dates_h)} rebalance dates...")
        reports_by_horizon[h] = [
            evaluate_factor(f, panel, dates_h, h, args.train_frac) for f in factors
        ]

    md = build_multi_horizon_markdown(
        reports_by_horizon, universe_label=args.universe, n_symbols=usable
    )
    (PROJECT_ROOT / "docs/factor_scorecard.md").write_text(md, encoding="utf-8")
    (PROJECT_ROOT / "docs/factor_scorecard.json").write_text(
        json.dumps(
            {
                "universe": args.universe,
                "n_symbols_usable": usable,
                "n_symbols_requested": len(symbols),
                "horizons": horizons,
                "start": args.start,
                "end": args.end,
                "reports_by_horizon": {str(h): reports_by_horizon[h] for h in horizons},
            },
            default=str,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(md)


if __name__ == "__main__":
    main()
