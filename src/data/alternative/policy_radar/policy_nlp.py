"""
政策 NLP 分析模块

通过大模型（OpenAI / 通义千问）对政策文本进行语义分析，
提取"政策转向度"和"长官意志强烈度"指标。
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── 关键词库（本地快速分析，无需 LLM） ──

STIMULUS_KEYWORDS_ZH = [
    "加大投入", "加快推进", "扩大", "降准", "降息", "减税",
    "刺激", "鼓励", "支持发展", "重大工程", "增量资金",
    "新基建", "扩容", "放宽", "提振", "加速",
]

STIMULUS_KEYWORDS_EN = [
    "support", "stimulus", "expand", "accelerate", "boost",
    "investment", "funding", "cut rates", "rate cut", "easing",
    "liquidity", "infrastructure", "capacity expansion", "promote",
]

TIGHTENING_KEYWORDS_ZH = [
    "收紧", "限制", "整顿", "规范", "严控", "压降",
    "去杠杆", "淘汰", "清退", "暂停", "叫停",
    "严格执行", "问责", "审查", "制裁",
]

TIGHTENING_KEYWORDS_EN = [
    "tighten", "restriction", "curb", "reduce", "suspend",
    "pause", "ban", "penalty", "compliance", "rate hike",
    "higher rates", "quantitative tightening", "deleveraging",
]

STRONG_WILL_KEYWORDS_ZH = [
    "坚决", "必须", "严禁", "不得", "立即", "全力",
    "重大部署", "战略", "底线", "红线", "零容忍",
    "高度重视", "亲自", "紧急", "限期",
]

STRONG_WILL_KEYWORDS_EN = [
    "must", "shall", "immediately", "strictly", "decisive",
    "firmly", "without delay", "enforce", "urgent", "mandatory",
    "committed", "determined", "no tolerance",
]

INDUSTRY_KEYWORDS = {
    "光伏": ["光伏", "太阳能", "硅片", "组件", "逆变器", "solar", "photovoltaic", "pv"],
    "风电": ["风电", "风机", "海上风电", "风力发电", "wind", "offshore wind", "turbine"],
    "核电": ["核电", "核能", "核准", "核反应堆", "nuclear", "reactor"],
    "AI算力": ["人工智能", "算力", "数据中心", "GPU", "芯片", "智算", "artificial intelligence", "data center", "compute", "semiconductor"],
    "新能源汽车": ["新能源汽车", "电动车", "充电桩", "动力电池", "electric vehicle", "ev", "battery"],
    "半导体": ["半导体", "芯片", "集成电路", "晶圆", "semiconductor", "chip", "wafer"],
    "电网": ["电网", "特高压", "输电", "变压器", "配电", "grid", "transmission", "distribution", "transformer"],
    "储能": ["储能", "电池储能", "抽水蓄能", "energy storage", "battery storage"],
}


class PolicyNLPAnalyzer:
    """
    政策 NLP 分析器

    提供两种分析模式：
    1. 本地关键词分析（快速、免费、离线可用）
    2. LLM 深度分析（精确、需要 API 密钥）

    Attributes:
        mode: 分析模式 ("local" | "llm")
        llm_provider: LLM 提供商 ("openai" | "qwen")
    """

    def __init__(
        self,
        mode: str = "local",
        llm_provider: str = "openai",
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.mode = mode
        self.llm_provider = llm_provider
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.config = config or {}
        self.logger = logger

    def analyze(self, text: str, title: str = "", source: str = "") -> Dict[str, Any]:
        """
        分析政策文本

        Args:
            text: 政策全文
            title: 政策标题
            source: 数据源

        Returns:
            {
                "policy_shift": float,        # 政策转向度 [-1, 1]
                "will_intensity": float,      # 长官意志强烈度 [0, 100]
                "industry_impact": dict,      # 产业影响标签
                "summary": str,               # 政策摘要
                "confidence": float,          # 分析置信度 [0, 1]
            }
        """
        if self.mode == "llm" and self.api_key:
            return self._analyze_with_llm(text, title, source)
        else:
            return self._analyze_local(text, title, source)

    def analyze_batch(
        self, documents: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        批量分析

        Args:
            documents: [{"text": ..., "title": ..., "source": ...}, ...]

        Returns:
            分析结果列表
        """
        results = []
        for doc in documents:
            result = self.analyze(
                text=doc.get("text", ""),
                title=doc.get("title", ""),
                source=doc.get("source", ""),
            )
            results.append(result)
        return results

    # ── 本地关键词分析 ──

    def _analyze_local(
        self, text: str, title: str, source: str
    ) -> Dict[str, Any]:
        """基于关键词的本地快速分析"""
        full_text = f"{title} {text}"

        # 1. 政策转向度：刺激 vs 紧缩关键词
        stimulus_score = self._count_keywords(full_text, STIMULUS_KEYWORDS_ZH + STIMULUS_KEYWORDS_EN)
        tightening_score = self._count_keywords(full_text, TIGHTENING_KEYWORDS_ZH + TIGHTENING_KEYWORDS_EN)

        total = stimulus_score + tightening_score
        if total > 0:
            policy_shift = (stimulus_score - tightening_score) / total
        else:
            policy_shift = 0.0

        # 2. 长官意志强烈度
        will_count = self._count_keywords(full_text, STRONG_WILL_KEYWORDS_ZH + STRONG_WILL_KEYWORDS_EN)
        # 归一化到 0-100，假设超过 10 个强烈词汇已经非常强
        will_intensity = min(100, will_count * 10)

        # 3. 产业影响标签
        industry_impact = {}
        for industry, keywords in INDUSTRY_KEYWORDS.items():
            count = self._count_keywords(full_text, keywords)
            if count > 0:
                # 判断该产业是利好还是利空
                stimulus_nearby = self._count_co_occurrence(
                    full_text, keywords, STIMULUS_KEYWORDS_ZH + STIMULUS_KEYWORDS_EN
                )
                tightening_nearby = self._count_co_occurrence(
                    full_text, keywords, TIGHTENING_KEYWORDS_ZH + TIGHTENING_KEYWORDS_EN
                )
                if stimulus_nearby > tightening_nearby:
                    impact = "positive"
                    impact_score = min(1.0, stimulus_nearby * 0.3)
                elif tightening_nearby > stimulus_nearby:
                    impact = "negative"
                    impact_score = -min(1.0, tightening_nearby * 0.3)
                else:
                    impact = "neutral"
                    impact_score = 0.0

                industry_impact[industry] = {
                    "impact": impact,
                    "score": round(impact_score, 3),
                    "mentions": count,
                }

        # 4. 简单摘要（取前 200 字）
        summary = title if title else text[:200]

        # 置信度：基于文本长度和关键词命中率
        text_length_factor = min(1.0, len(full_text) / 1000)
        keyword_hit_factor = min(1.0, total / 5)
        confidence = 0.3 + 0.4 * text_length_factor + 0.3 * keyword_hit_factor

        return {
            "policy_shift": round(policy_shift, 4),
            "will_intensity": round(will_intensity, 2),
            "industry_impact": industry_impact,
            "summary": summary,
            "confidence": round(confidence, 3),
            "analysis_mode": "local",
            "timestamp": datetime.now().isoformat(),
        }

    # ── LLM 深度分析 ──

    def _analyze_with_llm(
        self, text: str, title: str, source: str
    ) -> Dict[str, Any]:
        """使用 LLM 进行深度语义分析"""
        try:
            prompt = self._build_analysis_prompt(text, title, source)

            if self.llm_provider == "openai":
                result = self._call_openai(prompt)
            elif self.llm_provider == "qwen":
                result = self._call_qwen(prompt)
            else:
                self.logger.warning(f"未知的 LLM 提供商: {self.llm_provider}，回退到本地分析")
                return self._analyze_local(text, title, source)

            if result:
                result["analysis_mode"] = "llm"
                result["timestamp"] = datetime.now().isoformat()
                return result

        except Exception as e:
            self.logger.error(f"LLM 分析失败: {e}，回退到本地分析")

        # LLM 失败时回退到本地分析
        return self._analyze_local(text, title, source)

    def _build_analysis_prompt(
        self, text: str, title: str, source: str
    ) -> str:
        """构建 LLM 分析提示词"""
        # 截断过长文本
        max_text_len = 3000
        if len(text) > max_text_len:
            text = text[:max_text_len] + "..."

        return f"""你是一个专业的宏观经济政策分析师。请分析以下政策文件并以 JSON 格式返回分析结果。

政策来源：{source}
政策标题：{title}
政策内容：
{text}

请返回以下 JSON 格式（不要包含其他文字）：
{{
    "policy_shift": <float, 政策转向度, -1(强力紧缩) 到 1(大力刺激)>,
    "will_intensity": <float, 长官意志强烈度, 0-100, 从措辞力度判断执行概率>,
    "industry_impact": {{
        "<行业名>": {{
            "impact": "<positive/negative/neutral>",
            "score": <float, -1到1>,
            "reason": "<简要原因>"
        }}
    }},
    "summary": "<50字以内的政策核心要点>",
    "confidence": <float, 0-1, 分析置信度>
}}"""

    def _call_openai(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用 OpenAI API"""
        try:
            import requests

            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config.get("model", "gpt-4o-mini"),
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1000,
                },
                timeout=60,
            )
            response.raise_for_status()

            content = response.json()["choices"][0]["message"]["content"]
            return self._parse_llm_response(content)

        except Exception as e:
            self.logger.error(f"OpenAI API 调用失败: {e}")
            return None

    def _call_qwen(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用通义千问 API"""
        try:
            import requests

            api_url = self.config.get(
                "qwen_api_url",
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
            )

            response = requests.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config.get("model", "qwen-turbo"),
                    "input": {"messages": [{"role": "user", "content": prompt}]},
                    "parameters": {"temperature": 0.3, "max_tokens": 1000},
                },
                timeout=60,
            )
            response.raise_for_status()

            data = response.json()
            content = data.get("output", {}).get("text", "")
            return self._parse_llm_response(content)

        except Exception as e:
            self.logger.error(f"通义千问 API 调用失败: {e}")
            return None

    def _parse_llm_response(self, content: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                result = json.loads(json_match.group())

                # 确保字段存在且类型正确
                result["policy_shift"] = float(result.get("policy_shift", 0))
                result["will_intensity"] = float(result.get("will_intensity", 0))
                result["industry_impact"] = result.get("industry_impact", {})
                result["summary"] = str(result.get("summary", ""))
                result["confidence"] = float(result.get("confidence", 0.5))

                # 范围约束
                result["policy_shift"] = max(-1, min(1, result["policy_shift"]))
                result["will_intensity"] = max(0, min(100, result["will_intensity"]))
                result["confidence"] = max(0, min(1, result["confidence"]))

                return result

        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"解析 LLM 响应失败: {e}")

        return None

    # ── 辅助方法 ──

    @staticmethod
    def _count_keywords(text: str, keywords: List[str]) -> int:
        """统计关键词出现次数"""
        count = 0
        for kw in keywords:
            count += text.count(kw)
        return count

    @staticmethod
    def _count_co_occurrence(
        text: str,
        keywords_a: List[str],
        keywords_b: List[str],
        window: int = 50,
    ) -> int:
        """
        计算两组关键词的共现次数（在窗口范围内）
        """
        count = 0
        for kw_a in keywords_a:
            positions = [m.start() for m in re.finditer(re.escape(kw_a), text)]
            for pos in positions:
                context = text[max(0, pos - window): pos + len(kw_a) + window]
                for kw_b in keywords_b:
                    if kw_b in context:
                        count += 1
        return count
