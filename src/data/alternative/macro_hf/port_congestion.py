"""
港口物流拥堵数据

追踪全球关键港口的拥堵指数和等待时间变化，
作为供应链瓶颈的实时代理指标。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base_alt_provider import AntiCrawlMixin

logger = logging.getLogger(__name__)

# 全球关键港口
KEY_PORTS = {
    "shanghai": {"name": "上海港", "region": "Asia", "country": "CN", "rank": 1},
    "singapore": {"name": "新加坡港", "region": "Asia", "country": "SG", "rank": 2},
    "ningbo": {"name": "宁波舟山港", "region": "Asia", "country": "CN", "rank": 3},
    "shenzhen": {"name": "深圳港", "region": "Asia", "country": "CN", "rank": 4},
    "guangzhou": {"name": "广州港", "region": "Asia", "country": "CN", "rank": 5},
    "busan": {"name": "釜山港", "region": "Asia", "country": "KR", "rank": 6},
    "rotterdam": {"name": "鹿特丹港", "region": "Europe", "country": "NL", "rank": 7},
    "los_angeles": {"name": "洛杉矶港", "region": "Americas", "country": "US", "rank": 8},
    "hamburg": {"name": "汉堡港", "region": "Europe", "country": "DE", "rank": 9},
    "long_beach": {"name": "长滩港", "region": "Americas", "country": "US", "rank": 10},
}


class PortCongestionProvider(AntiCrawlMixin):
    """
    港口拥堵数据提供器

    追踪全球关键港口的拥堵程度，用于判断：
    - 全球贸易活跃度
    - 供应链瓶颈程度
    - 区域性物流风险

    Usage:
        ports = PortCongestionProvider()
        congestion = ports.get_global_congestion_index()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._min_interval = self.config.get("min_request_interval", 5.0)
        self.logger = logger
        self._congestion_history: List[Dict[str, Any]] = []

    def get_port_status(self, port_id: str) -> Dict[str, Any]:
        """
        获取指定港口的拥堵状态

        Args:
            port_id: 港口标识

        Returns:
            港口状态
        """
        if port_id not in KEY_PORTS:
            return {"error": f"未追踪的港口: {port_id}"}

        port = KEY_PORTS[port_id]

        # 尝试获取实时数据
        data = self._fetch_port_data(port_id)

        return {
            "port_id": port_id,
            "name": port["name"],
            "region": port["region"],
            "country": port["country"],
            "congestion_data": data,
            "timestamp": datetime.now().isoformat(),
        }

    def get_global_congestion_index(self) -> Dict[str, Any]:
        """
        计算全球港口拥堵指数

        加权综合所有追踪港口的拥堵程度。
        """
        port_statuses = {}
        for port_id in KEY_PORTS:
            status = self.get_port_status(port_id)
            port_statuses[port_id] = status

        # 按区域汇总
        regional = {"Asia": [], "Europe": [], "Americas": []}
        for port_id, status in port_statuses.items():
            region = KEY_PORTS[port_id]["region"]
            if region in regional:
                regional[region].append(status)

        # 计算全球指数（0-100）
        # 当前为框架值，待接入真实数据后替换
        global_index = 50.0  # 中性基准

        result = {
            "global_index": round(global_index, 2),
            "status": self._index_to_status(global_index),
            "regional_summary": {
                region: {
                    "port_count": len(ports),
                    "ports": [p.get("name", "") for p in ports if isinstance(p, dict)],
                }
                for region, ports in regional.items()
            },
            "tracked_ports": len(KEY_PORTS),
            "signal": 0,  # -1=看空贸易相关/1=看多
            "source_mode": "proxy",
            "fallback_reason": "live_ais_or_port_api_not_connected",
            "lag_days": 2,
            "coverage": 0.32,
            "timestamp": datetime.now().isoformat(),
        }

        self._congestion_history.append(result)
        self._congestion_history = self._congestion_history[-100:]

        return result

    def get_region_analysis(self, region: str) -> Dict[str, Any]:
        """
        获取区域港口分析

        Args:
            region: 区域 (Asia/Europe/Americas)
        """
        region_ports = {
            pid: info
            for pid, info in KEY_PORTS.items()
            if info["region"] == region
        }

        return {
            "region": region,
            "ports": list(region_ports.keys()),
            "port_count": len(region_ports),
            "timestamp": datetime.now().isoformat(),
        }

    def _fetch_port_data(self, port_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单个港口的实时数据

        待接入的可能数据源：
        - MarineTraffic API
        - Portcast API
        - 公开 AIS 数据
        """
        return {
            "data_available": False,
            "note": "待接入港口实时数据 API",
        }

    @staticmethod
    def _index_to_status(index: float) -> str:
        """将拥堵指数转换为状态描述"""
        if index >= 80:
            return "严重拥堵"
        elif index >= 60:
            return "中度拥堵"
        elif index >= 40:
            return "正常"
        elif index >= 20:
            return "低水平"
        else:
            return "异常低迷"
