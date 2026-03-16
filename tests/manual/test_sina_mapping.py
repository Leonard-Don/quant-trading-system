from src.data.providers.sina_provider import SinaFinanceProvider
import pandas as pd

p = SinaFinanceProvider()
industries = p.get_industry_list()
# Filter for something containing "酒"
liquor = industries[industries['industry_name'].str.contains('酒', na=False)]
print("Liquor industries in Sina:")
print(liquor)

if not liquor.empty:
    code = liquor.iloc[0]['industry_code']
    print(f"\nFetching stocks for code: {code}")
    stocks = p.get_industry_stocks(code)
    print(f"Found {len(stocks)} stocks")
    if stocks:
        print("First stock sample:", stocks[0])
else:
    print("No liquor industry found in Sina")
