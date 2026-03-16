"""
基本面分析模块
分析公司基本面数据，如市盈率、市值、财务指标等
"""

import logging
from typing import Dict, Any
from src.data.data_manager import DataManager

logger = logging.getLogger(__name__)


class FundamentalAnalyzer:
    """
    基本面分析器
    评估公司的财务健康状况和估值水平
    """

    def __init__(self):
        self.data_manager = DataManager()

    def analyze(self, symbol: str) -> Dict[str, Any]:
        """
        执行基本面分析

        Args:
            symbol: 股票代码

        Returns:
            基本面分析结果
        """
        try:
            # 获取基本面数据
            data = self.data_manager.provider_factory.get_provider("yahoo").get_fundamental_data(symbol)
            
            if "error" in data:
                logger.warning(f"基本面数据获取失败: {data['error']}")
                return self._get_empty_result()

            # 评估估值状态
            valuation = self._assess_valuation(data)
            
            # 评估财务健康
            health = self._assess_financial_health(data)
            
            # 评估增长性
            growth = self._assess_growth(data)

            return {
                "metrics": data,
                "valuation": valuation,
                "financial_health": health,
                "growth": growth,
                "summary": self._generate_summary(valuation, health, growth)
            }

        except Exception as e:
            logger.error(f"基本面分析出错 {symbol}: {e}")
            return self._get_empty_result()

    def _assess_valuation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """评估估值水平"""
        pe = data.get("pe_ratio", 0)
        peg = data.get("peg_ratio", 0)
        pb = data.get("price_to_book", 0)
        
        score = 50
        status = "neutral"
        
        # PE 评分
        if pe > 0:
            if pe < 15: score += 10
            elif pe > 30: score -= 10
            elif pe > 50: score -= 20
            
        # PEG 评分
        if peg > 0:
            if peg < 1: score += 15
            elif peg > 2: score -= 10
            
        if score > 70: status = "undervalued"
        elif score < 30: status = "overvalued"
        else: status = "fair_value"
            
        return {
            "score": score,
            "status": status,
            "pe": pe,
            "peg": peg,
            "pb": pb
        }

    def _assess_financial_health(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """评估财务健康"""
        current_ratio = data.get("current_ratio", 0)
        debt_to_equity = data.get("debt_to_equity", 0)
        profit_margin = data.get("profit_margin", 0)
        
        score = 50
        
        if current_ratio > 1.5: score += 10
        elif current_ratio < 1: score -= 10
        
        if debt_to_equity > 0:
            if debt_to_equity < 50: score += 10
            elif debt_to_equity > 100: score -= 10
            
        if profit_margin > 0.15: score += 10
        elif profit_margin < 0: score -= 10
        
        return {
            "score": score,
            "status": "healthy" if score > 60 else "weak" if score < 40 else "stable",
            "current_ratio": current_ratio,
            "debt_to_equity": debt_to_equity,
            "profit_margin": profit_margin
        }

    def _assess_growth(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """评估增长性"""
        rev_growth = data.get("revenue_growth", 0)
        earn_growth = data.get("earnings_growth", 0)
        
        score = 50
        
        if rev_growth > 0.2: score += 15
        elif rev_growth > 0.1: score += 5
        elif rev_growth < 0: score -= 10
        
        if earn_growth > 0.2: score += 15
        elif earn_growth > 0.1: score += 5
        elif earn_growth < 0: score -= 10
        
        return {
            "score": score,
            "status": "high_growth" if score > 70 else "slow_growth" if score < 30 else "moderate",
            "revenue_growth": rev_growth,
            "earnings_growth": earn_growth
        }

    def _generate_summary(self, val, health, growth) -> str:
        parts = []
        if val["status"] == "undervalued": parts.append("估值偏低")
        elif val["status"] == "overvalued": parts.append("估值偏高")
        
        if health["status"] == "healthy": parts.append("财务健康")
        elif health["status"] == "weak": parts.append("财务状况较弱")
        
        if growth["status"] == "high_growth": parts.append("高增长")
        
        return "，".join(parts) if parts else "基本面平稳"

    def _get_empty_result(self) -> Dict[str, Any]:
        return {
            "metrics": {},
            "valuation": {"score": 50, "status": "unknown"},
            "financial_health": {"score": 50, "status": "unknown"},
            "growth": {"score": 50, "status": "unknown"},
            "summary": "暂无基本面数据"
        }
