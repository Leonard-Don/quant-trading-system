"""行业名称映射表与映射函数（THS / Sina / 申万）。

从 ``sina_ths_adapter`` 中机械抽取的纯映射常量与函数，行为保持不变。
``sina_ths_adapter`` 仍以原名重新导出这些符号，调用方无需改动。
"""

from typing import List

INDUSTRY_ENRICHMENT_ALIASES = {
    "有色冶炼加工": "有色金属",
    "煤炭开采加工": "煤炭",
    "白酒": "食品饮料",
    "食品加工制造": "食品饮料",
    "景点及旅游": "社会服务",
    "酒店及餐饮": "社会服务",
    "保险及其他": "非银金融",
}

SINA_TO_THS_MAP = {
    "煤炭行业": "煤炭开采加工",
    "有色金属": "工业金属",
    "石油行业": "油气开采及服务",
    "钢铁行业": "钢铁",
    "化工行业": "化学制品",
    "农药化肥": "化学制品",
    "化纤行业": "化学纤维",
    "塑料制品": "塑料制品",
    "橡胶制品": "橡胶制品",
    "陶瓷行业": "建筑材料",
    "玻璃行业": "建筑材料",
    "水泥行业": "建筑材料",
    "建筑建材": "建筑材料",
    "造纸行业": "造纸",
    "印刷包装": "包装印刷",
    "电力行业": "电力",
    "发电设备": "电力设备",
    "供水供气": "燃气",
    "环保行业": "环保设备",
    "机械行业": "通用设备",
    "纺织机械": "专用设备",
    "矿物制品": "非金属材料",
    "电器行业": "白色家电",
    "家电行业": "小家电",
    "汽车制造": "汽车整车",
    "摩托车": "汽车零部件",
    "船舶制造": "军工装备",
    "飞机制造": "军工装备",
    "电子器件": "半导体及元件",
    "半导体": "半导体及元件",
    "电子信息": "计算机设备",
    "仪器仪表": "仪器仪表",
    "通信行业": "通信设备",
    "软件开发": "软件开发",
    "计算机行业": "计算机应用",
    "医疗器械": "医疗器械",
    "生物制药": "生物制品",
    "酿酒行业": "饮料制造",
    "白酒": "饮料制造",
    "饮料制造": "饮料制造",
    "食品行业": "食品加工制造",
    "纺织行业": "纺织制造",
    "服装鞋类": "服装家纺",
    "家具行业": "家用轻工",
    "商业百货": "零售",
    "贸易行业": "贸易",
    "物资外贸": "物流",
    "物流行业": "物流",
    "交通运输": "公路铁路运输",
    "公路桥梁": "公路铁路运输",
    "港口水运": "港口航运",
    "金融行业": "多元金融",
    "保险行业": "保险",
    "银行": "银行",
    "证券行业": "证券",
    "房地产": "房地产",
    "开发区": "园区开发",
    "综合行业": "综合",
    "其它行业": "综合",
    "酒店旅游": "旅游及酒店",
    "传媒娱乐": "传媒",
    "农林牧渔": "种植业与林业",
    "玻璃": "建筑材料",
    "水泥": "建筑材料",
    "装修装饰": "建筑装饰",
    "园林工程": "建筑装饰",
    "互联网": "互联网电商",
    "软件服务": "软件开发",
    "综合": "综合",
    "工艺商品": "家用轻工",
}

SINA_NEW_NODE_NAME_MAP = {
    "房地产": "new_fdc",
    "电力行业": "new_dlhy",
    "化纤行业": "new_hqhy",
    "医疗器械": "new_ylqx",
    "煤炭行业": "new_mthy",
    "农化制品": "new_nyhf",
    "塑料制品": "new_slzp",
    "酒店旅游": "new_jdly",
    "商业百货": "new_sybh",
    "钢铁行业": "new_gthy",
    "传媒娱乐": "new_cmyl",
    "文化传媒": "new_cmyl",
    "公路桥梁": "new_glql",
    "服装鞋类": "new_fzxl",
    "家具行业": "new_jjhy",
    "家居用品": "new_jjhy",
    "食品行业": "new_sphy",
    "食品加工制造": "new_sphy",
    "供水供气": "new_gsgq",
    "燃气": "new_gsgq",
    "石油行业": "new_syhy",
    "油气开采及服务": "new_syhy",
    "环保行业": "new_hbhy",
    "白色家电": "new_jdhy",
    "元件": "new_dzqj",
    "饮料制造": "new_ljhy",
    "化学制品": "new_hghy",
    "纺织制造": "new_fzhy",
    "生物制品": "new_swzz",
    "物流": "new_wzwm",
    "物资外贸": "new_wzwm",
    "包装印刷": "new_ysbz",
    "印刷包装": "new_ysbz",
    "造纸": "new_zzhy",
    "造纸行业": "new_zzhy",
    "综合": "new_zhhy",
    "综合行业": "new_zhhy",
    "工业金属": "new_ysjs",
    "有色金属": "new_ysjs",
}

SINA_PROXY_NODE_NAME_MAP = {
    "半导体": "new_dzqj",
    "半导体及元件": "new_dzqj",
    "电子元件": "new_dzqj",
    "消费电子": "new_dzqj",
    "光学光电子": "new_dzqj",
    "计算机设备": "new_dzxx",
    "计算机应用": "new_dzxx",
    "软件开发": "new_dzxx",
    "通信设备": "new_dzxx",
    "互联网电商": "new_sybh",
    "汽车整车": "new_qczz",
    "汽车零部件": "new_qczz",
    "通用设备": "new_jxhy",
    "工程机械": "new_jxhy",
    "港口航运": "new_jtys",
    "机场航运": "new_jtys",
    "风电设备": "new_fdsb",
    "光伏设备": "new_fdsb",
    "其他电源设备": "new_fdsb",
    "电池": "new_dqhy",
    "电机": "new_dqhy",
    "自动化设备": "new_jxhy",
    "化学制药": "new_swzz",
    "中药": "new_swzz",
    "电子化学品": "new_hghy",
    "非金属材料": "new_hghy",
    "贸易": "new_wzwm",
    "黑色家电": "new_jdhy",
    "小家电": "new_jdhy",
    "能源金属": "new_ysjs",
    "小金属": "new_ysjs",
    "贵金属": "new_ysjs",
    "证券": "new_jrhy",
    "保险": "new_jrhy",
    "银行": "new_jrhy",
}

SW_INDEX_ALIAS_MAP = {
    "半导体": "电子",
    "半导体及元件": "电子",
    "消费电子": "电子",
    "光学光电子": "电子",
    "元件": "电子",
    "软件开发": "计算机",
    "计算机应用": "计算机",
    "计算机设备": "计算机",
    "通信设备": "通信",
    "白色家电": "家用电器",
    "小家电": "家用电器",
    "饮料制造": "食品饮料",
    "食品加工制造": "食品饮料",
    "证券": "非银金融",
    "保险": "非银金融",
    "电力": "公用事业",
    "燃气": "公用事业",
    "医疗器械": "医药生物",
    "化学制药": "医药生物",
    "中药": "医药生物",
    "生物制品": "医药生物",
    "港口航运": "交通运输",
    "物流": "交通运输",
    "房地产开发": "房地产",
    "房地产服务": "房地产",
    "风电设备": "电力设备",
    "光伏设备": "电力设备",
    "电池": "电力设备",
    "电机": "电力设备",
}


def map_sina_to_ths(sina_name: str) -> str:
    """尝试将新浪行业名称映射到同花顺"""
    # 彻底清理后缀
    clean_name = sina_name.replace("行业", "").replace("制造", "").strip()
    if clean_name in SINA_TO_THS_MAP:
        return SINA_TO_THS_MAP[clean_name]
    if sina_name in SINA_TO_THS_MAP:
        return SINA_TO_THS_MAP[sina_name]
    return clean_name


def map_ths_to_sina(ths_name: str) -> List[str]:
    """尝试将同花顺行业名称逆向映射为可能的新浪行业名称"""
    possible_names = []
    # 1. 查找反向映射字典
    for sina, ths in SINA_TO_THS_MAP.items():
        if ths == ths_name:
            possible_names.append(sina)

    # 2. 特殊硬编码处理，确保核心行业能够补全
    ths_clean = ths_name.replace("Ⅲ", "").replace("Ⅱ", "").strip()

    if "白酒" in ths_clean or "饮料" in ths_clean:
        possible_names.extend(["酿酒行业", "食品饮料"])
    if "半导体" in ths_clean or "元件" in ths_clean:
        possible_names.extend(["电子器件", "半导体"])
    if "电力" in ths_clean or "电网" in ths_clean:
        possible_names.extend(["电力行业", "发电设备"])
    if "军工" in ths_clean or "航天" in ths_clean or "航空" in ths_clean:
        possible_names.extend(["飞机制造", "船舶制造", "军工装备"])
    if "医药" in ths_clean or "医疗" in ths_clean:
        possible_names.extend(["医药生物", "生物制药", "医疗器械"])
    if "房地产" in ths_clean:
        possible_names.append("房地产")

    # 3. 启发式替换
    possible_names.append(ths_clean.replace("开采加工", "行业"))
    possible_names.append(ths_clean.replace("制造", "行业"))
    possible_names.append(ths_clean.replace("设备", "行业"))
    possible_names.append(ths_clean + "行业")

    # 4. 原名兜底
    possible_names.append(ths_name)

    deduped = []
    seen = set()
    for name in possible_names:
        normalized = str(name or "").strip()
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped
