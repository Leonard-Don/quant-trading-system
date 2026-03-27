"""
期权/期货衍生品模块

提供期权定价、Greeks计算和期货合约管理功能
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OptionType(Enum):
    """期权类型"""
    CALL = "call"
    PUT = "put"


class OptionStyle(Enum):
    """期权风格"""
    EUROPEAN = "european"
    AMERICAN = "american"


class BlackScholesModel:
    """
    Black-Scholes 期权定价模型
    
    支持:
    - 欧式期权定价
    - Greeks 计算 (Delta, Gamma, Theta, Vega, Rho)
    - 隐含波动率计算
    """
    
    @staticmethod
    def d1(S: float, K: float, T: float, r: float, sigma: float, q: float = 0) -> float:
        """
        计算 d1 参数
        
        Args:
            S: 标的资产价格
            K: 行权价
            T: 到期时间 (年)
            r: 无风险利率
            sigma: 波动率
            q: 股息率
        """
        if T <= 0 or sigma <= 0:
            return 0
        return (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    
    @staticmethod
    def d2(S: float, K: float, T: float, r: float, sigma: float, q: float = 0) -> float:
        """计算 d2 参数"""
        return BlackScholesModel.d1(S, K, T, r, sigma, q) - sigma * np.sqrt(T)
    
    @staticmethod
    def price(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: OptionType = OptionType.CALL,
        q: float = 0
    ) -> float:
        """
        计算期权价格
        
        Args:
            S: 标的资产价格
            K: 行权价
            T: 到期时间 (年)
            r: 无风险利率
            sigma: 波动率
            option_type: 期权类型 (CALL/PUT)
            q: 股息率
            
        Returns:
            期权价格
        """
        if T <= 0:
            # 到期时的内在价值
            if option_type == OptionType.CALL:
                return max(S - K, 0)
            else:
                return max(K - S, 0)
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma, q)
        d2 = BlackScholesModel.d2(S, K, T, r, sigma, q)
        
        if option_type == OptionType.CALL:
            price = S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        else:  # PUT
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)
        
        return max(price, 0)
    
    @staticmethod
    def delta(
        S: float, K: float, T: float, r: float, sigma: float,
        option_type: OptionType = OptionType.CALL, q: float = 0
    ) -> float:
        """
        计算 Delta
        
        Delta 表示标的资产价格变动对期权价格的敏感度
        """
        if T <= 0:
            if option_type == OptionType.CALL:
                return 1 if S > K else 0
            else:
                return -1 if S < K else 0
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma, q)
        
        if option_type == OptionType.CALL:
            return np.exp(-q * T) * norm.cdf(d1)
        else:
            return np.exp(-q * T) * (norm.cdf(d1) - 1)
    
    @staticmethod
    def gamma(
        S: float, K: float, T: float, r: float, sigma: float, q: float = 0
    ) -> float:
        """
        计算 Gamma
        
        Gamma 表示 Delta 对标的资产价格变动的敏感度
        """
        if T <= 0 or sigma <= 0:
            return 0
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma, q)
        return np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
    
    @staticmethod
    def theta(
        S: float, K: float, T: float, r: float, sigma: float,
        option_type: OptionType = OptionType.CALL, q: float = 0
    ) -> float:
        """
        计算 Theta (每日)
        
        Theta 表示时间流逝对期权价格的影响
        """
        if T <= 0:
            return 0
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma, q)
        d2 = BlackScholesModel.d2(S, K, T, r, sigma, q)
        
        term1 = -S * sigma * np.exp(-q * T) * norm.pdf(d1) / (2 * np.sqrt(T))
        
        if option_type == OptionType.CALL:
            term2 = -r * K * np.exp(-r * T) * norm.cdf(d2)
            term3 = q * S * np.exp(-q * T) * norm.cdf(d1)
        else:
            term2 = r * K * np.exp(-r * T) * norm.cdf(-d2)
            term3 = -q * S * np.exp(-q * T) * norm.cdf(-d1)
        
        # 转换为每日 (除以365)
        return (term1 + term2 + term3) / 365
    
    @staticmethod
    def vega(
        S: float, K: float, T: float, r: float, sigma: float, q: float = 0
    ) -> float:
        """
        计算 Vega
        
        Vega 表示波动率变动对期权价格的敏感度
        返回每1%波动率变动的价格变化
        """
        if T <= 0:
            return 0
        
        d1 = BlackScholesModel.d1(S, K, T, r, sigma, q)
        return S * np.exp(-q * T) * norm.pdf(d1) * np.sqrt(T) / 100
    
    @staticmethod
    def rho(
        S: float, K: float, T: float, r: float, sigma: float,
        option_type: OptionType = OptionType.CALL, q: float = 0
    ) -> float:
        """
        计算 Rho
        
        Rho 表示无风险利率变动对期权价格的敏感度
        返回每1%利率变动的价格变化
        """
        if T <= 0:
            return 0
        
        d2 = BlackScholesModel.d2(S, K, T, r, sigma, q)
        
        if option_type == OptionType.CALL:
            return K * T * np.exp(-r * T) * norm.cdf(d2) / 100
        else:
            return -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100
    
    @staticmethod
    def implied_volatility(
        market_price: float,
        S: float, K: float, T: float, r: float,
        option_type: OptionType = OptionType.CALL,
        q: float = 0,
        max_iterations: int = 100,
        tolerance: float = 1e-6
    ) -> Optional[float]:
        """
        使用牛顿-拉夫森法计算隐含波动率
        
        Args:
            market_price: 期权市场价格
            其他参数同上
            
        Returns:
            隐含波动率，如果计算失败返回 None
        """
        if market_price <= 0 or T <= 0:
            return None
        
        # 初始猜测
        sigma = 0.3
        
        for _ in range(max_iterations):
            price = BlackScholesModel.price(S, K, T, r, sigma, option_type, q)
            vega = BlackScholesModel.vega(S, K, T, r, sigma, q) * 100  # 转回原始单位
            
            if vega == 0:
                return None
            
            diff = market_price - price
            if abs(diff) < tolerance:
                return sigma
            
            sigma = sigma + diff / vega
            
            # 保持在合理范围内
            sigma = max(0.01, min(5.0, sigma))
        
        return sigma
    
    @staticmethod
    def calculate_all_greeks(
        S: float, K: float, T: float, r: float, sigma: float,
        option_type: OptionType = OptionType.CALL, q: float = 0
    ) -> Dict[str, float]:
        """计算所有 Greeks"""
        return {
            'price': BlackScholesModel.price(S, K, T, r, sigma, option_type, q),
            'delta': BlackScholesModel.delta(S, K, T, r, sigma, option_type, q),
            'gamma': BlackScholesModel.gamma(S, K, T, r, sigma, q),
            'theta': BlackScholesModel.theta(S, K, T, r, sigma, option_type, q),
            'vega': BlackScholesModel.vega(S, K, T, r, sigma, q),
            'rho': BlackScholesModel.rho(S, K, T, r, sigma, option_type, q)
        }


class FuturesContract:
    """
    期货合约类
    
    管理期货合约的基本信息和定价
    """
    
    def __init__(
        self,
        symbol: str,
        underlying: str,
        expiry: datetime,
        contract_size: float = 1.0,
        tick_size: float = 0.01,
        margin_rate: float = 0.1
    ):
        """
        初始化期货合约
        
        Args:
            symbol: 合约代码
            underlying: 标的资产
            expiry: 到期日
            contract_size: 合约乘数
            tick_size: 最小变动价位
            margin_rate: 保证金比率
        """
        self.symbol = symbol
        self.underlying = underlying
        self.expiry = expiry
        self.contract_size = contract_size
        self.tick_size = tick_size
        self.margin_rate = margin_rate
        
        # 行情数据
        self.last_price: Optional[float] = None
        self.bid_price: Optional[float] = None
        self.ask_price: Optional[float] = None
        self.volume: int = 0
        self.open_interest: int = 0
    
    @property
    def days_to_expiry(self) -> int:
        """距离到期的天数"""
        return max(0, (self.expiry - datetime.now()).days)
    
    @property
    def years_to_expiry(self) -> float:
        """距离到期的年数"""
        return self.days_to_expiry / 365
    
    @property
    def is_expired(self) -> bool:
        """是否已到期"""
        return datetime.now() > self.expiry
    
    def theoretical_price(
        self,
        spot_price: float,
        risk_free_rate: float = 0.02,
        storage_cost: float = 0,
        convenience_yield: float = 0
    ) -> float:
        """
        计算期货理论价格
        
        使用持有成本模型: F = S * e^((r + c - y) * T)
        
        Args:
            spot_price: 现货价格
            risk_free_rate: 无风险利率
            storage_cost: 仓储成本率
            convenience_yield: 便利收益率
        """
        T = self.years_to_expiry
        return spot_price * np.exp((risk_free_rate + storage_cost - convenience_yield) * T)
    
    def basis(self, spot_price: float) -> Optional[float]:
        """
        计算基差 = 期货价格 - 现货价格
        """
        if self.last_price is None:
            return None
        return self.last_price - spot_price
    
    def margin_required(self, quantity: int = 1) -> float:
        """
        计算所需保证金
        
        Args:
            quantity: 合约数量
        """
        if self.last_price is None:
            return 0
        return self.last_price * self.contract_size * abs(quantity) * self.margin_rate
    
    def profit_loss(
        self,
        entry_price: float,
        current_price: float,
        quantity: int,
        is_long: bool = True
    ) -> float:
        """
        计算盈亏
        
        Args:
            entry_price: 开仓价格
            current_price: 当前价格
            quantity: 合约数量
            is_long: 是否做多
        """
        direction = 1 if is_long else -1
        return direction * (current_price - entry_price) * self.contract_size * quantity
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'underlying': self.underlying,
            'expiry': self.expiry.isoformat(),
            'days_to_expiry': self.days_to_expiry,
            'contract_size': self.contract_size,
            'tick_size': self.tick_size,
            'margin_rate': self.margin_rate,
            'last_price': self.last_price,
            'volume': self.volume,
            'open_interest': self.open_interest,
            'is_expired': self.is_expired
        }


class FuturesContractManager:
    """
    期货合约管理器
    
    管理多个期货合约，支持合约滚动
    """
    
    # 常见期货合约模板
    CONTRACT_SPECS = {
        'ES': {'name': 'E-mini S&P 500', 'size': 50, 'tick': 0.25, 'margin': 0.05},
        'NQ': {'name': 'E-mini NASDAQ', 'size': 20, 'tick': 0.25, 'margin': 0.05},
        'GC': {'name': 'Gold', 'size': 100, 'tick': 0.1, 'margin': 0.05},
        'CL': {'name': 'Crude Oil', 'size': 1000, 'tick': 0.01, 'margin': 0.08},
        'IF': {'name': '沪深300股指', 'size': 300, 'tick': 0.2, 'margin': 0.12},
        'IC': {'name': '中证500股指', 'size': 200, 'tick': 0.2, 'margin': 0.12},
        'IH': {'name': '上证50股指', 'size': 300, 'tick': 0.2, 'margin': 0.12},
    }
    
    def __init__(self):
        self.contracts: Dict[str, FuturesContract] = {}
    
    def create_contract(
        self,
        symbol: str,
        underlying: str,
        expiry: datetime,
        **kwargs
    ) -> FuturesContract:
        """创建新合约"""
        # 检查是否有预设规格
        base_symbol = ''.join(filter(str.isalpha, symbol.upper()))
        specs = self.CONTRACT_SPECS.get(base_symbol, {})
        
        contract = FuturesContract(
            symbol=symbol,
            underlying=underlying,
            expiry=expiry,
            contract_size=kwargs.get('contract_size', specs.get('size', 1)),
            tick_size=kwargs.get('tick_size', specs.get('tick', 0.01)),
            margin_rate=kwargs.get('margin_rate', specs.get('margin', 0.1))
        )
        
        self.contracts[symbol] = contract
        return contract
    
    def get_contract(self, symbol: str) -> Optional[FuturesContract]:
        """获取合约"""
        return self.contracts.get(symbol)
    
    def get_active_contracts(self) -> List[FuturesContract]:
        """获取所有未到期合约"""
        return [c for c in self.contracts.values() if not c.is_expired]
    
    def get_expiring_contracts(self, days: int = 5) -> List[FuturesContract]:
        """获取即将到期的合约"""
        return [c for c in self.contracts.values() if 0 < c.days_to_expiry <= days]
    
    def remove_expired(self) -> List[str]:
        """移除已到期合约"""
        expired = [k for k, v in self.contracts.items() if v.is_expired]
        for symbol in expired:
            del self.contracts[symbol]
        return expired
    
    def generate_contract_chain(
        self,
        base_symbol: str,
        underlying: str,
        num_months: int = 4,
        start_date: Optional[datetime] = None
    ) -> List[FuturesContract]:
        """
        生成合约链（多个到期月份的合约）
        
        Args:
            base_symbol: 基础合约代码
            underlying: 标的资产
            num_months: 生成几个月的合约
            start_date: 起始日期
        """
        contracts = []
        start = start_date or datetime.now()
        
        for i in range(num_months):
            # 计算到期日（每月第三个周五）
            month = start.month + i
            year = start.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            
            # 找到第三个周五
            first_day = datetime(year, month, 1)
            first_friday = first_day + timedelta(days=(4 - first_day.weekday() + 7) % 7)
            expiry = first_friday + timedelta(weeks=2)
            
            # 生成合约代码 (如 ES2403)
            symbol = f"{base_symbol}{year % 100:02d}{month:02d}"
            
            contract = self.create_contract(symbol, underlying, expiry)
            contracts.append(contract)
        
        return contracts
    
    def get_front_month(self, base_symbol: str) -> Optional[FuturesContract]:
        """获取主力合约（最近月份的未到期合约）"""
        active = [
            c for c in self.contracts.values()
            if c.symbol.startswith(base_symbol) and not c.is_expired
        ]
        if not active:
            return None
        return min(active, key=lambda c: c.expiry)
    
    def calculate_roll_spread(
        self,
        front_contract: FuturesContract,
        back_contract: FuturesContract
    ) -> Optional[float]:
        """
        计算换月价差
        
        Args:
            front_contract: 近月合约
            back_contract: 远月合约
        """
        if front_contract.last_price is None or back_contract.last_price is None:
            return None
        return back_contract.last_price - front_contract.last_price


# 全局实例
black_scholes = BlackScholesModel()
futures_manager = FuturesContractManager()
