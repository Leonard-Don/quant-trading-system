"""价格预测模块 (`src.analytics.predictor.PricePredictor`) 的单元测试。

这些测试真正实例化并驱动 ``PricePredictor`` —— 特征工程、训练、持久化、
递归预测 —— 并断言其行为契约与不变量；不依赖任何网络或真实行情，全部基于
确定性合成数据 (固定随机种子 + 模型 random_state=42)。

补充 ``test_ai_prediction.py`` 里那条端到端冒烟用例，覆盖更细的契约:
特征无未来泄漏、训练指标结构、模型落盘/加载往返、预测输出不变量、
确定性、以及"预测确实依赖输入数据"的反 mock 校验。
"""

import numpy as np
import pandas as pd
import pytest

from src.analytics.predictor import PricePredictor

# 训练至少需要 50 个有效样本；滚动窗口 (sma20 / rsi14 / volatility20) 会吃掉前 ~20 行,
# next_return 再吃掉最后 1 行,所以用 180 行留出充足余量。
_N_BARS = 180


def _make_ohlcv(*, periods: int = _N_BARS, seed: int = 7, daily_drift: float = 0.0005,
                daily_vol: float = 0.015, base_price: float = 100.0) -> pd.DataFrame:
    """构造确定性的合成 OHLCV 数据 (DatetimeIndex)。

    predict_next_days 依赖 ``index[-1]`` 取最后日期,因此索引必须是 DatetimeIndex。
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start="2023-01-01", periods=periods, freq="D")
    daily_returns = rng.normal(loc=daily_drift, scale=daily_vol, size=periods)
    close = base_price * np.cumprod(1.0 + daily_returns)
    high = close * (1.0 + np.abs(rng.normal(0, 0.006, periods)))
    low = close * (1.0 - np.abs(rng.normal(0, 0.006, periods)))
    open_ = close * (1.0 + rng.normal(0, 0.004, periods))
    volume = rng.integers(1_000_000, 10_000_000, periods).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    return _make_ohlcv()


@pytest.fixture
def predictor(tmp_path) -> PricePredictor:
    # 隔离模型落盘目录,避免污染 src/analytics/model_data。
    return PricePredictor(model_path=str(tmp_path / "rf_model_data"))


# ---------------------------------------------------------------------------
# 特征工程 + 无未来泄漏
# ---------------------------------------------------------------------------


def test_prepare_features_produces_all_feature_columns_without_nan(predictor, ohlcv):
    feat = predictor._prepare_features(ohlcv)

    # 8 个特征列 + 目标列都应存在
    for col in predictor.feature_columns:
        assert col in feat.columns, f"missing feature column {col}"
    assert "next_return" in feat.columns

    # dropna(subset=feature_columns) 之后,特征列内不应再有 NaN
    assert not feat[predictor.feature_columns].isna().any().any()
    # 滚动窗口吃掉前若干行后仍应留下足够样本
    assert len(feat) >= 50


def test_target_is_strictly_forward_looking_and_excluded_from_features(predictor, ohlcv):
    """``next_return`` 必须是 t+1 期收益 (前瞻目标),且绝不能进入特征集。"""
    feat = predictor._prepare_features(ohlcv)

    # 唯一的前瞻列 (next_return) 不在特征列里 —— 否则就是标签泄漏
    assert "next_return" not in predictor.feature_columns

    # next_return[i] 应等于下一行的 returns[i+1]
    aligned = feat[["returns", "next_return"]].dropna()
    assert len(aligned) > 10
    np.testing.assert_allclose(
        aligned["next_return"].to_numpy()[:-1],
        aligned["returns"].to_numpy()[1:],
        rtol=1e-9,
        atol=1e-12,
    )

    # returns 本身是当期 pct_change (后视),抽一行核对
    raw = ohlcv["close"].pct_change()
    sample_date = feat.index[5]
    assert feat.loc[sample_date, "returns"] == pytest.approx(raw.loc[sample_date])


# ---------------------------------------------------------------------------
# 训练契约
# ---------------------------------------------------------------------------


def test_train_returns_metrics_and_sets_state(predictor, ohlcv):
    metrics = predictor.train(ohlcv, "TEST_RF")

    assert set(metrics) >= {
        "mae", "rmse", "direction_accuracy", "train_samples", "test_samples", "trained_at",
    }
    assert metrics["mae"] >= 0.0
    assert metrics["rmse"] >= 0.0
    assert 0.0 <= metrics["direction_accuracy"] <= 100.0
    assert metrics["train_samples"] > metrics["test_samples"] > 0  # 80/20 时序切分

    assert predictor.is_trained is True
    assert predictor.trained_symbol == "TEST_RF"


def test_train_rejects_insufficient_data(predictor):
    too_short = _make_ohlcv(periods=40)
    with pytest.raises(ValueError):
        predictor.train(too_short, "TOO_SHORT")


def test_train_persists_model_and_scaler_to_disk(predictor, ohlcv, tmp_path):
    predictor.train(ohlcv, "PERSIST")
    model_dir = tmp_path / "rf_model_data"
    assert (model_dir / "rf_model_PERSIST.joblib").exists()
    assert (model_dir / "scaler_PERSIST.joblib").exists()


def test_save_load_roundtrip(tmp_path, ohlcv):
    shared_dir = str(tmp_path / "shared_models")
    trainer = PricePredictor(model_path=shared_dir)
    trainer.train(ohlcv, "ROUNDTRIP")

    # 全新实例从磁盘加载同一 symbol 的模型
    loader = PricePredictor(model_path=shared_dir)
    assert loader.is_trained is False
    assert loader.load_model("ROUNDTRIP") is True
    assert loader.is_trained is True
    assert loader.trained_symbol == "ROUNDTRIP"
    # 加载缺失 symbol 返回 False,不抛异常
    assert loader.load_model("NOPE") is False


# ---------------------------------------------------------------------------
# 递归预测输出不变量
# ---------------------------------------------------------------------------


def test_predict_next_days_structure_and_invariants(predictor, ohlcv):
    predictor.train(ohlcv, "PRED")
    out = predictor.predict_next_days(ohlcv, days=5, symbol="PRED")

    assert set(out) >= {
        "dates", "predicted_prices", "confidence_intervals", "currency",
        "prediction_summary", "model_metrics",
    }
    assert len(out["predicted_prices"]) == 5
    assert len(out["dates"]) == 5
    assert len(out["confidence_intervals"]) == 5

    # 价格为正;置信区间上界 >= 下界
    assert all(p > 0 for p in out["predicted_prices"])
    for ci in out["confidence_intervals"]:
        assert ci["upper"] >= ci["lower"]

    summary = out["prediction_summary"]
    assert summary["trend"] in {"bullish", "bearish", "neutral"}
    assert set(summary) >= {
        "trend", "trend_cn", "price_change", "price_change_pct",
        "starting_price", "ending_price", "confidence_score",
    }
    # 日期严格递增
    parsed = [pd.to_datetime(d) for d in out["dates"]]
    assert parsed == sorted(parsed)
    assert parsed[0] > ohlcv.index[-1]


def test_predict_default_horizon_is_five_days(predictor, ohlcv):
    predictor.train(ohlcv, "DEF")
    out = predictor.predict_next_days(ohlcv, symbol="DEF")
    assert len(out["predicted_prices"]) == 5


def test_trend_label_is_consistent_with_price_change(predictor, ohlcv):
    predictor.train(ohlcv, "TREND")
    out = predictor.predict_next_days(ohlcv, days=5, symbol="TREND")
    pct = out["prediction_summary"]["price_change_pct"]
    trend = out["prediction_summary"]["trend"]
    if pct > 1.0:
        assert trend == "bullish"
    elif pct < -1.0:
        assert trend == "bearish"
    else:
        assert trend == "neutral"


# ---------------------------------------------------------------------------
# 确定性 + 反 mock (预测确实依赖输入数据)
# ---------------------------------------------------------------------------


def test_predictions_are_deterministic_with_fixed_seed(tmp_path, ohlcv):
    # random_state=42 固定 → 相同数据训练应给出逐位相同的预测
    a = PricePredictor(model_path=str(tmp_path / "a"))
    b = PricePredictor(model_path=str(tmp_path / "b"))
    a.train(ohlcv, "SYM")
    b.train(ohlcv, "SYM")
    out_a = a.predict_next_days(ohlcv, days=5, symbol="SYM")
    out_b = b.predict_next_days(ohlcv, days=5, symbol="SYM")
    assert out_a["predicted_prices"] == out_b["predicted_prices"]


def test_predictions_depend_on_input_data(tmp_path):
    """不同的输入数据必须产生不同的预测 —— 证明走的是真实模型,而非返回常量。"""
    bullish = _make_ohlcv(seed=1, daily_drift=0.004, daily_vol=0.012)
    bearish = _make_ohlcv(seed=2, daily_drift=-0.004, daily_vol=0.012)

    p1 = PricePredictor(model_path=str(tmp_path / "p1"))
    p2 = PricePredictor(model_path=str(tmp_path / "p2"))
    p1.train(bullish, "BULL")
    p2.train(bearish, "BEAR")
    out1 = p1.predict_next_days(bullish, days=5, symbol="BULL")
    out2 = p2.predict_next_days(bearish, days=5, symbol="BEAR")

    assert out1["predicted_prices"] != out2["predicted_prices"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
