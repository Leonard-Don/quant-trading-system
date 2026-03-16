import akshare as ak
import pandas as pd
try:
    df = ak.stock_board_industry_name_ths()
    if not df.empty:
        symbol = df.iloc[0]['code']
        name = df.iloc[0]['name']
        print(f"Testing {name} ({symbol})...")
        hist = ak.stock_board_industry_index_ths(symbol=symbol)
        print("History head:")
        print(hist.head())
    else:
        print("Industry list is empty")
except Exception as e:
    print(f"Error: {e}")
