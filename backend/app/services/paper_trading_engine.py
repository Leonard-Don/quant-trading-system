"""Paper trading matching engine (Q1/Q2 slice).

A thin orchestrator on top of :class:`PaperTradingStore`. It consumes a
market price tick for a single symbol and:

- fills any pending LIMIT order for that symbol whose price condition is
  met (BUY when market <= limit, SELL when market >= limit), and
- auto-closes any open position for that symbol whose stop-loss or
  take-profit trigger has been reached.

The engine reuses the store's existing ledger semantics — cash,
positions, orders history, pending_orders — by reaching into the
store's atomic apply primitive. That keeps a single source of truth
for cash math and persistence and avoids any divergence between the
manual ``submit_order`` path and the automated tick path.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.app.services.paper_trading import (
    MAX_PAPER_ORDERS,
    PaperTradingError,
    PaperTradingStore,
    _normalize_symbol,
    _utc_now,
    paper_trading_store,
)

logger = logging.getLogger(__name__)

# Tolerance for SL/TP comparisons. ``stop_loss_price`` and
# ``take_profit_price`` are computed as ``avg_cost * (1 ± pct)`` and lose
# precision in IEEE 754: e.g. ``100 * (1 + 0.10) == 110.00000000000001``.
# Without this slack a tick at the user-intended target wouldn't fire.
_TRIGGER_EPSILON = 1e-9


class PaperTradingEngine:
    """Process market price ticks into pending-order fills and SL/TP closes."""

    def __init__(self, store: PaperTradingStore):
        self._store = store

    def on_market_tick(
        self,
        symbol: str,
        market_price: float,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Process a single ``(symbol, market_price)`` tick for one profile.

        Returns a dict with three keys:
            * ``filled_orders`` — LIMIT fills that fired this tick.
            * ``closed_positions`` — SL/TP auto-closes that fired.
            * ``account`` — the account public view after processing.
        """
        normalized_symbol = _normalize_symbol(symbol)
        price = float(market_price)

        # The store's RLock is reentrant — safe to hold across multiple
        # internal calls and across both phases of the tick.
        with self._store._lock:
            account = self._store._load(profile_id)

            filled_orders = self._fill_pending_limits(account, normalized_symbol, price)
            closed_positions = self._auto_close_positions(account, normalized_symbol, price)

            if filled_orders or closed_positions:
                account["updated_at"] = _utc_now()
                self._store._persist(profile_id, account)

            return {
                "filled_orders": filled_orders,
                "closed_positions": closed_positions,
                "account": self._store._public_view(profile_id, account),
            }

    # ------------------------------------------------------------------
    # Phase 1 — fill pending LIMITs
    # ------------------------------------------------------------------

    def _fill_pending_limits(
        self,
        account: dict[str, Any],
        symbol: str,
        market_price: float,
    ) -> list[dict[str, Any]]:
        pending = list(account.get("pending_orders") or [])
        remaining: list[dict[str, Any]] = []
        filled: list[dict[str, Any]] = []

        for order in pending:
            if _normalize_symbol(order.get("symbol", "")) != symbol:
                remaining.append(order)
                continue

            try:
                limit_price = float(order.get("limit_price"))
            except (TypeError, ValueError):
                # Malformed pending entry — drop without filling.
                logger.warning("Skipping pending order with bad limit_price: %s", order)
                continue

            side = str(order.get("side", "")).upper()
            should_fill = (side == "BUY" and market_price <= limit_price) or (
                side == "SELL" and market_price >= limit_price
            )
            if not should_fill:
                remaining.append(order)
                continue

            try:
                fill_record = self._store._apply_order(
                    account,
                    {
                        "symbol": symbol,
                        "side": side,
                        "quantity": order.get("quantity"),
                        "fill_price": market_price,
                    },
                )
            except PaperTradingError as exc:
                # Insufficient cash / position at fill time — keep pending.
                logger.warning(
                    "Auto-fill rejected for %s (%s %s): %s",
                    order.get("id"),
                    side,
                    symbol,
                    exc,
                )
                remaining.append(order)
                continue

            fill_record["order_type"] = "LIMIT"
            fill_record["limit_price"] = limit_price
            fill_record["pending_id"] = order.get("id")
            self._append_order(account, fill_record)
            filled.append(fill_record)

        account["pending_orders"] = remaining
        return filled

    # ------------------------------------------------------------------
    # Phase 2 — auto-close on SL/TP
    # ------------------------------------------------------------------

    def _auto_close_positions(
        self,
        account: dict[str, Any],
        symbol: str,
        market_price: float,
    ) -> list[dict[str, Any]]:
        positions: dict[str, dict[str, Any]] = account.get("positions") or {}
        position = positions.get(symbol)
        if not position:
            return []

        reason = self._trigger_reason(position, market_price)
        if reason is None:
            return []

        quantity = float(position.get("quantity") or 0)
        if quantity <= 0:
            return []

        try:
            fill_record = self._store._apply_order(
                account,
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "quantity": quantity,
                    "fill_price": market_price,
                },
            )
        except PaperTradingError as exc:
            logger.warning("Auto-close failed for %s: %s", symbol, exc)
            return []

        fill_record["order_type"] = "MARKET"
        fill_record["close_reason"] = reason
        self._append_order(account, fill_record)

        return [
            {
                "symbol": symbol,
                "quantity": quantity,
                "fill_price": market_price,
                "reason": reason,
                "order_id": fill_record.get("id"),
            }
        ]

    @staticmethod
    def _trigger_reason(position: dict[str, Any], market_price: float) -> str | None:
        stop_loss_price = position.get("stop_loss_price")
        if (
            stop_loss_price is not None
            and market_price <= float(stop_loss_price) + _TRIGGER_EPSILON
        ):
            return "stop_loss"
        take_profit_price = position.get("take_profit_price")
        if (
            take_profit_price is not None
            and market_price >= float(take_profit_price) - _TRIGGER_EPSILON
        ):
            return "take_profit"
        return None

    @staticmethod
    def _append_order(account: dict[str, Any], record: dict[str, Any]) -> None:
        orders = account.get("orders") or []
        orders = orders[-MAX_PAPER_ORDERS + 1 :]
        orders.append(record)
        account["orders"] = orders


paper_trading_engine = PaperTradingEngine(store=paper_trading_store)
