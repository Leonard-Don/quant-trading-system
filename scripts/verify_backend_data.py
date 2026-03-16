
import sys
import os
import time
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.providers.akshare_provider import AKShareProvider
from src.analytics.industry_analyzer import IndustryAnalyzer

def verify_data():
    print("Initializing Provider...")
    provider = AKShareProvider()
    analyzer = IndustryAnalyzer(provider)
    
    print("Fetching Heatmap Data...")
    start_time = time.time()
    data = analyzer.get_industry_heatmap_data()
    end_time = time.time()
    
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    
    if not data or "industries" not in data:
        print("Error: No data returned")
        return
        
    industries = data["industries"]
    print(f"Total industries: {len(industries)}")
    
    # Check for Liquor / White Spirit
    found_liquor = False
    liquor_names = ["白酒", "White Spirit", "Liquor", "白酒II", "白酒Ⅱ"]
    
    for ind in industries[:20]: # Check top 20
        name = ind["name"]
        print(f"Industry: {name}, Size: {ind.get('size')}, Change: {ind.get('value')}")
        if any(x in name for x in liquor_names):
            found_liquor = True
            print(f"Found Liquor Industry: '{name}'")
            if "Ⅱ" in name or "II" in name:
                print("FAIL: Roman numeral suffix still present!")
            else:
                print("SUCCESS: Name is clean.")

    print("\nSearching for all Liquor-related industries:")
    liquor_found = False
    for ind in industries:
        name = ind["name"]
        if any(x in name for x in liquor_names):
            print(f"Found: '{name}', Size: {ind.get('size')}")
            liquor_found = True
            
    if not liquor_found:
        print("CRITICAL: No Liquor industry found!")

if __name__ == "__main__":
    verify_data()
