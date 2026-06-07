"""常量映射表：申万一级行业代码 + AKShare 中文列名 → 标准英文列名映射。

从 ``AKShareProvider`` 机械抽取的纯常量（无状态、无副作用）。
``akshare_provider`` 重新导入这些字典；``SW_INDUSTRY_MAP`` 继续作为类属性绑定，
其余 rename 映射在各取数方法内原样引用，行为逐字节一致。
"""

from typing import Dict

# 申万一级行业代码映射
SW_INDUSTRY_MAP: Dict[str, str] = {
    "农林牧渔": "801010",
    "基础化工": "801030",
    "钢铁": "801040",
    "有色金属": "801050",
    "电子": "801080",
    "汽车": "801880",
    "家用电器": "801110",
    "食品饮料": "801120",
    "纺织服饰": "801130",
    "轻工制造": "801140",
    "医药生物": "801150",
    "公用事业": "801160",
    "交通运输": "801170",
    "房地产": "801180",
    "商贸零售": "801200",
    "社会服务": "801210",
    "银行": "801780",
    "非银金融": "801790",
    "综合": "801230",
    "建筑材料": "801710",
    "建筑装饰": "801720",
    "电力设备": "801730",
    "国防军工": "801740",
    "计算机": "801750",
    "传媒": "801760",
    "通信": "801770",
    "煤炭": "801020",
    "石油石化": "801960",
    "环保": "801970",
    "美容护理": "801980",
}

# get_historical_data: 东方财富日线 K 线列名映射
HISTORICAL_COLUMN_MAP: Dict[str, str] = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
    "换手率": "turnover",
}

# get_industry_index: 申万行业指数列名映射
INDUSTRY_INDEX_COLUMN_MAP: Dict[str, str] = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
}

# get_industry_money_flow: 行业资金流向列名映射（AKShare 返回列名带 "今日" 前缀）
INDUSTRY_MONEY_FLOW_COLUMN_MAP: Dict[str, str] = {
    "名称": "industry_name",
    "今日涨跌幅": "change_pct",
    "今日主力净流入-净额": "main_net_inflow",
    "今日主力净流入-净占比": "main_net_ratio",
    "今日超大单净流入-净额": "super_large_net",
    "今日超大单净流入-净占比": "super_large_ratio",
    "今日大单净流入-净额": "large_net",
    "今日大单净流入-净占比": "large_ratio",
    "今日中单净流入-净额": "medium_net",
    "今日中单净流入-净占比": "medium_ratio",
    "今日小单净流入-净额": "small_net",
    "今日小单净流入-净占比": "small_ratio",
    "今日主力净流入最大股": "leading_stock",
}

# _get_industry_metadata: 东方财富行业 metadata 列名映射
INDUSTRY_METADATA_COLUMN_MAP: Dict[str, str] = {
    "板块名称": "industry_name",
    "总市值": "total_market_cap",
    "换手率": "turnover_rate",
    "涨跌幅": "change_pct_meta",  # Avoid conflict
}

# _get_all_stocks_spot: Sina 全市场快照列名向 EM 看齐
SINA_SPOT_COLUMN_MAP: Dict[str, str] = {
    "symbol": "代码",
    "name": "名称",
    "mktcap": "流通市值",  # Sina 这个接口并没有直接的动态 PE，所以 PE 校验只能放空让它跳过
}
