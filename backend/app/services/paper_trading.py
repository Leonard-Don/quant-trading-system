"""Paper trading account persistence (v0).

Per-profile JSON ledger: cash, positions, and order history. Order rules
are deliberately simple — orders fill immediately at the user-supplied
``fill_price``, no bid/ask simulation, no shorting, no leverage. The
matching engine and strategy automation belong to a follow-up batch.

Persistence pattern mirrors ``research_journal.ResearchJournalStore``:
file-per-profile under ``data/paper_trading/``, ``threading.RLock`` for
intra-process consistency.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_INITIAL_CAPITAL = 10000.0
MAX_PAPER_ORDERS = 500


class PaperTradingError(ValueError):
    """Business-rule rejection (insufficient cash, oversell, etc.)."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _normalize_side(side: str) -> str:
    side_norm = str(side or "").strip().upper()
    if side_norm not in {"BUY", "SELL"}:
        raise PaperTradingError(f"invalid side: {side!r}")
    return side_norm


def _parse_optional_pct(
    request: dict[str, Any], field_name: str, upper: float
) -> float | None:
    raw = request.get(field_name)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise PaperTradingError(f"{field_name} must be a number") from exc
    if value < 0 or value > upper:
        raise PaperTradingError(f"{field_name} must be in [0, {upper}]")
    return value


def _without_pending_sell_exits(
    orders: list[dict[str, Any]], target_symbol: str
) -> list[dict[str, Any]]:
    """Drop pending SELL orders for ``target_symbol`` — used after a position
    fully closes to prevent stale exits from remaining armed."""
    return [
        order
        for order in orders
        if not (
            _normalize_symbol(order.get("symbol", "")) == target_symbol
            and str(order.get("side") or "").upper() == "SELL"
        )
    ]


def _default_account(initial_capital: float | None = None) -> dict[str, Any]:
    capital = float(initial_capital or DEFAULT_INITIAL_CAPITAL)
    now = _utc_now()
    return {
        "initial_capital": capital,
        "cash": capital,
        "positions": {},
        "orders": [],
        "pending_orders": [],
        "created_at": now,
        "updated_at": now,
    }


class PaperTradingStore:
    """File-backed paper trading store keyed by profile id."""

    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = PROJECT_ROOT / "data" / "paper_trading"
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Profile + I/O helpers
    # ------------------------------------------------------------------

    def _normalize_profile_id(self, profile_id: str | None) -> str:
        raw = str(profile_id or "default").strip().lower()
        sanitized = "".join(
            character if character.isalnum() or character in {"-", "_"} else "-"
            for character in raw
        ).strip("-_")
        return sanitized or "default"

    def _file_for(self, profile_id: str | None) -> Path:
        return self.storage_path / f"{self._normalize_profile_id(profile_id)}.json"

    def _load(self, profile_id: str | None) -> dict[str, Any]:
        path = self._file_for(profile_id)
        if path.exists():
            try:
                with open(path, encoding="utf-8") as file:
                    raw = json.load(file)
                if isinstance(raw, dict):
                    return self._coerce_account(raw)
            except Exception as exc:
                logger.warning("Failed to load paper account %s: %s", profile_id, exc)
        return _default_account()

    def _persist(self, profile_id: str | None, payload: dict[str, Any]) -> None:
        path = self._file_for(profile_id)
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to persist paper account %s: %s", profile_id, exc)

    @staticmethod
    def _coerce_account(raw: dict[str, Any]) -> dict[str, Any]:
        """Defensive: accept partially-valid persisted blobs."""
        defaults = _default_account()
        merged = {**defaults, **raw}
        # positions dict[str, dict]
        positions = raw.get("positions")
        if not isinstance(positions, dict):
            positions = {}
        merged["positions"] = {
            _normalize_symbol(symbol): dict(payload)
            for symbol, payload in positions.items()
            if isinstance(payload, dict) and _normalize_symbol(symbol)
        }
        orders = raw.get("orders")
        if not isinstance(orders, list):
            orders = []
        merged["orders"] = [order for order in orders if isinstance(order, dict)]
        # pending_orders new in C5 — older account files won't carry it
        pending = raw.get("pending_orders")
        if not isinstance(pending, list):
            pending = []
        merged["pending_orders"] = [order for order in pending if isinstance(order, dict)]
        merged["initial_capital"] = float(raw.get("initial_capital") or defaults["initial_capital"])
        merged["cash"] = float(raw.get("cash") or 0.0)
        return merged

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_account(self, profile_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            account = self._load(profile_id)
            return self._public_view(profile_id, account)

    def list_orders(self, profile_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            account = self._load(profile_id)
        orders = list(account.get("orders") or [])
        orders.sort(key=lambda order: order.get("submitted_at") or "", reverse=True)
        return orders[: max(0, limit)]

    def reset(
        self,
        initial_capital: float | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            account = _default_account(initial_capital)
            self._persist(profile_id, account)
            return self._public_view(profile_id, account)

    def submit_order(
        self,
        order_request: dict[str, Any],
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        order_type = str(order_request.get("order_type") or "MARKET").upper()
        canceled_orders: list[dict[str, Any]] = []
        with self._lock:
            account = self._load(profile_id)
            if order_type == "LIMIT":
                order = self._queue_limit_order(account, order_request)
                account["updated_at"] = _utc_now()
                self._persist(profile_id, account)
                return {
                    "order": order,
                    "account": self._public_view(profile_id, account),
                    "canceled": canceled_orders,
                }
            # MARKET — default behavior, fills immediately
            order = self._apply_order(account, order_request)
            if (
                order["side"] == "SELL"
                and order["symbol"] not in (account.get("positions") or {})
            ):
                prior_pending = list(account.get("pending_orders") or [])
                # Record each pruned stale SELL exit so the manual close is
                # observable to audit consumers, mirroring the SL/TP audit
                # shape — the manual SELL closed the position, the pending
                # exits could no longer be backed by shares, and a silent
                # drop would hide that causal link. `closing_order_id` ties
                # the cancel back to the specific fill that did the closing,
                # so a journal reader can resolve cause -> effect from the
                # persisted history alone.
                canceled_at = _utc_now()
                canceled_pending_ids: list[str] = []
                for pending_order in prior_pending:
                    if (
                        _normalize_symbol(pending_order.get("symbol", ""))
                        == order["symbol"]
                        and str(pending_order.get("side") or "").upper() == "SELL"
                    ):
                        pending_id = pending_order.get("id")
                        canceled_orders.append(
                            {
                                "pending_order_id": pending_id,
                                "symbol": order["symbol"],
                                "side": "SELL",
                                "reason": "manual_sell",
                                "canceled_at": canceled_at,
                                "closing_order_id": order["id"],
                            }
                        )
                        canceled_pending_ids.append(pending_id)
                if canceled_pending_ids:
                    # Symmetric link to `closing_order_id` on the canceled
                    # audit: the closing fill itself records the pending ids
                    # it pruned, so a journal reader walking persisted
                    # `orders` history alone can resolve closing fill →
                    # canceled pending ids without the response envelope.
                    order["canceled_pending_order_ids"] = canceled_pending_ids
                account["pending_orders"] = _without_pending_sell_exits(
                    prior_pending, order["symbol"]
                )
            account["updated_at"] = _utc_now()
            account["orders"] = (account.get("orders") or [])[-MAX_PAPER_ORDERS + 1 :]
            account["orders"].append(order)
            self._persist(profile_id, account)
            return {
                "order": order,
                "account": self._public_view(profile_id, account),
                "canceled": canceled_orders,
            }

    def run_matching(
        self,
        quotes: dict[str, float] | None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply quote-driven matching: fill pending LIMITs that have crossed
        and trigger SL/TP exits on positions whose threshold has been hit.

        ``quotes`` maps symbol → current price. Symbol lookup is case-insensitive.
        Returns ``{filled, triggered, rejected, account}``. When no quote is
        supplied for a symbol, anything tied to that symbol is left alone.
        """
        normalized_quotes: dict[str, float] = {}
        for symbol, price in (quotes or {}).items():
            symbol_norm = _normalize_symbol(symbol)
            if not symbol_norm:
                continue
            try:
                normalized_quotes[symbol_norm] = float(price)
            except (TypeError, ValueError):
                continue

        filled_orders: list[dict[str, Any]] = []
        triggered_orders: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        canceled_orders: list[dict[str, Any]] = []

        with self._lock:
            account = self._load(profile_id)
            history: list[dict[str, Any]] = account.setdefault("orders", [])
            pending: list[dict[str, Any]] = list(account.get("pending_orders") or [])
            remaining_pending: list[dict[str, Any]] = []
            # symbol -> {"at": canceled_at iso, "id": closing fill id, "fill":
            # closing fill order ref} of the LIMIT cross that closed it.
            # Stored per-symbol so subsequent stale-exit audits in the same
            # iteration share the closing event's timestamp, link back to the
            # closing order id, and append onto the SAME closing fill's
            # `canceled_pending_order_ids` list (durable reverse-direction
            # walk: closing fill -> canceled pending ids).
            closed_exit_symbols: dict[str, dict[str, Any]] = {}

            # Step 1: LIMIT auto-fill — process pending orders against quotes.
            for pending_order in pending:
                symbol = _normalize_symbol(pending_order.get("symbol", ""))
                side = str(pending_order.get("side") or "").upper()
                if side == "SELL" and symbol in closed_exit_symbols:
                    # Stale SELL exit ordered AFTER the closing fill in
                    # `pending`; the position no longer backs it. Audit
                    # the implicit cancel under the same shape as Step 2
                    # SL/TP pruning so the close → cancel chain stays
                    # observable to consumers.
                    closing = closed_exit_symbols[symbol]
                    pending_id = pending_order.get("id")
                    canceled_orders.append(
                        {
                            "pending_order_id": pending_id,
                            "symbol": symbol,
                            "side": "SELL",
                            "reason": "limit_cross",
                            "canceled_at": closing["at"],
                            "closing_order_id": closing["id"],
                        }
                    )
                    closing["fill"].setdefault(
                        "canceled_pending_order_ids", []
                    ).append(pending_id)
                    continue
                try:
                    limit_price = float(pending_order.get("limit_price") or 0)
                except (TypeError, ValueError):
                    limit_price = 0.0
                quote = normalized_quotes.get(symbol)
                if quote is None or limit_price <= 0:
                    remaining_pending.append(pending_order)
                    continue
                crosses = (
                    (side == "BUY" and quote <= limit_price)
                    or (side == "SELL" and quote >= limit_price)
                )
                if not crosses:
                    remaining_pending.append(pending_order)
                    continue
                fill_request: dict[str, Any] = {
                    "symbol": symbol,
                    "side": side,
                    "quantity": pending_order.get("quantity"),
                    "fill_price": limit_price,
                    "note": pending_order.get("note") or "",
                }
                # Bracket SL/TP captured at queue time must follow the order
                # into the position; _apply_order only honors them on BUY.
                if "stop_loss_pct" in pending_order:
                    fill_request["stop_loss_pct"] = pending_order["stop_loss_pct"]
                if "take_profit_pct" in pending_order:
                    fill_request["take_profit_pct"] = pending_order["take_profit_pct"]
                try:
                    order = self._apply_order(account, fill_request)
                except PaperTradingError as exc:
                    rejected.append(
                        {
                            "pending_order_id": pending_order.get("id"),
                            "symbol": symbol,
                            "reason": str(exc),
                        }
                    )
                    remaining_pending.append(pending_order)
                    continue
                order["pending_order_id"] = pending_order.get("id")
                order["trigger_reason"] = "limit_cross"
                history.append(order)
                filled_orders.append(order)
                if side == "SELL" and symbol not in (account.get("positions") or {}):
                    # Audit any stale pending SELL exits we're about to prune
                    # under the same shape as the SL/TP path: the LIMIT cross
                    # closed the position, the remaining pending SELLs can no
                    # longer be backed by shares, and a silent drop would hide
                    # that causal link.
                    canceled_at = _utc_now()
                    closed_exit_symbols[symbol] = {
                        "at": canceled_at,
                        "id": order["id"],
                        "fill": order,
                    }
                    for stale in remaining_pending:
                        if (
                            _normalize_symbol(stale.get("symbol", "")) == symbol
                            and str(stale.get("side") or "").upper() == "SELL"
                        ):
                            stale_id = stale.get("id")
                            canceled_orders.append(
                                {
                                    "pending_order_id": stale_id,
                                    "symbol": symbol,
                                    "side": "SELL",
                                    "reason": "limit_cross",
                                    "canceled_at": canceled_at,
                                    "closing_order_id": order["id"],
                                }
                            )
                            order.setdefault(
                                "canceled_pending_order_ids", []
                            ).append(stale_id)
                    remaining_pending = _without_pending_sell_exits(remaining_pending, symbol)
            account["pending_orders"] = remaining_pending

            # Step 2: SL/TP triggers — close positions whose threshold crossed.
            positions = account.get("positions") or {}
            for symbol in list(positions.keys()):
                position = positions.get(symbol)
                if not position:
                    continue
                quote = normalized_quotes.get(symbol)
                if quote is None:
                    continue
                try:
                    quantity = float(position.get("quantity") or 0)
                except (TypeError, ValueError):
                    continue
                if quantity <= 0:
                    continue
                tp_price = position.get("take_profit_price")
                sl_price = position.get("stop_loss_price")
                trigger_reason: str | None = None
                trigger_price: float | None = None
                if tp_price is not None and quote >= float(tp_price) - 1e-9:
                    trigger_reason = "take_profit"
                    trigger_price = float(tp_price)
                elif sl_price is not None and quote <= float(sl_price) + 1e-9:
                    trigger_reason = "stop_loss"
                    trigger_price = float(sl_price)
                if trigger_reason is None or trigger_price is None:
                    continue
                try:
                    order = self._apply_order(
                        account,
                        {
                            "symbol": symbol,
                            "side": "SELL",
                            "quantity": quantity,
                            "fill_price": trigger_price,
                        },
                    )
                except PaperTradingError as exc:
                    rejected.append(
                        {
                            "symbol": symbol,
                            "trigger_reason": trigger_reason,
                            "reason": str(exc),
                        }
                    )
                    continue
                order["trigger_reason"] = trigger_reason
                history.append(order)
                triggered_orders.append(order)
                prior_pending = list(account.get("pending_orders") or [])
                account["pending_orders"] = _without_pending_sell_exits(
                    prior_pending, symbol
                )
                # Record each pruned stale SELL exit so the cancellation is
                # observable to audit consumers — the bracket exit closed the
                # position, the pending exit could no longer be backed by
                # shares, and a silent drop would hide that causal link.
                # `closing_order_id` ties each cancel back to the specific
                # bracket-triggered fill that did the closing.
                canceled_at = _utc_now()
                trigger_canceled_ids: list[str] = []
                for pending_order in prior_pending:
                    if (
                        _normalize_symbol(pending_order.get("symbol", "")) == symbol
                        and str(pending_order.get("side") or "").upper() == "SELL"
                    ):
                        pending_id = pending_order.get("id")
                        canceled_orders.append(
                            {
                                "pending_order_id": pending_id,
                                "symbol": symbol,
                                "side": "SELL",
                                "reason": trigger_reason,
                                "canceled_at": canceled_at,
                                "closing_order_id": order["id"],
                            }
                        )
                        trigger_canceled_ids.append(pending_id)
                if trigger_canceled_ids:
                    # Symmetric link to `closing_order_id` on each canceled
                    # audit entry: the SL/TP fill itself records what it
                    # pruned, so persisted `orders` history alone supports
                    # closing fill -> canceled pending ids reconstruction.
                    order["canceled_pending_order_ids"] = trigger_canceled_ids

            account["orders"] = history[-MAX_PAPER_ORDERS:]

            if filled_orders or triggered_orders or rejected or canceled_orders:
                account["updated_at"] = _utc_now()
                self._persist(profile_id, account)

            return {
                "filled": filled_orders,
                "triggered": triggered_orders,
                "rejected": rejected,
                "canceled": canceled_orders,
                "account": self._public_view(profile_id, account),
            }

    def cancel_order(self, order_id: str, profile_id: str | None = None) -> dict[str, Any]:
        """Cancel a pending LIMIT order. Filled orders cannot be cancelled."""
        with self._lock:
            account = self._load(profile_id)
            pending = account.get("pending_orders") or []
            for index, candidate in enumerate(pending):
                if candidate.get("id") == order_id:
                    pending.pop(index)
                    account["pending_orders"] = pending
                    account["updated_at"] = _utc_now()
                    self._persist(profile_id, account)
                    return self._public_view(profile_id, account)
            # Not in pending — check if it's a filled order to give a useful error
            for candidate in account.get("orders") or []:
                if candidate.get("id") == order_id:
                    raise PaperTradingError(
                        f"order {order_id} already filled, cannot cancel",
                    )
            raise KeyError(order_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _apply_order(self, account: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        symbol = _normalize_symbol(request.get("symbol", ""))
        if not symbol:
            raise PaperTradingError("symbol is required")
        side = _normalize_side(str(request.get("side", "")))
        quantity = float(request.get("quantity") or 0)
        if quantity <= 0:
            raise PaperTradingError("quantity must be positive")
        fill_price = float(request.get("fill_price") or 0)
        if fill_price <= 0:
            raise PaperTradingError("fill_price must be positive")
        commission = float(request.get("commission") or 0)
        if commission < 0:
            raise PaperTradingError("commission must be non-negative")
        slippage_bps = float(request.get("slippage_bps") or 0)
        if slippage_bps < 0:
            raise PaperTradingError("slippage_bps must be non-negative")
        # stop_loss_pct / take_profit_pct only apply to BUY. SELL silently
        # ignores them so a generic client can always send the same shape.
        stop_loss_pct = _parse_optional_pct(request, "stop_loss_pct", 0.5)
        take_profit_pct = _parse_optional_pct(request, "take_profit_pct", 5.0)
        note = str(request.get("note") or "")[:200]

        # BUY pays *more* when slippage moves the market against the trader;
        # SELL receives *less*. bps = 1/10_000 of the underlying price.
        slippage_factor = slippage_bps / 10_000.0
        effective_fill_price = (
            fill_price * (1.0 + slippage_factor)
            if side == "BUY"
            else fill_price * (1.0 - slippage_factor)
        )

        positions: dict[str, dict[str, Any]] = account.setdefault("positions", {})
        cash = float(account.get("cash", 0.0))
        now = _utc_now()

        if side == "BUY":
            cost = quantity * effective_fill_price + commission
            if cost > cash + 1e-9:  # tolerance for float accumulation
                raise PaperTradingError(
                    f"insufficient cash: need {cost:.4f}, have {cash:.4f}"
                )
            existing = positions.get(symbol)
            if existing:
                old_qty = float(existing.get("quantity", 0))
                old_avg = float(existing.get("avg_cost", 0))
                new_qty = old_qty + quantity
                new_avg = (
                    (old_qty * old_avg + quantity * effective_fill_price) / new_qty
                    if new_qty > 0
                    else 0.0
                )
                existing["quantity"] = new_qty
                existing["avg_cost"] = new_avg
                existing["updated_at"] = now
                # Stop-loss / take-profit merge: new pct (if supplied) wins,
                # else keep old. Either way recompute the trigger price
                # against the new weighted avg.
                if stop_loss_pct is not None:
                    existing["stop_loss_pct"] = stop_loss_pct
                effective_sl = existing.get("stop_loss_pct")
                if effective_sl is not None:
                    existing["stop_loss_price"] = new_avg * (1.0 - float(effective_sl))

                if take_profit_pct is not None:
                    existing["take_profit_pct"] = take_profit_pct
                effective_tp = existing.get("take_profit_pct")
                if effective_tp is not None:
                    existing["take_profit_price"] = new_avg * (1.0 + float(effective_tp))
            else:
                position_payload = {
                    "symbol": symbol,
                    "quantity": quantity,
                    "avg_cost": effective_fill_price,
                    "opened_at": now,
                    "updated_at": now,
                }
                if stop_loss_pct is not None:
                    position_payload["stop_loss_pct"] = stop_loss_pct
                    position_payload["stop_loss_price"] = effective_fill_price * (1.0 - stop_loss_pct)
                if take_profit_pct is not None:
                    position_payload["take_profit_pct"] = take_profit_pct
                    position_payload["take_profit_price"] = effective_fill_price * (1.0 + take_profit_pct)
                positions[symbol] = position_payload
            account["cash"] = cash - cost
        else:  # SELL
            existing = positions.get(symbol)
            if not existing or float(existing.get("quantity", 0)) < quantity - 1e-9:
                have = float(existing.get("quantity", 0)) if existing else 0.0
                raise PaperTradingError(
                    f"insufficient position for {symbol}: need {quantity}, have {have}"
                )
            proceeds = quantity * effective_fill_price - commission
            new_qty = float(existing.get("quantity", 0)) - quantity
            if new_qty <= 1e-9:
                positions.pop(symbol, None)
            else:
                existing["quantity"] = new_qty
                existing["updated_at"] = now
            account["cash"] = cash + proceeds

        return {
            "id": f"ord-{uuid.uuid4().hex[:12]}",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "fill_price": fill_price,
            "effective_fill_price": effective_fill_price,
            "slippage_bps": slippage_bps,
            "commission": commission,
            "submitted_at": now,
            "note": note,
        }

    def _queue_limit_order(self, account: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        """Add a LIMIT order to the pending list without touching cash or positions."""
        symbol = _normalize_symbol(request.get("symbol", ""))
        if not symbol:
            raise PaperTradingError("symbol is required")
        side = _normalize_side(str(request.get("side", "")))
        quantity = float(request.get("quantity") or 0)
        if quantity <= 0:
            raise PaperTradingError("quantity must be positive")
        raw_limit = request.get("limit_price")
        if raw_limit is None:
            raise PaperTradingError("limit_price is required for LIMIT orders")
        try:
            limit_price = float(raw_limit)
        except (TypeError, ValueError) as exc:
            raise PaperTradingError("limit_price must be a number") from exc
        if limit_price <= 0:
            raise PaperTradingError("limit_price must be positive")
        note = str(request.get("note") or "")[:200]
        # Validate brackets at queue time even for SELL — same caps as MARKET —
        # so a malformed value is rejected eagerly rather than at fill time.
        stop_loss_pct = _parse_optional_pct(request, "stop_loss_pct", 0.5)
        take_profit_pct = _parse_optional_pct(request, "take_profit_pct", 5.0)

        pending = account.setdefault("pending_orders", [])
        order = {
            "id": f"ord-pending-{uuid.uuid4().hex[:10]}",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order_type": "LIMIT",
            "limit_price": limit_price,
            "submitted_at": _utc_now(),
            "note": note,
        }
        if stop_loss_pct is not None:
            order["stop_loss_pct"] = stop_loss_pct
        if take_profit_pct is not None:
            order["take_profit_pct"] = take_profit_pct
        pending.append(order)
        return order

    def _public_view(self, profile_id: str | None, account: dict[str, Any]) -> dict[str, Any]:
        positions_payload = list(account.get("positions", {}).values())
        positions_payload.sort(key=lambda position: position.get("symbol", ""))
        pending_payload = list(account.get("pending_orders") or [])
        pending_payload.sort(key=lambda order: order.get("submitted_at") or "", reverse=True)
        return {
            "profile_id": self._normalize_profile_id(profile_id),
            "initial_capital": float(account.get("initial_capital", 0.0)),
            "cash": float(account.get("cash", 0.0)),
            "positions": [deepcopy(position) for position in positions_payload],
            "pending_orders": [deepcopy(order) for order in pending_payload],
            "orders_count": len(account.get("orders") or []),
            "created_at": account.get("created_at", _utc_now()),
            "updated_at": account.get("updated_at", _utc_now()),
        }


paper_trading_store = PaperTradingStore()
