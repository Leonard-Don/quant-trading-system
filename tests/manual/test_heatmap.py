import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__name__)))
from src.analytics.industry_analyzer import IndustryAnalyzer
from src.data.providers.sina_ths_adapter import create_industry_provider
provider = create_industry_provider()
analyzer = IndustryAnalyzer(provider)
data = analyzer.get_industry_heatmap_data(days=5)
print([i.get("turnoverRate") for i in data.get("industries", [])[:15]])
