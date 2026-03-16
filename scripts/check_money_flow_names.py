
import akshare as ak
import pandas as pd

def check_names():
    print("Fetching money flow rank...")
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="5日")
        if df.empty:
            print("Empty dataframe")
            return
            
        print("Columns:", df.columns)
        # Usually "名称" is the name column
        if "名称" in df.columns:
            names = df["名称"].tolist()
            print(f"Total rows: {len(names)}")
            
            liquor = [n for n in names if "酒" in n]
            print("Liquor related names in Money Flow:", liquor)
            
            bank = [n for n in names if "银行" in n]
            print("Bank related names:", bank)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_names()
