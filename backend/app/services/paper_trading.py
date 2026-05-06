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
        with self._lock:
            account = self._load(profile_id)
            if order_type == "LIMIT":
                order = self._queue_limit_order(account, order_request)
                account["updated_at"] = _utc_now()
                self._persist(profile_id, account)
                return {
                    "order": order,
                    "account": self._public_view(profile_id, account),
                }
            # MARKET — default behavior, fills immediately
            order = self._apply_order(account, order_request)
            account["updated_at"] = _utc_now()
            account["orders"] = (account.get("orders") or [])[-MAX_PAPER_ORDERS + 1 :]
            account["orders"].append(order)
            self._persist(profile_id, account)
            return {
                "order": order,
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
        def _parse_optional_pct(field_name: str, upper: float) -> float | None:
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

        stop_loss_pct = _parse_optional_pct("stop_loss_pct", 0.5)
        take_profit_pct = _parse_optional_pct("take_profit_pct", 5.0)
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
