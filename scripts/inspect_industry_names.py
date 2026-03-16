import akshare as ak
import pandas as pd

def inspect_industries():
    print("Fetching industry list...")
    try:
        df = ak.stock_board_industry_name_em()
        print(f"Total rows: {len(df)}")
        print("Columns:", df.columns.tolist())
        
        keywords = ["银行", "证券", "保险", "半导体"]
        
        for keyword in keywords:
            print(f"\nScanning for '{keyword}':")
            matches = df[df['板块名称'].str.contains(keyword, na=False)]
            if not matches.empty:
                print(matches[['板块名称', '板块代码']].to_string())
            else:
                print("No matches found.")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_industries()
