
import requests
import sys
import json

# API Base URL
API_URL = "http://localhost:8000"

def verify_heatmap_data():
    print(f"Fetching heatmap data from {API_URL}/industry/industries/heatmap...")
    try:
        response = requests.get(f"{API_URL}/industry/industries/heatmap")
        response.raise_for_status()
        data = response.json()
        
        industries = data.get("industries", [])
        print(f"Received {len(industries)} industries.")
        
        if not industries:
            print("Error: No industries returned.")
            sys.exit(1)
            
        leading_stock_count = 0
        missing_leading_stock = []
        
        for item in industries:
            leading_stock = item.get("leadingStock")
            if leading_stock:
                leading_stock_count += 1
            else:
                missing_leading_stock.append(item.get("name"))
        
        print(f"Industries with leading stock: {leading_stock_count}/{len(industries)}")
        
        if leading_stock_count > 0:
            print("SUCCESS: Leading stock field is populated.")
            # Print a few examples
            print("\nExamples:")
            for item in industries[:5]:
                print(f"- {item['name']}: {item.get('leadingStock')}")
        else:
            print("FAILURE: No industries have leading stock populated.")
            sys.exit(1)
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_heatmap_data()
