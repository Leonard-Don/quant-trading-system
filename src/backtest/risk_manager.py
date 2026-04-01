"""
Risk Management Module

Provides a composable, strategy-agnostic risk management layer that can be
integrated with any backtester.  The RiskManager evaluates entry/exit
conditions based on configurable risk rules, independent of the trading
signal logic.

Usage:
    risk_mgr = RiskManager(
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        max_drawdown_limit=0.20,
        max_daily_loss_pct=0.03,
        max_consecutive_losses=5,
    )
    # Called on every bar inside the execution loop
    action = risk_mgr.evaluate(context)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class RiskAction(Enum):
    """Action recommended by the RiskManager."""
    NONE = "none"                   # No risk rule triggered
    FORCE_EXIT = "force_exit"       # Exit the current position immediately
    BLOCK_ENTRY = "block_entry"     # Prevent opening a new position
    REDUCE_SIZE = "reduce_size"     # Scale down position size


@dataclass
class RiskContext:
    """Snapshot of the current state supplied to the RiskManager on each bar.

    All fields use simple Python types so the caller does not need to depend
    on specific data structures.
    """
    # Current bar info
    bar_index: int = 0
    current_price: float = 0.0
    current_date: Any = None

    # Position state
    position_size: float = 0.0        # number of shares (0 = flat)
    entry_price: float = 0.0          # average entry price
    entry_date: Any = None

    # Portfolio state
    current_equity: float = 0.0       # total portfolio value
    peak_equity: float = 0.0          # high-water mark
    initial_capital: float = 0.0
    daily_return: float = 0.0         # return of the current bar

    # Trade history (recent)
    recent_trade_pnls: List[float] = field(default_factory=list)


@dataclass
class RiskDecision:
    """The output of a RiskManager evaluation."""
    action: RiskAction = RiskAction.NONE
    reason: str = ""
    scale_factor: float = 1.0         # Only used when action == REDUCE_SIZE
    triggered_rules: List[str] = field(default_factory=list)


class RiskManager:
    """Composable risk management engine.

    Each risk rule is evaluated independently.  The *most restrictive*
    action wins (FORCE_EXIT > BLOCK_ENTRY > REDUCE_SIZE > NONE).
    """

    # Priority: higher number = more restrictive
    _ACTION_PRIORITY = {
        RiskAction.NONE: 0,
        RiskAction.REDUCE_SIZE: 1,
        RiskAction.BLOCK_ENTRY: 2,
        RiskAction.FORCE_EXIT: 3,
    }

    def __init__(
        self,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        max_drawdown_limit: Optional[float] = None,
        max_daily_loss_pct: Optional[float] = None,
        max_consecutive_losses: Optional[int] = None,
        max_holding_days: Optional[int] = None,
        volatility_scaling: bool = False,
        volatility_target: float = 0.15,
        volatility_lookback: int = 20,
    ):
        """
        Args:
            stop_loss_pct: Fixed stop-loss (e.g. 0.05 = exit on 5% loss).
            take_profit_pct: Fixed take-profit (e.g. 0.10 = exit on 10% gain).
            trailing_stop_pct: Trailing stop distance from peak unrealized gain.
            max_drawdown_limit: Portfolio-level max drawdown limit (e.g. 0.20).
                                Blocks new entries when breached.
            max_daily_loss_pct: Max single-day portfolio loss (e.g. 0.03).
                                Forces exit if breached.
            max_consecutive_losses: Block new entries after N consecutive losing trades.
            max_holding_days: Force-exit positions held for too many calendar days.
            volatility_scaling: If True, recommend position size scaling
                                based on realized volatility.
            volatility_target: Annualized volatility target for scaling.
            volatility_lookback: Lookback window for realized volatility.
        """
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.max_drawdown_limit = max_drawdown_limit
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.max_holding_days = max_holding_days
        self.volatility_scaling = volatility_scaling
        self.volatility_target = volatility_target
        self.volatility_lookback = volatility_lookback

        # Internal tracking
        self._peak_unrealized: float = 0.0  # highest unrealized gain since entry
        self._daily_returns: List[float] = []

    def reset(self) -> None:
        """Reset internal state between backtests."""
        self._peak_unrealized = 0.0
        self._daily_returns = []

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        """Evaluate all risk rules and return the most restrictive decision."""
        decisions: List[RiskDecision] = []

        # Track daily return for volatility scaling
        self._daily_returns.append(ctx.daily_return)

        # ---- Position-level rules (only apply when holding a position) ----
        if ctx.position_size != 0 and ctx.entry_price > 0:
            unrealized_return = (ctx.current_price - ctx.entry_price) / ctx.entry_price

            # Stop-loss
            if self.stop_loss_pct is not None and unrealized_return <= -self.stop_loss_pct:
                decisions.append(RiskDecision(
                    action=RiskAction.FORCE_EXIT,
                    reason=f"止损触发: 未实现收益 {unrealized_return:.2%} <= -{self.stop_loss_pct:.2%}",
                    triggered_rules=["stop_loss"],
                ))

            # Take-profit
            if self.take_profit_pct is not None and unrealized_return >= self.take_profit_pct:
                decisions.append(RiskDecision(
                    action=RiskAction.FORCE_EXIT,
                    reason=f"止盈触发: 未实现收益 {unrealized_return:.2%} >= {self.take_profit_pct:.2%}",
                    triggered_rules=["take_profit"],
                ))

            # Trailing stop
            if self.trailing_stop_pct is not None:
                self._peak_unrealized = max(self._peak_unrealized, unrealized_return)
                drawdown_from_peak = self._peak_unrealized - unrealized_return
                if self._peak_unrealized > 0 and drawdown_from_peak >= self.trailing_stop_pct:
                    decisions.append(RiskDecision(
                        action=RiskAction.FORCE_EXIT,
                        reason=(
                            f"移动止损触发: 峰值收益 {self._peak_unrealized:.2%}, "
                            f"当前 {unrealized_return:.2%}, "
                            f"回撤 {drawdown_from_peak:.2%} >= {self.trailing_stop_pct:.2%}"
                        ),
                        triggered_rules=["trailing_stop"],
                    ))

            # Time stop
            holding_days = self._calculate_holding_days(ctx.entry_date, ctx.current_date)
            if (
                self.max_holding_days is not None
                and holding_days is not None
                and holding_days >= self.max_holding_days
            ):
                decisions.append(RiskDecision(
                    action=RiskAction.FORCE_EXIT,
                    reason=(
                        f"时间止损触发: 持仓 {holding_days} 天 "
                        f">= {self.max_holding_days} 天"
                    ),
                    triggered_rules=["max_holding_days"],
                ))

        else:
            # Reset trailing stop state when flat
            self._peak_unrealized = 0.0

        # ---- Portfolio-level rules ----

        # Max drawdown limit
        if self.max_drawdown_limit is not None and ctx.peak_equity > 0:
            portfolio_drawdown = (ctx.peak_equity - ctx.current_equity) / ctx.peak_equity
            if portfolio_drawdown >= self.max_drawdown_limit:
                decisions.append(RiskDecision(
                    action=RiskAction.BLOCK_ENTRY,
                    reason=(
                        f"最大回撤限制: 组合回撤 {portfolio_drawdown:.2%} "
                        f">= {self.max_drawdown_limit:.2%}"
                    ),
                    triggered_rules=["max_drawdown_limit"],
                ))

        # Max daily loss
        if self.max_daily_loss_pct is not None and ctx.daily_return <= -self.max_daily_loss_pct:
            decisions.append(RiskDecision(
                action=RiskAction.FORCE_EXIT,
                reason=(
                    f"单日最大亏损: 日收益 {ctx.daily_return:.2%} "
                    f"<= -{self.max_daily_loss_pct:.2%}"
                ),
                triggered_rules=["max_daily_loss"],
            ))

        # Max consecutive losses
        if self.max_consecutive_losses is not None and ctx.recent_trade_pnls:
            consecutive = self._count_consecutive_losses(ctx.recent_trade_pnls)
            if consecutive >= self.max_consecutive_losses:
                decisions.append(RiskDecision(
                    action=RiskAction.BLOCK_ENTRY,
                    reason=(
                        f"连续亏损限制: {consecutive} 次连续亏损 "
                        f">= {self.max_consecutive_losses}"
                    ),
                    triggered_rules=["max_consecutive_losses"],
                ))

        # Volatility scaling (advisory — sets scale_factor)
        if self.volatility_scaling and len(self._daily_returns) >= self.volatility_lookback:
            scale = self._calculate_vol_scale()
            if scale < 1.0:
                decisions.append(RiskDecision(
                    action=RiskAction.REDUCE_SIZE,
                    reason=f"波动率缩放: 建议仓位比例 {scale:.2%}",
                    scale_factor=scale,
                    triggered_rules=["volatility_scaling"],
                ))

        # Merge decisions — most restrictive wins
        if not decisions:
            return RiskDecision()

        merged = self._merge_decisions(decisions)
        for d in decisions:
            logger.debug("Risk rule: %s → %s (%s)", d.triggered_rules, d.action.value, d.reason)
        return merged

    def get_position_scale(self) -> float:
        """Return the volatility-based position scale factor (1.0 if disabled)."""
        if not self.volatility_scaling or len(self._daily_returns) < self.volatility_lookback:
            return 1.0
        return self._calculate_vol_scale()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _calculate_vol_scale(self) -> float:
        """Calculate position scale based on recent realized volatility."""
        recent = np.array(self._daily_returns[-self.volatility_lookback:])
        realized_vol = float(np.std(recent, ddof=1)) * np.sqrt(252)
        if realized_vol <= 0:
            return 1.0
        scale = self.volatility_target / realized_vol
        return float(np.clip(scale, 0.1, 2.0))

    @staticmethod
    def _calculate_holding_days(entry_date: Any, current_date: Any) -> Optional[int]:
        if entry_date is None or current_date is None:
            return None
        try:
            if hasattr(current_date, "to_pydatetime"):
                current_date = current_date.to_pydatetime()
            if hasattr(entry_date, "to_pydatetime"):
                entry_date = entry_date.to_pydatetime()
            if isinstance(current_date, datetime) and isinstance(entry_date, datetime):
                return max((current_date - entry_date).days, 0)
            delta = current_date - entry_date
            if hasattr(delta, "days"):
                return max(int(delta.days), 0)
            return max(int(delta / np.timedelta64(1, "D")), 0)
        except Exception:
            return None

    @staticmethod
    def _count_consecutive_losses(pnls: List[float]) -> int:
        """Count consecutive losses from the end of the PnL list."""
        count = 0
        for pnl in reversed(pnls):
            if pnl < 0:
                count += 1
            else:
                break
        return count

    def _merge_decisions(self, decisions: List[RiskDecision]) -> RiskDecision:
        """Return the most restrictive decision, combining triggered rules."""
        best = max(decisions, key=lambda d: self._ACTION_PRIORITY[d.action])
        all_rules = []
        all_reasons = []
        min_scale = 1.0
        for d in decisions:
            all_rules.extend(d.triggered_rules)
            all_reasons.append(d.reason)
            if d.scale_factor < min_scale:
                min_scale = d.scale_factor

        return RiskDecision(
            action=best.action,
            reason=" | ".join(all_reasons),
            scale_factor=min_scale,
            triggered_rules=all_rules,
        )

    def summary(self) -> Dict[str, Any]:
        """Return a dictionary describing the active risk rules."""
        rules = {}
        if self.stop_loss_pct is not None:
            rules["stop_loss_pct"] = self.stop_loss_pct
        if self.take_profit_pct is not None:
            rules["take_profit_pct"] = self.take_profit_pct
        if self.trailing_stop_pct is not None:
            rules["trailing_stop_pct"] = self.trailing_stop_pct
        if self.max_drawdown_limit is not None:
            rules["max_drawdown_limit"] = self.max_drawdown_limit
        if self.max_daily_loss_pct is not None:
            rules["max_daily_loss_pct"] = self.max_daily_loss_pct
        if self.max_consecutive_losses is not None:
            rules["max_consecutive_losses"] = self.max_consecutive_losses
        if self.max_holding_days is not None:
            rules["max_holding_days"] = self.max_holding_days
        if self.volatility_scaling:
            rules["volatility_scaling"] = True
            rules["volatility_target"] = self.volatility_target
            rules["volatility_lookback"] = self.volatility_lookback
        return {
            "active_rule_count": len(rules),
            "rules": rules,
        }
