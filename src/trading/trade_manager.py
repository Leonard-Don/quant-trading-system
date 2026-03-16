
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
import uuid

logger = logging.getLogger(__name__)

@dataclass
class TradeMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0

@dataclass
class Position:
    symbol: str
    quantity: int
    avg_price: float
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_percent: float = 0.0

@dataclass
class Trade:
    id: str
    timestamp: str
    symbol: str
    action: str  # BUY or SELL
    quantity: int
    price: float
    total_amount: float
    pnl: Optional[float] = None
    balance_after: float = 0.0

class TradeManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TradeManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        
        self.initial_balance = 100000.0
        self.balance = self.initial_balance
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[Trade] = []
        self.initialized = True
        logger.info(f"TradeManager initialized with ${self.initial_balance:,.2f}")
    
    @property
    def cash(self) -> float:
        """Alias for balance (backward compatibility)"""
        return self.balance

    def get_portfolio_status(self, current_prices: Dict[str, float] = None) -> Dict[str, Any]:
        """Get current portfolio status including positions and total equity"""
        current_prices = current_prices or {}
        
        total_market_value = 0.0
        portfolio_positions = []
        
        for symbol, position in self.positions.items():
            current_price = current_prices.get(symbol, position.avg_price)
            market_value = position.quantity * current_price
            
            # Calculate PnL
            cost_basis = position.quantity * position.avg_price
            unrealized_pnl = market_value - cost_basis
            unrealized_pnl_percent = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0
            
            # Update position details for display
            pos_dict = asdict(position)
            pos_dict.update({
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_percent": unrealized_pnl_percent
            })
            portfolio_positions.append(pos_dict)
            
            total_market_value += market_value

        total_equity = self.balance + total_market_value
        total_pnl = total_equity - self.initial_balance
        total_pnl_percent = (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0

        return {
            "balance": self.balance,
            "total_equity": total_equity,
            "total_market_value": total_market_value,
            "total_pnl": total_pnl,
            "total_pnl_percent": total_pnl_percent,
            "positions": portfolio_positions,
            "trade_count": len(self.trade_history)
        }

    def execute_trade(self, symbol: str, action: str, quantity: int, price: float) -> Dict[str, Any]:
        """Execute a trade (Buy or Sell)"""
        symbol = symbol.upper()
        action = action.upper()
        total_amount = quantity * price
        
        if action == "BUY":
            if total_amount > self.balance:
                raise ValueError(f"Insufficient funds. Required: ${total_amount:,.2f}, Available: ${self.balance:,.2f}")
            
            # Update Balance
            self.balance -= total_amount
            
            # Update Position
            if symbol in self.positions:
                pos = self.positions[symbol]
                new_quantity = pos.quantity + quantity
                # Calculate new average price (weighted average)
                new_avg_price = ((pos.quantity * pos.avg_price) + total_amount) / new_quantity
                
                pos.quantity = new_quantity
                pos.avg_price = new_avg_price
            else:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    avg_price=price
                )
            
            trade_pnl = None

        elif action == "SELL":
            if symbol not in self.positions:
                raise ValueError(f"No position found for {symbol}")
            
            pos = self.positions[symbol]
            if quantity > pos.quantity:
                raise ValueError(f"Insufficient quantity. Owned: {pos.quantity}, Selling: {quantity}")
            
            # Update Balance
            self.balance += total_amount
            
            # Calculate Realized PnL
            cost_basis = quantity * pos.avg_price
            trade_pnl = total_amount - cost_basis
            
            # Update Position
            pos.quantity -= quantity
            if pos.quantity == 0:
                del self.positions[symbol]
        
        else:
            raise ValueError(f"Invalid action: {action}")

        # Record Trade
        trade = Trade(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            total_amount=total_amount,
            pnl=trade_pnl,
            balance_after=self.balance
        )
        self.trade_history.insert(0, trade)  # Newest first
        
        logger.info(f"Trade executed: {action} {quantity} {symbol} @ ${price:,.2f}")
        
        return asdict(trade)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get trade history"""
        return [asdict(t) for t in self.trade_history[:limit]]

    def reset_account(self):
        """Reset account to initial state"""
        self.balance = self.initial_balance
        self.positions = {}
        self.trade_history = []
        logger.info("Account reset to initial state")

# Global instance
trade_manager = TradeManager()
