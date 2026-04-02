from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache

SYMBOL_CATALOG = [
    {"symbol": "AAPL", "name": "Apple", "group": "Mega Cap Tech", "market": "US", "aliases": ["苹果", "iphone", "consumer hardware"]},
    {"symbol": "MSFT", "name": "Microsoft", "group": "Mega Cap Tech", "market": "US", "aliases": ["微软", "azure", "office"]},
    {"symbol": "NVDA", "name": "NVIDIA", "group": "Semiconductor", "market": "US", "aliases": ["英伟达", "gpu", "ai chip"]},
    {"symbol": "AMZN", "name": "Amazon", "group": "Mega Cap Tech", "market": "US", "aliases": ["亚马逊", "aws", "ecommerce"]},
    {"symbol": "GOOGL", "name": "Alphabet", "group": "Mega Cap Tech", "market": "US", "aliases": ["谷歌", "google", "search", "youtube"]},
    {"symbol": "META", "name": "Meta Platforms", "group": "Mega Cap Tech", "market": "US", "aliases": ["facebook", "meta", "社交媒体"]},
    {"symbol": "TSLA", "name": "Tesla", "group": "EV", "market": "US", "aliases": ["特斯拉", "新能源车", "electric vehicle"]},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "group": "Semiconductor", "market": "US", "aliases": ["超微半导体", "cpu", "gpu"]},
    {"symbol": "AVGO", "name": "Broadcom", "group": "Semiconductor", "market": "US", "aliases": ["博通", "network chip", "vmware"]},
    {"symbol": "NFLX", "name": "Netflix", "group": "Internet", "market": "US", "aliases": ["奈飞", "streaming", "视频流媒体"]},
    {"symbol": "PLTR", "name": "Palantir", "group": "Software", "market": "US", "aliases": ["帕兰提尔", "国防软件", "data platform"]},
    {"symbol": "SNOW", "name": "Snowflake", "group": "Software", "market": "US", "aliases": ["数据云", "data warehouse"]},
    {"symbol": "CRM", "name": "Salesforce", "group": "Software", "market": "US", "aliases": ["赛富时", "crm", "saas"]},
    {"symbol": "NOW", "name": "ServiceNow", "group": "Software", "market": "US", "aliases": ["workflow", "it service"]},
    {"symbol": "ORCL", "name": "Oracle", "group": "Software", "market": "US", "aliases": ["甲骨文", "database", "cloud infra"]},
    {"symbol": "ADBE", "name": "Adobe", "group": "Software", "market": "US", "aliases": ["奥多比", "creative cloud", "设计软件"]},
    {"symbol": "INTC", "name": "Intel", "group": "Semiconductor", "market": "US", "aliases": ["英特尔", "x86", "foundry"]},
    {"symbol": "QCOM", "name": "Qualcomm", "group": "Semiconductor", "market": "US", "aliases": ["高通", "mobile chip", "5g"]},
    {"symbol": "TXN", "name": "Texas Instruments", "group": "Semiconductor", "market": "US", "aliases": ["德州仪器", "analog chip", "工业芯片"]},
    {"symbol": "MU", "name": "Micron", "group": "Semiconductor", "market": "US", "aliases": ["美光", "memory", "dram"]},
    {"symbol": "ARM", "name": "Arm Holdings", "group": "Semiconductor", "market": "US", "aliases": ["arm", "ip chip", "芯片架构"]},
    {"symbol": "SHOP", "name": "Shopify", "group": "Software", "market": "US", "aliases": ["电商软件", "merchant platform"]},
    {"symbol": "UBER", "name": "Uber", "group": "Internet", "market": "US", "aliases": ["网约车", "mobility", "delivery"]},
    {"symbol": "ABNB", "name": "Airbnb", "group": "Internet", "market": "US", "aliases": ["爱彼迎", "travel platform", "住宿平台"]},
    {"symbol": "PYPL", "name": "PayPal", "group": "Fintech", "market": "US", "aliases": ["贝宝", "payment", "支付"]},
    {"symbol": "COIN", "name": "Coinbase", "group": "Fintech", "market": "US", "aliases": ["加密交易所", "crypto exchange"]},
    {"symbol": "JPM", "name": "JPMorgan Chase", "group": "Banks", "market": "US", "aliases": ["摩根大通", "bank", "银行"]},
    {"symbol": "GS", "name": "Goldman Sachs", "group": "Banks", "market": "US", "aliases": ["高盛", "investment bank", "投行"]},
    {"symbol": "MS", "name": "Morgan Stanley", "group": "Banks", "market": "US", "aliases": ["摩根士丹利", "wealth management"]},
    {"symbol": "BAC", "name": "Bank of America", "group": "Banks", "market": "US", "aliases": ["美国银行", "bank of america"]},
    {"symbol": "WFC", "name": "Wells Fargo", "group": "Banks", "market": "US", "aliases": ["富国银行"]},
    {"symbol": "UNH", "name": "UnitedHealth", "group": "Healthcare", "market": "US", "aliases": ["联合健康", "医保"]},
    {"symbol": "LLY", "name": "Eli Lilly", "group": "Healthcare", "market": "US", "aliases": ["礼来", "减肥药", "glp-1"]},
    {"symbol": "PFE", "name": "Pfizer", "group": "Healthcare", "market": "US", "aliases": ["辉瑞", "pharma"]},
    {"symbol": "MRK", "name": "Merck", "group": "Healthcare", "market": "US", "aliases": ["默沙东", "oncology"]},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "group": "Healthcare", "market": "US", "aliases": ["强生", "medical devices"]},
    {"symbol": "COST", "name": "Costco", "group": "Consumer", "market": "US", "aliases": ["好市多", "warehouse retail"]},
    {"symbol": "WMT", "name": "Walmart", "group": "Consumer", "market": "US", "aliases": ["沃尔玛", "retail", "零售"]},
    {"symbol": "HD", "name": "Home Depot", "group": "Consumer", "market": "US", "aliases": ["家得宝", "home improvement"]},
    {"symbol": "NKE", "name": "Nike", "group": "Consumer", "market": "US", "aliases": ["耐克", "sportswear"]},
    {"symbol": "XOM", "name": "Exxon Mobil", "group": "Energy", "market": "US", "aliases": ["埃克森美孚", "oil major", "石油"]},
    {"symbol": "CVX", "name": "Chevron", "group": "Energy", "market": "US", "aliases": ["雪佛龙", "oil major"]},
    {"symbol": "SLB", "name": "Schlumberger", "group": "Energy", "market": "US", "aliases": ["油服", "oil service"]},
    {"symbol": "CAT", "name": "Caterpillar", "group": "Industrials", "market": "US", "aliases": ["卡特彼勒", "工程机械"]},
    {"symbol": "GE", "name": "GE Aerospace", "group": "Industrials", "market": "US", "aliases": ["通用电气", "aerospace"]},
    {"symbol": "DE", "name": "Deere", "group": "Industrials", "market": "US", "aliases": ["迪尔", "农机"]},
    {"symbol": "NEE", "name": "NextEra Energy", "group": "Utilities", "market": "US", "aliases": ["新能源公用事业", "utility"]},
    {"symbol": "DUK", "name": "Duke Energy", "group": "Utilities", "market": "US", "aliases": ["公用事业", "electric utility"]},
    {"symbol": "BABA", "name": "Alibaba", "group": "China ADR", "market": "US", "aliases": ["阿里巴巴", "电商", "cloud"]},
    {"symbol": "PDD", "name": "PDD Holdings", "group": "China ADR", "market": "US", "aliases": ["拼多多", "temu"]},
    {"symbol": "JD", "name": "JD.com", "group": "China ADR", "market": "US", "aliases": ["京东", "retail"]},
    {"symbol": "NIO", "name": "NIO", "group": "China EV", "market": "US", "aliases": ["蔚来"]},
    {"symbol": "XPEV", "name": "XPeng", "group": "China EV", "market": "US", "aliases": ["小鹏"]},
    {"symbol": "LI", "name": "Li Auto", "group": "China EV", "market": "US", "aliases": ["理想汽车"]},
]
POPULAR_SYMBOLS = SYMBOL_CATALOG[:12]
CATALOG_BY_SYMBOL = OrderedDict((item["symbol"], item) for item in SYMBOL_CATALOG)


@lru_cache(maxsize=256)
def peer_candidate_pool(symbol: str) -> tuple[str, ...]:
    target_symbol = str(symbol or "").strip().upper()
    target_catalog = CATALOG_BY_SYMBOL.get(target_symbol, {})
    preferred_group = target_catalog.get("group", "")
    preferred_market = target_catalog.get("market", "")

    primary_candidates = [
        item["symbol"]
        for item in SYMBOL_CATALOG
        if item["symbol"] != target_symbol
        and (
            (preferred_group and item.get("group") == preferred_group)
            or (preferred_market and item.get("market") == preferred_market)
        )
    ]
    fallback_candidates = [
        item["symbol"]
        for item in SYMBOL_CATALOG
        if item["symbol"] != target_symbol and item["symbol"] not in primary_candidates
    ]
    return tuple([*primary_candidates, *fallback_candidates])


def search_symbol_suggestions(q: str, limit: int) -> dict:
    query = str(q or "").strip().lower()
    if not query:
        return {"data": POPULAR_SYMBOLS[:limit], "total": min(limit, len(POPULAR_SYMBOLS))}

    ranked: list[tuple[int, dict]] = []
    for item in SYMBOL_CATALOG:
        symbol = item["symbol"].lower()
        name = item["name"].lower()
        group = item["group"].lower()
        aliases = [alias.lower() for alias in item.get("aliases", [])]
        tokens = [symbol, name, group, *aliases]
        if not any(query in token for token in tokens):
            continue

        rank = 0
        if symbol.startswith(query):
            rank += 8
        if name.startswith(query):
            rank += 6
        if any(alias.startswith(query) for alias in aliases):
            rank += 5
        if query == symbol:
            rank += 12
        if query == name:
            rank += 9
        if query in group:
            rank += 2
        rank += sum(1 for token in tokens if query in token)
        ranked.append((rank, item))

    matches = [item for _, item in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["symbol"]))[:limit]]
    return {"data": matches, "total": len(matches)}


def build_screener_response(result: dict) -> dict:
    return {
        **result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_sensitivity_overrides(payload: dict) -> dict:
    return {
        key: value
        for key, value in payload.items()
        if key != "symbol" and value is not None
    }


def run_screening(analyzer, symbols: list[str], period: str, limit: int, max_workers: int):
    try:
        return analyzer.screen(symbols, period, limit, max_workers)
    except TypeError:
        return analyzer.screen(symbols, period, limit)


def build_benchmark_factors_payload(ff) -> dict:
    if ff.empty:
        return {"error": "无法获取因子数据", "factors": {}}

    recent = ff.tail(21)
    factors = {}
    for col in ["Mkt-RF", "SMB", "HML", "RF"]:
        if col in recent.columns:
            series = recent[col]
            factors[col] = {
                "mean_daily": round(float(series.mean()), 6),
                "mean_annual": round(float(series.mean() * 252), 4),
                "std_daily": round(float(series.std()), 6),
                "latest": round(float(series.iloc[-1]), 6),
                "cumulative_1m": round(float((1 + series).prod() - 1), 4),
            }

    return {
        "period": "recent_1m",
        "data_points": len(recent),
        "factors": factors,
        "last_date": str(recent.index[-1].date()) if len(recent) > 0 else None,
    }
