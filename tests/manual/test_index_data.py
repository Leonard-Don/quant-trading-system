import yfinance as yf
import pandas as pd

def check_index_data(symbol):
    print(f"Checking {symbol}...")
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="1mo", interval="1d")
    print(f"Empty: {data.empty}")
    if not data.empty:
        print("Columns:", data.columns)
        print("Tail:\n", data.tail())
        print("Volume check:", data['Volume'].sum())

check_index_data("^GSPC") # S&P 500
check_index_data("^IXIC") # Nasdaq
