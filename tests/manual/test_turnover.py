import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__name__)))
from src.data.providers.sina_ths_adapter import create_industry_provider
provider = create_industry_provider()
df = provider.get_industry_money_flow(days=5)
print("columns:", df.columns.tolist() if not df.empty else "empty df")
print("total_market_cap:", df["total_market_cap"].head().tolist() if not df.empty and "total_market_cap" in df.columns else "None")
print("total_inflow:", df["total_inflow"].head().tolist() if not df.empty and "total_inflow" in df.columns else "None")
print("total_outflow:", df["total_outflow"].head().tolist() if not df.empty and "total_outflow" in df.columns else "None")
print("turnover_rate:", df["turnover_rate"].head().tolist() if not df.empty and "turnover_rate" in df.columns else "None")
