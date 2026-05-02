"""
另类数据提供器基类

定义标准化的 fetch → parse → normalize → to_signal 四步管道，
为政策爬虫、产业链爬虫、宏观高频接口提供统一抽象。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import logging
import random
import time
import hashlib

import requests
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ── 枚举与数据结构 ──────────────────────────────────────────────


class AltDataCategory(str, Enum):
    """另类数据类别"""
    POLICY = "policy"                   # 政策文件
    POLICY_EXECUTION = "policy_execution"  # 政策执行/部门混乱
    BIDDING = "bidding"                 # 招标采购
    ENV_ASSESSMENT = "env_assessment"   # 环评公示
    HIRING = "hiring"                   # 招聘趋势
    EXECUTIVE_GOVERNANCE = "executive_governance"  # 高管/治理画像
    INSIDER_FLOW = "insider_flow"       # 内部人交易/持股流向
    CUSTOMS = "customs"                 # 海关进出口
    COMMODITY_INVENTORY = "commodity_inventory"  # 大宗商品库存
    PORT_CONGESTION = "port_congestion" # 港口拥堵
    MEDIA_SENTIMENT = "media_sentiment" # 媒体情绪


class AltDataError(Exception):
    """另类数据异常"""
    pass


@dataclass
class AltDataRecord:
    """
    另类数据标准化记录

    所有另类数据源的输出都必须转换为此格式，
    确保下游因子库和信号引擎可以统一消费。
    """
    timestamp: datetime                 # 数据时间戳
    source: str                         # 数据源名称
    category: AltDataCategory           # 数据类别
    raw_value: Any                      # 原始值（可以是文本、数字、字典等）
    normalized_score: float             # 标准化得分 [-1.0, 1.0]
    confidence: float                   # 置信度 [0.0, 1.0]
    metadata: Dict[str, Any] = field(default_factory=dict)  # 附加元数据
    tags: List[str] = field(default_factory=list)            # 标签（行业/地区等）
    record_id: str = ""                 # 唯一标识

    def __post_init__(self):
        if not self.record_id:
            # 基于内容生成唯一 ID
            content = f"{self.timestamp.isoformat()}-{self.source}-{self.category.value}"
            self.record_id = hashlib.sha256(content.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "category": self.category.value,
            "raw_value": self.raw_value if not isinstance(self.raw_value, (pd.DataFrame, pd.Series)) else str(self.raw_value),
            "normalized_score": self.normalized_score,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AltDataRecord":
        return cls(
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            source=payload["source"],
            category=AltDataCategory(payload["category"]),
            raw_value=payload.get("raw_value"),
            normalized_score=float(payload.get("normalized_score", 0.0)),
            confidence=float(payload.get("confidence", 0.0)),
            metadata=payload.get("metadata") or {},
            tags=payload.get("tags") or [],
            record_id=payload.get("record_id", ""),
        )


# ── 反爬虫策略 ───────────────────────────────────────────────


class AntiCrawlMixin:
    """
    反爬虫策略混入类

    提供 UserAgent 轮转、请求间隔控制、重试机制等。
    """

    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]

    _last_request_time: float = 0.0
    _min_interval: float = 1.0  # 最小请求间隔（秒）

    def _get_random_ua(self) -> str:
        """获取随机 User-Agent"""
        return random.choice(self._USER_AGENTS)

    def _get_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "User-Agent": self._get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        if extra:
            headers.update(extra)
        return headers

    def _throttle(self):
        """请求节流"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            sleep_time = self._min_interval - elapsed + random.uniform(0, 0.5)
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _safe_request(
        self,
        url: str,
        method: str = "GET",
        max_retries: int = 3,
        timeout: int = 30,
        **kwargs,
    ) -> Optional[requests.Response]:
        """
        带重试和节流的安全请求

        Args:
            url: 请求 URL
            method: HTTP 方法
            max_retries: 最大重试次数
            timeout: 超时时间（秒）

        Returns:
            Response 对象，失败返回 None
        """
        for attempt in range(max_retries):
            try:
                self._throttle()
                headers = kwargs.pop("headers", {})
                merged_headers = self._get_headers(headers)

                response = requests.request(
                    method,
                    url,
                    headers=merged_headers,
                    timeout=timeout,
                    **kwargs,
                )
                response.raise_for_status()
                return response

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else "unknown"
                logger.warning(
                    f"HTTP {status} for {url} (attempt {attempt + 1}/{max_retries})"
                )
                if status == 429:  # Too Many Requests
                    time.sleep(min(30, 2 ** attempt * 5))
                elif status in (403, 503):
                    time.sleep(min(60, 2 ** attempt * 10))
                else:
                    break  # 其他 HTTP 错误不重试

            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error for {url} (attempt {attempt + 1}/{max_retries})")
                time.sleep(2 ** attempt)

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout for {url} (attempt {attempt + 1}/{max_retries})")
                time.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"Unexpected error fetching {url}: {e}")
                break

        logger.error(f"Failed to fetch {url} after {max_retries} attempts")
        return None


# ── 另类数据提供器基类 ────────────────────────────────────────


class BaseAltDataProvider(AntiCrawlMixin, ABC):
    """
    另类数据提供器抽象基类

    定义 fetch → parse → normalize → to_signal 四步标准管道。
    所有另类数据源提供器必须继承此类。

    Attributes:
        name: 数据源名称
        category: 数据类别
        update_interval: 更新间隔（秒）
        enabled: 是否启用
    """

    name: str = "base_alt"
    category: AltDataCategory = AltDataCategory.POLICY
    update_interval: int = 3600  # 默认 1 小时
    enabled: bool = True

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化

        Args:
            config: 配置参数（API 密钥、代理等）
        """
        self.config = config or {}
        self._min_interval = self.config.get("min_request_interval", 1.0)
        self._history: List[AltDataRecord] = []
        self._last_update: Optional[datetime] = None
        self.logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    # ── 四步管道（子类必须实现） ──

    @abstractmethod
    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """
        步骤一：抓取原始数据

        Returns:
            原始数据列表（每个元素为字典）
        """
        pass

    @abstractmethod
    def parse(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        步骤二：解析结构化数据

        Args:
            raw_data: fetch() 返回的原始数据

        Returns:
            结构化数据列表
        """
        pass

    @abstractmethod
    def normalize(self, parsed_data: List[Dict[str, Any]]) -> List[AltDataRecord]:
        """
        步骤三：标准化为 AltDataRecord

        Args:
            parsed_data: parse() 返回的结构化数据

        Returns:
            标准化记录列表
        """
        pass

    def to_signal(self, records: List[AltDataRecord]) -> Dict[str, Any]:
        """
        步骤四：生成交易信号（可选覆盖）

        默认实现：对所有记录的 normalized_score 取加权平均。

        Args:
            records: normalize() 返回的标准化记录

        Returns:
            信号字典
        """
        if not records:
            return {
                "source": self.name,
                "category": self.category.value,
                "signal": 0,
                "strength": 0.0,
                "confidence": 0.0,
                "record_count": 0,
                "timestamp": datetime.now().isoformat(),
            }

        # 按置信度加权平均
        total_weight = sum(r.confidence for r in records)
        if total_weight > 0:
            weighted_score = sum(r.normalized_score * r.confidence for r in records) / total_weight
        else:
            weighted_score = np.mean([r.normalized_score for r in records])

        avg_confidence = np.mean([r.confidence for r in records])

        # 信号方向
        if weighted_score > 0.3:
            signal = 1   # 看多
        elif weighted_score < -0.3:
            signal = -1  # 看空
        else:
            signal = 0   # 中性

        return {
            "source": self.name,
            "category": self.category.value,
            "signal": signal,
            "strength": round(abs(weighted_score), 4),
            "score": round(weighted_score, 4),
            "confidence": round(avg_confidence, 4),
            "record_count": len(records),
            "latest_record": records[-1].to_dict() if records else None,
            "timestamp": datetime.now().isoformat(),
        }

    # ── 完整管道执行 ──

    def run_pipeline(self, **kwargs) -> Dict[str, Any]:
        """
        执行完整的四步管道

        Returns:
            信号字典
        """
        try:
            self.logger.info(f"[{self.name}] 开始执行数据管道...")

            # Step 1: Fetch
            raw_data = self.fetch(**kwargs)
            self.logger.info(f"[{self.name}] fetch 完成，获取 {len(raw_data)} 条原始数据")

            if not raw_data:
                self.logger.warning(f"[{self.name}] 未获取到任何数据")
                return self.to_signal([])

            # Step 2: Parse
            parsed_data = self.parse(raw_data)
            self.logger.info(f"[{self.name}] parse 完成，解析 {len(parsed_data)} 条数据")

            # Step 3: Normalize
            records = self.normalize(parsed_data)
            self.logger.info(f"[{self.name}] normalize 完成，生成 {len(records)} 条标准化记录")

            # 保存到历史
            self._history.extend(records)
            # 保留最近 500 条
            self._history = self._history[-500:]
            self._last_update = datetime.now()

            # Step 4: Signal
            signal = self.to_signal(records)
            self.logger.info(
                f"[{self.name}] 管道完成 → signal={signal['signal']}, "
                f"strength={signal['strength']}, confidence={signal['confidence']}"
            )

            return signal

        except Exception as e:
            self.logger.error(f"[{self.name}] 管道执行失败: {e}", exc_info=True)
            raise AltDataError(f"Pipeline failed for {self.name}: {e}") from e

    # ── 辅助方法 ──

    def get_history(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AltDataRecord]:
        """获取历史记录"""
        records = self._history
        if start:
            records = [r for r in records if r.timestamp >= start]
        if end:
            records = [r for r in records if r.timestamp <= end]
        return records[-limit:]

    def get_history_df(self, limit: int = 100) -> pd.DataFrame:
        """获取历史记录为 DataFrame"""
        records = self.get_history(limit=limit)
        if not records:
            return pd.DataFrame()
        return pd.DataFrame([r.to_dict() for r in records])

    def needs_update(self) -> bool:
        """检查是否需要更新"""
        if self._last_update is None:
            return True
        elapsed = (datetime.now() - self._last_update).total_seconds()
        return elapsed >= self.update_interval

    def get_provider_info(self) -> Dict[str, Any]:
        """获取提供器信息"""
        return {
            "name": self.name,
            "category": self.category.value,
            "enabled": self.enabled,
            "update_interval": self.update_interval,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "history_count": len(self._history),
            "needs_update": self.needs_update(),
        }

    @staticmethod
    def _score_to_range(value: float, min_val: float, max_val: float) -> float:
        """将值映射到 [-1, 1] 范围"""
        if max_val == min_val:
            return 0.0
        normalized = 2 * (value - min_val) / (max_val - min_val) - 1
        return max(-1.0, min(1.0, normalized))

    @staticmethod
    def _z_score(value: float, mean: float, std: float) -> float:
        """计算 z-score"""
        if std == 0:
            return 0.0
        return (value - mean) / std
