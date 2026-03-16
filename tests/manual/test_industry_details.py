import sys
import os
import pandas as pd
import akshare as ak
import time
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.getcwd())

def test_industry_stocks(name):
    print(f"--- Testing Industry: {name} ---")
    try:
        start_time = time.time()
        df = ak.stock_board_industry_cons_em(symbol=name)
        elapsed = time.time() - start_time
        print(f"Fetched {len(df)} stocks in {elapsed:.2f}s")
        if not df.empty:
            print("Columns:", df.columns.tolist())
            print("First few rows:")
            print(df.head(3))
        else:
            print("Empty result returned from AKShare.")
    except Exception as e:
        print(f"Error: {e}")

def test_leader_stocks_cold_start():
    print("\n--- Testing Leader Stock Cold Start ---")
    from src.data.providers.sina_ths_adapter import SinaIndustryAdapter
    from src.analytics.leader_stock_scorer import LeaderStockScorer
    
    provider = SinaIndustryAdapter()
    scorer = LeaderStockScorer(provider)
    
    start_time = time.time()
    # Mocking what get_hot_leader_stocks does
    print("Getting hot industries...")
    from src.analytics.industry_analyzer import IndustryAnalyzer
    analyzer = IndustryAnalyzer(provider)
    hot_industries = analyzer.rank_industries(top_n=5)
    print(f"Got {len(hot_industries)} industries")
    
    for ind in hot_industries:
        name = ind['industry_name']
        print(f"Scoring leaders for {name}...")
        sub_start = time.time()
        # This is where the slowness usually is
        candidates = provider.get_stock_list_by_industry(name)
        print(f"Found {len(candidates)} candidates for {name}")
        if candidates:
            # Only score one to see speed - actually the slowness is often the per-stock details
            pass
        print(f"Industry {name} took {time.time() - sub_start:.2f}s")
        
    print(f"Total cold start test took {time.time() - start_time:.2f}s")

if __name__ == "__main__":
    # Test a few potentially problematic industries
    test_industry_stocks("白酒")
    test_industry_stocks("房地产开发")
    test_industry_stocks("贵州茅台") # This is a stock, not an industry, but let's see
    
    # Test cold start
    test_leader_stocks_cold_start()
