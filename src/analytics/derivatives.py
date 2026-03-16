"""
衍生品定价模块

支持期权定价和希腊字母计算
"""

import numpy as np
from scipy.stats import norm
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OptionType(Enum):
    CALL = "call"
    PUT = "put"


@dataclass
class OptionContract:
    """期权合约"""
    underlying_price: float  # 标的价格
    strike_price: float      # 行权价
    time_to_expiry: float    # 到期时间（年）
    risk_free_rate: float    # 无风险利率
    volatility: float        # 波动率
    option_type: OptionType  # 期权类型
    dividend_yield: float = 0.0  # 股息率


@dataclass
class OptionGreeks:
    """期权希腊字母"""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


class BlackScholesModel:
    """
    Black-Scholes期权定价模型
    
    用于计算欧式期权的理论价格和希腊字母
    """
    
    @staticmethod
    def calculate_d1_d2(
        S: float,  # 标的价格
        K: float,  # 行权价
        T: float,  # 到期时间
        r: float,  # 无风险利率
        sigma: float,  # 波动率
        q: float = 0  # 股息率
    ) -> Tuple[float, float]:
        """计算d1和d2"""
        if T <= 0:
            return 0, 0
        
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        return d1, d2
    
    @classmethod
    def price(cls, contract: OptionContract) -> float:
        """
        计算期权价格
        
        Args:
            contract: 期权合约
            
        Returns:
            期权理论价格
        """
        S = contract.underlying_price
        K = contract.strike_price
        T = contract.time_to_expiry
        r = contract.risk_free_rate
        sigma = contract.volatility
        q = contract.dividend_yield
        
        if T <= 0:
            # 已到期
            if contract.option_type == OptionType.CALL:
                return max(S - K, 0)
            else:
                return max(K - S, 0)
        
        d1, d2 = cls.calculate_d1_d2(S, K, T, r, sigma, q)
        
        if contract.option_type == OptionType.CALL:
            price = S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        else:
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)
        
        return price
    
    @classmethod
    def greeks(cls, contract: OptionContract) -> OptionGreeks:
        """
        计算希腊字母
        
        Returns:
            OptionGreeks对象
        """
        S = contract.underlying_price
        K = contract.strike_price
        T = contract.time_to_expiry
        r = contract.risk_free_rate
        sigma = contract.volatility
        q = contract.dividend_yield
        
        if T <= 0:
            return OptionGreeks(delta=0, gamma=0, theta=0, vega=0, rho=0)
        
        d1, d2 = cls.calculate_d1_d2(S, K, T, r, sigma, q)
        
        # Delta
        if contract.option_type == OptionType.CALL:
            delta = np.exp(-q * T) * norm.cdf(d1)
        else:
            delta = -np.exp(-q * T) * norm.cdf(-d1)
        
        # Gamma (same for calls and puts)
        gamma = np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
        
        # Theta
        term1 = -S * sigma * np.exp(-q * T) * norm.pdf(d1) / (2 * np.sqrt(T))
        if contract.option_type == OptionType.CALL:
            term2 = -r * K * np.exp(-r * T) * norm.cdf(d2)
            term3 = q * S * np.exp(-q * T) * norm.cdf(d1)
        else:
            term2 = r * K * np.exp(-r * T) * norm.cdf(-d2)
            term3 = -q * S * np.exp(-q * T) * norm.cdf(-d1)
        theta = (term1 + term2 + term3) / 365  # 每日theta
        
        # Vega
        vega = S * np.exp(-q * T) * norm.pdf(d1) * np.sqrt(T) / 100  # 每1%波动率
        
        # Rho
        if contract.option_type == OptionType.CALL:
            rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100  # 每1%利率
        else:
            rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100
        
        return OptionGreeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=rho
        )
    
    @classmethod
    def implied_volatility(
        cls,
        market_price: float,
        contract: OptionContract,
        max_iterations: int = 100,
        tolerance: float = 1e-5
    ) -> Optional[float]:
        """
        计算隐含波动率（使用牛顿法）
        
        Args:
            market_price: 市场价格
            contract: 期权合约
            
        Returns:
            隐含波动率
        """
        sigma = 0.3  # 初始猜测
        
        for _ in range(max_iterations):
            contract.volatility = sigma
            price = cls.price(contract)
            greeks = cls.greeks(contract)
            vega = greeks.vega * 100  # 转回实际vega
            
            if abs(vega) < 1e-10:
                break
            
            diff = market_price - price
            
            if abs(diff) < tolerance:
                return sigma
            
            sigma += diff / vega
            
            # 边界检查
            if sigma <= 0:
                sigma = 0.01
            elif sigma > 5:
                sigma = 5
        
        return sigma


class OptionAnalyzer:
    """
    期权分析器
    
    提供期权定价、希腊字母分析和策略评估
    """
    
    def __init__(self):
        self.model = BlackScholesModel()
    
    def analyze_option(
        self,
        underlying_price: float,
        strike_price: float,
        days_to_expiry: int,
        risk_free_rate: float = 0.02,
        volatility: float = 0.3,
        option_type: str = "call",
        dividend_yield: float = 0.0
    ) -> Dict:
        """
        分析期权
        """
        contract = OptionContract(
            underlying_price=underlying_price,
            strike_price=strike_price,
            time_to_expiry=days_to_expiry / 365,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
            option_type=OptionType.CALL if option_type.lower() == "call" else OptionType.PUT,
            dividend_yield=dividend_yield
        )
        
        price = self.model.price(contract)
        greeks = self.model.greeks(contract)
        
        # 内在价值
        if contract.option_type == OptionType.CALL:
            intrinsic = max(underlying_price - strike_price, 0)
        else:
            intrinsic = max(strike_price - underlying_price, 0)
        
        time_value = price - intrinsic
        
        # 盈亏平衡点
        if contract.option_type == OptionType.CALL:
            breakeven = strike_price + price
        else:
            breakeven = strike_price - price
        
        return {
            "contract": {
                "underlying_price": underlying_price,
                "strike_price": strike_price,
                "days_to_expiry": days_to_expiry,
                "option_type": option_type,
                "volatility": volatility
            },
            "pricing": {
                "theoretical_price": round(price, 4),
                "intrinsic_value": round(intrinsic, 4),
                "time_value": round(time_value, 4),
                "breakeven_price": round(breakeven, 4)
            },
            "greeks": {
                "delta": round(greeks.delta, 4),
                "gamma": round(greeks.gamma, 6),
                "theta": round(greeks.theta, 4),
                "vega": round(greeks.vega, 4),
                "rho": round(greeks.rho, 4)
            },
            "interpretation": self._interpret_greeks(greeks, contract.option_type)
        }
    
    def _interpret_greeks(self, greeks: OptionGreeks, option_type: OptionType) -> Dict:
        """希腊字母解读"""
        return {
            "delta": f"标的价格变动$1，期权价格变动${abs(greeks.delta):.2f}",
            "gamma": f"Delta的变化速度，当前{greeks.gamma:.4f}",
            "theta": f"每天时间价值衰减${abs(greeks.theta):.4f}",
            "vega": f"波动率变动1%，期权价格变动${greeks.vega:.4f}"
        }
    
    def calculate_payoff(
        self,
        contract: OptionContract,
        price_range: Tuple[float, float],
        steps: int = 50
    ) -> Dict:
        """
        计算到期收益曲线
        """
        prices = np.linspace(price_range[0], price_range[1], steps)
        payoffs = []
        
        option_cost = self.model.price(contract)
        
        for p in prices:
            if contract.option_type == OptionType.CALL:
                payoff = max(p - contract.strike_price, 0) - option_cost
            else:
                payoff = max(contract.strike_price - p, 0) - option_cost
            payoffs.append(payoff)
        
        return {
            "underlying_prices": prices.tolist(),
            "payoffs": payoffs,
            "breakeven": contract.strike_price + option_cost if contract.option_type == OptionType.CALL else contract.strike_price - option_cost
        }


# 全局实例
option_analyzer = OptionAnalyzer()
