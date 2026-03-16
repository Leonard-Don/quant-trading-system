import sys
import os
import asyncio
import logging

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.data.providers.sina_ths_adapter import SinaIndustryAdapter
from src.analytics.industry_analyzer import IndustryAnalyzer

async def test_merged_stock_list():
    print("--- Testing Merged Stock List ---")
    provider = SinaIndustryAdapter()
    # Test a target sector like "Liquor" (白酒)
    name = "白酒"
    stocks = provider.get_stock_list_by_industry(name)
    print(f"Found {len(stocks)} stocks for {name}")
    if stocks:
        print(f"Sample: {stocks[0]['name']} ({stocks[0]['symbol']})")
    
    analyzer = IndustryAnalyzer(provider)
    trend = analyzer.get_industry_trend(name)
    print(f"Trend Analysis for {name}:")
    print(f"  Stock Count: {trend.get('stock_count')}")
    print(f"  Rise/Fall/Flat: {trend.get('rise_count')}/{trend.get('fall_count')}/{trend.get('flat_count')}")
    print(f"  Note: {trend.get('note')}")
    print(f"  Degraded: {trend.get('degraded')}")

if __name__ == "__main__":
    asyncio.run(test_merged_stock_list())
