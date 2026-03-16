import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class PortfolioOptimizer:
    """
    Portfolio Optimizer using Markowitz Mean-Variance Analysis.
    Calculates optimal asset weights for Max Sharpe Ratio or Min Volatility.
    """

    def __init__(self, risk_free_rate: float = 0.02):
        self.risk_free_rate = risk_free_rate

    def optimize_portfolio(self, historical_prices: pd.DataFrame, objective: str = "max_sharpe") -> Dict[str, Any]:
        """
        Optimize portfolio weights.
        
        Args:
            historical_prices: DataFrame where columns are symbol names and index is date.
                               Values should be adjusted close prices.
            objective: "max_sharpe" or "min_volatility"
            
        Returns:
            Dictionary containing optimal weights, portfolio metrics, and efficient frontier data.
        """
        try:
            # Calculate daily returns
            returns = historical_prices.pct_change().dropna()
            mean_returns = returns.mean()
            cov_matrix = returns.cov()
            num_assets = len(mean_returns)
            assets = historical_prices.columns.tolist()

            if num_assets < 2:
                raise ValueError("Portfolio must contain at least 2 assets for optimization")

            # Annualized metrics helpers
            def portfolio_performance(weights):
                weights = np.array(weights)
                ret = np.sum(mean_returns * weights) * 252
                std = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
                return ret, std

            def negative_sharpe_ratio(weights):
                p_ret, p_std = portfolio_performance(weights)
                return -(p_ret - self.risk_free_rate) / p_std

            def portfolio_volatility(weights):
                return portfolio_performance(weights)[1]

            # Constraints: weights sum to 1
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
            # Bounds: 0 <= weight <= 1 (no short selling)
            bounds = tuple((0.0, 1.0) for _ in range(num_assets))
            
            # Initial guess: equal distribution
            init_guess = num_assets * [1. / num_assets,]

            # Optimization
            if objective == "max_sharpe":
                result = minimize(negative_sharpe_ratio, init_guess, method='SLSQP', bounds=bounds, constraints=constraints)
            else: # min_volatility
                result = minimize(portfolio_volatility, init_guess, method='SLSQP', bounds=bounds, constraints=constraints)

            if not result.success:
                logger.warning(f"Optimization failed: {result.message}")
            
            optimal_weights = result.x
            opt_return, opt_volatility = portfolio_performance(optimal_weights)
            opt_sharpe = (opt_return - self.risk_free_rate) / opt_volatility

            # Generate Efficient Frontier mainly for plotting
            frontier_volatility = []
            frontier_return = []
            # Calculate 20 points along the frontier (min var to max return isn't easy to simplisticly loop)
            # Simplified: generate random portfolios to show the cloud + optimal point
            # Or assume we want strictly the frontier line.
            # For UI visualization, a scattering of random portfolios is often used to show the "bullet".
            
            random_portfolios = []
            num_portfolios = 200
            for _ in range(num_portfolios):
                w = np.random.random(num_assets)
                w /= np.sum(w)
                p_ret, p_std = portfolio_performance(w)
                p_sharpe = (p_ret - self.risk_free_rate) / p_std
                random_portfolios.append({
                    "return": round(p_ret * 100, 2),
                    "volatility": round(p_std * 100, 2),
                    "sharpe": round(p_sharpe, 2)
                })

            return {
                "success": True,
                "optimal_portfolio": {
                    "return": round(opt_return * 100, 2),
                    "volatility": round(opt_volatility * 100, 2),
                    "sharpe_ratio": round(opt_sharpe, 2),
                    "weights": {asset: round(weight, 4) for asset, weight in zip(assets, optimal_weights)}
                },
                "assets": assets,
                "efficient_frontier": random_portfolios # Returning random cloud for visualization
            }

        except Exception as e:
            logger.error(f"Portfolio optimization error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
