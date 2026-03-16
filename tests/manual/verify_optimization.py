import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__name__)))
from src.data.providers.sina_ths_adapter import create_industry_provider
from src.analytics.industry_analyzer import IndustryAnalyzer
import pandas as pd

provider = create_industry_provider()
analyzer = IndustryAnalyzer(provider)

print("--- Testing Money Flow with Expanded Mappings ---")
df = provider.get_industry_money_flow(days=5)
print(f"Columns: {df.columns.tolist()}")
print(f"Industries count: {len(df)}")
# Check for a specific mapped name
internet = df[df['industry_name'] == '互联网服务']
print(f"Internet service found: {not internet.empty}")
if not internet.empty:
    print(internet[['industry_name', 'pe_ttm', 'pb']].to_string())

print("\n--- Testing 4D Clustering ---")
clusters = analyzer.cluster_hot_industries(n_clusters=4)
if clusters['points']:
    p = clusters['points'][0]
    print(f"Cluster point sample keys: {p.keys()}")
    print(f"PE: {p.get('pe_ttm')}, PB: {p.get('pb')}")
else:
    print("No cluster points generated")
