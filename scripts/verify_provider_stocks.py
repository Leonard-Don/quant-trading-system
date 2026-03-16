
import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.providers.akshare_provider import AKShareProvider

# Configure logging
logging.basicConfig(level=logging.INFO)

def verify_provider():
    print("Initializing Provider...")
    provider = AKShareProvider()
    
    # Warm up cache (optional but helpful for the first call in script)
    # The provider lazily loads metadata
    
    industry_name = "白酒"
    print(f"Fetching stocks for '{industry_name}' via Provider...")
    
    stocks = provider.get_stock_list_by_industry(industry_name)
    
    if not stocks:
        print(f"FAIL: No stocks found for '{industry_name}'")
    else:
        print(f"SUCCESS: Found {len(stocks)} stocks for '{industry_name}'")
        print("Sample:", stocks[:2])

if __name__ == "__main__":
    verify_provider()
