
import akshare as ak
import pandas as pd
import os

# Bypass proxy for akshare
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

try:
    print("Fetching stock_board_industry_name_em...")
    df = ak.stock_board_industry_name_em()
    print("Columns:", df.columns.tolist())
    print("First row:", df.iloc[0].to_dict() if not df.empty else "Empty")
except Exception as e:
    print("Error stock_board_industry_name_em:", e)

print("-" * 20)

try:
    print("Fetching stock_board_industry_summary_ths...")
    df = ak.stock_board_industry_summary_ths()
    print("Columns:", df.columns.tolist())
    print("First row:", df.iloc[0].to_dict() if not df.empty else "Empty")
except Exception as e:
    print("Error stock_board_industry_summary_ths:", e)
