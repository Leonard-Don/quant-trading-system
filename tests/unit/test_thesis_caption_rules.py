"""Regression tests for thesis figure/table caption regex rules.

The figure/table caption regexes in ``scripts/finalize_shu_thesis_docx.py`` were
tightened so that body sentences mentioning a figure (e.g. ``如图 4.1 所示，...``)
and bare ``图 X.Y``/``表 X.Y`` references are no longer styled as centered captions.
These tests pin that contract by extracting the live regex literals from the
script via AST and asserting positive/negative match cases.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

THESIS_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "finalize_shu_thesis_docx.py"
)


def _extract_caption_patterns() -> dict[str, str]:
    tree = ast.parse(THESIS_SCRIPT.read_text(encoding="utf-8"))
    patterns: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "match"
            and isinstance(func.value, ast.Name)
            and func.value.id == "re"
        ):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        pattern = first.value
        if pattern.startswith("^图") and "figure" not in patterns:
            patterns["figure"] = pattern
        elif pattern.startswith("^表") and "table" not in patterns:
            patterns["table"] = pattern
    return patterns


@pytest.fixture(scope="module")
def caption_patterns() -> dict[str, str]:
    patterns = _extract_caption_patterns()
    assert "figure" in patterns, "figure caption regex missing in finalize_shu_thesis_docx.py"
    assert "table" in patterns, "table caption regex missing in finalize_shu_thesis_docx.py"
    return patterns


@pytest.mark.parametrize(
    "caption_text",
    [
        "图 4.1 行业指数趋势",
        "图 5.2 行业热力图界面",
        "图 1.1 系统总体架构",
    ],
)
def test_figure_caption_regex_matches_real_caption(
    caption_patterns: dict[str, str], caption_text: str
) -> None:
    assert re.match(caption_patterns["figure"], caption_text) is not None


@pytest.mark.parametrize(
    "body_text",
    [
        # body sentence prefixed with 如图 — never a caption
        "如图 4.1 所示，本文采用多源数据采集方案。",
        # body sentence starting with 图 X.Y but containing Chinese punctuation
        "图 5.2 描述了热力图界面，与表 5.3 的数据呼应。",
        # bare reference without title body
        "图 4.1",
        # cramped caption-like text using Chinese colon (must not be styled as caption)
        "图4.1：行业指数趋势",
    ],
)
def test_figure_caption_regex_rejects_body_or_partial(
    caption_patterns: dict[str, str], body_text: str
) -> None:
    assert re.match(caption_patterns["figure"], body_text) is None


@pytest.mark.parametrize(
    "caption_text",
    [
        "表 4.1 行业评分指标",
        "表 6.1 系统功能测试用例",
    ],
)
def test_table_caption_regex_matches_real_caption(
    caption_patterns: dict[str, str], caption_text: str
) -> None:
    assert re.match(caption_patterns["table"], caption_text) is not None


@pytest.mark.parametrize(
    "body_text",
    [
        "如表 4.1 所示，行业评分指标包含动量、估值与波动率。",
        "表 6.1 中给出了详细的功能测试用例：覆盖正常路径。",
        "表 4.1",
    ],
)
def test_table_caption_regex_rejects_body_or_partial(
    caption_patterns: dict[str, str], body_text: str
) -> None:
    assert re.match(caption_patterns["table"], body_text) is None
