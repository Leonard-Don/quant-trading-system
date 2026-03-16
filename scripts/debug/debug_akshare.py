
import akshare as ak
import pandas as pd
import os

# Bypass proxy for akshare
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

try:
    print("Fetching stock_sector_fund_flow_rank...")
    df = ak.stock_sector_fund_flow_rank(indicator="今日")
    print("Columns:", df.columns.tolist())
    print("First row:", df.iloc[0].to_dict() if not df.empty else "Empty")
except Exception as e:
    print("Error:", e)
