
import yfinance as yf
import json
import sys

def check_symbol(symbol):
    print(f"Checking {symbol}...")
    ticker = yf.Ticker(symbol)
    
    # 1. Check history
    try:
        hist = ticker.history(period="1d")
        if hist.empty:
            print(f"❌ History is empty for {symbol}")
        else:
            print(f"✅ History fetch successful. Columns: {hist.columns.tolist()}")
    except Exception as e:
        print(f"❌ History fetch failed: {e}")

    # 2. Check info keys
    try:
        info = ticker.info
        print("\n🔍 Available Info Keys (Top 20):")
        keys = list(info.keys())[:20]
        print(keys)
        
        print("\n🔍 Specific Keys Check:")
        target_keys = [
            "regularMarketPrice", "currentPrice",
            "regularMarketChange", 
            "regularMarketChangePercent",
            "regularMarketVolume",
            "marketCap",
            "trailingPE"
        ]
        
        for key in target_keys:
            val = info.get(key)
            print(f"  {key}: {val} (Type: {type(val)})")
            
    except Exception as e:
        print(f"❌ Info fetch failed: {e}")

if __name__ == "__main__":
    check_symbol("AAPL")
