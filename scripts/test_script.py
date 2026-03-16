import pandas as pd
from src.data.providers.sina_ths_adapter import SinaIndustryAdapter
from src.analytics.industry_analyzer import IndustryAnalyzer

a = SinaIndustryAdapter()
analyzer = IndustryAnalyzer(a)

heatmap = analyzer.get_industry_heatmap_data(days=1)
ind = heatmap.get('industries', [])
# Check AKShare data
with_pe = [i for i in ind if i.get('pe_ttm') is not None]
print(f'Total industries: {len(ind)}')
print(f'With PE data: {len(with_pe)}')

if with_pe:
    print('Sample:')
    for i in sorted(with_pe, key=lambda x: x['value'], reverse=True)[:5]:
        print(f'  {i["name"]}: 涨幅={i["value"]}%, PE={i.get("pe_ttm")}, PB={i.get("pb")}, Div={i.get("dividend_yield")}')
