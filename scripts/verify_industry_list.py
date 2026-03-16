import os
import sys
import urllib.request
from pathlib import Path

# 彻底清除代理设置，防止东方财富 API 失败
proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
for var in proxy_vars:
    if var in os.environ:
        del os.environ[var]
os.environ['NO_PROXY'] = '*'
urllib.request.getproxies = lambda: {}

# 添加项目根目录到路径 (如果需要导入项目内部模块)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import akshare as ak
import pandas as pd

def check_industry_filtering():
    print("Fetching industry list...")
    try:
        # 尝试直接调用 akshare 获取行业板块
        df = ak.stock_board_industry_name_em()
        original_count = len(df)
        print(f"Original row count: {original_count}")
        
        if df.empty:
            print("Warning: Received empty dataframe from AKShare")
            return

        # 简单的展示，确认数据是否回来
        print(f"\n--- Top 10 Industries ---")
        print(df.head(10)[['板块名称', '板块代码']].to_string())

        # 检查特定关键词
        keywords = ["银行", "证券", "半导体", "计算机"]
        print("\n--- Check Specific Industries ---")
        for keyword in keywords:
            matches = df[df['板块名称'].str.contains(keyword, na=False)]
            if not matches.empty:
                print(f"Matches for '{keyword}': {matches['板块名称'].tolist()}")
            else:
                print(f"No matches found for '{keyword}'")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_industry_filtering()
