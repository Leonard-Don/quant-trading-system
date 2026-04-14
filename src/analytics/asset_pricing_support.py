"""
资产定价 support helpers
提取统计计算、结果解读和摘要生成逻辑，降低主引擎文件复杂度。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from src.data.data_manager import DataManager


DEFAULT_FACTOR_PREMIA = {
    "market": 0.06,
    "size": 0.02,
    "value": 0.03,
}

FACTOR_PREMIUM_BOUNDS = {
    "market": (-0.12, 0.18),
    "size": (-0.08, 0.08),
    "value": (-0.08, 0.08),
}


def normalize_daily_index(data: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Normalize market time series to a tz-naive daily DatetimeIndex."""
    if data is None or data.empty:
        return data

    normalized = data.copy()
    index = pd.to_datetime(normalized.index)
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    normalized.index = index.normalize()
    return normalized.sort_index()


def period_to_days(period: str) -> int:
    """将 period 字符串转换为天数"""
    mapping = {"6mo": 180, "1y": 365, "2y": 730, "3y": 1095, "5y": 1825}
    return mapping.get(period, 365)


def estimate_ff_factors(period: str, logger: Any) -> pd.DataFrame:
    """若网络获取失败，使用市场指数代理估算因子。"""
    dm = DataManager()
    days = period_to_days(period)
    start = datetime.now() - timedelta(days=days)

    try:
        sp500 = dm.get_historical_data("^GSPC", start_date=start)
        if sp500.empty:
            return pd.DataFrame()

        mkt_rf = sp500["close"].pct_change().dropna()
        rf = 0.05 / 252
        short_momentum = mkt_rf.rolling(5, min_periods=1).mean()
        medium_momentum = mkt_rf.rolling(20, min_periods=1).mean()
        long_momentum = mkt_rf.rolling(60, min_periods=1).mean()
        smb_proxy = ((short_momentum - medium_momentum) * 0.6).clip(-0.02, 0.02)
        hml_proxy = ((medium_momentum - long_momentum) * -0.5).clip(-0.02, 0.02)

        df = pd.DataFrame({
            "Mkt-RF": mkt_rf - rf,
            "SMB": smb_proxy,
            "HML": hml_proxy,
            "RF": rf,
        }, index=mkt_rf.index)
        df = normalize_daily_index(df)
        df.attrs["source"] = {
            "type": "market_proxy",
            "label": "市场代理估算",
            "is_proxy": True,
            "warning": "SMB/HML 采用市场动量代理构造，结果仅供参考。",
        }

        logger.info("Using proxy FF factors (estimated)")
        return df
    except Exception as exc:
        logger.error(f"因子数据估算失败: {exc}")
        return pd.DataFrame()


def estimate_ff5_factors(period: str, logger: Any) -> pd.DataFrame:
    """五因子代理估算，保证结果可复现并显式标注为代理值。"""
    ff3 = estimate_ff_factors(period, logger)
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


def fetch_ff_factors(ff_cache: Dict[str, Any], period: str, logger: Any) -> pd.DataFrame:
    """
    获取 Fama-French 三因子数据，失败时回退到代理估算。
    """
    cache_key = f"ff3_{period}"
    if cache_key in ff_cache:
        cached = ff_cache[cache_key]
        if (datetime.now() - cached["ts"]).total_seconds() < 86400:
            return cached["data"]

    try:
        import pandas_datareader.data as web

        ff = web.DataReader(
            "F-F_Research_Data_Factors_daily",
            "famafrench",
            start=datetime.now() - timedelta(days=period_to_days(period)),
        )
        df = ff[0] / 100.0
        df.index = pd.to_datetime(df.index)
        df = normalize_daily_index(df)
        df.attrs["source"] = {
            "type": "kenneth_french_library",
            "label": "Kenneth French Data Library",
            "is_proxy": False,
            "warning": "",
        }
        ff_cache[cache_key] = {"data": df, "ts": datetime.now()}
        logger.info(f"Fetched Fama-French factors: {len(df)} days")
        return df
    except Exception as exc:
        logger.warning(f"无法从 Kenneth French Library 获取因子数据: {exc}")
        return estimate_ff_factors(period, logger)


def fetch_ff5_factors(ff_cache: Dict[str, Any], period: str, logger: Any) -> pd.DataFrame:
    """获取 Fama-French 五因子数据，失败时回退到代理估算。"""
    cache_key = f"ff5_{period}"
    if cache_key in ff_cache:
        cached = ff_cache[cache_key]
        if (datetime.now() - cached["ts"]).total_seconds() < 86400:
            return cached["data"]

    try:
        import pandas_datareader.data as web

        ff = web.DataReader(
            "F-F_Research_Data_5_Factors_2x3_daily",
            "famafrench",
            start=datetime.now() - timedelta(days=period_to_days(period)),
        )
        df = ff[0] / 100.0
        df.index = pd.to_datetime(df.index)
        df = normalize_daily_index(df)
        df.attrs["source"] = {
            "type": "kenneth_french_library",
            "label": "Kenneth French 5-Factor Library",
            "is_proxy": False,
            "warning": "",
        }
        ff_cache[cache_key] = {"data": df, "ts": datetime.now()}
        return df
    except Exception as exc:
        logger.warning(f"无法从 Kenneth French Library 获取五因子数据: {exc}")
        return estimate_ff5_factors(period, logger)


def interpret_capm(alpha: float, beta: float, r2: float) -> Dict[str, str]:
    """CAPM 结果解读"""
    if alpha > 0.05:
        alpha_desc = "显著正Alpha，说明该股票相对市场有超额收益能力"
    elif alpha > 0:
        alpha_desc = "正Alpha，略跑赢市场基准"
    elif alpha > -0.05:
        alpha_desc = "负Alpha，略跑输市场基准"
    else:
        alpha_desc = "显著负Alpha，持续跑输市场"

    if beta > 1.5:
        beta_desc = "高Beta(>1.5)，波动远大于市场，进攻型股票"
    elif beta > 1:
        beta_desc = "Beta>1，波动略大于市场，具有一定攻击性"
    elif beta > 0.5:
        beta_desc = "Beta在0.5-1之间，波动小于市场，偏防御"
    else:
        beta_desc = "低Beta(<0.5)，波动远小于市场，防御型或特殊资产"

    if r2 > 0.7:
        r2_desc = "R²高，收益主要由市场系统性风险驱动"
    elif r2 > 0.4:
        r2_desc = "R²中等，市场因素解释部分收益波动"
    else:
        r2_desc = "R²低，收益主要由个股特质因素驱动"

    return {"alpha": alpha_desc, "beta": beta_desc, "r_squared": r2_desc}


def interpret_ff3(alpha: float, mkt: float, smb: float, hml: float) -> Dict[str, str]:
    """FF3 结果解读"""
    interpretations: Dict[str, str] = {}

    if mkt > 1.2:
        interpretations["market"] = "高市场敏感度，牛市跑赢、熊市跑输"
    elif mkt < 0.8:
        interpretations["market"] = "低市场敏感度，受大盘影响较小"
    else:
        interpretations["market"] = "市场敏感度适中，基本跟随大盘"

    if smb > 0.3:
        interpretations["size"] = "偏小盘风格，受小盘股溢价驱动"
    elif smb < -0.3:
        interpretations["size"] = "偏大盘风格，体现大盘股特征"
    else:
        interpretations["size"] = "规模因子暴露中性"

    if hml > 0.3:
        interpretations["value"] = "偏价值风格，受高账面市值比因子驱动"
    elif hml < -0.3:
        interpretations["value"] = "偏成长风格，表现类似低账面市值比股票"
    else:
        interpretations["value"] = "价值/成长风格中性"

    if alpha > 0.03:
        interpretations["alpha"] = "三因子模型下仍有显著正Alpha，存在额外收益来源"
    elif alpha < -0.03:
        interpretations["alpha"] = "三因子模型下Alpha为负，风险调整后表现不佳"
    else:
        interpretations["alpha"] = "Alpha接近零，收益可被三因子充分解释"

    return interpretations


def interpret_ff5(alpha: float, mkt: float, smb: float, hml: float, rmw: float, cma: float) -> Dict[str, str]:
    interpretations = interpret_ff3(alpha, mkt, smb, hml)
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


def generate_factor_summary(capm: Dict[str, Any], ff3: Dict[str, Any], ff5: Optional[Dict[str, Any]] = None) -> str:
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


def factor_source_meta(ff_factors: pd.DataFrame) -> Dict[str, Any]:
    source = ff_factors.attrs.get("source", {}) if ff_factors is not None else {}
    return {
        "type": source.get("type", "unknown"),
        "label": source.get("label", "来源未知"),
        "is_proxy": bool(source.get("is_proxy")),
        "warning": source.get("warning", ""),
    }


def annualized_factor_premia(ff_factors: Optional[pd.DataFrame], trading_days: int = 252) -> Dict[str, Any]:
    """
    基于当前窗口的因子数据动态估算年化因子溢价。

    优先使用真实 Kenneth French 因子；若当前窗口数据不足或仅有代理值，则回退到长期默认假设。
    """
    source_meta = factor_source_meta(ff_factors)
    fallback = {
        "values": DEFAULT_FACTOR_PREMIA.copy(),
        "source": "long_term_defaults",
        "label": "长期默认因子溢价",
        "window_days": 0,
        "is_proxy": bool(source_meta.get("is_proxy")),
    }
    if ff_factors is None or ff_factors.empty or source_meta.get("is_proxy"):
        return fallback

    columns = {
        "market": "Mkt-RF",
        "size": "SMB",
        "value": "HML",
    }
    clean = ff_factors[[column for column in columns.values() if column in ff_factors.columns]].dropna()
    if len(clean) < 30:
        return fallback

    values = {}
    for key, column in columns.items():
        if column not in clean.columns:
            values[key] = DEFAULT_FACTOR_PREMIA[key]
            continue
        annualized = float(clean[column].mean() * trading_days)
        low, high = FACTOR_PREMIUM_BOUNDS[key]
        values[key] = float(np.clip(annualized, low, high))

    return {
        "values": values,
        "source": "rolling_realized_window",
        "label": "滚动窗口年化因子溢价",
        "window_days": int(len(clean)),
        "is_proxy": False,
    }


def safe_linear_prediction(design_matrix: np.ndarray, coeffs: np.ndarray) -> np.ndarray:
    matrix = np.asarray(design_matrix, dtype=np.float64)
    weights = np.asarray(coeffs, dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        predicted = matrix @ weights
    return np.nan_to_num(predicted, nan=0.0, posinf=0.0, neginf=0.0)


def safe_regression_metrics(
    y: np.ndarray,
    design_matrix: np.ndarray,
    coeffs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    target = np.nan_to_num(np.asarray(y, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    predicted = safe_linear_prediction(design_matrix, coeffs)
    residuals = np.nan_to_num(target - predicted, nan=0.0, posinf=0.0, neginf=0.0)
    ss_res = float(np.sum(residuals ** 2))
    centered = target - float(target.mean()) if target.size else target
    ss_tot = float(np.sum(centered ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return predicted, residuals, float(np.clip(r_squared, -1.0, 1.0))


def ols_statistics(y: np.ndarray, design_matrix: np.ndarray, coeffs: np.ndarray) -> Dict[str, Any]:
    _, residuals, _ = safe_regression_metrics(y, design_matrix, coeffs)
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


def empty_asset_pricing_result(reason: str) -> Dict[str, Any]:
    return {
        "symbol": "",
        "period": "",
        "data_points": 0,
        "capm": {"error": reason},
        "fama_french": {"error": reason},
        "fama_french_five_factor": {"error": reason},
        "attribution": {"error": reason},
        "summary": reason,
    }
