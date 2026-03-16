
import sys
import os
import json
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.data_manager import DataManager
from src.strategy.strategies import MovingAverageCrossover
from src.backtest.backtester import Backtester
from src.utils.data_validation import validate_and_fix_backtest_results, ensure_json_serializable

def debug_backtest():
    print("🚀 Starting Backtest Debug...")
    
    # 1. Fetch Data
    dm = DataManager()
    data = dm.get_historical_data("AAPL", start_date=datetime(2023, 1, 1), end_date=datetime(2023, 12, 1))
    print(f"✅ Data fetched: {len(data)} rows")
    print(f"Index name: {data.index.name}")
    
    # 2. Run Strategy
    strategy = MovingAverageCrossover(fast_period=10, slow_period=20)
    backtester = Backtester(initial_capital=10000)
    results = backtester.run(strategy, data)
    print("✅ Backtest run complete")

    # 3. Validate
    try:
        results = validate_and_fix_backtest_results(results)
        print("✅ Validation passed")
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return

    # 4. Serialize
    json_results = ensure_json_serializable(results)
    
    # 5. Inspect Portfolio Structure
    portfolio = json_results.get("portfolio", [])
    if not portfolio:
        print("❌ Portfolio is empty!")
        return
        
    first_item = portfolio[0]
    print("\n🔍 First Portfolio Item Structure:")
    for k, v in first_item.items():
        print(f"  {k}: {v} (Type: {type(v)})")

    # Check specifically for 'date'
    if "date" in first_item:
        print(f"\n✅ Found 'date' key: {first_item['date']}")
    elif "Date" in first_item:
        print(f"\n⚠️ Found 'Date' key but frontend might expect 'date': {first_item['Date']}")
    else:
        print("\n❌ NO 'date' KEY FOUND in portfolio item keys:", list(first_item.keys()))

if __name__ == "__main__":
    debug_backtest()
