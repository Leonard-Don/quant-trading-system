#!/usr/bin/env python3
"""Backtest the full live-strategy pipeline against historical prices.

Unlike ``scripts/backtest_etf_rotation.py`` which only exercises the pure
trend strategy, this harness mirrors what ``EtfRotationService`` does on
every refresh: classify regime → derate gross_cap → swap scoring
overrides → ensemble blend trend + mean-reversion → apply portfolio risk
rules. Then we feed the resulting target-weight matrix to
``PortfolioBacktester`` for accurate P&L simulation.

The point is to answer one question: **does each layer (regime,
scoring overrides, ensemble, risk rules) add or subtract historical
value vs. the bare trend strategy?** Run with multiple ``--mode`` values
and compare the JSON outputs.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.daily_etf_signal import (  # noqa: E402
    build_risk_config,
    build_strategy_config,
    load_default_holdings,
)
from src.backtest.portfolio_backtester import PortfolioBacktester  # noqa: E402
from src.risk.etf_portfolio_rules import apply_etf_portfolio_risk_rules  # noqa: E402
from src.strategy.etf_mean_reversion_strategy import (  # noqa: E402
    EtfMeanReversionConfig,
    EtfMeanReversionRotationConfig,
    EtfMeanReversionStrategy,
)
from src.strategy.etf_regime_detector import build_detector_config, classify_regime  # noqa: E402
from src.strategy.etf_rotation_config_loader import (  # noqa: E402
    StrategyConfig,
    load_strategy_config,
)
from src.strategy.etf_rotation_strategy import (  # noqa: E402
    DEFAULT_REBALANCE_THRESHOLD,
    EtfRotationStrategy,
)
from src.strategy.etf_strategy_blend import EtfStrategyBlend, EtfStrategyBlendConfig  # noqa: E402

logger = logging.getLogger(__name__)

# Default tolerance for per-bar failures during a full historical walk.
# Above this rate we treat the run as data-integrity-broken rather than a
# few transient errors and raise to halt the cron job loudly. Tunable via
# ``--max-error-rate`` and the ``max_error_rate`` kwarg.
DEFAULT_MAX_ERROR_RATE = 0.25


class FullPipelineStrategy:
    """Drop-in for ``PortfolioBacktester`` that runs the full live pipeline.

    On ``generate_signals(price_matrix)`` we walk every bar from
    ``warmup_days`` onward, replay the live decision sequence on the
    price-history-so-far, and record the post-risk-rule target weights.
    The result is shifted by ``lag_days`` to eliminate look-ahead bias —
    same convention as ``EtfRotationStrategy.generate_signals``.

    Layers can be toggled via ``mode``:
    * ``trend``: pure trend strategy, no regime / no ensemble
    * ``regime``: trend + regime adjustment (gross_cap + scoring override)
    * ``ensemble``: regime + trend/MR ensemble (full live pipeline)

    Per-bar failures are swallowed by default (some transient scoring
    bugs shouldn't abort a multi-year backtest), but once the cumulative
    failure rate crosses ``max_error_rate`` we raise — that pattern means
    the input data is broken, not just a couple of bad bars.
    """

    def __init__(
        self,
        *,
        strategy_config: StrategyConfig,
        mode: str = "ensemble",
        lag_days: int = 1,
        apply_risk_rules: bool = True,
        max_error_rate: float = DEFAULT_MAX_ERROR_RATE,
    ) -> None:
        if mode not in {"trend", "regime", "ensemble"}:
            raise ValueError(f"mode must be trend|regime|ensemble, got {mode}")
        if not 0.0 <= max_error_rate <= 1.0:
            raise ValueError(
                f"max_error_rate must be in [0.0, 1.0], got {max_error_rate}"
            )
        self._cfg = strategy_config
        self._mode = mode
        self._lag_days = lag_days
        self._apply_risk_rules = apply_risk_rules
        self._max_error_rate = max_error_rate
        # Holdings are needed for build_strategy_config — use the example seed.
        self._holdings = load_default_holdings()
        self._asset_codes = [h.code for h in self._holdings]
        self._risk_config = build_risk_config(strategy_config)
        self._last_regime: Optional[str] = None
        self._regime_counts: Dict[str, int] = {}
        self._regime_history: List[Dict[str, Any]] = []

    @property
    def regime_history(self) -> List[Dict[str, Any]]:
        return self._regime_history

    @property
    def regime_counts(self) -> Dict[str, int]:
        return dict(self._regime_counts)

    def generate_signals(self, price_matrix: pd.DataFrame) -> pd.DataFrame:
        warmup = max(int(self._cfg.strategy.get("warmup_days", 60)), 200)
        prices = price_matrix.apply(pd.to_numeric, errors="coerce").ffill().dropna(how="all")

        weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        total_bars = 0
        error_count = 0
        for idx in range(warmup, len(prices)):
            window = prices.iloc[: idx + 1]
            timestamp = prices.index[idx]
            total_bars += 1
            try:
                bar_weights, regime_label = self._compute_bar(window, timestamp)
            except Exception as exc:
                error_count += 1
                logger.warning("bar at %s failed (%s); using zero weights", timestamp, exc)
                continue
            for code, w in bar_weights.items():
                if code in weights.columns:
                    weights.iat[idx, weights.columns.get_loc(code)] = float(w)
            self._regime_counts[regime_label] = self._regime_counts.get(regime_label, 0) + 1

        if total_bars > 0:
            error_rate = error_count / total_bars
            if error_rate > self._max_error_rate:
                raise RuntimeError(
                    f"Per-bar failure rate {error_rate:.1%} exceeds threshold "
                    f"{self._max_error_rate:.1%} ({error_count}/{total_bars} bars "
                    f"failed); check input data integrity"
                )
            success = total_bars - error_count
            logger.info(
                "Backtest completed: %d/%d bars succeeded (%.1f%% success)",
                success, total_bars, (success / total_bars) * 100.0,
            )

        if self._lag_days > 0:
            weights = weights.shift(self._lag_days).fillna(0.0)
        return weights

    # -----------------------------------------------------------------------
    # Per-bar mechanics — mirrors EtfRotationService._build_plan
    # -----------------------------------------------------------------------

    def _compute_bar(
        self, window: pd.DataFrame, timestamp: pd.Timestamp,
    ) -> tuple[Dict[str, float], str]:
        regime_label = "unknown"
        active_cfg = self._cfg

        # 1. Regime classification (only when mode != trend)
        if self._mode in {"regime", "ensemble"}:
            decision = self._classify(window)
            if decision is not None:
                regime_label = decision.regime
                self._regime_history.append({
                    "timestamp": timestamp.isoformat(),
                    "regime": decision.regime,
                    "gross_cap_multiplier": decision.gross_cap_multiplier,
                })
                # Apply gross_cap + min_score offset + scoring overrides
                base_strategy = dict(active_cfg.strategy)
                base_strategy["gross_cap"] = max(0.05, min(
                    1.0,
                    float(base_strategy.get("gross_cap", 0.90)) * decision.gross_cap_multiplier,
                ))
                base_strategy["min_score_to_hold"] = (
                    float(base_strategy.get("min_score_to_hold", 25.0))
                    + decision.min_score_to_hold_offset
                )
                base_strategy["min_score_full_hold"] = max(
                    base_strategy["min_score_to_hold"] + 1.0,
                    float(base_strategy.get("min_score_full_hold", 35.0))
                    + decision.min_score_to_hold_offset,
                )
                scoring_overrides = (
                    self._cfg.regime.get("scoring_overrides") or {}
                ).get(decision.regime) or {}
                base_scoring = dict(active_cfg.scoring)
                base_scoring.update(scoring_overrides)
                active_cfg = dc_replace(active_cfg, strategy=base_strategy, scoring=base_scoring)

        # 2. Build trend strategy from the (possibly regime-adjusted) config
        trend_strategy = EtfRotationStrategy(
            build_strategy_config(self._holdings, active_cfg)
        )

        # 3. Build the ensemble if mode == ensemble + ensemble enabled
        ensemble_cfg = active_cfg.ensemble or {}
        if self._mode == "ensemble" and ensemble_cfg.get("enabled", False):
            mr_raw = ensemble_cfg.get("mean_reversion") or {}
            mr_fields = {
                f.name for f in EtfMeanReversionConfig.__dataclass_fields__.values()  # type: ignore[attr-defined]
            }
            mr_kwargs = {k: v for k, v in mr_raw.items() if k in mr_fields}
            mr_scoring = EtfMeanReversionConfig(**mr_kwargs)
            mr_cfg = EtfMeanReversionRotationConfig(
                assets=list(trend_strategy.config.assets),
                gross_cap=float(trend_strategy.config.gross_cap),
                warmup_days=int(trend_strategy.config.warmup_days),
                scoring=mr_scoring,
                min_score_to_hold=float(mr_raw.get("min_score_to_hold", 25.0)),
                min_score_full_hold=float(mr_raw.get("min_score_full_hold", 40.0)),
            )
            mr_strategy = EtfMeanReversionStrategy(mr_cfg)
            blend = EtfStrategyBlend(
                trend_strategy=trend_strategy,
                mr_strategy=mr_strategy,
                config=EtfStrategyBlendConfig(
                    enabled=True,
                    regime_blend_weights=dict(
                        ensemble_cfg.get("regime_blend_weights") or {}
                    ),
                    alpha_floor=float(ensemble_cfg.get("alpha_floor", 0.20)),
                    alpha_ceiling=float(ensemble_cfg.get("alpha_ceiling", 1.00)),
                ),
                regime=regime_label,
            )
            strategy = blend
        else:
            strategy = trend_strategy

        # 4. Evaluate strategy
        signals = strategy.evaluate(window)
        target_weights: Dict[str, float] = {
            sig.symbol: float(sig.target_weight) for sig in signals
        }
        for code in self._asset_codes:
            target_weights.setdefault(code, 0.0)

        # 5. Portfolio risk rules
        if self._apply_risk_rules:
            decision = apply_etf_portfolio_risk_rules(
                proposed_weights=target_weights,
                current_weights={},  # backtester doesn't have a current snapshot here
                asset_metadata=active_cfg.asset_metadata(),
                config=self._risk_config,
            )
            adjusted = {
                k: v for k, v in decision.adjusted_weights.items() if k != "CASH"
            }
            return adjusted, regime_label
        return target_weights, regime_label

    def _classify(self, window: pd.DataFrame):
        regime_cfg = self._cfg.regime
        if not regime_cfg or not regime_cfg.get("enabled", True):
            return None
        detector_cfg = build_detector_config(regime_cfg)
        if detector_cfg.proxy_code not in window.columns:
            return None
        decision = classify_regime(
            window[detector_cfg.proxy_code],
            config=detector_cfg,
            previous_regime=self._last_regime,
        )
        self._last_regime = decision.regime
        return decision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_price_matrix(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index)
    return frame.apply(pd.to_numeric, errors="coerce").ffill().dropna(how="all")


def run_backtest(
    prices_csv: str | Path,
    *,
    mode: str = "ensemble",
    initial_capital: float = 100_000.0,
    commission: float = 0.001,
    slippage: float = 0.001,
    min_rebalance_weight_delta: float = DEFAULT_REBALANCE_THRESHOLD,
    strategy_config: Optional[StrategyConfig] = None,
    max_error_rate: float = DEFAULT_MAX_ERROR_RATE,
) -> Dict[str, Any]:
    prices = load_price_matrix(prices_csv)
    strat_cfg = strategy_config or load_strategy_config()
    strategy = FullPipelineStrategy(
        strategy_config=strat_cfg, mode=mode, lag_days=1,
        max_error_rate=max_error_rate,
    )

    backtester = PortfolioBacktester(
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        allow_fractional_shares=False,
        max_gross_exposure=0.95,
        min_rebalance_weight_delta=min_rebalance_weight_delta,
    )
    result = backtester.run(strategy, prices)
    if not result:
        return {}
    summary = {
        "mode": mode,
        "initial_capital": result["initial_capital"],
        "final_value": result["final_value"],
        "total_return": result["total_return"],
        "annualized_return": result.get("annualized_return"),
        "max_drawdown": result.get("max_drawdown"),
        "sharpe_ratio": result.get("sharpe_ratio"),
        "num_trades": result["num_trades"],
        "execution_costs": result.get("execution_costs"),
        "regime_breakdown": strategy.regime_counts,
    }
    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Full-pipeline ETF rotation backtest (regime + ensemble + risk rules).",
    )
    parser.add_argument("--prices-csv", required=True)
    parser.add_argument(
        "--mode",
        choices=("trend", "regime", "ensemble"),
        default="ensemble",
        help="Which pipeline layers to enable.",
    )
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--commission", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.001)
    parser.add_argument(
        "--min-rebalance-weight-delta",
        type=float,
        default=DEFAULT_REBALANCE_THRESHOLD,
    )
    parser.add_argument(
        "--max-error-rate",
        type=float,
        default=DEFAULT_MAX_ERROR_RATE,
        help=(
            "Maximum tolerated per-bar failure rate during the historical "
            "walk (default: %(default)s). Above this fraction we raise — "
            "that pattern usually means broken input data, not transient "
            "edge cases. Set to 1.0 to disable the guard."
        ),
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_arg_parser().parse_args(argv)
    result = run_backtest(
        args.prices_csv,
        mode=args.mode,
        initial_capital=args.initial_capital,
        commission=args.commission,
        slippage=args.slippage,
        min_rebalance_weight_delta=args.min_rebalance_weight_delta,
        max_error_rate=args.max_error_rate,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
