#!/usr/bin/env python
"""
测试股票分析功能
"""

from src.analytics.comprehensive_scorer import ComprehensiveScorer
from src.data.data_manager import DataManager
from datetime import datetime, timedelta

def test_comprehensive_analysis():
    """测试综合分析功能"""
    print("=" * 60)
    print("测试股票综合分析功能")
    print("=" * 60)

    # 初始化
    data_manager = DataManager()
    scorer = ComprehensiveScorer()

    # 测试股票
    symbol = "AAPL"
    print(f"\n正在获取 {symbol} 的数据...")

    # 获取最近3个月的数据
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)

    data = data_manager.get_historical_data(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date
    )

    if data.empty:
        print(f"错误：无法获取 {symbol} 的数据")
        return

    print(f"成功获取 {len(data)} 条数据")
    print(f"数据范围: {data.index[0]} 到 {data.index[-1]}")

    # 执行综合分析
    print(f"\n正在执行综合分析...")
    result = scorer.comprehensive_analysis(data, symbol)

    # 打印结果
    print("\n" + "=" * 60)
    print("分析结果")
    print("=" * 60)

    print(f"\n【综合评分】: {result['overall_score']}/100")
    print(f"【投资建议】: {result['recommendation']}")
    print(f"【置信度】: {result['confidence']}")

    print(f"\n【各维度得分】:")
    scores = result['scores']
    print(f"  - 趋势得分: {scores['trend']}/100")
    print(f"  - 量价得分: {scores['volume']}/100")
    print(f"  - 情绪得分: {scores['sentiment']}/100")
    print(f"  - 技术得分: {scores['technical']}/100")

    print(f"\n【趋势分析】:")
    trend = result['trend_analysis']
    print(f"  - 趋势方向: {trend['trend']}")
    print(f"  - 趋势强度: {trend.get('trend_strength', 'N/A')}")
    print(f"  - 支撑位: {trend['support_levels']}")
    print(f"  - 阻力位: {trend['resistance_levels']}")

    print(f"\n【关键信号】:")
    for signal in result['key_signals']:
        print(f"  - [{signal['type']}] {signal['signal']} (重要性: {signal['importance']})")

    if result['risk_warnings']:
        print(f"\n【风险提示】:")
        for warning in result['risk_warnings']:
            print(f"  ⚠️  {warning}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    test_comprehensive_analysis()
