"""
招聘趋势追踪器

追踪核心科技企业的招聘岗位变动趋势，
通过"营销岗 vs 技术岗"比例变化洞察企业战略重心偏移。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

from ..base_alt_provider import AntiCrawlMixin

logger = logging.getLogger(__name__)

# ── 岗位分类关键词 ──

JOB_CATEGORIES = {
    "core_tech": {
        "name": "核心技术岗",
        "keywords": [
            "算法工程师", "系统架构师", "芯片设计", "FPGA", "ASIC",
            "编译器", "操作系统", "内核开发", "底层算力", "GPU开发",
            "AI研究员", "机器学习", "深度学习", "自动驾驶",
            "量化研究", "嵌入式", "硬件工程",
        ],
    },
    "applied_tech": {
        "name": "应用技术岗",
        "keywords": [
            "前端开发", "后端开发", "全栈", "移动开发", "iOS", "Android",
            "产品经理", "测试工程师", "DevOps", "云计算",
            "数据分析师", "BI分析",
        ],
    },
    "marketing_biz": {
        "name": "营销/商务岗",
        "keywords": [
            "市场营销", "品牌经理", "新媒体运营", "直播", "带货",
            "销售经理", "商务拓展", "渠道经理", "客户经理",
            "广告投放", "增长运营", "社区运营",
        ],
    },
    "finance_compliance": {
        "name": "金融/合规岗",
        "keywords": [
            "财务总监", "CFO", "合规经理", "风控", "审计",
            "投资者关系", "董秘", "法务", "IPO",
            "ESG", "内控", "合规官",
        ],
    },
}

# 需追踪的核心企业
TRACKED_COMPANIES = {
    "alibaba": {"name": "阿里巴巴", "ticker": "BABA", "sector": "互联网"},
    "tencent": {"name": "腾讯", "ticker": "0700.HK", "sector": "互联网"},
    "baidu": {"name": "百度", "ticker": "BIDU", "sector": "AI"},
    "huawei": {"name": "华为", "ticker": None, "sector": "ICT"},
    "bytedance": {"name": "字节跳动", "ticker": None, "sector": "互联网"},
    "nvidia": {"name": "英伟达", "ticker": "NVDA", "sector": "半导体"},
    "tsmc": {"name": "台积电", "ticker": "TSM", "sector": "半导体"},
}


class HiringTracker(AntiCrawlMixin):
    """
    招聘趋势追踪器

    通过分析企业招聘岗位的结构变化，推断企业战略方向的偏移。

    核心指标：
    - tech_ratio: 核心技术岗占比
    - marketing_ratio: 营销/商务岗占比
    - dilution_signal: 当营销岗占比上升+技术岗下降 → 做空信号

    Usage:
        tracker = HiringTracker()
        report = tracker.analyze_company("alibaba")
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._min_interval = self.config.get("min_request_interval", 3.0)
        self.logger = logger
        # 历史数据存储（用于计算趋势）
        self._history: Dict[str, List[Dict[str, Any]]] = {}

    def analyze_company(
        self,
        company_id: str,
        source: str = "auto",
    ) -> Dict[str, Any]:
        """
        分析单个公司的招聘趋势

        Args:
            company_id: 公司标识
            source: 数据源（auto/manual）

        Returns:
            招聘趋势分析报告
        """
        company = TRACKED_COMPANIES.get(company_id)
        if not company:
            return {"error": f"未追踪的公司: {company_id}"}

        # 获取招聘数据
        job_data = self._fetch_job_listings(company_id, company["name"])

        # 分类统计
        category_counts = self._classify_jobs(job_data)

        # 计算关键比率
        total = sum(category_counts.values())
        if total == 0:
            return {
                "company": company["name"],
                "ticker": company.get("ticker"),
                "total_jobs": 0,
                "signal": "no_data",
                "timestamp": datetime.now().isoformat(),
            }

        tech_ratio = (
            category_counts.get("core_tech", 0) + category_counts.get("applied_tech", 0)
        ) / total
        marketing_ratio = category_counts.get("marketing_biz", 0) / total
        finance_ratio = category_counts.get("finance_compliance", 0) / total
        core_tech_ratio = category_counts.get("core_tech", 0) / total

        # 技术高管稀释度
        dilution_ratio = (
            (category_counts.get("finance_compliance", 0) + category_counts.get("marketing_biz", 0))
            / max(1, category_counts.get("core_tech", 0))
        )

        # 生成信号
        signal = "neutral"
        signal_strength = 0.0

        if dilution_ratio > 1.5:
            signal = "bearish"  # 做空信号
            signal_strength = min(1.0, (dilution_ratio - 1.5) / 1.5)
        elif core_tech_ratio > 0.3 and marketing_ratio < 0.2:
            signal = "bullish"  # 技术驱动，看好
            signal_strength = min(1.0, core_tech_ratio / 0.5)

        # 记录历史
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "category_counts": category_counts,
            "tech_ratio": tech_ratio,
            "marketing_ratio": marketing_ratio,
            "dilution_ratio": dilution_ratio,
        }
        if company_id not in self._history:
            self._history[company_id] = []
        self._history[company_id].append(snapshot)
        self._history[company_id] = self._history[company_id][-30:]

        return {
            "company": company["name"],
            "ticker": company.get("ticker"),
            "sector": company.get("sector"),
            "total_jobs": total,
            "category_breakdown": {
                cat_id: {
                    "name": JOB_CATEGORIES[cat_id]["name"],
                    "count": count,
                    "ratio": round(count / total, 4),
                }
                for cat_id, count in category_counts.items()
            },
            "key_ratios": {
                "tech_ratio": round(tech_ratio, 4),
                "core_tech_ratio": round(core_tech_ratio, 4),
                "marketing_ratio": round(marketing_ratio, 4),
                "finance_compliance_ratio": round(finance_ratio, 4),
                "dilution_ratio": round(dilution_ratio, 4),
            },
            "signal": signal,
            "signal_strength": round(signal_strength, 4),
            "alert": dilution_ratio > 1.5,
            "alert_message": (
                f"⚠️ {company['name']} 技术高管稀释度 {dilution_ratio:.2f} 超过警戒线 1.5"
                if dilution_ratio > 1.5
                else None
            ),
            "timestamp": datetime.now().isoformat(),
        }

    def analyze_all_companies(self) -> Dict[str, Dict[str, Any]]:
        """分析所有追踪的公司"""
        results = {}
        for company_id in TRACKED_COMPANIES:
            results[company_id] = self.analyze_company(company_id)
        return results

    def get_dilution_ranking(self) -> List[Dict[str, Any]]:
        """
        获取技术稀释度排名

        Returns:
            按稀释度从高到低排序的公司列表
        """
        analyses = self.analyze_all_companies()
        rankings = []
        for company_id, data in analyses.items():
            if "key_ratios" in data:
                rankings.append({
                    "company_id": company_id,
                    "company": data["company"],
                    "ticker": data.get("ticker"),
                    "dilution_ratio": data["key_ratios"]["dilution_ratio"],
                    "signal": data["signal"],
                    "alert": data.get("alert", False),
                })

        rankings.sort(key=lambda x: x["dilution_ratio"], reverse=True)
        return rankings

    def _fetch_job_listings(
        self, company_id: str, company_name: str
    ) -> List[Dict[str, Any]]:
        """
        获取招聘列表

        尝试从公开招聘平台获取数据。
        网络不可用时返回空列表。
        """
        # 尝试从公司官网或公开平台获取
        jobs = []

        # 尝试搜索引擎辅助获取公开数据
        try:
            search_url = f"https://search.51job.com/list/000000,000000,0000,00,9,99,{company_name},2,1.html"
            response = self._safe_request(search_url, timeout=10)
            
            if response:
                jobs = self._parse_51job_response(response, company_name)

        except Exception as e:
            self.logger.debug(f"获取 {company_name} 招聘数据失败: {e}")

        return jobs

    def _parse_51job_response(
        self, response, company_name: str
    ) -> List[Dict[str, Any]]:
        """解析招聘网站响应"""
        jobs = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")

            for item in soup.select(".j_joblist .e"):
                title = item.select_one(".jname")
                if title:
                    jobs.append({
                        "title": title.get_text(strip=True),
                        "company": company_name,
                    })
        except Exception:
            pass

        return jobs

    def _classify_jobs(self, jobs: List[Dict[str, Any]]) -> Dict[str, int]:
        """将岗位按类别分类"""
        counts = {cat_id: 0 for cat_id in JOB_CATEGORIES}

        for job in jobs:
            title = job.get("title", "")
            classified = False
            for cat_id, category in JOB_CATEGORIES.items():
                for kw in category["keywords"]:
                    if kw in title:
                        counts[cat_id] += 1
                        classified = True
                        break
                if classified:
                    break

            if not classified:
                # 未分类的归入应用技术岗
                counts["applied_tech"] += 1

        return counts
