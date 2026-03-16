import yfinance as yf
import pandas as pd
import numpy as np

# Simulate backend get_historical_data
def get_historical_data(symbol):
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="1mo", interval="1d")
    data.columns = data.columns.str.lower()
    # Simulate cleaning - json serialization often converts NaNs to nulls or specific values
    # Let's check what it looks like before serialization
    return data

# Simulate frontend fetchKlineData logic
def simulate_frontend_logic(data):
    if data.empty:
        print("Data is empty")
        return

    # Convert DataFrame to list of dicts (like JSON)
    priceData = []
    for index, row in data.iterrows():
        item = row.to_dict()
        item['date'] = str(index)
        # item['volume'] could be NaN or 0
        priceData.append(item)
    
    # Processed Data mapping
    processedData = []
    for i, item in enumerate(priceData):
        prev_close = priceData[i-1]['close'] if i > 0 else item['close']
        processedData.append({
            'close': item['close'],
            'volume': item['volume'] if not pd.isna(item['volume']) else 0
        })

    # Stats calculation
    closes = [d['close'] for d in processedData]
    volumes = [d['volume'] for d in processedData]
    
    print(f"Volume sample: {volumes[:5]}")
    
    # Simulate reduce with potential NaN (if not handled above)
    try:
        avgVolume = sum(volumes) / len(volumes)
        print(f"Avg Volume: {avgVolume}")
    except Exception as e:
        print(f"Avg Volume Error: {e}")

    print(f"Latest Price: {closes[-1]}")

print("--- Testing ^GSPC ---")
df = get_historical_data("^GSPC")
simulate_frontend_logic(df)
