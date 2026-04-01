"""
多因子资产定价引擎
实现 CAPM 和 Fama-French 三因子模型，提供因子暴露度分析和 Alpha 归因
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from scipy import stats as scipy_stats

from src.data.data_manager import DataManager

logger = logging.getLogger(__name__)

# Fama-French 因子数据的本地缓存
_ff_cache: Dict[str, Any] = {}


def _normalize_daily_index(data: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Normalize market time series to a tz-naive daily DatetimeIndex."""
    if data is None or data.empty:
        return data

    normalized = data.copy()
    index = pd.to_datetime(normalized.index)
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    normalized.index = index.normalize()
    return normalized.sort_index()


def _fetch_ff_factors(period: str = "1y") -> pd.DataFrame:
    """
    获取 Fama-French 三因子数据

    尝试从 Kenneth French Data Library 获取；若失败则使用代理方法估算。

    Returns:
        DataFrame with columns: Mkt-RF, SMB, HML, RF (日频, 百分比已转为小数)
    """
    cache_key = f"ff3_{period}"
    if cache_key in _ff_cache:
        cached = _ff_cache[cache_key]
        if (datetime.now() - cached["ts"]).total_seconds() < 86400:
            return cached["data"]

    try:
        import pandas_datareader.data as web

        ff = web.DataReader("F-F_Research_Data_Factors_daily", "famafrench",
                            start=datetime.now() - timedelta(days=_period_to_days(period)))
        df = ff[0] / 100.0  # 百分比 -> 小数
        df.index = pd.to_datetime(df.index)
        df = _normalize_daily_index(df)
        df.attrs["source"] = {
            "type": "kenneth_french_library",
            "label": "Kenneth French Data Library",
            "is_proxy": False,
            "warning": "",
        }
        _ff_cache[cache_key] = {"data": df, "ts": datetime.now()}
        logger.info(f"Fetched Fama-French factors: {len(df)} days")
        return df
    except Exception as e:
        logger.warning(f"无法从 Kenneth French Library 获取因子数据: {e}")
        return _estimate_ff_factors(period)


def _fetch_ff5_factors(period: str = "1y") -> pd.DataFrame:
    """获取 Fama-French 五因子数据，失败时回退到代理估算。"""
    cache_key = f"ff5_{period}"
    if cache_key in _ff_cache:
        cached = _ff_cache[cache_key]
        if (datetime.now() - cached["ts"]).total_seconds() < 86400:
            return cached["data"]

    try:
        import pandas_datareader.data as web

        ff = web.DataReader(
            "F-F_Research_Data_5_Factors_2x3_daily",
            "famafrench",
            start=datetime.now() - timedelta(days=_period_to_days(period))
        )
        df = ff[0] / 100.0
        df.index = pd.to_datetime(df.index)
        df = _normalize_daily_index(df)
        df.attrs["source"] = {
            "type": "kenneth_french_library",
            "label": "Kenneth French 5-Factor Library",
            "is_proxy": False,
            "warning": "",
        }
        _ff_cache[cache_key] = {"data": df, "ts": datetime.now()}
        return df
    except Exception as e:
        logger.warning(f"无法从 Kenneth French Library 获取五因子数据: {e}")
        return _estimate_ff5_factors(period)


def _estimate_ff_factors(period: str = "1y") -> pd.DataFrame:
    """
    若网络获取失败，使用市场指数代理估算因子
    """
    dm = DataManager()
    days = _period_to_days(period)
    start = datetime.now() - timedelta(days=days)

    try:
        sp500 = dm.get_historical_data("^GSPC", start_date=start)
        if sp500.empty:
            return pd.DataFrame()

        mkt_rf = sp500["close"].pct_change().dropna()
        rf = 0.05 / 252  # 近似日无风险利率
        short_momentum = mkt_rf.rolling(5, min_periods=1).mean()
        medium_momentum = mkt_rf.rolling(20, min_periods=1).mean()
        long_momentum = mkt_rf.rolling(60, min_periods=1).mean()
        smb_proxy = ((short_momentum - medium_momentum) * 0.6).clip(-0.02, 0.02)
        hml_proxy = ((medium_momentum - long_momentum) * -0.5).clip(-0.02, 0.02)

        df = pd.DataFrame({
            "Mkt-RF": mkt_rf - rf,
            "SMB": smb_proxy,
            "HML": hml_proxy,
            "RF": rf
        }, index=mkt_rf.index)
        df = _normalize_daily_index(df)
        df.attrs["source"] = {
            "type": "market_proxy",
            "label": "市场代理估算",
            "is_proxy": True,
            "warning": "SMB/HML 采用市场动量代理构造，结果仅供参考。",
        }

        logger.info("Using proxy FF factors (estimated)")
        return df
    except Exception as e:
        logger.error(f"因子数据估算失败: {e}")
        return pd.DataFrame()


def _estimate_ff5_factors(period: str = "1y") -> pd.DataFrame:
    """五因子代理估算，保证结果可复现并显式标注为代理值。"""
    ff3 = _estimate_ff_factors(period)
    if ff3.empty:
        return pd.DataFrame()

    market = ff3["Mkt-RF"]
    short_term = market.rolling(5, min_periods=1).mean()
    long_term = market.rolling(40, min_periods=1).mean()
    rmw_proxy = ((long_term - short_term) * 0.35).clip(-0.015, 0.015)
    cma_proxy = ((short_term - long_term) * 0.25).clip(-0.015, 0.015)
    df = ff3.copy()
    df["RMW"] = rmw_proxy
    df["CMA"] = cma_proxy
    df.attrs["source"] = {
        "type": "market_proxy",
        "label": "五因子代理估算",
        "is_proxy": True,
        "warning": "RMW/CMA 采用市场趋势代理构造，结果仅供研究参考。",
    }
    return df


def _period_to_days(period: str) -> int:
    """将 period 字符串转换为天数"""
    mapping = {"6mo": 180, "1y": 365, "2y": 730, "3y": 1095, "5y": 1825}
    return mapping.get(period, 365)


class AssetPricingEngine:
    """
    资产定价引擎
    提供 CAPM 和 Fama-French 三因子分析
    """

    def __init__(self):
        self.data_manager = DataManager()

    def analyze(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        """
        完整的因子模型分析

        Args:
            symbol: 股票代码 (如 'AAPL')
            period: 分析周期 ('6mo', '1y', '2y', '3y', '5y')

        Returns:
            包含 CAPM 和 FF3 分析结果的字典
        """
        try:
            days = _period_to_days(period)
            start = datetime.now() - timedelta(days=days)
            stock_data = self.data_manager.get_historical_data(symbol, start_date=start)
            stock_data = _normalize_daily_index(stock_data)

            if stock_data.empty or len(stock_data) < 60:
                return self._empty_result("数据不足，至少需要60个交易日")

            stock_returns = stock_data["close"].pct_change().dropna()

            # CAPM 分析
            capm_result = self._run_capm(stock_returns, period)

            # Fama-French 三因子分析
            ff3_result = self._run_ff3(stock_returns, period)
            ff5_result = self._run_ff5(stock_returns, period)

            # 因子归因
            attribution = self._factor_attribution(capm_result, ff3_result)
            ff_factors = _fetch_ff_factors(period)
            factor_source = self._factor_source_meta(ff_factors)
            ff5_source = self._factor_source_meta(_fetch_ff5_factors(period))

            return {
                "symbol": symbol,
                "period": period,
                "data_points": len(stock_returns),
                "factor_source": factor_source,
                "five_factor_source": ff5_source,
                "capm": capm_result,
                "fama_french": ff3_result,
                "fama_french_five_factor": ff5_result,
                "attribution": attribution,
                "summary": self._generate_summary(capm_result, ff3_result, ff5_result)
            }

        except Exception as e:
            logger.error(f"因子模型分析出错 {symbol}: {e}", exc_info=True)
            return self._empty_result(str(e))

    def _run_capm(self, stock_returns: pd.Series, period: str) -> Dict[str, Any]:
        """CAPM 回归: R_i - R_f = alpha + beta * (R_m - R_f) + epsilon"""
        try:
            ff = _fetch_ff_factors(period)
            if ff.empty:
                return {"error": "无法获取市场因子数据"}

            # 对齐日期
            aligned = pd.DataFrame({
                "stock": stock_returns,
                "mkt_rf": ff["Mkt-RF"],
                "rf": ff["RF"]
            }).dropna()

            if len(aligned) < 30:
                return {"error": "对齐后数据不足30天"}

            y = aligned["stock"] - aligned["rf"]  # 超额收益
            X = aligned["mkt_rf"]

            # OLS 回归
            X_with_const = np.column_stack([np.ones(len(X)), X.values])
            coeffs = np.linalg.lstsq(X_with_const, y.values, rcond=None)[0]
            alpha_daily = coeffs[0]
            beta = coeffs[1]

            # R² 计算
            y_pred = X_with_const @ coeffs
            ss_res = np.sum((y.values - y_pred) ** 2)
            ss_tot = np.sum((y.values - y.values.mean()) ** 2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            stats_meta = self._ols_statistics(y.values, X_with_const, coeffs)

            # 年化 Alpha
            alpha_annual = alpha_daily * 252

            # 残差标准差 (特质风险)
            residuals = y.values - y_pred
            idiosyncratic_risk = np.std(residuals) * np.sqrt(252)

            return {
                "alpha_daily": round(float(alpha_daily), 6),
                "alpha_annual": round(float(alpha_annual), 4),
                "alpha_pct": round(float(alpha_annual * 100), 2),
                "beta": round(float(beta), 4),
                "r_squared": round(float(r_squared), 4),
                "idiosyncratic_risk": round(float(idiosyncratic_risk), 4),
                "data_points": len(aligned),
                "significance": {
                    "alpha_t_stat": round(float(stats_meta["t_stats"][0]), 3),
                    "alpha_p_value": round(float(stats_meta["p_values"][0]), 4),
                    "beta_t_stat": round(float(stats_meta["t_stats"][1]), 3),
                    "beta_p_value": round(float(stats_meta["p_values"][1]), 4),
                },
                "residual_diagnostics": stats_meta["residual_diagnostics"],
                "interpretation": self._interpret_capm(alpha_annual, beta, r_squared)
            }

        except Exception as e:
            logger.error(f"CAPM 分析出错: {e}")
            return {"error": str(e)}

    def _run_ff3(self, stock_returns: pd.Series, period: str) -> Dict[str, Any]:
        """Fama-French 三因子回归: R_i - R_f = α + β1*(Mkt-RF) + β2*SMB + β3*HML + ε"""
        try:
            ff = _fetch_ff_factors(period)
            if ff.empty:
                return {"error": "无法获取FF因子数据"}

            aligned = pd.DataFrame({
                "stock": stock_returns,
                "mkt_rf": ff["Mkt-RF"],
                "smb": ff["SMB"],
                "hml": ff["HML"],
                "rf": ff["RF"]
            }).dropna()

            if len(aligned) < 30:
                return {"error": "对齐后数据不足30天"}

            y = aligned["stock"] - aligned["rf"]
            X = aligned[["mkt_rf", "smb", "hml"]].values
            X_with_const = np.column_stack([np.ones(len(X)), X])

            coeffs = np.linalg.lstsq(X_with_const, y.values, rcond=None)[0]

            alpha_daily = coeffs[0]
            beta_mkt = coeffs[1]
            beta_smb = coeffs[2]
            beta_hml = coeffs[3]

            # R²
            y_pred = X_with_const @ coeffs
            ss_res = np.sum((y.values - y_pred) ** 2)
            ss_tot = np.sum((y.values - y.values.mean()) ** 2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            alpha_annual = alpha_daily * 252
            stats_meta = self._ols_statistics(y.values, X_with_const, coeffs)

            return {
                "alpha_daily": round(float(alpha_daily), 6),
                "alpha_annual": round(float(alpha_annual), 4),
                "alpha_pct": round(float(alpha_annual * 100), 2),
                "factor_loadings": {
                    "market": round(float(beta_mkt), 4),
                    "size": round(float(beta_smb), 4),
                    "value": round(float(beta_hml), 4)
                },
                "r_squared": round(float(r_squared), 4),
                "data_points": len(aligned),
                "significance": {
                    "alpha_t_stat": round(float(stats_meta["t_stats"][0]), 3),
                    "alpha_p_value": round(float(stats_meta["p_values"][0]), 4),
                    "market_t_stat": round(float(stats_meta["t_stats"][1]), 3),
                    "market_p_value": round(float(stats_meta["p_values"][1]), 4),
                    "size_t_stat": round(float(stats_meta["t_stats"][2]), 3),
                    "size_p_value": round(float(stats_meta["p_values"][2]), 4),
                    "value_t_stat": round(float(stats_meta["t_stats"][3]), 3),
                    "value_p_value": round(float(stats_meta["p_values"][3]), 4),
                },
                "residual_diagnostics": stats_meta["residual_diagnostics"],
                "interpretation": self._interpret_ff3(alpha_annual, beta_mkt, beta_smb, beta_hml)
            }

        except Exception as e:
            logger.error(f"FF3 分析出错: {e}")
            return {"error": str(e)}

    def _run_ff5(self, stock_returns: pd.Series, period: str) -> Dict[str, Any]:
        """Fama-French 五因子回归。"""
        try:
            ff = _fetch_ff5_factors(period)
            if ff.empty:
                return {"error": "无法获取FF5因子数据"}

            aligned = pd.DataFrame({
                "stock": stock_returns,
                "mkt_rf": ff["Mkt-RF"],
                "smb": ff["SMB"],
                "hml": ff["HML"],
                "rmw": ff["RMW"],
                "cma": ff["CMA"],
                "rf": ff["RF"],
            }).dropna()

            if len(aligned) < 30:
                return {"error": "对齐后数据不足30天"}

            y = aligned["stock"] - aligned["rf"]
            X = aligned[["mkt_rf", "smb", "hml", "rmw", "cma"]].values
            X_with_const = np.column_stack([np.ones(len(X)), X])
            coeffs = np.linalg.lstsq(X_with_const, y.values, rcond=None)[0]
            y_pred = X_with_const @ coeffs
            ss_res = np.sum((y.values - y_pred) ** 2)
            ss_tot = np.sum((y.values - y.values.mean()) ** 2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            alpha_annual = coeffs[0] * 252
            stats_meta = self._ols_statistics(y.values, X_with_const, coeffs)

            return {
                "alpha_daily": round(float(coeffs[0]), 6),
                "alpha_annual": round(float(alpha_annual), 4),
                "alpha_pct": round(float(alpha_annual * 100), 2),
                "factor_loadings": {
                    "market": round(float(coeffs[1]), 4),
                    "size": round(float(coeffs[2]), 4),
                    "value": round(float(coeffs[3]), 4),
                    "profitability": round(float(coeffs[4]), 4),
                    "investment": round(float(coeffs[5]), 4),
                },
                "r_squared": round(float(r_squared), 4),
                "data_points": len(aligned),
                "significance": {
                    "alpha_p_value": round(float(stats_meta["p_values"][0]), 4),
                    "profitability_p_value": round(float(stats_meta["p_values"][4]), 4),
                    "investment_p_value": round(float(stats_meta["p_values"][5]), 4),
                },
                "residual_diagnostics": stats_meta["residual_diagnostics"],
                "interpretation": self._interpret_ff5(
                    alpha_annual,
                    coeffs[1],
                    coeffs[2],
                    coeffs[3],
                    coeffs[4],
                    coeffs[5],
                ),
            }
        except Exception as e:
            logger.error(f"FF5 分析出错: {e}")
            return {"error": str(e)}

    def _factor_attribution(self, capm: Dict, ff3: Dict) -> Dict[str, Any]:
        """因子归因分析：解释超额收益的来源"""
        if "error" in capm or "error" in ff3:
            return {"error": "因子模型分析失败，无法进行归因"}

        loadings = ff3.get("factor_loadings", {})
        mkt = loadings.get("market", 0)
        smb = loadings.get("size", 0)
        hml = loadings.get("value", 0)

        # 估算各因子年化贡献 (简化：使用典型年化因子溢价)
        mkt_premium = 0.06   # 市场溢价约 6%
        smb_premium = 0.02   # 规模溢价约 2%
        hml_premium = 0.03   # 价值溢价约 3%

        mkt_contribution = mkt * mkt_premium
        smb_contribution = smb * smb_premium
        hml_contribution = hml * hml_premium
        alpha_contribution = ff3.get("alpha_annual", 0)
        total = mkt_contribution + smb_contribution + hml_contribution + alpha_contribution

        return {
            "total_expected_excess_return": round(total, 4),
            "components": {
                "alpha": {
                    "value": round(alpha_contribution, 4),
                    "pct": round(alpha_contribution * 100, 2),
                    "label": "超额收益 (Alpha)"
                },
                "market": {
                    "value": round(mkt_contribution, 4),
                    "pct": round(mkt_contribution * 100, 2),
                    "label": "市场因子贡献"
                },
                "size": {
                    "value": round(smb_contribution, 4),
                    "pct": round(smb_contribution * 100, 2),
                    "label": "规模因子贡献"
                },
                "value": {
                    "value": round(hml_contribution, 4),
                    "pct": round(hml_contribution * 100, 2),
                    "label": "价值因子贡献"
                }
            }
        }

    def _interpret_capm(self, alpha: float, beta: float, r2: float) -> Dict[str, str]:
        """CAPM 结果解读"""
        # Alpha 解读
        if alpha > 0.05:
            alpha_desc = "显著正Alpha，说明该股票相对市场有超额收益能力"
        elif alpha > 0:
            alpha_desc = "正Alpha，略跑赢市场基准"
        elif alpha > -0.05:
            alpha_desc = "负Alpha，略跑输市场基准"
        else:
            alpha_desc = "显著负Alpha，持续跑输市场"

        # Beta 解读
        if beta > 1.5:
            beta_desc = "高Beta(>1.5)，波动远大于市场，进攻型股票"
        elif beta > 1:
            beta_desc = "Beta>1，波动略大于市场，具有一定攻击性"
        elif beta > 0.5:
            beta_desc = "Beta在0.5-1之间，波动小于市场，偏防御"
        else:
            beta_desc = "低Beta(<0.5)，波动远小于市场，防御型或特殊资产"

        # R² 解读
        if r2 > 0.7:
            r2_desc = "R²高，收益主要由市场系统性风险驱动"
        elif r2 > 0.4:
            r2_desc = "R²中等，市场因素解释部分收益波动"
        else:
            r2_desc = "R²低，收益主要由个股特质因素驱动"

        return {"alpha": alpha_desc, "beta": beta_desc, "r_squared": r2_desc}

    def _interpret_ff3(self, alpha: float, mkt: float, smb: float, hml: float) -> Dict[str, str]:
        """FF3 结果解读"""
        interpretations = {}

        # 市场因子
        if mkt > 1.2:
            interpretations["market"] = "高市场敏感度，牛市跑赢、熊市跑输"
        elif mkt < 0.8:
            interpretations["market"] = "低市场敏感度，受大盘影响较小"
        else:
            interpretations["market"] = "市场敏感度适中，基本跟随大盘"

        # 规模因子
        if smb > 0.3:
            interpretations["size"] = "偏小盘风格，受小盘股溢价驱动"
        elif smb < -0.3:
            interpretations["size"] = "偏大盘风格，体现大盘股特征"
        else:
            interpretations["size"] = "规模因子暴露中性"

        # 价值因子
        if hml > 0.3:
            interpretations["value"] = "偏价值风格，受高账面市值比因子驱动"
        elif hml < -0.3:
            interpretations["value"] = "偏成长风格，表现类似低账面市值比股票"
        else:
            interpretations["value"] = "价值/成长风格中性"

        # Alpha
        if alpha > 0.03:
            interpretations["alpha"] = "三因子模型下仍有显著正Alpha，存在额外收益来源"
        elif alpha < -0.03:
            interpretations["alpha"] = "三因子模型下Alpha为负，风险调整后表现不佳"
        else:
            interpretations["alpha"] = "Alpha接近零，收益可被三因子充分解释"

        return interpretations

    def _interpret_ff5(self, alpha: float, mkt: float, smb: float, hml: float, rmw: float, cma: float) -> Dict[str, str]:
        interpretations = self._interpret_ff3(alpha, mkt, smb, hml)
        if rmw > 0.2:
            interpretations["profitability"] = "盈利能力因子暴露为正，更接近高质量/高盈利企业特征"
        elif rmw < -0.2:
            interpretations["profitability"] = "盈利能力因子暴露为负，更接近低质量或盈利波动较大的企业"
        else:
            interpretations["profitability"] = "盈利能力因子暴露中性"

        if cma > 0.2:
            interpretations["investment"] = "投资因子暴露为正，更接近保守投资风格"
        elif cma < -0.2:
            interpretations["investment"] = "投资因子暴露为负，更接近激进扩张风格"
        else:
            interpretations["investment"] = "投资因子暴露中性"

        return interpretations

    def _generate_summary(self, capm: Dict, ff3: Dict, ff5: Optional[Dict[str, Any]] = None) -> str:
        """生成因子模型分析摘要"""
        parts = []

        if "error" not in capm:
            beta = capm.get("beta", 1)
            alpha_pct = capm.get("alpha_pct", 0)
            if beta > 1:
                parts.append(f"Beta={beta:.2f}(高于市场)")
            else:
                parts.append(f"Beta={beta:.2f}(低于市场)")
            parts.append(f"CAPM Alpha={alpha_pct:.1f}%")

        if "error" not in ff3:
            loadings = ff3.get("factor_loadings", {})
            if loadings.get("size", 0) > 0.2:
                parts.append("偏小盘风格")
            elif loadings.get("size", 0) < -0.2:
                parts.append("偏大盘风格")
            if loadings.get("value", 0) > 0.2:
                parts.append("偏价值风格")
            elif loadings.get("value", 0) < -0.2:
                parts.append("偏成长风格")
            ff3_alpha = ff3.get("alpha_pct", 0)
            parts.append(f"FF3 Alpha={ff3_alpha:.1f}%")

        if ff5 and "error" not in ff5:
            loadings = ff5.get("factor_loadings", {})
            if abs(float(loadings.get("profitability", 0))) > 0.2:
                parts.append("盈利能力暴露显著")
            if abs(float(loadings.get("investment", 0))) > 0.2:
                parts.append("投资风格暴露显著")

        return "，".join(parts) if parts else "因子分析数据不足"

    def _factor_source_meta(self, ff_factors: pd.DataFrame) -> Dict[str, Any]:
        source = ff_factors.attrs.get("source", {}) if ff_factors is not None else {}
        return {
            "type": source.get("type", "unknown"),
            "label": source.get("label", "来源未知"),
            "is_proxy": bool(source.get("is_proxy")),
            "warning": source.get("warning", ""),
        }

    def _ols_statistics(self, y: np.ndarray, design_matrix: np.ndarray, coeffs: np.ndarray) -> Dict[str, Any]:
        residuals = y - design_matrix @ coeffs
        sample_size = len(y)
        param_count = design_matrix.shape[1]
        degrees_of_freedom = max(sample_size - param_count, 1)
        sigma_squared = float(np.sum(residuals ** 2) / degrees_of_freedom)

        xtx_inv = np.linalg.pinv(design_matrix.T @ design_matrix)
        standard_errors = np.sqrt(np.clip(np.diag(sigma_squared * xtx_inv), a_min=1e-12, a_max=None))
        t_stats = np.divide(coeffs, standard_errors, out=np.zeros_like(coeffs), where=standard_errors > 0)
        p_values = 2 * (1 - scipy_stats.t.cdf(np.abs(t_stats), degrees_of_freedom))
        lagged = residuals[:-1]
        shifted = residuals[1:]
        autocorr = float(np.corrcoef(lagged, shifted)[0, 1]) if len(residuals) > 2 and np.std(residuals) > 0 else 0.0
        durbin_watson = float(np.sum(np.diff(residuals) ** 2) / np.sum(residuals ** 2)) if np.sum(residuals ** 2) > 0 else 0.0

        return {
            "standard_errors": standard_errors,
            "t_stats": t_stats,
            "p_values": p_values,
            "residual_diagnostics": {
                "autocorr_lag1": round(autocorr, 4),
                "durbin_watson": round(durbin_watson, 4),
            },
        }

    def _empty_result(self, reason: str) -> Dict[str, Any]:
        return {
            "symbol": "",
            "period": "",
            "data_points": 0,
            "capm": {"error": reason},
            "fama_french": {"error": reason},
            "fama_french_five_factor": {"error": reason},
            "attribution": {"error": reason},
            "summary": reason
        }
