#!/usr/bin/env python3
"""
系统测试脚本 - 前后端分离版本
"""

import sys
import os
import requests
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# 添加项目根目录到路径
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, project_root)

from src.strategy.strategies import MovingAverageCrossover  # noqa: E402
from src.backtest.backtester import Backtester  # noqa: E402
from src.analytics.dashboard import PerformanceAnalyzer  # noqa: E402


def build_synthetic_ohlcv(periods: int = 80) -> pd.DataFrame:
    """生成稳定的本地行情样本，避免系统测试依赖外部数据源。"""
    dates = pd.date_range(
        datetime.now() - timedelta(days=periods - 1),
        periods=periods,
        freq="D",
    )
    trend = np.linspace(100, 120, periods)
    cycle = np.sin(np.linspace(0, 6 * np.pi, periods)) * 4
    close = trend + cycle
    return pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(periods, 1_000_000),
        },
        index=dates,
    )


def test_core_modules():
    """测试核心模块"""
    print("🧪 测试核心模块...")

    try:
        # 使用本地合成数据测试核心链路，避免外部行情源波动影响默认验证。
        data = build_synthetic_ohlcv()
        assert not data.empty, "数据获取失败"
        assert {"open", "high", "low", "close", "volume"}.issubset(data.columns), "行情样本结构不完整"
        print("✅ 本地行情样本测试通过")

        # 测试策略
        strategy = MovingAverageCrossover(fast_period=5, slow_period=10)
        signals = strategy.generate_signals(data)
        assert len(signals) == len(data), "策略信号生成失败"
        print("✅ 策略模块测试通过")

        # 测试回测引擎
        backtester = Backtester(initial_capital=10000)
        results = backtester.run(strategy, data)
        assert "total_return" in results, "回测结果不完整"
        print("✅ 回测引擎测试通过")

        # 测试分析模块
        analyzer = PerformanceAnalyzer(results)
        metrics = analyzer.calculate_metrics()
        assert "loss_rate" in metrics, "性能分析失败"
        print("✅ 分析模块测试通过")

        return True

    except Exception as e:
        print(f"❌ 核心模块测试失败: {e}")
        return False


def test_backend_api():
    """测试后端API"""
    print("\n🌐 测试后端API...")

    base_url = "http://localhost:8000"

    try:
        # 测试健康检查
        response = requests.get(f"{base_url}/health", timeout=5)
        assert response.status_code == 200, "健康检查失败"
        print("✅ 健康检查通过")

        # 测试策略列表
        response = requests.get(f"{base_url}/strategies", timeout=5)
        assert response.status_code == 200, "策略列表获取失败"
        strategies = response.json()
        assert len(strategies) > 0, "策略列表为空"
        print("✅ 策略列表获取通过")

        return True

    except requests.exceptions.ConnectionError:
        print("⏭️  后端服务未启动，跳过API联通测试")
        return None
    except Exception as e:
        print(f"❌ 后端API测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🚀 开始系统测试...")
    print("=" * 50)

    # 测试核心模块
    core_test_passed = test_core_modules()

    # 测试后端API
    api_test_passed = test_backend_api()

    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    print(f"核心模块: {'✅ 通过' if core_test_passed else '❌ 失败'}")
    if api_test_passed is None:
        api_status = "⏭️ 跳过（服务未启动）"
    else:
        api_status = "✅ 通过" if api_test_passed else "❌ 失败"
    print(f"后端API: {api_status}")

    if core_test_passed and api_test_passed is not False:
        print("\n🎉 核心模块测试通过！")
        if api_test_passed is None:
            print("💡 提示：启动后端服务后可测试API功能")
        return 0
    if core_test_passed:
        print("\n⚠️  后端API测试失败，请检查正在运行的服务")
        return 1
    else:
        print("\n⚠️  核心模块测试失败，请检查系统配置")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
