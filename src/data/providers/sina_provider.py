"""
新浪财经数据提供器
用于获取中国 A 股行业数据，作为东方财富 API 的备选方案
支持海外网络访问
"""

import re
import json
import copy
import fcntl
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import pandas as pd
import time
import functools
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def ttl_cache(ttl_seconds: int = 60):
    """Simple TTL cache decorator"""
    def decorator(func):
        cache: Dict[str, Any] = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args[1:]) + str(kwargs)
            now = time.time()
            
            if key in cache:
                value, timestamp = cache[key]
                if now - timestamp < ttl_seconds:
                    return value
            
            result = func(*args, **kwargs)
            
            # 增强逻辑：不缓存空结果，并优先返回过期老数据（兜底）
            is_empty = False
            if result is None:
                is_empty = True
            elif hasattr(result, "empty") and result.empty:
                is_empty = True
            elif isinstance(result, (list, dict, str)) and not result:
                is_empty = True
                
            if is_empty and key in cache:
                logger.warning(f"SinaFinanceProvider API returned empty. Using stale cache for {func.__name__}")
                return cache[key][0]  # 返回老数据，但不更新时间戳，这样下次还会尝试获取新数据
                
            if not is_empty:
                cache[key] = (result, now)
                
            return result
            
        return wrapper
    return decorator


class SinaFinanceProvider:
    """
    新浪财经数据提供器
    
    特点:
    - 全球可访问（无地理限制）
    - 提供申万行业分类数据
    - 提供概念板块数据
    - 提供个股实时行情
    - 内置重试机制与缓存
    
    使用示例:
        provider = SinaFinanceProvider()
        industries = provider.get_industry_list()
        stocks = provider.get_industry_stocks("new_blhy")  # 玻璃行业
    """
    
    BASE_URL = "https://vip.stock.finance.sina.com.cn"
    HQ_URL = "https://hq.sinajs.cn"
    _industry_list_cache_path = Path(__file__).resolve().parents[3] / "cache" / "sina_industry_list_cache.json"
    _industry_stocks_cache_path = Path(__file__).resolve().parents[3] / "cache" / "sina_industry_stocks_cache.json"
    _json_cache_memory: Dict[str, Dict[str, Any]] = {}
    _persistent_industry_list_frame_cache: Dict[str, Dict[str, Any]] = {}
    _persistent_industry_list_lookup_cache: Dict[str, Dict[str, Any]] = {}
    _persistent_industry_stocks_rows_cache: Dict[str, Dict[str, Any]] = {}
    _persistent_industry_stock_codes_cache: Dict[str, Dict[str, Any]] = {}
    
    def __init__(self):
        """初始化新浪财经提供器"""
        self.session = requests.Session()
        
        # 配置重试策略
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://finance.sina.com.cn/",
            "Accept": "*/*",
        })
        self._industry_cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        logger.info("SinaFinanceProvider initialized with retries")

    @classmethod
    def _load_json_cache(cls, path: Path) -> Dict[str, Any]:
        try:
            if not path.exists():
                cls._json_cache_memory.pop(str(path), None)
                return {}
            stat = path.stat()
            cache_key = str(path)
            cache_entry = cls._json_cache_memory.get(cache_key)
            if (
                cache_entry
                and cache_entry.get("mtime_ns") == stat.st_mtime_ns
                and cache_entry.get("size") == stat.st_size
            ):
                return copy.deepcopy(cache_entry.get("payload") or {})

            payload = json.loads(path.read_text(encoding="utf-8"))
            cls._json_cache_memory[cache_key] = {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "payload": payload,
            }
            return copy.deepcopy(payload)
        except Exception as e:
            logger.warning(f"Failed to load Sina persistent cache {path.name}: {e}")
            return {}

    @classmethod
    def _write_json_cache(cls, path: Path, payload: Dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name(f"{path.name}.tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(path)
            stat = path.stat()
            cls._json_cache_memory[str(path)] = {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "payload": copy.deepcopy(payload),
            }
        except Exception as e:
            logger.warning(f"Failed to write Sina persistent cache {path.name}: {e}")

    @classmethod
    def _locked_json_update(cls, path: Path, updater: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        lock_path = path.with_name(f"{path.name}.lock")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("w", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                payload = cls._load_json_cache(path)
                updated = updater(payload or {})
                cls._write_json_cache(path, updated)
        except Exception as e:
            logger.warning(f"Failed to update Sina persistent cache {path.name}: {e}")

    @classmethod
    def _load_persistent_industry_list(cls) -> pd.DataFrame:
        cache_path = cls._industry_list_cache_path
        cache_key = str(cache_path)
        try:
            if cache_path.exists():
                stat = cache_path.stat()
                cache_entry = cls._persistent_industry_list_frame_cache.get(cache_key)
                if (
                    cache_entry
                    and cache_entry.get("mtime_ns") == stat.st_mtime_ns
                    and cache_entry.get("size") == stat.st_size
                ):
                    cached_df = cache_entry.get("data")
                    if isinstance(cached_df, pd.DataFrame):
                        return cached_df.copy()
        except Exception:
            pass

        payload = cls._load_json_cache(cache_path)
        rows = payload.get("data", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        try:
            if cache_path.exists():
                stat = cache_path.stat()
                cls._persistent_industry_list_frame_cache[cache_key] = {
                    "mtime_ns": stat.st_mtime_ns,
                    "size": stat.st_size,
                    "data": df.copy(),
                }
        except Exception:
            pass
        logger.debug("Loaded persistent Sina industry list cache with %s industries", len(df))
        return df

    @classmethod
    def _get_persistent_industry_list_lookup(cls) -> Dict[str, List[Dict[str, Any]]]:
        cache_path = cls._industry_list_cache_path
        cache_key = str(cache_path)
        try:
            if cache_path.exists():
                stat = cache_path.stat()
                cache_entry = cls._persistent_industry_list_lookup_cache.get(cache_key)
                if (
                    cache_entry
                    and cache_entry.get("mtime_ns") == stat.st_mtime_ns
                    and cache_entry.get("size") == stat.st_size
                ):
                    rows_by_name = cache_entry.get("rows_by_name") or {}
                    return rows_by_name
        except Exception:
            pass

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load Sina persistent industry lookup cache {cache_path.name}: {e}")
            return {}

        rows = payload.get("data", [])
        rows_by_name: Dict[str, List[Dict[str, Any]]] = {}
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("industry_name") or "").strip()
                if not name:
                    continue
                rows_by_name.setdefault(name, []).append(dict(row))

        try:
            if cache_path.exists():
                stat = cache_path.stat()
                cls._persistent_industry_list_lookup_cache[cache_key] = {
                    "mtime_ns": stat.st_mtime_ns,
                    "size": stat.st_size,
                    "rows_by_name": rows_by_name,
                }
        except Exception:
            pass

        return rows_by_name

    @classmethod
    def _persist_industry_list(cls, df: pd.DataFrame) -> None:
        payload = {
            "updated_at": datetime.now().isoformat(),
            "data": df.to_dict(orient="records"),
        }
        cls._locked_json_update(
            cls._industry_list_cache_path,
            lambda _: payload,
        )

    @classmethod
    def _persist_industry_stocks(cls, industry_code: str, stocks: List[Dict[str, Any]]) -> None:
        def update_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
            data = payload.get("data", {})
            data[industry_code] = {
                "updated_at": datetime.now().isoformat(),
                "rows": stocks,
            }
            payload["updated_at"] = datetime.now().isoformat()
            payload["data"] = data
            return payload

        cls._locked_json_update(
            cls._industry_stocks_cache_path,
            update_payload,
        )

    @classmethod
    def _get_persistent_industry_stock_rows(cls, industry_code: str) -> List[Dict[str, Any]]:
        cache_path = cls._industry_stocks_cache_path
        cache_key = str(cache_path)
        try:
            if cache_path.exists():
                stat = cache_path.stat()
                cache_entry = cls._persistent_industry_stocks_rows_cache.get(cache_key)
                if (
                    cache_entry
                    and cache_entry.get("mtime_ns") == stat.st_mtime_ns
                    and cache_entry.get("size") == stat.st_size
                ):
                    rows_by_code = cache_entry.get("rows_by_code") or {}
                    rows = rows_by_code.get(industry_code, [])
                    if rows:
                        logger.debug("Loaded persistent Sina stocks cache for %s with %s stocks", industry_code, len(rows))
                    return rows
        except Exception:
            pass

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load Sina persistent stocks cache {cache_path.name}: {e}")
            return []

        data = payload.get("data", {})
        rows_by_code: Dict[str, List[Dict[str, Any]]] = {}
        if isinstance(data, dict):
            for code, item in data.items():
                rows = item.get("rows", []) if isinstance(item, dict) else []
                if isinstance(rows, list):
                    rows_by_code[str(code)] = rows
        try:
            if cache_path.exists():
                stat = cache_path.stat()
                cls._persistent_industry_stocks_rows_cache[cache_key] = {
                    "mtime_ns": stat.st_mtime_ns,
                    "size": stat.st_size,
                    "rows_by_code": rows_by_code,
                }
        except Exception:
            pass

        rows = rows_by_code.get(industry_code, [])
        if rows:
            logger.debug("Loaded persistent Sina stocks cache for %s with %s stocks", industry_code, len(rows))
        return rows

    @classmethod
    def _load_persistent_industry_stocks(cls, industry_code: str) -> List[Dict[str, Any]]:
        rows = cls._get_persistent_industry_stock_rows(industry_code)
        return [dict(row) for row in rows]

    @classmethod
    def _get_persistent_industry_stock_codes(cls) -> set[str]:
        cache_path = cls._industry_stocks_cache_path
        cache_key = str(cache_path)
        try:
            if cache_path.exists():
                stat = cache_path.stat()
                codes_cache_entry = cls._persistent_industry_stock_codes_cache.get(cache_key)
                if (
                    codes_cache_entry
                    and codes_cache_entry.get("mtime_ns") == stat.st_mtime_ns
                    and codes_cache_entry.get("size") == stat.st_size
                ):
                    return set(codes_cache_entry.get("codes") or set())
                cache_entry = cls._persistent_industry_stocks_rows_cache.get(cache_key)
                if (
                    cache_entry
                    and cache_entry.get("mtime_ns") == stat.st_mtime_ns
                    and cache_entry.get("size") == stat.st_size
                ):
                    rows_by_code = cache_entry.get("rows_by_code") or {}
                    codes = {
                        str(code).strip()
                        for code, rows in rows_by_code.items()
                        if str(code).strip().startswith("new_") and rows
                    }
                    cls._persistent_industry_stock_codes_cache[cache_key] = {
                        "mtime_ns": stat.st_mtime_ns,
                        "size": stat.st_size,
                        "codes": set(codes),
                    }
                    return codes
        except Exception:
            pass

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load Sina persistent stock-code cache {cache_path.name}: {e}")
            return set()

        data = payload.get("data", {})
        codes: set[str] = set()
        if isinstance(data, dict):
            for code, item in data.items():
                normalized_code = str(code).strip()
                rows = item.get("rows", []) if isinstance(item, dict) else []
                if normalized_code.startswith("new_") and isinstance(rows, list) and rows:
                    codes.add(normalized_code)
        try:
            if cache_path.exists():
                stat = cache_path.stat()
                cls._persistent_industry_stock_codes_cache[cache_key] = {
                    "mtime_ns": stat.st_mtime_ns,
                    "size": stat.st_size,
                    "codes": set(codes),
                }
        except Exception:
            pass

        return codes

    @staticmethod
    def _has_preferred_industry_codes(df: pd.DataFrame) -> bool:
        if df.empty or "industry_code" not in df.columns:
            return False
        codes = df["industry_code"].astype(str)
        return codes.str.startswith("new_").any()
    
    @ttl_cache(ttl_seconds=120)  # 缓存 2 分钟
    def get_industry_list(self) -> pd.DataFrame:
        """
        获取申万行业分类列表
        
        Returns:
            包含行业代码、名称、涨跌幅等信息的 DataFrame
        """
        try:
            data_dict = None
            candidate_urls = [
                f"{self.BASE_URL}/q/view/newSinaHy.php",
                "https://money.finance.sina.com.cn/q/view/newFLJK.php?param=industry",
                "https://money.finance.sina.com.cn/q/view/newFLJK.php?param=hy",
            ]
            selected_url = None
            for url in candidate_urls:
                try:
                    resp = self.session.get(url, timeout=15)
                    resp.raise_for_status()
                    content = resp.text
                    match = re.search(r'var\s+\w+\s*=\s*(\{.+\})', content, re.DOTALL)
                    if not match:
                        continue
                    data_str = match.group(1).replace("'", '"')
                    try:
                        data_dict = json.loads(data_str)
                    except json.JSONDecodeError:
                        data_dict = self._parse_js_object(data_str)
                    if data_dict:
                        selected_url = url
                        break
                except Exception as endpoint_error:
                    logger.warning(f"Sina industry endpoint failed {url}: {endpoint_error}")

            if not data_dict:
                logger.warning("Failed to parse industry data from Sina")
                cached = self._load_persistent_industry_list()
                if not cached.empty:
                    logger.warning("Using persistent Sina industry list cache")
                    return cached
                return pd.DataFrame()
            
            industries = []
            for code, value in data_dict.items():
                parts = value.split(",")
                if len(parts) >= 11:
                    industries.append({
                        "industry_code": parts[0],
                        "industry_name": parts[1],
                        "stock_count": int(parts[2]) if parts[2].isdigit() else 0,
                        "avg_price": float(parts[3]) if parts[3] else 0,
                        "change_pct": float(parts[4]) if parts[4] else 0,
                        "change_amount": float(parts[5]) if parts[5] else 0,
                        "volume": int(parts[6]) if parts[6].isdigit() else 0,
                        "turnover": float(parts[7]) if parts[7] else 0,
                        "leading_stock_code": parts[8],
                        "leading_stock_price": float(parts[9]) if parts[9] else 0,
                        "leading_stock_change": float(parts[10]) if parts[10] else 0,
                        "leading_stock_name": parts[11] if len(parts) > 11 else "",
                    })
            
            df = pd.DataFrame(industries)
            logger.info(f"Fetched {len(df)} industries from Sina Finance")
            if not df.empty:
                cached = self._load_persistent_industry_list()
                if (
                    selected_url
                    and "newSinaHy.php" not in selected_url
                    and not cached.empty
                    and self._has_preferred_industry_codes(cached)
                    and not self._has_preferred_industry_codes(df)
                ):
                    logger.info("Using persistent Sina industry list because it contains preferred new_* codes")
                    return cached
                self._persist_industry_list(df)
            return df
            
        except Exception as e:
            logger.error(f"Error fetching industry list: {e}")
            cached = self._load_persistent_industry_list()
            if not cached.empty:
                logger.warning("Using persistent Sina industry list cache")
                return cached
            return pd.DataFrame()
    
    @ttl_cache(ttl_seconds=300)  # 缓存 5 分钟
    def get_concept_list(self) -> pd.DataFrame:
        """
        获取概念板块列表
        
        Returns:
            包含概念代码、名称、涨跌幅等信息的 DataFrame
        """
        try:
            url = "https://money.finance.sina.com.cn/q/view/newFLJK.php?param=class"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            
            content = resp.text
            match = re.search(r'var\s+\w+\s*=\s*(\{.+\})', content, re.DOTALL)
            if not match:
                logger.warning("Failed to parse concept data from Sina")
                return pd.DataFrame()
            
            import json
            data_str = match.group(1)
            
            try:
                data_dict = json.loads(data_str)
            except json.JSONDecodeError:
                data_dict = self._parse_js_object(data_str)
            
            concepts = []
            for code, value in data_dict.items():
                parts = value.split(",")
                if len(parts) >= 11:
                    concepts.append({
                        "concept_code": parts[0],
                        "concept_name": parts[1],
                        "stock_count": int(parts[2]) if parts[2].isdigit() else 0,
                        "avg_price": float(parts[3]) if parts[3] else 0,
                        "change_pct": float(parts[4]) if parts[4] else 0,
                        "change_amount": float(parts[5]) if parts[5] else 0,
                        "volume": int(parts[6]) if parts[6].isdigit() else 0,
                        "turnover": float(parts[7]) if parts[7] else 0,
                        "leading_stock_code": parts[8],
                        "leading_stock_price": float(parts[9]) if parts[9] else 0,
                        "leading_stock_change": float(parts[10]) if parts[10] else 0,
                        "leading_stock_name": parts[11] if len(parts) > 11 else "",
                    })
            
            df = pd.DataFrame(concepts)
            logger.info(f"Fetched {len(df)} concepts from Sina Finance")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching concept list: {e}")
            return pd.DataFrame()
    
    @ttl_cache(ttl_seconds=60)  # 缓存 1 分钟
    def get_industry_stocks(
        self,
        industry_code: str,
        page: int = 1,
        count: int = 50,
        fetch_all: bool = False,
        max_pages: int = 20,
    ) -> List[Dict]:
        """
        获取行业成分股列表
        
        Args:
            industry_code: 行业代码（如 new_blhy）
            page: 页码
            count: 每页数量
            
        Returns:
            成分股列表
        """
        try:
            url = f"{self.BASE_URL}/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
            params = {
                "page": page,
                "num": count,
                "sort": "changepercent",
                "asc": 0,
                "node": industry_code,
                "symbol": "",
                "_s_r_a": "page",
            }
            
            import json

            def parse_payload(payload: str) -> List[Dict[str, Any]]:
                stocks = json.loads(payload)
                result = []
                for stock in stocks:
                    result.append({
                        "symbol": stock.get("symbol", ""),
                        "code": stock.get("code", ""),
                        "name": stock.get("name", ""),
                        "trade": float(stock.get("trade", 0)),
                        "price_change": float(stock.get("pricechange", 0)),
                        "change_pct": float(stock.get("changepercent", 0)),
                        "buy": float(stock.get("buy", 0)),
                        "sell": float(stock.get("sell", 0)),
                        "settlement": float(stock.get("settlement", 0)),
                        "open": float(stock.get("open", 0)),
                        "high": float(stock.get("high", 0)),
                        "low": float(stock.get("low", 0)),
                        "volume": int(stock.get("volume", 0)),
                        "amount": float(stock.get("amount", 0)),
                        "mktcap": float(stock.get("mktcap", 0)),
                        "nmc": float(stock.get("nmc", 0)),
                        "turnover_ratio": float(stock.get("turnoverratio", 0)),
                        "pe_ratio": float(stock.get("per", 0)) if stock.get("per") else 0,
                        "pb_ratio": float(stock.get("pb", 0)) if stock.get("pb") else 0,
                    })
                return result

            page_index = page
            merged: Dict[str, Dict[str, Any]] = {}
            while page_index < page + max_pages:
                params["page"] = page_index
                resp = self.session.get(url, params=params, timeout=15)
                resp.raise_for_status()

                page_items = parse_payload(resp.text)
                if not page_items:
                    break

                for item in page_items:
                    code = item.get("code") or item.get("symbol")
                    if code:
                        merged[str(code)] = item

                if not fetch_all or len(page_items) < count:
                    break

                page_index += 1

            result = list(merged.values())
            logger.info(f"Fetched {len(result)} stocks for industry {industry_code}")
            if result:
                self._persist_industry_stocks(industry_code, result)
            return result
            
        except Exception as e:
            logger.error(f"Error fetching industry stocks for {industry_code}: {e}")
            cached = self._load_persistent_industry_stocks(industry_code)
            if cached:
                logger.warning(f"Using persistent Sina stocks cache for {industry_code}")
                return cached
            return []
    
    def get_stock_realtime(self, symbols: List[str]) -> pd.DataFrame:
        """
        获取股票实时行情
        
        Args:
            symbols: 股票代码列表（如 ["sh600000", "sz000001"]）
            
        Returns:
            实时行情 DataFrame
        """
        if not symbols:
            return pd.DataFrame()
        
        try:
            # 新浪行情 API 支持批量查询
            symbols_str = ",".join(symbols)
            url = f"{self.HQ_URL}/list={symbols_str}"
            
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            
            content = resp.text
            stocks = []
            
            # 解析行情数据
            # 格式: var hq_str_sh600000="股票名称,今开,昨收,现价,最高,最低,买一,卖一,成交量,..."
            for line in content.strip().split("\n"):
                match = re.match(r'var hq_str_(\w+)="(.+)"', line)
                if match:
                    symbol = match.group(1)
                    data = match.group(2).split(",")
                    if len(data) >= 32 and data[0]:  # 确保有数据
                        stocks.append({
                            "symbol": symbol,
                            "name": data[0],
                            "open": float(data[1]) if data[1] else 0,
                            "pre_close": float(data[2]) if data[2] else 0,
                            "price": float(data[3]) if data[3] else 0,
                            "high": float(data[4]) if data[4] else 0,
                            "low": float(data[5]) if data[5] else 0,
                            "bid": float(data[6]) if data[6] else 0,
                            "ask": float(data[7]) if data[7] else 0,
                            "volume": int(data[8]) if data[8].isdigit() else 0,
                            "amount": float(data[9]) if data[9] else 0,
                            "date": data[30] if len(data) > 30 else "",
                            "time": data[31] if len(data) > 31 else "",
                        })
            
            return pd.DataFrame(stocks)
            
        except Exception as e:
            logger.error(f"Error fetching realtime quotes: {e}")
            return pd.DataFrame()
    
    def get_industry_money_flow(self) -> pd.DataFrame:
        """
        获取行业资金流向数据
        
        Note: 新浪财经直接在行业列表中包含了成交量和成交额，
              可以用来估算资金流向
        
        Returns:
            包含行业资金流向估算的 DataFrame
        """
        df = self.get_industry_list()
        
        if df.empty:
            return pd.DataFrame()
        
        # 计算资金流向强度（基于涨跌幅和成交额）
        if "turnover" in df.columns and "change_pct" in df.columns:
            max_turnover = df["turnover"].max()
            if max_turnover > 0:
                df["flow_strength"] = (
                    df["change_pct"] * (df["turnover"] / max_turnover)
                )
            else:
                df["flow_strength"] = 0
            
            # 估算主力净流入（基于涨跌方向和成交额）
            df["main_net_inflow"] = df["turnover"] * (df["change_pct"] / 100) * 0.3
        
        return df
    
    def _parse_js_object(self, js_str: str) -> Dict:
        """手动解析 JavaScript 对象字符串"""
        result = {}
        # 移除花括号
        content = js_str.strip()[1:-1]
        
        # 匹配 "key":"value" 对
        pattern = r'"([^"]+)"\s*:\s*"([^"]*)"'
        matches = re.findall(pattern, content)
        
        for key, value in matches:
            result[key] = value
        
        return result


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    provider = SinaFinanceProvider()
    
    print("=== Industry List ===")
    industries = provider.get_industry_list()
    print(industries.head(10).to_string())
    
    print("\n=== Concept List ===")
    concepts = provider.get_concept_list()
    print(concepts.head(10).to_string())
    
    if not industries.empty:
        first_code = industries.iloc[0]["industry_code"]
        print(f"\n=== Stocks in {first_code} ===")
        stocks = provider.get_industry_stocks(first_code)
        for s in stocks[:5]:
            print(f"  {s['code']} {s['name']}: {s['change_pct']}%")
