
import akshare as ak
import pandas as pd
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_fetch(industry_name):
    print(f"Fetching stocks for industry: '{industry_name}'")
    try:
        df = ak.stock_board_industry_cons_em(symbol=industry_name)
        if df.empty:
            print(f"RESULT: Empty dataframe for '{industry_name}'")
        else:
            print(f"RESULT: Found {len(df)} stocks for '{industry_name}'")
            print(df.head(3))
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_fetch("白酒")
    test_fetch("白酒Ⅱ")
