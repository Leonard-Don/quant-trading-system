#!/usr/bin/env python3
"""
性能测试脚本
"""
import sys
import time
import psutil
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.data_manager import DataManager  # noqa: E402
from src.strategy.strategies import MovingAverageCrossover, RSIStrategy  # noqa: E402
from src.strategy.advanced_strategies import (  # noqa: E402
    MACDStrategy,
    MeanReversionStrategy,
)
from src.backtest.backtester import Backtester  # noqa: E402
from src.utils.cache import cache_manager  # noqa: E402


class PerformanceTester:
    """性能测试器"""

    def __init__(self):
        self.results = {}
        self.dm = DataManager()

    def measure_time(self, func, *args, **kwargs):
        """测量函数执行时间"""
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        result = func(*args, **kwargs)

        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        return {
            "result": result,
            "execution_time": end_time - start_time,
            "memory_used": end_memory - start_memory,
            "start_memory": start_memory,
            "end_memory": end_memory,
        }

    def test_data_fetching(self):
        """测试数据获取性能"""
        print("🔍 测试数据获取性能...")

        # 测试小数据集
        small_data_test = self.measure_time(
            self.dm.get_stock_data, "AAPL", "2024-01-01", "2024-01-31"
        )

        # 测试大数据集
        large_data_test = self.measure_time(
            self.dm.get_stock_data, "AAPL", "2023-01-01", "2024-01-31"
        )

        # 测试缓存性能
        cache_test = self.measure_time(
            self.dm.get_stock_data, "AAPL", "2023-01-01", "2024-01-31"  # 应该从缓存获取
        )

        self.results["data_fetching"] = {
            "small_dataset": {
                "time": small_data_test["execution_time"],
                "memory": small_data_test["memory_used"],
                "records": (
                    len(small_data_test["result"])
                    if not small_data_test["result"].empty
                    else 0
                ),
            },
            "large_dataset": {
                "time": large_data_test["execution_time"],
                "memory": large_data_test["memory_used"],
                "records": (
                    len(large_data_test["result"])
                    if not large_data_test["result"].empty
                    else 0
                ),
            },
            "cache_hit": {
                "time": cache_test["execution_time"],
                "memory": cache_test["memory_used"],
                "speedup": (
                    large_data_test["execution_time"] / cache_test["execution_time"]
                    if cache_test["execution_time"] > 0
                    else 0
                ),
            },
        }

        small_time = small_data_test["execution_time"]
        small_mem = small_data_test["memory_used"]
        print(f"   小数据集: {small_time: .3f}s, {small_mem: .1f}MB")

        large_time = large_data_test["execution_time"]
        large_mem = large_data_test["memory_used"]
        print(f"   大数据集: {large_time: .3f}s, {large_mem: .1f}MB")

        cache_time = cache_test["execution_time"]
        speedup = self.results["data_fetching"]["cache_hit"]["speedup"]
        print(f"   缓存命中: {cache_time: .3f}s, 加速比: {speedup: .1f}x")

    def test_strategy_performance(self):
        """测试策略性能"""
        print("📊 测试策略性能...")

        # 准备测试数据
        data = self.dm.get_stock_data("AAPL", "2023-01-01", "2024-01-31")
        if data.empty:
            print("   ⚠️ 无法获取测试数据，跳过策略测试")
            return

        strategies = [
            ("MovingAverage", MovingAverageCrossover(10, 30)),
            ("RSI", RSIStrategy(14, 30, 70)),
            ("MACD", MACDStrategy(12, 26, 9)),
            ("MeanReversion", MeanReversionStrategy(20, 2.0)),
        ]

        self.results["strategies"] = {}

        for name, strategy in strategies:
            test_result = self.measure_time(strategy.generate_signals, data)

            self.results["strategies"][name] = {
                "time": test_result["execution_time"],
                "memory": test_result["memory_used"],
                "signals_generated": (
                    len(test_result["result"])
                    if hasattr(test_result["result"], "__len__")
                    else 0
                ),
            }

            print(
                f"   {name}: {test_result['execution_time']: .3f}s, "
                f"{test_result['memory_used']: .1f}MB"
            )

    def test_backtest_performance(self):
        """测试回测性能"""
        print("⚡ 测试回测性能...")

        # 准备测试数据
        data = self.dm.get_stock_data("AAPL", "2023-01-01", "2024-01-31")
        if data.empty:
            print("   ⚠️ 无法获取测试数据，跳过回测测试")
            return

        strategy = MovingAverageCrossover(10, 30)
        backtester = Backtester(initial_capital=10000)

        # 测试不同数据量的回测性能
        data_sizes = [
            ("1个月", data.iloc[-30:] if len(data) > 30 else data),
            ("3个月", data.iloc[-90:] if len(data) > 90 else data),
            ("1年", data),
        ]

        self.results["backtest"] = {}

        for size_name, test_data in data_sizes:
            if test_data.empty:
                continue

            test_result = self.measure_time(backtester.run, strategy, test_data)

            self.results["backtest"][size_name] = {
                "time": test_result["execution_time"],
                "memory": test_result["memory_used"],
                "data_points": len(test_data),
                "trades": (
                    test_result["result"].get("num_trades", 0)
                    if test_result["result"]
                    else 0
                ),
            }

            exec_time = test_result["execution_time"]
            mem_used = test_result["memory_used"]
            data_count = len(test_data)
            print(
                f"   {size_name} ({data_count}条): {exec_time: .3f}s, {mem_used: .1f}MB"
            )

    def test_cache_performance(self):
        """测试缓存性能"""
        print("💾 测试缓存性能...")

        # 清空缓存
        cache_manager.clear()

        # 测试缓存设置性能
        test_data = {"test": list(range(1000))}

        set_test = self.measure_time(cache_manager.set, "test_key", test_data)
        get_test = self.measure_time(cache_manager.get, "test_key")

        # 测试缓存统计
        stats = cache_manager.get_stats()

        self.results["cache"] = {
            "set_time": set_test["execution_time"],
            "get_time": get_test["execution_time"],
            "stats": stats,
        }

        print(f"   设置: {set_test['execution_time']: .6f}s")
        print(f"   获取: {get_test['execution_time']: .6f}s")
        print(f"   命中率: {stats['hit_rate']: .1%}")

    def test_memory_usage(self):
        """测试内存使用情况"""
        print("🧠 测试内存使用...")

        process = psutil.Process()
        memory_info = process.memory_info()

        self.results["memory"] = {
            "rss": memory_info.rss / 1024 / 1024,  # MB
            "vms": memory_info.vms / 1024 / 1024,  # MB
            "percent": process.memory_percent(),
        }

        print(f"   RSS内存: {self.results['memory']['rss']: .1f}MB")
        print(f"   虚拟内存: {self.results['memory']['vms']: .1f}MB")
        print(f"   内存占用: {self.results['memory']['percent']: .1f}%")

    def generate_report(self):
        """生成性能报告"""
        print("\n" + "=" * 60)
        print("📋 性能测试报告")
        print("=" * 60)

        # 数据获取性能
        if "data_fetching" in self.results:
            print("\n📊 数据获取性能: ")
            df = self.results["data_fetching"]
            print(
                f"   小数据集: {df['small_dataset']['time']: .3f}s "
                f"({df['small_dataset']['records']}条记录)"
            )
            print(
                f"   大数据集: {df['large_dataset']['time']: .3f}s "
                f"({df['large_dataset']['records']}条记录)"
            )
            print(f"   缓存加速: {df['cache_hit']['speedup']: .1f}x")

        # 策略性能
        if "strategies" in self.results:
            print("\n⚡ 策略性能: ")
            for name, data in self.results["strategies"].items():
                print(f"   {name}: {data['time']: .3f}s")

        # 回测性能
        if "backtest" in self.results:
            print("\n🔄 回测性能: ")
            for size, data in self.results["backtest"].items():
                throughput = (
                    data["data_points"] / data["time"] if data["time"] > 0 else 0
                )
                print(f"   {size}: {data['time']: .3f}s ({throughput: .0f} 条/秒)")

        # 缓存性能
        if "cache" in self.results:
            print("\n💾 缓存性能: ")
            cache_data = self.results["cache"]
            print(f"   设置延迟: {cache_data['set_time'] * 1000: .2f}ms")
            print(f"   获取延迟: {cache_data['get_time'] * 1000: .2f}ms")
            print(f"   命中率: {cache_data['stats']['hit_rate']: .1%}")

        # 内存使用
        if "memory" in self.results:
            print("\n🧠 内存使用: ")
            mem_data = self.results["memory"]
            print(f"   当前RSS: {mem_data['rss']: .1f}MB")
            print(f"   系统占用: {mem_data['percent']: .1f}%")

        print("\n" + "=" * 60)
        print("测试完成时间: ", datetime.now().strftime("%Y-%m-%d %H: %M: %S"))
        print("=" * 60)

    def run_all_tests(self):
        """运行所有性能测试"""
        print("🚀 开始性能测试...")
        print("=" * 60)

        start_time = time.time()

        try:
            self.test_data_fetching()
            self.test_strategy_performance()
            self.test_backtest_performance()
            self.test_cache_performance()
            self.test_memory_usage()
        except Exception as e:
            print(f"❌ 测试过程中出现错误: {e}")
            import traceback

            traceback.print_exc()

        total_time = time.time() - start_time
        print(f"\n⏱️ 总测试时间: {total_time: .2f}秒")

        self.generate_report()


def main():
    """主函数"""
    tester = PerformanceTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
