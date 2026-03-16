import akshare as ak
import pandas as pd
import squarify

def simulate_treemap():
    print("Fetching industry heatmap data...")
    # Fetch real data to get realistic sizes
    try:
        # Get industry flow data (approximate)
        df = ak.stock_sector_fund_flow_rank(indicator="今日")
        if df.empty:
            print("No data.")
            return

        df = df.rename(columns={
            "名称": "industry_name",
            "今日涨跌幅": "change_pct",
        })
        
        # Fetch market cap
        df_meta = ak.stock_board_industry_name_em()
        if not df_meta.empty:
             df_meta = df_meta.rename(columns={
                "板块名称": "industry_name",
                "总市值": "total_market_cap",
            })
             if "total_market_cap" in df_meta.columns:
                df = df.merge(
                    df_meta[["industry_name", "total_market_cap"]],
                    on="industry_name",
                    how="left"
                )
                df["total_market_cap"] = df["total_market_cap"].fillna(0)

        # Filter Liquor
        liquor = df[df['industry_name'].str.contains('白酒')]
        print("Liquor data:\n", liquor[['industry_name', 'total_market_cap']])

        # Sort by Market Cap Desc
        df['size'] = df['total_market_cap']
        df = df.sort_values('size', ascending=False)
        
        # Take Top 100 to find Liquor
        top30 = df.head(100)
        
        print("\nTop 100 Industries (Partial):")
        print(top30[['industry_name', 'size']].to_string())
        
        # Normalize sizes (simple)
        sizes = top30['size'].tolist()
        
        # Simulate Squarify
        # Container 800x450 (from JS)
        width = 800
        height = 450
        
        norm_sizes = squarify.normalize_sizes(sizes, width, height)
        layout = squarify.squarify(norm_sizes, 0, 0, width, height)
        
        print("\nLayout Results:")
        for res, (idx, row) in zip(layout, top30.iterrows()):
            name = row['industry_name']
            if '白酒' in name:
                w = res['dx']
                h = res['dy']
                aspect = max(w/h, h/w) if h > 0 and w > 0 else 0
                print(f"*** {name}: w={w:.1f}, h={h:.1f}, aspect={aspect:.2f}, x={res['x']:.1f}, y={res['y']:.1f}")
            elif idx < 5: # Print top 5 for context
                print(f"{name}: w={res['dx']:.1f}, h={res['dy']:.1f}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    simulate_treemap()
