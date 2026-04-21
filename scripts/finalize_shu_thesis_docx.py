from __future__ import annotations

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_BREAK
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt
from docxcompose.composer import Composer
from pypdf import PdfReader, PdfWriter


def resolve_existing_path(description: str, *candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = "\n".join(f"- {candidate}" for candidate in candidates)
    raise FileNotFoundError(f"Failed to locate {description}. Checked:\n{searched}")


def find_first_existing_path(*candidates: Path) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOC_OUTPUT_DIR = PROJECT_ROOT / "output" / "doc"
TMP_DOC_DIR = PROJECT_ROOT / "tmp" / "docs"
SCREENSHOT_DIR = PROJECT_ROOT / "docs" / "screenshots"
DOWNLOAD_DIR = Path.home() / "Downloads"
HEATMAP_HISTORY_PATH = PROJECT_ROOT / "data" / "industry" / "heatmap_history.json"
THESIS_HEATMAP_SNAPSHOT_PATH = PROJECT_ROOT / "docs" / "thesis_assets" / "frozen_heatmap_snapshot.json"
THESIS_LEADER_CASE_PATH = PROJECT_ROOT / "docs" / "thesis_assets" / "frozen_leader_case.json"

DOC_PATH = DOC_OUTPUT_DIR / "上海大学本科毕业论文_基于大数据的热门行业识别与龙头股遴选研究.docx"
TEMPLATE_PATH = resolve_existing_path(
    "official template DOCX",
    DOWNLOAD_DIR / "论文模版" / "上海大学本科毕业论文（设计）撰写格式模板.docx",
    DOWNLOAD_DIR / "上海大学本科毕业论文（设计）撰写格式模板.docx",
)
TEMPLATE_PDF_PATH = resolve_existing_path(
    "official template PDF",
    DOWNLOAD_DIR / "论文模版" / "上海大学本科毕业论文（设计）撰写格式模板.pdf",
    DOWNLOAD_DIR / "上海大学本科毕业论文（设计）撰写格式模板.pdf",
)
OUTPUT_PDF_PATH = DOC_OUTPUT_DIR / "上海大学本科毕业论文_基于大数据的热门行业识别与龙头股遴选研究.pdf"
LEGACY_DUPLICATE_PDF_PATH = DOC_OUTPUT_DIR / "上海大学本科毕业论文_基于大数据的热门行业识别与龙头股遴选研究_送审版.pdf"
COMPOSED_TMP_PATH = TMP_DOC_DIR / "shu_thesis_composed.docx"
TMP_TEMPLATE_PDF_DIR = TMP_DOC_DIR / "template_pdf_pages"
TMP_DOCX_RENDER_DIR = TMP_DOC_DIR / "current_docx_render"
TMP_SUBMISSION_RENDER_DIR = TMP_DOC_DIR / "submission_pdf_pages"
TMP_FRONT_ASSET_DIR = TMP_DOC_DIR / "pdf_front_assets"
TEMPLATE_XML_PREFIX = TMP_TEMPLATE_PDF_DIR / "template_layout"

THESIS_TITLE = "基于大数据的热门行业识别与龙头股遴选研究"
STUDENT_INFO = {
    "college": "通信与信息工程学院",
    "major": "通信工程",
    "student_id": "22121527",
    "student_name": "唐梓涵",
    "advisor": "沈文辉",
    "duration": "2025.12-2026.6",
}

FIGURE_IMAGES = {
    "图 5.1 行业热度总览界面": {
        "path": SCREENSHOT_DIR / "industry-ranking-overview.png",
        "crop": (250, 140, 1360, 1160),
        "slug": "figure_5_1",
        "width_scale": 0.72,
    },
    "图 5.2 行业热力图界面": {
        "path": SCREENSHOT_DIR / "industry-heatmap-overview.png",
        "crop": (240, 120, 1360, 1180),
        "slug": "figure_5_2",
    },
    "图 5.3 龙头股详情界面": {
        "path": SCREENSHOT_DIR / "leader-stock-detail.png",
        "crop": (300, 90, 1160, 1080),
        "slug": "figure_5_3",
    },
}
FIGURE_INTRO_PARAGRAPHS = {
    "图 5.1 行业热度总览界面":
        "如图 5.1 所示，行业热度总览页面将热力图、行业排行榜、趋势面板与龙头股入口整合在同一研究界面中，便于研究者快速完成行业筛选、排序比较与详情联动。",
    "图 5.2 行业热力图界面":
        "如图 5.2 所示，热力图视图支持按颜色维度、尺寸维度和统计周期切换行业强弱，使热门行业的横截面分布特征能够被直观比较。",
    "图 5.3 龙头股详情界面":
        "如图 5.3 所示，龙头股详情页面展示综合得分、维度拆解、价格走势与关键财务字段，能够帮助用户理解候选股票被遴选出的具体依据。",
}
TMP_ASSET_DIR = TMP_DOC_DIR / "figure_assets"
ARCHITECTURE_FIGURE_PATH = TMP_ASSET_DIR / "figure_3_1_system_architecture.png"
CJK_FONT_SOURCES = (
    (Path("/Library/Fonts/SimSun.ttf"), 0),
    (Path("/System/Library/Fonts/SimSun.ttf"), 0),
    (Path("/System/Library/Fonts/Supplemental/Songti.ttc"), 6),
    (Path("/System/Library/Fonts/Supplemental/Songti.ttc"), 1),
    (Path("/System/Library/Fonts/Supplemental/Songti.ttc"), 4),
)
BODY_PDF_ABSTRACT_PAGE_INDEX = 4
BODY_FIRST_LINE_INDENT = Emu(266700)
BODY_LINE_SPACING = Pt(23)
ABSTRACT_LINE_SPACING = Pt(20)
SOURCE_NOTE = "图片来源：系统运行截图（作者自制）"
ARCHITECTURE_SOURCE_NOTE = "图片来源：作者根据系统实现绘制"
HEADER_TEXT = "上海大学本科毕业论文（设计）"
SIGNED_DECLARATION_PAGE_CANDIDATES = (
    DOC_OUTPUT_DIR / "上海大学本科毕业论文_签字页扫描.pdf",
    DOC_OUTPUT_DIR / "上海大学本科毕业论文_签字页扫描.png",
    DOC_OUTPUT_DIR / "上海大学本科毕业论文_签字页扫描.jpg",
    DOC_OUTPUT_DIR / "上海大学本科毕业论文_签字页扫描.jpeg",
    DOC_OUTPUT_DIR / "签字页扫描.pdf",
    DOC_OUTPUT_DIR / "签字页扫描.png",
    DOC_OUTPUT_DIR / "签字页扫描.jpg",
    DOC_OUTPUT_DIR / "签字页扫描.jpeg",
)
LEADER_CASE_ANALYSIS_FALLBACK_TEXT = (
    "为补充说明龙头股遴选结果，本文固定引用项目中保存的一条龙头股双榜单样本。"
    "从该样本可以看到，系统不会把行业热度排序简单重复为单一股票列表，而是同时输出"
    "core（核心资产）与 hot（热点先锋）两类结果：前者更强调规模、估值与盈利质量，"
    "后者更强调短期涨幅和资金承接。该设计使行业识别结果能够进一步延伸为行业内个股的"
    "结构化筛选结果。"
)

COVER_FIELD_ORDER = [
    "title",
    "college",
    "major",
    "student_id",
    "student_name",
    "advisor",
    "duration",
]

COVER_FIELD_SPECS = {
    "title": {
        "text": THESIS_TITLE,
        # SHU cover spec: title in small No.2, rendered here on the
        # 150dpi template image as an approximately equivalent pixel size.
        "font_size": 38,
        "max_width": 520,
        "align": "center",
        "padding_x": 0,
        "gap_above_line": 4,
    },
    "college": {
        "text": STUDENT_INFO["college"],
        "font_size": 33,
        "max_width": 438,
        "align": "left",
        "padding_x": 8,
        "gap_above_line": 2,
    },
    "major": {
        "text": STUDENT_INFO["major"],
        "font_size": 33,
        "max_width": 438,
        "align": "left",
        "padding_x": 8,
        "gap_above_line": 2,
    },
    "student_id": {
        "text": STUDENT_INFO["student_id"],
        "font_size": 33,
        "max_width": 440,
        "align": "left",
        "padding_x": 8,
        "gap_above_line": 2,
    },
    "student_name": {
        "text": STUDENT_INFO["student_name"],
        "font_size": 33,
        "max_width": 440,
        "align": "left",
        "padding_x": 8,
        "gap_above_line": 2,
    },
    "advisor": {
        "text": STUDENT_INFO["advisor"],
        "font_size": 33,
        "max_width": 440,
        "align": "left",
        "padding_x": 8,
        "gap_above_line": 2,
    },
    "duration": {
        "text": STUDENT_INFO["duration"],
        "font_size": 33,
        "max_width": 440,
        "align": "left",
        "padding_x": 8,
        "gap_above_line": 2,
    },
}

COVER_FALLBACK_LINES = {
    "title": {"x_start": 458, "x_end": 964, "y_line": 848},
    "college": {"x_start": 444, "x_end": 949, "y_line": 976},
    "major": {"x_start": 444, "x_end": 949, "y_line": 1041},
    "student_id": {"x_start": 444, "x_end": 949, "y_line": 1106},
    "student_name": {"x_start": 444, "x_end": 949, "y_line": 1171},
    "advisor": {"x_start": 444, "x_end": 949, "y_line": 1236},
    "duration": {"x_start": 444, "x_end": 949, "y_line": 1301},
}

DECLARATION_FIELD_SPECS = {
    "student_name": {
        "text": STUDENT_INFO["student_name"],
        "anchor_label": "姓名：",
        "font_size": 20,
        "max_width": 160,
        "padding_x": 18,
        "vertical_align": "center",
    },
    "student_id": {
        "text": STUDENT_INFO["student_id"],
        "anchor_label": "学号：",
        "font_size": 19,
        "max_width": 170,
        "padding_x": 16,
        "vertical_align": "center",
    },
    "thesis_title": {
        "text": THESIS_TITLE,
        "anchor_label": "论文题目：",
        "font_size": 20,
        "max_width": 560,
        "padding_x": 22,
        "vertical_align": "center",
    },
}

DECLARATION_FALLBACK_LABEL_BOXES = {
    "姓名：": {"left": 214, "top": 160, "right": 339, "bottom": 185},
    "学号：": {"left": 747, "top": 160, "right": 822, "bottom": 185},
    "论文题目：": {"left": 214, "top": 208, "right": 339, "bottom": 233},
}


TOC_BLUEPRINT = [
    ("toc 1", "摘  要"),
    ("toc 1", "ABSTRACT"),
    ("toc 1", "1 绪论"),
    ("toc 2", "1.1 研究背景与意义"),
    ("toc 2", "1.2 国内外研究现状"),
    ("toc 2", "1.3 研究内容与技术路线"),
    ("toc 2", "1.4 论文结构安排"),
    ("toc 1", "2 相关技术与理论基础"),
    ("toc 2", "2.1 金融大数据的特征"),
    ("toc 2", "2.2 多源数据采集与清洗"),
    ("toc 2", "2.3 热门行业识别的理论基础"),
    ("toc 2", "2.4 龙头股评价的理论基础"),
    ("toc 2", "2.5 系统关键技术"),
    ("toc 1", "3 系统需求分析与总体设计"),
    ("toc 2", "3.1 设计目标"),
    ("toc 2", "3.2 功能需求分析"),
    ("toc 2", "3.3 非功能需求分析"),
    ("toc 2", "3.4 系统总体架构设计"),
    ("toc 2", "3.5 数据流程设计"),
    ("toc 2", "3.6 存储设计"),
    ("toc 1", "4 热门行业识别与龙头股遴选模型设计"),
    ("toc 2", "4.1 数据预处理与指标标准化"),
    ("toc 2", "4.2 热门行业识别模型设计"),
    ("toc 2", "4.3 行业波动率估计与聚类辅助分析"),
    ("toc 2", "4.4 龙头股综合评分模型设计"),
    ("toc 2", "4.5 快速评分机制设计"),
    ("toc 1", "5 系统实现"),
    ("toc 2", "5.1 数据提供器与回退机制实现"),
    ("toc 2", "5.2 行业分析模块实现"),
    ("toc 2", "5.3 龙头股评分模块实现"),
    ("toc 2", "5.4 后端接口实现"),
    ("toc 2", "5.5 前端可视化实现"),
    ("toc 2", "5.6 偏好配置与持续跟踪实现"),
    ("toc 1", "6 系统测试与结果分析"),
    ("toc 2", "6.1 测试环境"),
    ("toc 2", "6.2 功能测试"),
    ("toc 2", "6.3 热力图快照结果分析"),
    ("toc 2", "6.4 系统特征与不足分析"),
    ("toc 2", "6.5 对毕业设计目标的达成情况"),
    ("toc 1", "结 论"),
    ("toc 1", "参考文献"),
    ("toc 1", "致 谢"),
]


def clear_paragraph(paragraph) -> None:
    p = paragraph._element
    p_pr = p.pPr
    for child in list(p):
        if child is not p_pr:
            p.remove(child)


def delete_paragraph(paragraph) -> None:
    element = paragraph._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def remove_section_break(paragraph) -> None:
    p_pr = paragraph._element.pPr
    if p_pr is None:
        return
    sect_pr = p_pr.find(qn("w:sectPr"))
    if sect_pr is not None:
        p_pr.remove(sect_pr)


def set_east_asia_font(run, font_name: str) -> None:
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.rFonts
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, r_fonts)
    r_fonts.set(qn("w:eastAsia"), font_name)
    r_fonts.set(qn("w:ascii"), "Times New Roman")
    r_fonts.set(qn("w:hAnsi"), "Times New Roman")


def replace_paragraph_text(paragraph, text: str) -> None:
    clear_paragraph(paragraph)
    paragraph.add_run(text)


def replace_cover_line(paragraph, prefix: str, value: str, gap_spaces: int = 8) -> None:
    clear_paragraph(paragraph)
    paragraph.add_run(f"{prefix}{' ' * gap_spaces}{value}")


def ensure_page_break_before(paragraph) -> None:
    previous = paragraph._element.getprevious()
    if previous is not None and previous.tag == qn("w:p"):
        from docx.text.paragraph import Paragraph

        previous_para = Paragraph(previous, paragraph._parent)
        if previous_para.text.strip() == "" and 'w:type="page"' in previous_para._element.xml:
            return
    break_para = paragraph.insert_paragraph_before()
    break_para.add_run().add_break(WD_BREAK.PAGE)


def remove_page_break_before_flag(paragraph) -> None:
    p_pr = paragraph._element.get_or_add_pPr()
    for node in p_pr.findall(qn("w:pageBreakBefore")):
        p_pr.remove(node)


def format_unnumbered_heading(paragraph) -> None:
    paragraph.style = "Normal"
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing = 1.0
    if not paragraph.runs:
        paragraph.add_run(paragraph.text)
    for run in paragraph.runs:
        run.font.bold = True
        run.font.size = Pt(18)
        run.font.name = "Times New Roman"
        set_east_asia_font(run, "黑体")


def format_toc_title(paragraph) -> None:
    clear_paragraph(paragraph)
    paragraph.style = "Normal"
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = Pt(20)
    paragraph.paragraph_format.page_break_before = True
    run = paragraph.add_run("目  录")
    run.font.bold = False
    run.font.size = Pt(18)
    run.font.name = "Times New Roman"
    set_east_asia_font(run, "黑体")


def add_page_number_field(paragraph) -> None:
    clear_paragraph(paragraph)
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_separate = OxmlElement("w:fldChar")
    fld_separate.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")

    run = paragraph.add_run()
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_separate)
    run._r.append(fld_end)
    run.font.name = "Times New Roman"
    run.font.size = Pt(10.5)
    set_east_asia_font(run, "宋体")


def set_section_page_number_format(section, fmt: str | None = None, start: int | None = None) -> None:
    sect_pr = section._sectPr
    pg_num = sect_pr.find(qn("w:pgNumType"))
    if pg_num is None:
        pg_num = OxmlElement("w:pgNumType")
        sect_pr.append(pg_num)
    if fmt:
        pg_num.set(qn("w:fmt"), fmt)
    if start is not None:
        pg_num.set(qn("w:start"), str(start))


def configure_section_header(section, text: str | None) -> None:
    section.different_first_page_header_footer = False
    header_para = section.header.paragraphs[0]
    clear_paragraph(header_para)
    header_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header_para.paragraph_format.first_line_indent = Pt(0)
    header_para.paragraph_format.space_before = Pt(0)
    header_para.paragraph_format.space_after = Pt(0)
    if text:
        run = header_para.add_run(text)
        run.font.name = "Times New Roman"
        run.font.size = Pt(10.5)
        run.font.bold = False
        set_east_asia_font(run, "宋体")


def configure_section_footer(section, with_page_number: bool) -> None:
    footer_para = section.footer.paragraphs[0]
    clear_paragraph(footer_para)
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_para.paragraph_format.first_line_indent = Pt(0)
    footer_para.paragraph_format.space_before = Pt(0)
    footer_para.paragraph_format.space_after = Pt(0)
    if with_page_number:
        add_page_number_field(footer_para)


def set_run_text_font(run, east_asia_font: str, size: Pt, bold: bool | None = None) -> None:
    run.font.name = "Times New Roman"
    run.font.size = size
    if bold is not None:
        run.font.bold = bold
    set_east_asia_font(run, east_asia_font)


def format_body_run(run) -> None:
    if not run.text:
        return
    if run.font.size is None:
        run.font.size = Pt(12)
    run.font.name = "Times New Roman"
    set_east_asia_font(run, "宋体")


def normalize_search_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", text or "")
    return normalized.replace("（", "(").replace("）", ")")


def insert_paragraph_after(paragraph, text: str = ""):
    from docx.text.paragraph import Paragraph

    new_p = OxmlElement("w:p")
    paragraph._element.addnext(new_p)
    new_para = Paragraph(new_p, paragraph._parent)
    if text:
        new_para.add_run(text)
    return new_para


def insert_paragraph_before_element(element, parent):
    from docx.text.paragraph import Paragraph

    new_p = OxmlElement("w:p")
    element.addprevious(new_p)
    return Paragraph(new_p, parent)


def parse_iso_datetime(value: str | None) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def format_chinese_timestamp(value: str | None) -> str:
    parsed = parse_iso_datetime(value)
    if parsed is None:
        return str(value or "").strip()
    return f"{parsed.year} 年 {parsed.month} 月 {parsed.day} 日 {parsed.hour:02d}:{parsed.minute:02d}:{parsed.second:02d}"


def coerce_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_heatmap_snapshot_from_path(path: Path, days: int = 5) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("days", 0) or 0) != days:
        return None
    industries = payload.get("industries")
    if not isinstance(industries, list) or not industries:
        return None
    return payload


def load_latest_heatmap_snapshot(days: int = 5) -> dict | None:
    if not HEATMAP_HISTORY_PATH.exists():
        return None
    try:
        payload = json.loads(HEATMAP_HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None

    candidates = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if int(item.get("days", 0) or 0) != days:
            continue
        industries = item.get("industries")
        if not isinstance(industries, list) or not industries:
            continue
        candidates.append(item)
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item: (
            parse_iso_datetime(item.get("captured_at"))
            or parse_iso_datetime(item.get("update_time"))
            or datetime.min
        ),
    )


def load_thesis_heatmap_snapshot(days: int = 5) -> dict | None:
    frozen_snapshot = _load_heatmap_snapshot_from_path(THESIS_HEATMAP_SNAPSHOT_PATH, days=days)
    if frozen_snapshot is not None:
        frozen_payload = dict(frozen_snapshot)
        frozen_payload["_thesis_frozen"] = True
        return frozen_payload
    return load_latest_heatmap_snapshot(days=days)


def load_thesis_leader_case() -> dict | None:
    if not THESIS_LEADER_CASE_PATH.exists():
        return None
    try:
        payload = json.loads(THESIS_LEADER_CASE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    focus_industry = str(payload.get("focus_industry") or "").strip()
    core = payload.get("core")
    hot = payload.get("hot")
    if not focus_industry or not isinstance(core, list) or not isinstance(hot, list):
        return None
    if not core or not hot:
        return None
    return payload


def build_leader_case_analysis_text(payload: dict | None) -> str:
    if payload is None:
        return LEADER_CASE_ANALYSIS_FALLBACK_TEXT

    focus_industry = str(payload.get("focus_industry") or "").strip()
    captured_display = format_chinese_timestamp(payload.get("captured_at"))
    related_heatmap_display = format_chinese_timestamp(payload.get("related_heatmap_captured_at"))
    core_names = "、".join(
        str(item.get("name") or "").strip()
        for item in payload.get("core", [])[:3]
        if str(item.get("name") or "").strip()
    )
    hot_names = "、".join(
        str(item.get("name") or "").strip()
        for item in payload.get("hot", [])[:3]
        if str(item.get("name") or "").strip()
    )
    if not focus_industry or not core_names or not hot_names:
        return LEADER_CASE_ANALYSIS_FALLBACK_TEXT

    if related_heatmap_display:
        prefix = (
            "为保证龙头股案例与热力图样例一样可复核，本文固定引用项目中保存的一条龙头股双榜单样本。"
            f"结合 {related_heatmap_display} 保留的热力图样例可以看到，{focus_industry}行业处于当期热点前列；"
        )
    else:
        prefix = (
            "为保证龙头股案例可复核，本文固定引用项目中保存的一条龙头股双榜单样本。"
        )

    if captured_display:
        prefix += f"根据 {captured_display} 记录的榜单结果，"

    return (
        prefix
        + f"{focus_industry}行业的 core 榜单前列主要为{core_names}，"
        f"hot 榜单前列则出现{hot_names}；前者更偏向规模、估值和盈利质量的综合筛选，"
        "后者更强调短期涨幅与资金承接。该结果说明龙头股遴选并非对行业热度排序的简单复制，"
        "而是在已识别热门行业基础上进一步提供“核心资产”和“热点先锋”两类互补视角。"
    )


def build_heatmap_result_section_text(snapshot: dict | None) -> tuple[str, str, str]:
    fallback_intro = (
        "为了增强论文结果分析的真实性，本文直接选取项目中已经保存的热力图历史快照作为样本。"
        "表 6.2 展示了项目当前保留的一条五日窗口快照中的前十个行业横截面字段，包括综合得分、5 日涨跌"
        "幅、资金流和换手率等信息，用于说明系统在固定统计窗口下的输出结果。需要说明的是，这里给出的结果"
        "主要用于样例分析，并不构成完整回测结论。"
    )
    fallback_analysis = (
        "从表 6.2 可以看出，样本时点前列行业并不完全由单一风格板块构成，而是呈现出多方向扩散特征。"
        "这说明系统并非只根据某一项价格指标排序，而是在统一横截面上综合考虑动量、资金流、活跃度和波动率"
        "代理后给出相对得分。"
    )
    fallback_conclusion = (
        "从快照字段本身也能看出，系统输出的不是单一涨跌幅排行。表 6.2 同时保留了 value、total_score、"
        "moneyFlow、turnoverRate、行业波动率和市值来源等信息，所以后文讨论某个行业为什么排在前面时，"
        "能够直接回到对应字段去解释。对毕业设计答辩来说，这样的结果更便于把评分逻辑讲清楚。"
    )
    if snapshot is None:
        return fallback_intro, fallback_analysis, fallback_conclusion

    industries = [
        item for item in snapshot.get("industries", [])
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ][:10]
    if not industries:
        return fallback_intro, fallback_analysis, fallback_conclusion

    captured_display = format_chinese_timestamp(snapshot.get("captured_at") or snapshot.get("update_time"))
    update_display = format_chinese_timestamp(snapshot.get("update_time") or snapshot.get("captured_at"))
    lead_names = "、".join(item["name"] for item in industries[:6])
    top_item = industries[0]
    contrast_item = next(
        (
            item for item in industries[1:]
            if coerce_float(item.get("moneyFlow")) < 0 and coerce_float(item.get("value")) > 0
        ),
        None,
    )

    is_frozen_snapshot = bool(snapshot.get("_thesis_frozen"))
    intro_prefix = (
        "为保证论文样例在多次生成过程中的一致性，本文固定引用项目中已经保存的一条五日窗口热力图快照作为样本。"
        if is_frozen_snapshot
        else "为了增强论文结果分析的真实性，本文直接选取项目当前仍保留的历史快照作为样本。"
    )

    if captured_display and captured_display == update_display:
        intro_text = (
            intro_prefix
            + f"根据 {captured_display} 记录的一条五日窗口热力图快照，表 6.2 展示了该样本时点前十个行业的综"
            "合得分、5 日涨跌幅、资金流和换手率等字段，用于说明系统在固定横截面上的输出结果。需要说明的是，"
            "这里给出的结果主要用于样例分析，并不构成完整回测结论。"
        )
    else:
        intro_text = (
            intro_prefix
            + f"根据 {captured_display} 记录的一条五日窗口热力图快照（对应快照更新时间为 {update_display}），"
            "表 6.2 展示了该样本时点前十个行业的综合得分、5 日涨跌幅、资金流和换手率等字段，用于说明系统"
            "在固定横截面上的输出结果。需要说明的是，这里给出的结果主要用于样例分析，并不构成完整回测结论。"
        )
    if contrast_item is None:
        analysis_text = (
            f"从表 6.2 可以看出，{lead_names}等行业位于前列，说明样本时点的市场热点呈现出多方向扩散特征，"
            "而非只集中在单一子行业。由此可见，系统给出的综合得分并不是对单一涨跌幅的简单重排，而是对多项横"
            "截面指标进行统一标准化之后的综合结果。"
        )
    else:
        contrast_flow_yi = coerce_float(contrast_item.get("moneyFlow")) / 1e8
        contrast_change = coerce_float(contrast_item.get("value"))
        analysis_text = (
            f"从表 6.2 可以看出，{lead_names}等行业位于前列，说明样本时点的市场热点呈现出多方向扩散特征，"
            f"而非只集中在单一子行业。值得注意的是，{contrast_item['name']}在 5 日涨跌幅达到 "
            f"{contrast_change:.2f}% 的同时资金流仍为 {contrast_flow_yi:.2f} 亿元，而{top_item['name']}"
            "的综合得分更高。这说明系统生成的 total_score 并不简单等同于单一涨跌幅排序，而是横截面标准"
            "化后多个因子共同作用的结果。"
        )
    conclusion_text = (
        "从这条快照保留的字段就能看出，系统输出的不是单一涨跌幅排行。表 6.2 同时记录了 value、"
        "total_score、moneyFlow、turnoverRate、行业波动率和市值来源等信息，所以后文讨论某个行业"
        "为什么排在前面时，能够直接回到对应字段去解释。对毕业设计答辩来说，这样的结果有一个现实好处："
        "老师看到的不只是“哪个行业涨得多”，而是还能继续追问资金、活跃度和波动代理分别起了什么作用。"
    )
    return intro_text, analysis_text, conclusion_text


def update_heatmap_sample_table(sample_table, snapshot: dict | None) -> None:
    if sample_table is None or len(sample_table.rows) < 2 or len(sample_table.columns) < 6:
        return

    sample_table.cell(0, 0).text = "序号"
    sample_table.cell(0, 4).text = "资金流(亿元)"

    industries = []
    if isinstance(snapshot, dict):
        industries = [
            item for item in snapshot.get("industries", [])
            if isinstance(item, dict)
        ][:10]

    for row_index in range(1, min(len(sample_table.rows), 11)):
        if row_index - 1 < len(industries):
            item = industries[row_index - 1]
            sample_table.cell(row_index, 0).text = str(row_index)
            sample_table.cell(row_index, 1).text = str(item.get("name", ""))
            sample_table.cell(row_index, 2).text = f"{coerce_float(item.get('total_score')):.2f}"
            sample_table.cell(row_index, 3).text = f"{coerce_float(item.get('value')):.2f}"
            sample_table.cell(row_index, 4).text = f"{coerce_float(item.get('moneyFlow')) / 1e8:.2f}"
            sample_table.cell(row_index, 5).text = f"{coerce_float(item.get('turnoverRate')):.2f}"
        else:
            for col_index in range(6):
                sample_table.cell(row_index, col_index).text = ""


def ensure_section_trailing_paragraph(doc: Document, next_heading_text: str, prefix: str, text: str):
    from docx.text.paragraph import Paragraph

    heading = find_paragraph_by_text(doc, next_heading_text)
    previous = heading._element.getprevious()
    while previous is not None:
        if previous.tag != qn("w:p"):
            previous = previous.getprevious()
            continue
        paragraph = Paragraph(previous, heading._parent)
        stripped = paragraph.text.strip()
        if not stripped:
            previous = previous.getprevious()
            continue
        if stripped.startswith(prefix) or stripped == text:
            replace_paragraph_text(paragraph, text)
            return paragraph
        break

    inserted = insert_paragraph_before_element(heading._element, heading._parent)
    inserted.add_run(text)
    return inserted


def insert_table_before_element(doc: Document, element, rows: int, cols: int):
    table = doc.add_table(rows=rows, cols=cols)
    tbl = table._tbl
    element.addprevious(tbl)
    return table


def fill_cover(doc: Document) -> None:
    replacements = {
        "题   目：": (THESIS_TITLE, 8),
        "学    院：": (STUDENT_INFO["college"], 8),
        "专    业：": (STUDENT_INFO["major"], 8),
        "学    号：": (STUDENT_INFO["student_id"], 8),
        "学生姓名：": (STUDENT_INFO["student_name"], 6),
        "指导教师：": (STUDENT_INFO["advisor"], 6),
        "起讫日期：": (STUDENT_INFO["duration"], 8),
    }
    for paragraph in doc.paragraphs:
        for prefix, (value, gap_spaces) in replacements.items():
            if paragraph.text.startswith(prefix):
                replace_cover_line(paragraph, prefix, value, gap_spaces=gap_spaces)


def fill_declaration_table(doc: Document) -> None:
    if not doc.tables:
        return
    table = doc.tables[0]
    table.cell(0, 0).text = f"姓    名：{STUDENT_INFO['student_name']}"
    table.cell(0, 1).text = f"学号：{STUDENT_INFO['student_id']}"
    merged = table.cell(1, 0).merge(table.cell(1, 1))
    merged.text = f"论文题目：{THESIS_TITLE}"


def remove_elements_before_paragraph(doc: Document, text: str) -> None:
    body = doc._element.body
    anchor = None
    for paragraph in doc.paragraphs:
        if paragraph.text.strip() == text:
            anchor = paragraph._element
            break
    if anchor is None:
        raise RuntimeError(f"Paragraph not found for strip-before: {text}")

    for child in list(body):
        if child is anchor:
            break
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def remove_elements_from_paragraph(doc: Document, text: str) -> None:
    body = doc._element.body
    anchor = None
    for paragraph in doc.paragraphs:
        if paragraph.text.strip() == text:
            anchor = paragraph._element
            break
    if anchor is None:
        raise RuntimeError(f"Paragraph not found for strip-after: {text}")

    removing = False
    for child in list(body):
        if child is anchor:
            removing = True
        if removing and child.tag != qn("w:sectPr"):
            body.remove(child)


def find_heading_break_paragraph(doc: Document, heading_text: str):
    heading_index = None
    for index, paragraph in enumerate(doc.paragraphs):
        if paragraph.text.strip() == heading_text:
            heading_index = index
            break
    if heading_index is None:
        raise RuntimeError(f"Heading not found: {heading_text}")

    for index in range(heading_index - 1, max(-1, heading_index - 5), -1):
        if "w:sectPr" in doc.paragraphs[index]._element.xml:
            return doc.paragraphs[index]
    raise RuntimeError(f"Section break paragraph not found before heading: {heading_text}")


def replace_first_paragraph_starting_with(doc: Document, prefix: str, replacement: str) -> bool:
    prefix_hint = prefix[:24]
    replacement_prefix = replacement[:24]
    for paragraph in doc.paragraphs:
        stripped = paragraph.text.strip()
        if stripped.startswith(prefix) or stripped.startswith(prefix_hint) or stripped.startswith(replacement_prefix):
            replace_paragraph_text(paragraph, replacement)
            return True
    return False


def find_last_paragraph_index_by_text(doc: Document, text: str) -> int:
    matches = [idx for idx, paragraph in enumerate(doc.paragraphs) if paragraph.text.strip() == text]
    if not matches:
        raise RuntimeError(f"Paragraph not found: {text}")
    return matches[-1]


def replace_section_body(doc: Document, heading_text: str, next_heading_text: str, paragraphs: list[str]) -> None:
    start_index = find_last_paragraph_index_by_text(doc, heading_text)
    end_index = next(
        (
            idx
            for idx in range(start_index + 1, len(doc.paragraphs))
            if doc.paragraphs[idx].text.strip() == next_heading_text
        ),
        None,
    )
    if end_index is None:
        raise RuntimeError(f"Section end heading not found after {heading_text}: {next_heading_text}")

    heading_para = doc.paragraphs[start_index]
    end_element = doc.paragraphs[end_index]._element
    current_element = heading_para._element.getnext()
    while current_element is not None and current_element is not end_element:
        next_element = current_element.getnext()
        current_element.getparent().remove(current_element)
        current_element = next_element

    current = heading_para
    for text in paragraphs:
        current = insert_paragraph_after(current, text)
        if re.match(r"^\d+\.\d+\.\d+\s+", text):
            current.style = "Heading 3"


def insert_table_after(doc: Document, paragraph, rows: int, cols: int):
    table = doc.add_table(rows=rows, cols=cols)
    tbl = table._tbl
    paragraph._element.addnext(tbl)
    return table


def set_cell_fill(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)


def set_cell_borders(cell, color: str | None = None, size: str = "16") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = tc_borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            tc_borders.append(node)
        if color:
            node.set(qn("w:val"), "single")
            node.set(qn("w:sz"), size)
            node.set(qn("w:space"), "0")
            node.set(qn("w:color"), color)
        else:
            node.set(qn("w:val"), "nil")


def format_architecture_cell(cell, title: str, body_lines: list[str], fill: str, border_color: str) -> None:
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    set_cell_fill(cell, fill)
    set_cell_borders(cell, border_color, size="18")
    paragraph = cell.paragraphs[0]
    clear_paragraph(paragraph)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = Pt(17)
    title_run = paragraph.add_run(title)
    set_run_text_font(title_run, "宋体", Pt(16), bold=True)
    title_run.add_break(WD_BREAK.LINE)
    body_run = paragraph.add_run("\n".join(body_lines))
    set_run_text_font(body_run, "宋体", Pt(12))


def format_architecture_arrow_cell(cell) -> None:
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    set_cell_fill(cell, "F8FAFD")
    set_cell_borders(cell, None)
    paragraph = cell.paragraphs[0]
    clear_paragraph(paragraph)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run("↓")
    set_run_text_font(run, "宋体", Pt(16), bold=True)


def format_architecture_summary_cell(cell, lines: list[str]) -> None:
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    set_cell_fill(cell, "FFFFFF")
    set_cell_borders(cell, "B0B8C2", size="12")
    paragraph = cell.paragraphs[0]
    clear_paragraph(paragraph)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = Pt(16)
    run = paragraph.add_run("\n".join(lines))
    set_run_text_font(run, "宋体", Pt(11))


def build_architecture_diagram(output_path: Path) -> Path:
    TMP_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    width, height = 1280, 980
    image = Image.new("RGB", (width, height), "#F8FAFD")
    draw = ImageDraw.Draw(image)
    font_sources = get_available_cjk_font_sources()

    title_font = fit_cjk_font(draw, "系统总体架构图", 520, 34, min_size=28, font_sources=font_sources)
    layer_font = fit_cjk_font(draw, "表现层", 260, 28, min_size=22, font_sources=font_sources)
    text_font = fit_cjk_font(draw, "行业热力图 / 行业排行榜", 920, 22, min_size=18, font_sources=font_sources)
    summary_font = fit_cjk_font(draw, "多源适配、分层缓存与前后端协同", 900, 20, min_size=16, font_sources=font_sources)

    draw.text((width / 2, 44), "系统总体架构图", fill="#243447", font=title_font, anchor="ma")

    layer_specs = [
        ("表现层", "行业热力图 / 行业排行榜\n行业趋势面板 / 龙头股详情", "#D9EAFB", "#5B8FD9"),
        ("服务层", "FastAPI 行业接口 / 参数校验\n响应封装 / 端点缓存", "#E3F4E8", "#5BA36B"),
        ("分析层", "行业分析器 / 龙头股评分器\n快速评分链路 / 波动率估计", "#FDEBCF", "#C58B1C"),
        ("数据层", "THS 主数据 / AKShare 增强\nSina 与腾讯补充 / JSON 与 localStorage", "#EFE2FB", "#8B62C4"),
    ]

    box_left, box_right = 120, 1160
    box_height = 145
    gap = 28
    start_top = 88

    for index, (layer_name, layer_text, fill_color, line_color) in enumerate(layer_specs):
        top = start_top + index * (box_height + gap)
        bottom = top + box_height
        draw.rounded_rectangle((box_left, top, box_right, bottom), radius=28, fill=fill_color, outline=line_color, width=5)
        draw.text((width / 2, top + 42), layer_name, fill="#1F2D3D", font=layer_font, anchor="ma")
        draw.multiline_text(
            (width / 2, top + 88),
            layer_text,
            fill="#2E3A46",
            font=text_font,
            anchor="ma",
            align="center",
            spacing=10,
        )
        if index < len(layer_specs) - 1:
            arrow_center_x = width // 2
            arrow_top = bottom + 8
            arrow_bottom = bottom + gap - 4
            draw.line((arrow_center_x, arrow_top, arrow_center_x, arrow_bottom), fill="#7A8794", width=5)
            draw.polygon(
                [
                    (arrow_center_x, arrow_bottom + 10),
                    (arrow_center_x - 12, arrow_bottom - 6),
                    (arrow_center_x + 12, arrow_bottom - 6),
                ],
                fill="#7A8794",
            )

    draw.rounded_rectangle((185, 865, 1095, 935), radius=20, fill="#FFFFFF", outline="#B0B8C2", width=3)
    draw.multiline_text(
        (width / 2, 898),
        "多源适配、分层缓存与前后端协同\n共同支撑热门行业识别与龙头股遴选闭环",
        fill="#3A4652",
        font=summary_font,
        anchor="mm",
        align="center",
        spacing=10,
    )

    image.save(output_path)
    return output_path


def insert_architecture_figure(doc: Document) -> None:
    anchor = find_last_paragraph_by_text(doc, "3.5 数据流程设计")
    break_para = insert_paragraph_before_element(anchor._element, anchor._parent)
    break_para.paragraph_format.first_line_indent = Pt(0)
    break_para.paragraph_format.space_before = Pt(0)
    break_para.paragraph_format.space_after = Pt(0)
    break_para.paragraph_format.page_break_before = True
    break_para.paragraph_format.keep_with_next = True

    diagram_table = insert_table_after(doc, break_para, rows=8, cols=1)
    diagram_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    diagram_table.autofit = False
    table_width = int((doc.sections[-1].page_width - doc.sections[-1].left_margin - doc.sections[-1].right_margin) * 0.88)
    for row in diagram_table.rows:
        row.cells[0].width = Emu(table_width)
        _set_row_no_split(row)

    row_specs = [
        ("layer", "表现层", ["行业热力图 / 行业排行榜", "行业趋势面板 / 龙头股详情"], "D9EAFB", "5B8FD9", Cm(2.2)),
        ("arrow",),
        ("layer", "服务层", ["FastAPI 行业接口 / 参数校验", "响应封装 / 端点缓存"], "E3F4E8", "5BA36B", Cm(2.1)),
        ("arrow",),
        ("layer", "分析层", ["行业分析器 / 龙头股评分器", "快速评分 / 波动率估计"], "FDEBCF", "C58B1C", Cm(2.1)),
        ("arrow",),
        ("layer", "数据层", ["THS 主数据 / AKShare 增强", "Sina 与腾讯补充 / JSON 与 localStorage"], "EFE2FB", "8B62C4", Cm(2.2)),
        ("summary", ["多源适配、分层缓存与前后端协同", "共同支撑热门行业识别与龙头股遴选闭环"], Cm(1.55)),
    ]

    for row, spec in zip(diagram_table.rows, row_specs):
        kind = spec[0]
        if kind == "layer":
            _, title, lines, fill, border, height = spec
            row.height = height
            row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
            format_architecture_cell(row.cells[0], title, lines, fill, border)
        elif kind == "summary":
            _, lines, height = spec
            row.height = height
            row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
            format_architecture_summary_cell(row.cells[0], lines)
        else:
            row.height = Cm(0.45)
            row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
            format_architecture_arrow_cell(row.cells[0])

    caption = insert_paragraph_before_element(anchor._element, anchor._parent)
    caption.add_run("图 3.1 系统总体架构图")
    caption.paragraph_format.keep_with_next = True
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.first_line_indent = Pt(0)
    caption.paragraph_format.space_before = Pt(6)
    caption.paragraph_format.space_after = Pt(0)
    for run in caption.runs:
        set_run_text_font(run, "宋体", Pt(12))

    source = insert_paragraph_before_element(anchor._element, anchor._parent)
    source.add_run(ARCHITECTURE_SOURCE_NOTE)
    source.alignment = WD_ALIGN_PARAGRAPH.CENTER
    source.paragraph_format.first_line_indent = Pt(0)
    source.paragraph_format.space_before = Pt(0)
    source.paragraph_format.space_after = Pt(0)
    source.paragraph_format.keep_with_next = True
    for run in source.runs:
        set_run_text_font(run, "宋体", Pt(12), bold=True)


def insert_task_completion_table(doc: Document) -> None:
    heading = find_last_paragraph_by_text(doc, "6.5 对毕业设计目标的达成情况")
    intro_para = None
    next_element = heading._element.getnext()
    if next_element is not None and next_element.tag == qn("w:p"):
        from docx.text.paragraph import Paragraph

        intro_para = Paragraph(next_element, heading._parent)
    if intro_para is None:
        intro_para = insert_paragraph_after(heading, "对照任务书要求，如表 6.3 所示，本文在理论分析、模型设计和系统实现三个层面均完成了核心目标。")

    caption = insert_paragraph_after(intro_para, "表 6.3 毕业设计任务书目标达成情况")
    caption.paragraph_format.keep_with_next = True

    table = insert_table_after(doc, caption, rows=4, cols=4)
    rows = [
        ("任务书要求", "论文对应内容", "系统对应实现", "达成情况"),
        ("理解金融大数据挖掘相关技术与研究现状", "第 1 章与第 2 章完成文献综述和理论基础梳理", "明确行业子系统的数据来源、分析流程与关键技术", "已达成"),
        ("掌握行业识别与龙头股筛选方法", "第 4 章构建行业热度模型与龙头股评分模型", "实现行业横截面评分、波动率代理与双路径个股评分", "已达成"),
        ("编程设计软件系统跟踪重点行业和关键企业", "第 5 章与第 6 章说明系统实现与验证过程", "完成 THS-first、FastAPI、React、热力图快照与偏好持久化闭环", "已达成"),
    ]
    for r_idx, row in enumerate(rows):
        for c_idx, value in enumerate(row):
            table.cell(r_idx, c_idx).text = value


def ensure_blank_page_before_declaration(doc: Document) -> None:
    if not doc.tables:
        return

    declaration_table = doc.tables[0]

    next_sibling = declaration_table._element.getnext()
    if next_sibling is not None and next_sibling.tag == qn("w:p") and 'w:type="page"' in next_sibling.xml:
        next_sibling.getparent().remove(next_sibling)

    previous_sibling = declaration_table._element.getprevious()
    if previous_sibling is not None and previous_sibling.tag == qn("w:p") and 'w:type="page"' in previous_sibling.xml:
        return

    break_para = OxmlElement("w:p")
    run = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    run.append(br)
    break_para.append(run)
    declaration_table._element.addprevious(break_para)


def set_core_properties(doc: Document) -> None:
    doc.core_properties.author = STUDENT_INFO["student_name"]
    doc.core_properties.title = THESIS_TITLE
    doc.core_properties.subject = THESIS_TITLE
    doc.core_properties.keywords = "金融大数据, 热门行业识别, 龙头股遴选, 多源数据, 量化研究平台"


def run_checked(command: list[str]) -> None:
    subprocess.run(command, check=True)


def get_available_cjk_font_sources() -> list[tuple[Path, int]]:
    sources = [(path, index) for path, index in CJK_FONT_SOURCES if path.exists()]
    if not sources:
        raise RuntimeError("No available CJK font found for thesis front-page rendering.")
    return sources


def load_cjk_font(size: int, font_sources: list[tuple[Path, int]] | None = None):
    sources = font_sources or get_available_cjk_font_sources()
    for path, index in sources:
        try:
            return ImageFont.truetype(str(path), size=size, index=index)
        except OSError:
            continue
    raise RuntimeError("Failed to load a usable CJK font source for thesis rendering.")


def fit_cjk_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    min_size: int = 14,
    font_sources: list[tuple[Path, int]] | None = None,
):
    for size in range(start_size, min_size - 1, -1):
        font = load_cjk_font(size, font_sources=font_sources)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return load_cjk_font(min_size, font_sources=font_sources)


def make_box(left: float, top: float, right: float, bottom: float) -> dict[str, float]:
    return {
        "left": float(left),
        "top": float(top),
        "right": float(right),
        "bottom": float(bottom),
    }


def merge_boxes(boxes: list[dict[str, float]]) -> dict[str, float]:
    return make_box(
        min(box["left"] for box in boxes),
        min(box["top"] for box in boxes),
        max(box["right"] for box in boxes),
        max(box["bottom"] for box in boxes),
    )


def scale_box(box: dict[str, float], scale_x: float, scale_y: float) -> dict[str, float]:
    return make_box(
        box["left"] * scale_x,
        box["top"] * scale_y,
        box["right"] * scale_x,
        box["bottom"] * scale_y,
    )


def normalize_pdf_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def ensure_template_pdf_xml() -> Path:
    TMP_TEMPLATE_PDF_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(TMP_TEMPLATE_PDF_DIR.glob("template_layout*.xml"))
    if existing:
        return existing[0]

    run_checked([
        "pdftohtml",
        "-xml",
        "-f",
        "1",
        "-l",
        "2",
        "-nomerge",
        "-noroundcoord",
        str(TEMPLATE_PDF_PATH),
        str(TEMPLATE_XML_PREFIX),
    ])
    generated = sorted(TMP_TEMPLATE_PDF_DIR.glob("template_layout*.xml"))
    if not generated:
        raise RuntimeError("Failed to extract template XML layout for thesis front pages.")
    return generated[0]


def ensure_template_pdf_pages() -> tuple[Path, Path]:
    TMP_TEMPLATE_PDF_DIR.mkdir(parents=True, exist_ok=True)
    page_1 = TMP_TEMPLATE_PDF_DIR / "template_page-01.png"
    page_2 = TMP_TEMPLATE_PDF_DIR / "template_page-02.png"
    if page_1.exists() and page_2.exists():
        return page_1, page_2

    prefix = TMP_TEMPLATE_PDF_DIR / "template_page"
    run_checked([
        "pdftoppm",
        "-f",
        "1",
        "-l",
        "2",
        "-png",
        str(TEMPLATE_PDF_PATH),
        str(prefix),
    ])
    if not page_1.exists() or not page_2.exists():
        raise RuntimeError("Failed to render official template PDF pages.")
    return page_1, page_2


def detect_cover_lines_in_image(image: Image.Image) -> dict[str, dict[str, int]]:
    grayscale = image.convert("L")
    width, height = grayscale.size
    search_left = int(width * 0.34)
    search_right = int(width * 0.80)
    search_top = int(height * 0.43)
    search_bottom = int(height * 0.75)
    min_length = int(width * 0.20)
    candidates: list[tuple[int, int, int]] = []

    for y in range(search_top, search_bottom):
        best_start = None
        best_end = None
        run_start = None
        for x in range(search_left, search_right + 1):
            is_dark = grayscale.getpixel((x, y)) < 120
            if is_dark:
                if run_start is None:
                    run_start = x
            elif run_start is not None:
                if best_start is None or x - run_start > best_end - best_start:
                    best_start, best_end = run_start, x - 1
                run_start = None
        if run_start is not None:
            if best_start is None or search_right - run_start > best_end - best_start:
                best_start, best_end = run_start, search_right
        if best_start is not None and best_end is not None and best_end - best_start >= min_length:
            candidates.append((y, best_start, best_end))

    groups: list[list[tuple[int, int, int]]] = []
    for row in candidates:
        if not groups or row[0] - groups[-1][-1][0] > 3:
            groups.append([row])
        else:
            groups[-1].append(row)

    normalized_groups = []
    for group in groups:
        line = {
            "y_line": int(round(sum(item[0] for item in group) / len(group))),
            "x_start": int(round(sum(item[1] for item in group) / len(group))),
            "x_end": int(round(sum(item[2] for item in group) / len(group))),
        }
        if line["x_end"] - line["x_start"] >= min_length:
            normalized_groups.append(line)

    if len(normalized_groups) < len(COVER_FIELD_ORDER):
        raise RuntimeError("Failed to detect all cover underline anchors from the official template.")
    if len(normalized_groups) > len(COVER_FIELD_ORDER):
        normalized_groups = sorted(
            normalized_groups,
            key=lambda line: line["x_end"] - line["x_start"],
            reverse=True,
        )[:len(COVER_FIELD_ORDER)]
        normalized_groups.sort(key=lambda line: line["y_line"])

    return {
        key: line
        for key, line in zip(COVER_FIELD_ORDER, normalized_groups[: len(COVER_FIELD_ORDER)])
    }


def detect_cover_lines(template_page: Path) -> dict[str, dict[str, int]]:
    try:
        with Image.open(template_page) as image:
            return detect_cover_lines_in_image(image)
    except Exception:
        return deepcopy(COVER_FALLBACK_LINES)


def extract_template_text_boxes(
    template_xml_path: Path,
    template_page: Path,
    page_number: int,
    labels: list[str],
) -> dict[str, dict[str, float]]:
    tree = ET.parse(template_xml_path)
    root = tree.getroot()
    page = next(
        (node for node in root.findall("page") if node.get("number") == str(page_number)),
        None,
    )
    if page is None:
        raise RuntimeError(f"Template XML page {page_number} not found.")

    with Image.open(template_page) as page_image:
        width, height = page_image.size
    scale_x = width / float(page.get("width"))
    scale_y = height / float(page.get("height"))

    nodes = []
    for element in page.findall("text"):
        raw_text = "".join(element.itertext())
        normalized = normalize_pdf_text(raw_text)
        if not normalized:
            continue
        left = float(element.get("left"))
        top = float(element.get("top"))
        box = make_box(
            left * scale_x,
            top * scale_y,
            (left + float(element.get("width"))) * scale_x,
            (top + float(element.get("height"))) * scale_y,
        )
        nodes.append({
            "text": raw_text,
            "normalized": normalized,
            "left_raw": left,
            "top_raw": top,
            "box": box,
        })

    lines: list[list[dict[str, object]]] = []
    for node in sorted(nodes, key=lambda item: (item["top_raw"], item["left_raw"])):
        if not lines or abs(node["top_raw"] - lines[-1][0]["top_raw"]) > 4:
            lines.append([node])
        else:
            lines[-1].append(node)

    boxes: dict[str, dict[str, float]] = {}
    for label in labels:
        normalized_label = normalize_pdf_text(label)
        for line in lines:
            sorted_line = sorted(line, key=lambda item: item["left_raw"])
            for start in range(len(sorted_line)):
                matched_nodes = []
                candidate = ""
                for end in range(start, len(sorted_line)):
                    piece = sorted_line[end]["normalized"]
                    next_candidate = candidate + piece
                    if not normalized_label.startswith(next_candidate):
                        break
                    candidate = next_candidate
                    matched_nodes.append(sorted_line[end]["box"])
                    if candidate == normalized_label:
                        boxes[label] = merge_boxes(matched_nodes)
                        break
                if label in boxes:
                    break
            if label in boxes:
                break

    for label in labels:
        if label not in boxes and label in DECLARATION_FALLBACK_LABEL_BOXES:
            boxes[label] = deepcopy(DECLARATION_FALLBACK_LABEL_BOXES[label])
    missing = [label for label in labels if label not in boxes]
    if missing:
        raise RuntimeError(f"Failed to extract template label boxes: {', '.join(missing)}")
    return boxes


def draw_text_above_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    line_box: dict[str, int],
    spec: dict[str, object],
    font_sources: list[tuple[Path, int]],
) -> dict[str, float]:
    line_width = line_box["x_end"] - line_box["x_start"]
    padding = int(spec["padding_x"])
    available_width = min(int(spec["max_width"]), line_width - 2 * padding)
    font = fit_cjk_font(
        draw,
        text,
        available_width,
        int(spec["font_size"]),
        font_sources=font_sources,
    )
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    if spec["align"] == "center":
        desired_left = line_box["x_start"] + (line_width - text_width) / 2
    else:
        desired_left = line_box["x_start"] + padding
    desired_bottom = line_box["y_line"] - int(spec["gap_above_line"])
    draw_x = desired_left - bbox[0]
    draw_y = desired_bottom - bbox[3]
    draw.text((draw_x, draw_y), text, font=font, fill=(18, 18, 18, 255))
    return make_box(
        draw_x + bbox[0],
        draw_y + bbox[1],
        draw_x + bbox[2],
        draw_y + bbox[3],
    )


def draw_text_after_label(
    draw: ImageDraw.ImageDraw,
    text: str,
    label_box: dict[str, float],
    spec: dict[str, object],
    font_sources: list[tuple[Path, int]],
) -> dict[str, float]:
    font = fit_cjk_font(
        draw,
        text,
        int(spec["max_width"]),
        int(spec["font_size"]),
        font_sources=font_sources,
    )
    bbox = draw.textbbox((0, 0), text, font=font)
    desired_left = label_box["right"] + int(spec["padding_x"])
    label_center_y = (label_box["top"] + label_box["bottom"]) / 2
    desired_center_y = label_center_y
    draw_x = desired_left - bbox[0]
    draw_y = desired_center_y - (bbox[1] + bbox[3]) / 2
    draw.text((draw_x, draw_y), text, font=font, fill=(18, 18, 18, 255))
    return make_box(
        draw_x + bbox[0],
        draw_y + bbox[1],
        draw_x + bbox[2],
        draw_y + bbox[3],
    )


def render_cover_page(template_page: Path, output_path: Path) -> dict[str, object]:
    line_boxes = detect_cover_lines(template_page)
    font_sources = get_available_cjk_font_sources()
    image = Image.open(template_page).convert("RGBA")
    draw = ImageDraw.Draw(image)
    placements = {}
    for key in COVER_FIELD_ORDER:
        placements[key] = draw_text_above_line(
            draw,
            str(COVER_FIELD_SPECS[key]["text"]),
            line_boxes[key],
            COVER_FIELD_SPECS[key],
            font_sources,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return {
        "placements": placements,
        "anchors": line_boxes,
        "image_size": image.size,
    }


def render_declaration_page(template_page: Path, output_path: Path) -> dict[str, object]:
    font_sources = get_available_cjk_font_sources()
    template_xml = ensure_template_pdf_xml()
    label_boxes = extract_template_text_boxes(
        template_xml,
        template_page,
        2,
        [spec["anchor_label"] for spec in DECLARATION_FIELD_SPECS.values()],
    )
    image = Image.open(template_page).convert("RGBA")
    draw = ImageDraw.Draw(image)
    placements = {}
    for key, spec in DECLARATION_FIELD_SPECS.items():
        placements[key] = draw_text_after_label(
            draw,
            str(spec["text"]),
            label_boxes[str(spec["anchor_label"])],
            spec,
            font_sources,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return {
        "placements": placements,
        "label_boxes": label_boxes,
        "image_size": image.size,
    }


def prepare_declaration_page_asset(template_page: Path, output_path: Path) -> tuple[Path, dict[str, object] | None]:
    signed_page = find_first_existing_path(*SIGNED_DECLARATION_PAGE_CANDIDATES)
    if signed_page is None:
        return output_path, render_declaration_page(template_page, output_path)

    if signed_page.suffix.lower() == ".pdf":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        override_prefix = output_path.with_name(f"{output_path.stem}_signed_override")
        run_checked([
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "1",
            "-singlefile",
            "-png",
            str(signed_page),
            str(override_prefix),
        ])
        return override_prefix.with_suffix(".png"), None

    return signed_page, None


def build_front_pdf(front_cover_png: Path, declaration_png: Path, output_pdf: Path) -> None:
    first = Image.open(front_cover_png).convert("RGB")
    second = Image.open(declaration_png).convert("RGB")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    first.save(output_pdf, "PDF", save_all=True, append_images=[second], resolution=150.0)


def export_docx_pdf(doc_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_checked([
        "soffice",
        "-env:UserInstallation=file:///tmp/lo_profile_shu_thesis",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(doc_path),
    ])
    pdf_path = output_dir / f"{doc_path.stem}.pdf"
    if not pdf_path.exists():
        raise RuntimeError(f"Failed to export PDF from DOCX: {pdf_path}")
    return pdf_path


def merge_submission_pdf(front_pdf: Path, body_pdf: Path, output_pdf: Path) -> None:
    front_reader = PdfReader(str(front_pdf))
    body_reader = PdfReader(str(body_pdf))
    writer = PdfWriter()

    for page in front_reader.pages:
        writer.add_page(page)
    for page in body_reader.pages[BODY_PDF_ABSTRACT_PAGE_INDEX:]:
        writer.add_page(page)

    with output_pdf.open("wb") as fp:
        writer.write(fp)


def render_pdf_preview(input_pdf: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "page"
    run_checked([
        "pdftoppm",
        "-f",
        "1",
        "-l",
        "40",
        "-png",
        str(input_pdf),
        str(prefix),
    ])


def get_rendered_preview_page(output_dir: Path, page_number: int) -> Path:
    candidates = [
        output_dir / f"page-{page_number:02d}.png",
        output_dir / f"page-{page_number}.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = sorted(output_dir.glob(f"page-*{page_number:02d}.png"))
    if matches:
        return matches[0]
    raise RuntimeError(f"Rendered preview page not found: {page_number}")


def validate_front_page_alignment(
    rendered_page: Path,
    placements: dict[str, dict[str, float]],
    source_size: tuple[int, int],
) -> None:
    with Image.open(rendered_page) as image:
        rendered_lines = detect_cover_lines_in_image(image)
        scale_x = image.size[0] / source_size[0]
        scale_y = image.size[1] / source_size[1]

    for key in COVER_FIELD_ORDER:
        placement = scale_box(placements[key], scale_x, scale_y)
        line_box = rendered_lines[key]
        gap = line_box["y_line"] - placement["bottom"]
        if placement["bottom"] >= line_box["y_line"]:
            raise RuntimeError(f"Cover field '{key}' overlaps the underline in the final PDF.")
        if gap < 1.5 or gap > 10:
            raise RuntimeError(
                f"Cover field '{key}' is not aligned above the underline: gap={gap:.2f}px."
            )


def validate_declaration_page_alignment(
    rendered_page: Path,
    placements: dict[str, dict[str, float]],
    label_boxes: dict[str, dict[str, float]],
    source_size: tuple[int, int],
) -> None:
    with Image.open(rendered_page) as image:
        scale_x = image.size[0] / source_size[0]
        scale_y = image.size[1] / source_size[1]

    for key, spec in DECLARATION_FIELD_SPECS.items():
        placement = scale_box(placements[key], scale_x, scale_y)
        label_box = scale_box(label_boxes[str(spec["anchor_label"])], scale_x, scale_y)
        center_delta = abs(
            ((placement["top"] + placement["bottom"]) / 2)
            - ((label_box["top"] + label_box["bottom"]) / 2)
        )
        if center_delta > 2:
            raise RuntimeError(
                f"Declaration field '{key}' is vertically misaligned: delta={center_delta:.2f}px."
            )
        if placement["left"] <= label_box["right"]:
            raise RuntimeError(f"Declaration field '{key}' overlaps its label region.")


def write_toc_entry(paragraph, style_name: str, title: str, page: str) -> None:
    clear_paragraph(paragraph)
    paragraph.style = style_name
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = ABSTRACT_LINE_SPACING
    run = paragraph.add_run(f"{title}\t{page}")
    set_run_text_font(run, "宋体", Pt(12), bold=False)


def normalize_chapter_headings(doc: Document) -> None:
    chapter_pattern = re.compile(r"^\d+\s+")
    for paragraph in doc.paragraphs:
        if paragraph.style.name != "Heading 1":
            continue
        text = paragraph.text.strip()
        if not text:
            paragraph.style = "Normal"
            continue
        if text in {"结 论", "参考文献", "致 谢"}:
            format_unnumbered_heading(paragraph)
            continue
        if chapter_pattern.match(text):
            clear_paragraph(paragraph)
            run = paragraph.add_run(chapter_pattern.sub("", text))
            run.font.name = "Times New Roman"
            set_east_asia_font(run, "黑体")


def rebuild_toc(doc: Document, toc_pages: dict[str, str] | None = None) -> None:
    title_para = None
    for paragraph in doc.paragraphs:
        if paragraph.text.strip() == "目  录":
            title_para = paragraph
            break
    if title_para is None:
        raise RuntimeError("Failed to locate TOC title paragraph.")

    toc_end = None
    search_started = False
    for paragraph in doc.paragraphs:
        if paragraph._element is title_para._element:
            search_started = True
            continue
        if search_started and "w:sectPr" in paragraph._element.xml:
            toc_end = paragraph
            break
    if toc_end is None:
        raise RuntimeError("Failed to locate TOC section end.")

    remove_section_break(title_para)
    current = title_para._element.getnext()
    toc_end_element = toc_end._element
    while current is not None and current is not toc_end_element:
        nxt = current.getnext()
        current.getparent().remove(current)
        current = nxt

    format_toc_title(title_para)
    resolved_pages = toc_pages or {title: "" for _, title in TOC_BLUEPRINT}
    for style_name, title in TOC_BLUEPRINT:
        paragraph = toc_end.insert_paragraph_before()
        write_toc_entry(paragraph, style_name, title, resolved_pages.get(title, ""))


def find_table_containing_text(doc: Document, needle: str):
    for table in doc.tables:
        text = "\n".join(cell.text for row in table.rows for cell in row.cells)
        if needle in text:
            return table
    return None


def update_body_content(doc: Document) -> None:
    replacements = {
        "本文依托的项目并不是单一的课程设计程序":
            "本文依托的项目并不是单一的课程设计程序，而是一个较为完整的量化研究平台。当前公开仓库对外聚焦策略回测、实时行情与行业热度三个主工作区，同时仍保留部分相关研究能力代码与接口。在这些能力中，行业热度页面与毕业设计任务书的目标最为一致，因此本文不再泛化讨论平台全部模块，而是从现有工程实现中抽取行业热度子系统作为核心研究对象，在真实代码、真实接口与真实历史快照的基础上完成毕业论文撰写。",
        "随着金融市场数据规模持续增长":
            "A 股市场的行业轮动很快，真正做研究时，光靠人工盯盘、翻资讯和手工比对往往跟不上节奏。毕业设计任务书希望解决的正是这一类问题，所以本文没有另外搭一套脱离项目背景的新系统，而是把现有量化研究平台里已经在运行的行业热度子系统拿出来，按真实代码、真实接口和真实历史快照重新梳理一遍，把数据接入、行业评分、个股筛选和可视化展示这几条主链路讲清楚。",
        "A 股行情更新很快":
            "A 股市场的行业轮动很快，真正做研究时，光靠人工盯盘、翻资讯和手工比对往往跟不上节奏。毕业设计任务书希望解决的正是这一类问题，所以本文没有另外搭一套脱离项目背景的新系统，而是把现有量化研究平台里已经在运行的行业热度子系统拿出来，按真实代码、真实接口和真实历史快照重新梳理一遍，把数据接入、行业评分、个股筛选和可视化展示这几条主链路讲清楚。",
        "系统采用前后端分离架构。前端基于 React 与 Ant Design 构建行业热力图":
            "从工程实现看，这个子系统没有追求大而全，而是围绕日常行业研究最常用的界面来组织。前端主要保留热力图、排行榜、趋势面板和龙头股详情这些入口；后端用 FastAPI 把热门行业、成分股、热力图、趋势和龙头股相关接口串起来；评分和整理逻辑则放在 Python 分析层中完成。数据侧也不是单一来源，而是先由同花顺优先（Tonghuashun-first，以下简称 THS-first）适配器拿行业目录和摘要，再按字段缺口补接 AKShare、新浪财经和腾讯接口。",
        "具体实现上，前端保留了行业研究最常用的几个界面":
            "从工程实现看，这个子系统没有追求大而全，而是围绕日常行业研究最常用的界面来组织。前端主要保留热力图、排行榜、趋势面板和龙头股详情这些入口；后端用 FastAPI 把热门行业、成分股、热力图、趋势和龙头股相关接口串起来；评分和整理逻辑则放在 Python 分析层中完成。数据侧也不是单一来源，而是先由同花顺优先（Tonghuashun-first，以下简称 THS-first）适配器拿行业目录和摘要，再按字段缺口补接 AKShare、新浪财经和腾讯接口。",
        "系统采用前后端分离架构。前端围绕行业热力图、行业排行榜、行业趋势与龙头股详情构建研究界面":
            "从工程实现看，这个子系统没有追求大而全，而是围绕日常行业研究最常用的界面来组织。前端主要保留热力图、排行榜、趋势面板和龙头股详情这些入口；后端用 FastAPI 把热门行业、成分股、热力图、趋势和龙头股相关接口串起来；评分和整理逻辑则放在 Python 分析层中完成。数据侧也不是单一来源，而是先由同花顺优先（Tonghuashun-first，以下简称 THS-first）适配器拿行业目录和摘要，再按字段缺口补接 AKShare、新浪财经和腾讯接口。",
        "在模型设计方面，本文依据项目中已经实现的 IndustryAnalyzer 与 LeaderStockScorer 两个核心模块":
            "模型部分没有额外引入难以解释的黑箱方法，而是直接沿用项目里已经落地的两个分析类。IndustryAnalyzer 负责判断行业热度，看的主要是价格变化、资金承接、交易活跃度和波动率代理；LeaderStockScorer 负责在行业内部比较个股，把规模、估值、盈利、成长、动量和活跃度六个维度合成综合分，并保留快照场景下的快速评分链路。这样的写法虽然不炫技，但更容易和现有工程实现一一对应。",
        "模型部分没有采用难以解释的黑箱方法":
            "模型部分没有额外引入难以解释的黑箱方法，而是直接沿用项目里已经落地的两个分析类。IndustryAnalyzer 负责判断行业热度，看的主要是价格变化、资金承接、交易活跃度和波动率代理；LeaderStockScorer 负责在行业内部比较个股，把规模、估值、盈利、成长、动量和活跃度六个维度合成综合分，并保留快照场景下的快速评分链路。这样的写法虽然不炫技，但更容易和现有工程实现一一对应。",
        "结合项目保存的行业热力图历史快照数据":
            "论文写作时，本文直接使用项目保留下来的热力图历史快照和本地运行结果做样例验证。按五日窗口观察，电子化学品、通信设备、半导体、消费电子和能源金属等阶段性强势行业能够被系统稳定排到前列，行业内部也能继续给出代表性龙头候选。换句话说，这套原型系统至少已经能够支撑“先识别热点，再往行业内部找代表股票”这一最核心的研究流程。",
        "结合项目保存的行业热力图历史快照和系统运行结果进行验证":
            "论文写作时，本文直接使用项目保留下来的热力图历史快照和本地运行结果做样例验证。按五日窗口观察，电子化学品、通信设备、半导体、消费电子和能源金属等阶段性强势行业能够被系统稳定排到前列，行业内部也能继续给出代表性龙头候选。换句话说，这套原型系统至少已经能够支撑“先识别热点，再往行业内部找代表股票”这一最核心的研究流程。",
        "关键词：金融大数据；行业热度识别；龙头股遴选；多源数据；量化研究平台":
            "关键词：金融大数据；热门行业识别；龙头股遴选；多源数据；量化研究平台",
        "With the rapid growth of financial market data":
            "Against the backdrop of rapidly expanding financial market datasets, approaches that rely primarily on manual experience are no longer sufficient for identifying hot industries and representative leader stocks in a timely and interpretable manner. Focusing on the graduation-project topic of hot-industry identification and leader-stock selection, this thesis takes the industry-heat subsystem of an existing quantitative research platform as its research object and develops an A-share-oriented prototype for financial big-data analysis that integrates data acquisition, industry scoring, stock screening, and visual presentation.",
        "The system adopts a front end and back end separated architecture. The front end is implemented with React and Ant Design":
            "The system follows a front-end/back-end separated architecture. The front end, implemented with React and Ant Design, provides core research views including industry heatmaps, ranking boards, trend panels, and leader-stock detail pages. The back end is built on FastAPI, while the analytical layer is implemented in Python. At the data layer, a Tonghuashun-first (THS-first) adapter organizes industry catalog data, summary snapshots, and money-flow information, with AKShare, Sina Finance, and Tencent valuation endpoints serving as multi-source complements and fallback sources.",
        "According to the actual implementation of the project, the thesis summarizes two core models.":
            "Based on the actual implementation of the project, the thesis summarizes two core models. The industry-heat model evaluates momentum, money-flow strength, trading activity, and a volatility proxy, while the leader-stock model evaluates market capitalization, valuation, profitability, growth, price momentum, and trading activity. A lightweight fast-scoring path is additionally retained for scenarios in which complete financial data are temporarily unavailable.",
        "Historical heatmap snapshots stored in the project show that the system can iden":
            "Historical heatmap snapshots stored in the project show that the system can identify stage-specific strong industries and further screen representative leader-stock candidates within those industries. The results indicate that the proposed prototype maintains reasonable engineering usability, interpretability, and visual readability, and can provide a practical reference for continuous industry tracking.",
        "Keywords: financial big data; industry heat; leader stock selection; quantitative platform":
            "Keywords: financial big data; hot-industry identification; leading stock selection; multi-source data; quantitative research platform",
        "在热门行业识别与龙头股遴选过程中，不同数据字段的量纲差异很大。例如，行业资金流通常以亿元计量，涨跌幅以百分比计量，市值则以十亿或万亿规模计量。如果直接对原始数据进行加权，容易导致尺度较大的变量主导结果。因此，系统在分析阶段首先对指标做数值清洗和标准化处理。":
            "在热门行业识别与龙头股遴选过程中，不同数据字段的量纲差异很大。例如，行业资金流通常以亿元计量，涨跌幅以百分比计量，市值则以十亿或万亿规模计量。如果直接对原始数据进行加权，容易导致尺度较大的变量主导结果。因此，系统在分析阶段首先对指标做数值清洗和标准化处理。[9-10]",
        "行业评分部分主要使用标准化方法将动量、资金流、活跃度和波动率等因子转换到统一尺度后再进行加权；个股评分部分则结合线性归一化、对数标准化和区间裁剪等方式处理市值、成交额、ROE、营收同比和利润同比等指标。对于缺失数据，系统采用中性值或回退值，保证评分流程不因少量字段缺失而中断。":
            "行业评分部分主要使用标准化方法将动量、资金流、活跃度和波动率等因子转换到统一尺度后再进行加权；个股评分部分则结合线性归一化、对数标准化和区间裁剪等方式处理市值、成交额、净资产收益率（Return on Equity, ROE）、营业收入同比和利润同比等指标。对于缺失数据，系统采用中性值或回退值，保证评分流程不因少量字段缺失而中断。[9-10]",
        "根据项目中的实际实现，行业热度模型以价格动量、资金流强度、交易活跃度和行业波动率四个因子为核心，但在工程实现上并非简单依赖抽象的四因子加总。动量因子主要来自 change_pct 或 weighted_change，用于刻画行业近期相对强弱；资金因子主要来自 flow_strength，用于衡量行业吸引资金的能力；活跃度因子优先采用 avg_volume，缺失时退化为 turnover_rate；波动率因子则优先使用行业指数历史收益率计算的真实波动率，不足时再回退到振幅、换手率或涨跌幅代理值。":
            "根据项目中的实际实现，行业热度判断主要围绕四类信号展开：价格动量、资金流强度、交易活跃度和行业波动率。不过代码里并不是把“四因子模型”当成一句口号来写，而是把每个字段都落到了可追踪的数据口径上。动量主要来自 change_pct 或 weighted_change，资金因子对应 flow_strength，活跃度优先看 avg_volume，拿不到时再退化到 turnover_rate。波动率这一项最能体现工程取舍：热力图和排行榜的冷启动阶段先复用振幅、换手率或涨跌幅代理值，等用户缩小到指定行业集合或进入详情分析后，再尽量补充行业指数历史收益率波动率。即使历史序列暂时拿不到，系统也会沿用代理值保持输出连续性。这种做法与行业轮动研究里强调多维信号综合判断的思路是一致的。[4][7-8]",
        "在实际运行中，并不是所有行业都能稳定获得完整的历史波动率数据。为提高系统鲁棒性，项目在行业分析引擎中设计了多级回退机制：优先使用真实行业指数历史收益率计算波动率；若历史数据不可用，则依次回退到振幅代理、换手率代理和涨跌幅代理。该设计保证了波动率因子在多数场景下都能被估算出来。":
            "在实际运行中，并不是所有行业都能稳定获得完整的历史波动率数据。为兼顾首屏响应速度与结果稳定性，项目在行业分析引擎中设计了分层波动率策略：页面冷启动时先用振幅代理、换手率代理或涨跌幅代理把热力图和排行榜跑起来；当用户缩小到指定行业集合，或者继续打开详情分析时，系统再补拉真实行业指数历史收益率去修正波动率。如果历史数据仍然拿不到，就继续沿用代理值。这样做的重点不是追求某一个字段绝对完美，而是让结果在大多数场景下都能持续输出，同时保持口径大体稳定。[9-10]",
        "此外，系统还使用 K-Means 聚类对行业进行辅助划分，并通过轮廓系数自动选择较优聚类数。需要说明的是，聚类分析在本系统中主要承担辅助解释角色，用于观察若干行业是否共同形成热点簇，而不是替代行业热度综合评分本身。":
            "此外，系统还使用 K-Means 聚类方法对行业进行辅助划分，并通过轮廓系数自动选择较优聚类数。需要说明的是，聚类分析在本系统中主要承担辅助解释角色，用于观察若干行业是否共同形成热点簇，而不是替代行业热度综合评分本身。[10]",
        "龙头股评分模型的目标是在已识别出的热门行业或指定行业内部，从多只成分股中筛选更具代表性的股票。结合项目中的实际实现，系统从六个维度构建综合评分模型：市值规模、估值水平、盈利能力、成长性、价格动量和交易活跃度。":
            "龙头股评分模型的目标，是在已经识别出的热门行业或指定行业内部，从多只成分股里找出更能代表行业状态的股票。结合项目中的实际实现，系统没有只盯短期涨幅，而是同时看市值规模、估值水平、盈利能力、成长性、价格动量和交易活跃度六个维度。这样的口径与既有龙头企业识别和财务可视化研究中常见的分析框架基本一致。[3][5-6]",
        "其中，市值规模通过对数标准化反映企业体量；估值水平以 PE 处于合理区间得分更高为原则；盈利能力通过 ROE 体现；成长性通过营收同比和利润同比共同体现；价格动量反映短期市场强弱；交易活跃度通过成交额或换手率衡量。设六个维度得分分别为 s1 至 s6，则龙头股综合得分可以表示为：":
            "其中，市值规模通过对数标准化反映企业体量；估值水平以市盈率（Price-to-Earnings Ratio, PE）处于合理区间得分更高为原则；盈利能力通过净资产收益率（Return on Equity, ROE）体现；成长性通过营业收入同比和利润同比共同体现；价格动量反映短期市场强弱；交易活跃度通过成交额或换手率衡量。设六个维度得分分别为 s1 至 s6，则龙头股综合得分可以表示为：[3][5-6]",
        "后端行业接口基于 FastAPI 构建，已经形成较完整的功能集合，包括热门行业列表、行业成分股、热力图、热力图历史、行业趋势、龙头股列表、龙头股详情以及偏好配置等核心接口。聚类与轮动接口在系统中主要承担辅助分析职责，偏好接口还支持按 profile 读写与导入导出，便于前端在不同研究配置之间切换。":
            "后端行业接口基于 FastAPI 构建，已经形成较完整的功能集合，包括热门行业列表、行业成分股、热力图、热力图历史、行业趋势、龙头股列表、龙头股详情以及偏好配置等核心接口。聚类与轮动接口在系统中主要承担辅助分析职责，偏好接口还支持按 profile 读写与导入导出，便于前端在不同研究配置之间切换。该接口组织方式与前文围绕多源金融数据处理和 Python 分析工具链构建研究系统的技术基础相衔接。[1-2][9-10]",
        "技术路线方面，系统采用前后端分离架构。前端使用 React 实现可视化交互":
            "技术路线并不是先写一套抽象模型再去找实现载体，而是从现有行业子系统的真实链路反推出来。前端用 React 承载热力图、榜单和详情弹窗，后端以 FastAPI 暴露行业分析接口，分析侧通过 pandas、NumPy 与 scikit-learn 完成字段清洗、标准化、评分和辅助聚类，数据侧则由 THS-first 适配器先接同花顺，再用 AKShare、新浪和腾讯补齐缺失字段。围绕这条实际链路，本文再展开数据获取、预处理、指标计算、结果展示和样例验证。",
        "在投资研究实践中，市值较大的企业更容易体现行业代表性":
            "落到行业内个股比较时，系统并没有把“龙头股”简单理解成短期涨幅最大的股票，而是把规模、盈利、成长、估值和市场交易信号放在一起看。原因也比较直接：市值更大的公司通常更能代表行业，净资产收益率和营收、利润增速能够反映经营质量，而成交额、换手率和近期涨跌幅则补足市场确认信息。把这些维度合在一起，得到的筛选结果通常比只看某一个指标更稳定。",
        "多源数据采集是本系统实现的基础。结合项目代码，系统通过数据提供器工厂统一管理不同来源的数据接口。":
            "多源数据采集是整个行业子系统能跑起来的前提。结合项目代码来看，这部分并不是把几个接口简单拼在一起，而是按 THS-first 的思路来组织。对于 A 股行业分析任务，同花顺相关接口优先提供行业目录、行业摘要、资金流与领涨股等主数据；AKShare 负责补齐行业元数据、成分股、估值与财务信息；新浪财经和腾讯接口则更多承担回退和字段补缺职责。这样处理的目的很直接，就是尽量减少单一数据源波动对整条分析链路的影响。",
        "根据项目中的实际实现，行业热度模型以价格动量、资金流强度、交易活跃度和行业波动率四个因子为核心。":
            "根据项目中的实际实现，行业热度判断主要围绕四类信号展开：价格动量、资金流强度、交易活跃度和行业波动率。实际代码并没有停留在抽象的“四因子加总”上，而是把每个信号都落到了具体字段和回退口径上。动量主要来自 change_pct 或 weighted_change，资金因子对应 flow_strength，活跃度优先看 avg_volume，拿不到时再退化到 turnover_rate。波动率则优先尝试行业指数历史收益率，拿不到时退回振幅、换手率或涨跌幅代理值。这种写法更符合行业轮动研究里强调多维信号综合判断的思路。[4][7-8]",
        "设行业动量、资金流、活跃度和波动率标准化后的结果分别为 Zm、Zf、Zv 和 Zr":
            "设行业动量、资金流、活跃度和波动率标准化后的结果分别为 Zm、Zf、Zv 和 Zr，则行业横截面原始评分可表示为：",
        "系统采用前后端分离架构，前端使用 React 与 Ant Design 构建行业热力图、行业排行榜、龙头股面板、行业趋势图和轮动对比图等交互页面，后端基于 FastAPI 提供数据接口与分析服务，核心分析逻辑由 Python 完成。数据层以 AKShare 获取 A 股行业分类、行业资金流、行业指数、个股估值和财务数据，同时引入新浪行业适配层作为回退机制，以提升系统运行中的稳定性和可用性。":
            "系统采用前后端分离架构，前端使用 React 与 Ant Design 构建行业热力图、行业排行榜、行业趋势图和龙头股详情等核心页面，后端基于 FastAPI 提供行业分析接口与偏好配置服务，核心分析逻辑由 Python 完成。行业数据层并非简单依赖 AKShare 单一数据源，而是由 THS-first 适配器主导：同花顺行业目录与行业摘要提供主要的行业热度底座，AKShare 负责行业元数据、成分股、财务与历史行情补齐，新浪财经和腾讯估值接口承担回退与字段补充，从而提升行业模块的连通性与抗故障能力。",
        "结合项目真实实现，本文的研究内容主要包括四个方面：第一，对现有量化研究平台中的行业热度子系统进行模块化梳理，明确其在整个平台中的功能定位；第二，围绕行业热度识别建立以动量、资金流、活跃度和波动率为核心的行业评分机制；第三，围绕行业内核心公司筛选建立以规模、估值、盈利、成长、动量和活跃度为核心的龙头股评分机制；第四，对系统的前后端实现、缓存机制、历史快照保存和运行结果进行分析。":
            "结合项目真实实现，本文的研究内容是沿着行业子系统已经跑通的链路来展开的。首先需要把 THS-first 数据适配器、FastAPI 路由层和前端行业页面之间的关系交代清楚；随后再说明 IndustryAnalyzer 如何完成行业热度横截面评分、热力图生成和趋势统计，以及 LeaderStockScorer 如何组织完整评分与快照快速评分两条龙头股筛选链路；最后再回到缓存、历史快照和偏好持久化这些工程细节，对系统的整体闭环做总结。",
        "本系统的关键技术包括以下几个方面。第一，后端采用 FastAPI 构建 REST 接口，具备较好的开发效率和接口组织能力。第二，前端采用 React 与 Ant Design 构建仪表盘式交互页面，便于完成热力图、表格、趋势图和弹窗详情的联动。第三，数据分析部分主要使用 pandas、NumPy 和 scikit-learn，实现数据处理、标准化与聚类。第四，数据持久化部分采用 JSON 与 SQLite 相结合的方式，以较低成本实现历史快照和用户偏好的保存。[9-10]":
            "本系统的关键技术包括以下几个方面。第一，后端采用 FastAPI 构建 REST 接口，行业模块通过参数化路由输出热门行业、热力图、成分股、龙头股、趋势和偏好配置等核心数据。第二，前端采用 React 与 Ant Design 实现仪表盘式页面，并结合 Recharts 等组件完成热力图、榜单、趋势和详情弹窗联动。第三，分析部分使用 pandas、NumPy 和 scikit-learn 完成字段清洗、横截面标准化、综合评分和辅助聚类分析。第四，行业子系统的持久化主要依赖 JSON 文件与浏览器 localStorage；其他研究模块即便采用结构化存储方式，也不属于本文行业分析主链路的核心内容。[9-10]",
        "系统总体上采用四层结构：表现层、服务层、分析层和数据层。表现层由 IndustryDashboard 及相关前端组件构成，负责用户交互和图表展示；服务层由 FastAPI 行业接口组成，负责请求接收、参数校验、缓存与响应封装；分析层由 IndustryAnalyzer 和 LeaderStockScorer 组成，负责评分计算和结果整理；数据层则通过数据提供器工厂统一管理 AKShare、新浪等数据源。":
            "系统总体上采用四层结构：表现层、服务层、分析层和数据层。表现层以前端行业主页面、排行榜组件以及行业详情和龙头股详情弹窗为核心，回放和偏好配置组件作为辅助交互存在；服务层由 FastAPI 行业接口组成，负责请求接收、参数校验、缓存与响应封装；分析层由 IndustryAnalyzer 行业分析器和 LeaderStockScorer 龙头股评分器组成，负责评分计算和结果整理；数据层则以 THS-first 适配器为核心，统一协调同花顺、AKShare、新浪和腾讯等数据源。",
        "系统数据流程可概括为：前端页面发起请求后，接口层根据请求类型调用行业分析器或龙头股评分器；分析器从主数据源获取行业与个股原始数据，必要时启用回退数据源；随后对数据进行清洗、字段统一和异常兜底；在标准化后计算行业或个股综合得分；最后将结果封装为统一响应结构返回前端，并在本地缓存和快照文件中记录必要信息。":
            "系统数据流程可概括为：前端页面通过 REST 请求调用行业接口；路由层优先检查端点缓存，随后根据请求类型调用 IndustryAnalyzer 或 LeaderStockScorer；分析层优先从 THS-first 适配器获取行业摘要、行业资金流和成分股快照，必要时再回退到 AKShare、新浪或腾讯接口，并在必要时返回过期缓存以维持结果连续性；在字段统一、异常处理和标准化之后，系统计算行业或个股综合得分，将结果封装为统一响应结构返回前端，并把必要的历史快照与偏好配置持久化到本地文件或浏览器缓存。",
        "项目并未采用复杂的大型数据库方案，而是根据实际需求选择轻量化存储方式。行业偏好配置和热力图历史快照保存为 JSON 文件，便于快速读写和迁移；研究工作台任务则使用 SQLite 持久化，以支持更稳定的结构化存储。":
            "项目并未为行业子系统引入独立数据库，而是根据真实实现选择轻量化存储方式。后端将热力图历史快照写入 data/industry/heatmap_history.json，将行业偏好按 profile 写入 data/industry_preferences/<profile>.json，并把龙头股财务缓存保存在 cache/financial_cache.json；前端还将热力图回放快照和当前选中状态保存到浏览器 localStorage 中。其他研究模块若采用结构化存储方式，也不影响本文行业子系统以文件缓存和浏览器状态为主的实现路径。",
        "系统的数据层以数据提供器工厂为统一入口，对不同数据源进行注册、管理与切换。对于行业分析任务，AKShare 是主数据源，承担行业分类、行业资金流、行业指数、成分股、估值与财务信息的获取工作；新浪行业适配层则负责在部分接口失败或字段不完整时进行补充。":
            "系统的数据层以 THS-first 适配器作为行业分析主入口。该适配器优先利用同花顺行业目录与行业一览表获取行业名称、涨跌幅、资金流与领涨股等主数据，再由 AKShare 补齐行业元数据、成分股、财务与历史 K 线，新浪财经接口承担行业列表、成分股与行情补充，腾讯财经接口则补单股估值核心字段。",
        "这种设计使系统形成了主数据源优先、备用数据源兜底的运行模式。对于面向真实市场数据的应用场景而言，这种容错机制比单纯依赖单一接口更具工程可用性。":
            "这种设计使系统形成了“同花顺主导、AKShare 增强、新浪与腾讯补充”的运行模式。对于面向真实市场数据的行业研究场景而言，多源适配比依赖单一接口更具工程可用性，也更能覆盖行业目录、资金流、成分股、估值和历史走势等不同类型的数据需求。",
        "行业分析模块的核心类为 IndustryAnalyzer。该模块负责完成行业资金流分析、行业动量计算、行业波动率估计、热门行业排序、热力图数据生成、行业趋势分析和聚类分析等任务。为提高效率，模块内部设置了 30 分钟缓存，避免在短时间内重复计算相同结果。":
            "行业分析模块的核心类为 IndustryAnalyzer。该模块负责行业资金流分析、行业动量计算、波动率估计、热门行业排序、热力图数据生成和行业趋势统计等任务，聚类与轮动分析则作为辅助能力存在。其实现中优先采用快速路径：直接复用行业资金流与横截面摘要结果，避免逐行业拉取全部成分股；在此基础上，再对 change_pct 或 weighted_change、flow_strength、avg_volume 或 turnover_rate 以及 industry_volatility 做标准化，并按默认权重计算原始分数。得到原始分数后，系统还会进一步压缩到约 20 至 95 的展示区间，以减少样本集中时 0 分和 100 分贴边的问题。为提高效率，分析器内部设置了 30 分钟缓存，避免在短时间内重复计算相同结果。",
        "在接口调用链路中，热门行业接口首先获取行业分类列表，再根据行业资金流和动量数据生成横截面数据表，随后计算综合得分并输出行业排行榜。热力图接口则在此基础上增加尺寸映射和颜色映射所需字段。趋势接口会进一步拉取行业指数序列并汇总行业内涨跌分布。":
            "在接口调用链路中，热门行业接口首先获取行业分类列表，再根据行业资金流、涨跌幅、换手率和波动代理生成横截面数据表，随后计算综合得分并输出行业排行榜。热力图接口则在此基础上增加尺寸映射、颜色映射和市值来源标签所需字段；当真实市值缺失时，系统还会退化到成交额、资金流或成分股数量代理。趋势接口会进一步拉取行业指数序列、汇总成分股涨跌分布，并返回覆盖率与降级说明字段。",
        "龙头股评分模块的核心类为 LeaderStockScorer。该模块负责对单只股票评分、在行业内部进行排名、生成龙头股列表以及输出评分拆解与原始数据。模块同时支持基于完整财务数据的完整评分和基于快照数据的轻量快速评分。":
            "龙头股评分模块的核心类为 LeaderStockScorer，即系统中的龙头股评分器。该模块负责对单只股票评分、在行业内部进行排名、生成龙头股列表以及输出评分拆解与原始数据。模块同时支持两条链路：其一是基于估值与财务数据的完整评分，其二是直接复用行业成分股快照的轻量快速评分。前者用于龙头股详情和深度研究，后者用于行业列表页中的快速筛选；在结果组织上，系统进一步把输出划分为 core（核心资产）与 hot（热点先锋）两个榜单，用于区分综合质量筛选和短期热点确认。",
        "在实现层面，模块通过缓存机制对财务数据进行暂存，避免在批量评分过程中重复请求；同时使用统一的原始数据结构将估值、财务和行情字段映射为评分输入，使不同评分路径共享同一套维度计算逻辑。":
            "在实现层面，模块会将财务数据以 24 小时缓存方式保存到 financial_cache.json，避免在批量评分过程中重复请求；同时使用统一的 raw_data 原始字段结构映射市值、市盈率（Price-to-Earnings Ratio, PE）、净资产收益率（Return on Equity, ROE）、营收同比、利润同比、涨跌幅和成交额等数据。完整评分链路按六维权重体系生成综合得分；快速评分链路则复用相同字段结构，在无法获取 ROE 与增长指标时采用中性分处理，以兼顾结果稳定性与页面响应效率。",
        "在实现层面，模块会将财务数据以 24 小时 TTL 缓存到 financial_cache.json，避免在批量评分过程中重复请求；同时使用统一的 raw_data 原始字段结构映射市值、PE、ROE、营收同比、利润同比、涨跌幅和成交额等数据，使完整评分与快速评分共享同一套六维评分逻辑。对于快速评分暂时无法获得的 ROE 与增长指标，系统采用中性分处理，以换取页面响应效率。":
            "在实现层面，模块会将财务数据以 24 小时缓存方式保存到 financial_cache.json，避免在批量评分过程中重复请求；同时使用统一的 raw_data 原始字段结构映射市值、市盈率（Price-to-Earnings Ratio, PE）、净资产收益率（Return on Equity, ROE）、营收同比、利润同比、涨跌幅和成交额等数据。完整评分链路按六维权重体系生成综合得分；快速评分链路则复用相同字段结构，在无法获取 ROE 与增长指标时采用中性分处理，以兼顾结果稳定性与页面响应效率。",
        "后端行业接口基于 FastAPI 构建，已经形成较完整的功能集合，包括热门行业列表接口、行业成分股接口、热力图接口、热力图历史接口、行业趋势接口、行业聚类接口、行业轮动接口、龙头股列表接口、龙头股详情接口以及偏好配置接口。":
            "后端行业接口基于 FastAPI 构建，已经形成较完整的功能集合，包括热门行业列表、行业成分股、热力图、热力图历史、行业趋势、龙头股列表、龙头股详情以及偏好配置等核心接口。聚类与轮动接口在系统中主要承担辅助分析职责，偏好接口还支持按 profile 读写与导入导出，便于前端在不同研究配置之间切换。该接口组织方式与前文围绕多源金融数据处理和 Python 分析工具链构建研究系统的技术基础相衔接。[1-2][9-10]",
        "为了提升接口稳定性，接口层额外设置了结果缓存，并在必要时使用过期缓存作为兜底返回。这一设计能够在外部数据源短暂波动时尽量保持页面可用。":
            "为了提升接口稳定性，路由层额外维护了 3 分钟端点缓存、30 分钟 parity 缓存以及完整版成分股异步构建机制，并在必要时返回过期缓存作为补充保障。热力图历史数据还设置了最多 48 条记录和 2MB 文件大小上限，从而在外部数据源短暂波动时尽量保持页面可用。",
        "行业热度页面由 IndustryDashboard 及其子组件实现。页面集成热力图、行业排行榜、行业趋势面板、龙头股面板、轮动分析图、预警面板、观察列表和评分雷达图弹窗等功能。用户可以通过点击行业名称进入详细面板，进一步查看该行业的趋势、成分股和龙头股。":
            "行业热度页面由 IndustryDashboard 及其子组件实现。页面以热力图、行业排行榜、行业趋势面板和龙头股面板为核心，同时保留回放与偏好配置等辅助功能。用户可以通过点击行业名称进入详细面板，进一步查看该行业的趋势、成分股和龙头股。",
        "与传统静态报表不同，本系统更强调交互式研究体验。热力图支持不同颜色维度和尺寸维度切换，排行榜支持多字段排序，详情页支持评分拆解和价格走势查看。这种设计更加符合行业分析工作的实际使用场景。":
            "与传统静态报表不同，本系统更强调交互式研究体验。热力图支持不同颜色维度、尺寸维度和市值来源筛选，排行榜支持回看窗口、波动过滤和排序口径切换，详情页支持评分拆解和价格走势查看；历史快照回放与偏好配置则作为研究辅助能力存在。这种设计更加符合行业分析工作的实际使用场景。",
        "项目中已经实现行业偏好持久化功能，支持保存观察行业、已保存视图和告警阈值。默认告警条件覆盖行业得分、涨跌幅、资金净流入和波动率等指标。该功能说明系统并非一次性分析工具，而是支持持续跟踪的研究原型。":
            "项目中已经实现行业偏好持久化功能，用于保存观察行业和研究配置等辅助信息。后端以 profile 维度将观察行业、研究视图和阈值配置写入 JSON 文件，前端则把热力图回放快照和当前选中状态保存在浏览器本地存储中。上述能力主要服务于持续跟踪与复盘分析，而不是改变行业热度识别与龙头股遴选这一核心研究流程。",
        "此外，系统还会记录热力图历史快照，为后续对比分析提供基础。研究工作台模块则为进一步沉淀分析结果和任务状态提供了可能。":
            "此外，系统后端还会持续记录热力图历史快照，为后续对比分析和前端热力图回放提供基础；这些快照不仅保存涨跌幅，还保留 total_score、资金流、换手率、市值来源和估值字段，便于后续复盘不同时间点的行业状态。",
        "本文的系统测试基于项目当前本地环境展开。系统采用 Python 作为后端分析语言，FastAPI 作为接口框架，React 作为前端框架，数据源主要为 AKShare，并结合项目中保存的历史快照进行结果验证。由于本课题属于毕业设计性质，测试重点放在功能闭环、数据连通性、结果可解释性和页面展示效果，而非面向生产环境的极限压测。":
            "本文的系统测试基于项目当前本地环境展开。系统采用 Python 作为后端分析语言，FastAPI 作为接口框架，React 作为前端框架，行业主数据经由 THS-first 适配器提供，并在需要时调用 AKShare、新浪与腾讯接口补齐字段，同时结合项目中保存的历史快照进行结果验证。除样例快照分析外，项目还保留了行业评分逻辑、适配器映射、偏好服务与前端行业页面的测试脚本，用于验证评分逻辑、回退逻辑和页面交互闭环。由于本课题属于毕业设计性质，测试重点放在功能闭环、数据连通性、结果可解释性和页面展示效果，而非面向生产环境的极限压测。",
        "为了增强论文结果分析的真实性，本文直接选取项目中已经保存的热力图历史快照作为样本。根据 2026 年 4 月 11 日 22:59:20 保存的五日窗口行业热力图数据，系统输出的前十个行业结果如表 6.2 所示。":
            "为了增强论文结果分析的真实性，本文直接选取项目中已经保存的热力图历史快照作为样本。选择 2026 年 4 月 11 日 22:59:20 保存的五日窗口快照，是因为该样本由系统自动记录、字段较为完整，并同时覆盖综合得分、涨跌幅、资金流和换手率等核心指标，便于展示系统在固定统计窗口下的横截面输出。表 6.2 展示了该样本时点按热力图默认顺序截取的前十个行业横截面字段，包括 total_score、5 日涨跌幅、资金流和换手率等信息。需要说明的是，这里给出的结果用于样例分析，并不构成完整回测结论。",
        "从表 6.2 可以看出，通信设备、半导体、电子化学品、消费电子、光学光电子和自动化设备等科技成长风格行业在该时间窗口内表现较强，说明系统能够较好识别当期市场热点方向。值得注意的是，综合得分并不完全等同于涨跌幅。例如，能源金属行业在五日涨跌幅较高的同时，还表现出正向资金流，因此综合得分达到较高水平；而部分行业虽然涨幅较大，但资金流为负，说明系统在排序时并非只依赖价格因子。":
            "从表 6.2 可以看出，电子化学品、通信设备、其他电子、元件、半导体和消费电子等电子科技链行业在该时间窗口内整体表现较强，说明样本时点的市场热点明显集中在成长风格板块。值得注意的是，表中多数科技行业虽然 5 日涨幅较高，但资金流仍为负；只有能源金属表现出较明显的正向资金流。这说明系统生成的 total_score 并不简单等同于单一资金因子或单一涨跌幅，而是横截面标准化后多个因子共同作用的结果。",
        "这一结果与系统的模型设计是一致的。行业热度评分同时考虑动量、资金流、活跃度和波动率，因此能够较好平衡短期趋势与资金确认。对于毕业设计来说，这种结果不仅能够支持论文中的实验分析，也便于在答辩中解释评分逻辑。":
            "这一结果与系统代码中的模型设计是一致的。热力图快照不仅保留 value 和 total_score，还同步记录资金流、换手率、行业波动率和市值来源等字段，因此能够较好平衡短期趋势、资金确认和数据来源差异。需要强调的是，total_score 反映的是样本时点的多因子横截面综合状态，并不直接构成对未来收益的预测。对于毕业设计来说，这种结果既支持论文中的样例分析，也便于在答辩中解释为什么某些行业会在资金流暂时偏弱时仍保持较高的综合得分。",
        "同时，系统仍存在一些不足。首先，行业评分和龙头股评分的权重主要依据工程经验设定，尚未通过更系统的学习或优化方法进行自适应调整。其次，系统当前对政策文本、新闻舆情和产业链关系等数据的融合仍不充分。再次，系统的“实时性”主要体现为准实时刷新与历史快照持续积累，并非高频交易系统意义上的毫秒级实时。最后，行业识别结果与未来收益之间的定量回测仍可进一步强化。":
            "同时，系统仍存在一些不足。首先，行业评分和龙头股评分的权重主要依据工程经验设定，尚未通过更系统的学习或优化方法进行自适应调整。其次，虽然 THS-first 适配器提高了整体可用性，但部分行业成分股在实际运行中仍可能触发降级路径，只能返回不完整明细或代理字段。再次，行业模块当前主要依赖 REST 拉取、缓存和历史快照实现准实时更新，而非基于持续流式订阅的实时分析系统。最后，行业识别结果与后续收益表现之间的定量回测，以及前瞻性验证工作，仍有进一步强化空间。",
        "本文以现有量化研究平台中的行业热度子系统为依托，围绕热门行业识别与龙头股遴选这一毕业设计主题，完成了系统分析、模型设计、工程实现和结果总结。通过梳理项目中的数据提供器、行业分析引擎、龙头股评分器、FastAPI 接口层和 React 仪表盘页面，本文构建了一条从多源数据获取到可视化展示的完整研究主线。":
            "本文以现有量化研究平台中的行业热度子系统为依托，围绕热门行业识别与龙头股遴选这一毕业设计主题，完成了系统分析、模型设计、工程实现和结果总结。通过梳理项目中的 THS-first 数据适配器、行业分析器、龙头股评分器、后端接口层以及前端行业仪表盘页面，本文构建了一条从多源数据获取到可视化展示的完整研究主线。",
        "在模型方面，本文总结并实现了以动量、资金流、活跃度和波动率为核心的行业热度评分模型，以及以规模、估值、盈利、成长、动量和活跃度为核心的龙头股综合评分模型；在实现方面，本文说明了多源数据回退、缓存机制、历史快照、偏好持久化和前端可视化协同工作方式；在结果方面，本文结合项目保存的历史热力图快照展示了系统对阶段性强势行业的识别能力。":
            "在模型方面，本文总结并实现了以动量、资金流、活跃度和波动率代理为核心的行业热度评分模型，以及以规模、估值、盈利、成长、动量和活跃度为核心的龙头股综合评分模型；在实现方面，本文说明了 THS-first 多源数据回退、分析层与路由层缓存、热力图历史快照和按 profile 偏好持久化的协同工作方式；在结果方面，本文结合项目保存的历史热力图快照展示了系统对阶段性强势行业的识别能力。",
        "未来工作可以从以下方向展开：第一，引入舆情、政策文本和产业链数据，增强行业识别的前瞻性；第二，采用熵权法、层次分析法或机器学习方法优化权重；第三，完善行业识别结果的回测验证；第四，强化与研究工作台的联动，形成更完整的研究闭环。总体而言，本文所完成的工作已经能够满足本科毕业设计对理论分析、系统实现与应用展示的综合要求。":
            "未来工作可以从以下方向展开：第一，引入舆情、政策文本和产业链数据，增强行业识别的前瞻性；第二，采用熵权法、层次分析法或机器学习方法优化权重；第三，完善行业识别结果与后续收益表现之间的回测验证；第四，继续提高成分股映射完整度并优化核心行业分析链路。总体而言，本文所完成的工作已经能够满足本科毕业设计对理论分析、系统实现与应用展示的综合要求。",
        "该公式中的权重与项目代码中的默认权重保持一致":
            "该公式中的权重与项目代码中的默认权重保持一致。需要强调的是，公式（4.2.1）对应的是横截面原始评分，并不直接等同于前端最终展示值。系统在完成加权之后，会进一步调用分数压缩函数，把结果统一映射到约 20 至 95 的展示区间，以减少样本集中时 0 分和 100 分贴边的问题。因此，排行榜和热力图中的 total_score 更适合用于相对比较，而不应被理解为行业的绝对评价值。",
        "此外，系统还使用 K-Means 聚类对行业进行辅助划分":
            "此外，系统还使用 K-Means 聚类对行业进行辅助划分，并通过轮廓系数自动选择较优聚类数。需要说明的是，聚类分析在本系统中主要承担辅助解释角色，用于观察若干行业是否共同形成热点簇，而不是替代行业热度综合评分本身。",
        "该模型突出盈利和成长的权重":
            "从工程实现看，公式（4.4.1）对应的是完整评分链路下的六维加权总分，其中 s1 至 s6 分别表示市值规模、估值水平、盈利能力、成长性、价格动量和交易活跃度的归一化得分。系统会在统一的 raw_data 结构上聚合估值、财务和行情字段，并按该权重体系生成总分。由于盈利能力和成长性权重相对较高，该模型更适合作为行业内核心标的筛选依据；与单纯按涨幅排序相比，它能够减少短期情绪对结果的扰动。同时需要说明的是，公式（4.4.1）主要对应 core 榜单的综合评分语义，而 hot 榜单则更强调短期涨幅与资金承接，并对暂时缺失的估值、盈利和成长字段采用中性处理。",
        "从工程实现看，完整评分链路会在统一的 raw_data 结构上聚合估值、财务和行情字段，并按六维权重体系生成总分。由于盈利能力和成长性权重相对较高，该模型更适合作为行业内核心标的筛选依据；与单纯按涨幅排序相比，它能够减少短期情绪对结果的扰动。":
            "从工程实现看，公式（4.4.1）对应的是完整评分链路下的六维加权总分，其中 s1 至 s6 分别表示市值规模、估值水平、盈利能力、成长性、价格动量和交易活跃度的归一化得分。完整评分链路会在统一的 raw_data 结构上聚合估值、财务和行情字段，并按该权重体系生成总分。因此，前端 core 榜单主要反映这一综合评分语义；与单纯按涨幅排序相比，它能够减少短期情绪对结果的扰动，更适合作为行业内核心标的筛选依据。",
        "在行业热度页面中，页面响应速度非常重要":
            "快速评分是从页面响应路径倒推出来的。行业热度页一次可能要同时给出多个候选股，如果每只股票都临时补抓完整财务数据，列表刷新会明显变慢。为此，系统在行业列表场景里优先复用成分股快照中已经带回的价格、成交额和资金承接等字段先生成一轮结果，只有用户进入详情页或继续深挖时再走完整评分链路。",
        "快速评分模式适合用于行业热度页中的候选股预筛选":
            "因此，快速评分和完整评分不是谁替代谁，而是分别服务于不同界面。前者解决的是“先把候选集合稳定列出来”，后者解决的是“把一只股票为什么排在前面解释清楚”。在结果组织上，前端继续把输出拆成 core（核心资产）和 hot（热点先锋）两类榜单：core 更接近行业内长期代表性筛选，hot 则专门保留短期涨幅和资金承接的冲击信息。这样用户先在行业页缩小范围，再到详情页看拆解，整个交互会更顺。",
        "从工程角度看，本系统具有以下几个明显特征":
            "从工程角度看，本系统具有以下几个明显特征。第一，系统以 THS-first 适配器为主入口，并通过 AKShare、新浪和腾讯形成多源补齐链路，保证了行业数据的连通性。第二，行业评分与龙头股评分同时引入快速评分链路与多级缓存机制，在保证响应速度的同时尽量维持评分口径一致。第三，系统输出不仅提供综合得分，还提供资金、波动率、市值来源和评分拆解等辅助信息，因此具有较好的结果解释性。",
        "在本次毕业设计与论文写作过程中":
            "在本次毕业设计与论文写作过程中，感谢指导教师沈文辉老师在选题论证、系统设计、论文结构与写作规范等方面给予的耐心指导与帮助。感谢项目开发和调试过程中提供建议与支持的同学和朋友，他们的交流与反馈为系统完善和论文修改提供了重要参考。",
        "同时，也感谢开源社区提供的 Python、FastAPI、React、AKShare 等工具和框架":
            "另外，论文能够完成，也离不开 Python、FastAPI、React、AKShare、scikit-learn 等开源工具在开发阶段提供的直接帮助。正是因为这些工具足够成熟，我才能把更多精力放在行业分析流程、页面交互和论文整理本身；也感谢学校和学院为毕业设计提供的学习环境与资源支持。"
    }

    for old_text, new_text in replacements.items():
        replace_first_paragraph_starting_with(doc, old_text, new_text)

    heatmap_snapshot = load_thesis_heatmap_snapshot(days=5)
    leader_case_payload = load_thesis_leader_case()
    heatmap_intro_text, heatmap_analysis_text, heatmap_conclusion_text = build_heatmap_result_section_text(heatmap_snapshot)
    leader_case_text = build_leader_case_analysis_text(leader_case_payload)
    replace_first_paragraph_starting_with(doc, "为了增强论文结果分析的真实性", heatmap_intro_text)
    replace_first_paragraph_starting_with(doc, "表 6.2 项目历史快照中的前十行业结果样例", "表 6.2 项目当前保留五日快照中的前十行业结果样例")
    replace_first_paragraph_starting_with(doc, "从表 6.2 可以看出", heatmap_analysis_text)
    replace_first_paragraph_starting_with(doc, "这一结果与系统代码中的模型设计是一致的。", heatmap_conclusion_text)

    replace_section_body(
        doc,
        "1.1 研究背景与意义",
        "1.2 国内外研究现状",
        [
            "在证券市场里，真正难做的往往不是盯住一两只股票，而是同时判断热点行业怎么切换、行业内部哪些公司更值得继续跟踪。一个行业持续走强，通常意味着资金、预期和景气度正在往同一方向聚集；而行业里的代表性公司又会因为规模、盈利和市场关注度，被更频繁地拿来比较。于是，如何从海量数据中尽快识别当期热点，并在行业内部继续缩小到更有代表性的股票，就成了一个既有研究价值也有实际用途的问题。",
            "过去这类工作很大程度依赖研究员人工切行情终端、翻行业报告和积累经验。行情节奏慢的时候，这种方式还勉强可行；但市场数据量和更新频率上来之后，单靠人工已经很难同时完成横截面比较、历史跟踪和多维交叉验证。也正因为如此，把大数据处理、量化评分和可视化页面真正接成一条可持续运行的研究链路，比单独写一套纸面分析方法更有工程意义。[1]",
            "本文依托的项目并不是单一的课程设计程序，而是一个较为完整的量化研究平台。当前公开仓库对外聚焦策略回测、实时行情与行业热度三个主工作区，同时仍保留部分相关研究能力代码与接口。在这些能力中，行业热度页面与毕业设计任务书的目标最为一致，因此本文不再泛化讨论平台全部模块，而是从现有工程实现中抽取行业热度子系统作为核心研究对象，在真实代码、真实接口与真实历史快照的基础上完成毕业论文撰写。",
            "对本文而言，这项工作的价值不只在于“做出一个页面”。一方面，系统把多源金融数据整理成可比较的行业研究结果，能够明显减少人工筛选成本；另一方面，评分过程保持了较强可解释性，便于把工程实现和理论依据放在一起说明。更现实的一点是，这个原型系统已经可以直接支撑毕业设计展示、运行截图获取和后续迭代，而不是停留在方案层面。",
        ],
    )

    replace_section_body(
        doc,
        "1.2 国内外研究现状",
        "1.3 研究内容与技术路线",
        [
            "1.2.1 金融大数据分析研究现状",
            "把现有文献和实际系统实现放在一起看，最先暴露出来的问题往往不是算法本身，而是数据怎么接、怎么对齐。行业快照、资金流、估值和财务表来自不同接口时，更新时间、单位和字段名经常对不上；同一个行业在不同平台里也可能对应不同叫法。孟小峰等对大数据管理技术的梳理说明，容量、速度、多样性和真实性这些约束在金融场景里一直存在。[1] 张晓琳等关于风险监测的研究也说明，多源金融数据融合已经成了很多金融分析工作的前提。[2]",
            "因此，本文借鉴这些研究时，更看重它们对数据组织方式的启发，而不是再额外设计一套抽象工具链。具体到本课题，后文采用 pandas、NumPy 和 scikit-learn，并不是因为这些工具本身更“先进”，而是因为它们已经足够支撑项目里真实存在的字段清洗、横截面比较和评分计算流程。[9-10]",
            "1.2.2 行业轮动与热点识别研究现状",
            "在行业轮动与热点识别方面，国内外研究普遍不主张只看单一指标。无论是从宏观周期、风格切换出发，还是从价格动量、资金流向和交易活跃度出发，最终都要回到多因子综合判断上来。[4][7-8] 这也解释了为什么本文没有把“热门行业”简单理解成短期涨幅排名，而是希望在横截面上同时观察价格、资金和活跃度这些信号。",
            "1.2.3 龙头股筛选与系统实现研究现状",
            "把文献里的龙头股识别方法和当前项目放在一起看，有一个很直接的共识：真正能长期代表行业状态的股票，通常不会只靠某一天的涨幅来判断。规模、盈利、成长和估值提供的是相对稳定的基本面线索，成交额、换手率和近期动量则更像市场有没有继续确认这一判断。[3][5-6]",
            "但不少既有研究停留在静态评价、因子验证或回测层面，对一套系统真正落地后要面对的缓存、回退、详情解释和页面展示写得比较少。本文之所以单列这一节，就是因为毕业设计依托的是已经在运行的行业子系统，后文需要把这些工程细节和评分逻辑一起说清楚，而不是只给出一套纸面指标体系。",
            "总体来看，现有研究已经为热门行业识别和龙头股筛选提供了较充分的理论基础，但一落到工程实现，就还会遇到两个明显空档：一是很少有人细讲多源适配、字段回退和页面展示这些真正影响可用性的细节；二是行业识别和龙头股遴选经常被拆开讨论，缺少统一的研究闭环。本文的重点并不是再堆一个复杂模型，而是在真实项目基础上，把多源数据获取、行业评分、龙头股筛选和前端展示这几部分真正接起来。",
        ],
    )

    replace_section_body(
        doc,
        "1.3 研究内容与技术路线",
        "1.4 论文结构安排",
        [
            "写作时，本文没有把研究内容拆成几块互不相干的模块，而是尽量按系统真实使用的顺序来梳理。更接近日常研究场景的路径，是先打开行业页，看热力图和排行榜怎样把横截面结果摆出来；接着沿着某个行业继续查看趋势、成分股和龙头股详情；最后再回头解释这些结果是怎样由适配器、缓存和评分器一步步算出来的。",
            "对应到实现链路，前端页面先请求热门行业、热力图和详情相关数据，路由层再把请求分发给 IndustryAnalyzer 和 LeaderStockScorer，分析层继续向 THS-first 主路径和补充数据源取回字段并整理结果。本文之所以按这条顺序展开，是因为这样最容易让论文里的截图、表格和项目代码彼此对上，也更方便答辩时解释页面里每一步是怎么来的。",
        ],
    )

    replace_section_body(
        doc,
        "1.4 论文结构安排",
        "相关技术与理论基础",
        [
            "全文按“提出问题、解释方法、落到系统、再看结果”的顺序展开。第一章说明选题背景、研究现状以及本文聚焦的行业子系统；第二章交代金融数据特征、多源采集和理论基础；第三章从需求、架构、数据流程和存储设计角度说明系统整体方案；第四章展开热门行业识别与龙头股遴选模型；第五章回到具体实现；第六章结合测试结果和固定快照样例分析系统输出，最后给出结论与后续改进方向。",
        ],
    )

    replace_section_body(
        doc,
        "2.1 金融大数据的特征",
        "2.2 多源数据采集与清洗",
        [
            "落到这个课题里，金融大数据最突出的麻烦并不只是“量大”这一个词，而是不同数据一起进来时口径很不整齐。股票日线、行业资金流、财务报表、估值指标和新闻文本的更新频率不同，结构也不同，可信程度还会跟着来源变化。比如行业快照可以按日更新，财务指标却按季度披露；同一个字段在不同接口里又可能出现名称不一致、单位不同或缺失值写法不同的情况。真要把这些数据送进同一条分析链路，先解决标准化和可用性问题，比直接套模型更重要。",
            "对于热门行业识别尤其如此。只盯涨跌幅，很容易把短期情绪波动当成热点；只看资金流，又可能忽略趋势已经转弱的行业。行业研究真正需要的是把价格、资金、活跃度乃至风险约束放在同一横截面里比较，这也是本文后续采用多维评分而不是单指标排序的原因。",
        ],
    )

    replace_section_body(
        doc,
        "2.2 多源数据采集与清洗",
        "2.3 热门行业识别的理论基础",
        [
            "多源采集在本项目里不是可有可无的补充，而是整条行业分析主链路的一部分。行业子系统按 THS-first 组织数据接口：同花顺负责提供行业目录、行业摘要、资金流和领涨股这类主数据，AKShare 补行业元数据、成分股、估值与财务字段，新浪和腾讯主要承担回退与补缺。这样做并不是为了“多接几个接口”，而是因为单一来源很难同时覆盖行业研究真正需要的全部字段。",
            "数据拿到之后，马上要处理的不是模型，而是口径统一。项目里会先统一行业名称、字段命名和数值类型，再根据字段特征做缺失值处理、异常值裁剪和重复剔除。例如行业名称需要映射到统一的 industry_name，涨跌幅和资金流要变成可运算的浮点数，个股快照里暂时缺失的财务字段则用中性值参与快速评分。只有经过这一步，不同来源的数据才能进入后面的行业评分和龙头股筛选链路。[9]",
        ],
    )

    replace_section_body(
        doc,
        "2.4 龙头股评价的理论基础",
        "2.5 系统关键技术",
        [
            "在这个课题里，“龙头股”并不等于某一天涨得最快的股票。更常见的情况是，短期涨幅靠前的个股未必真的能代表行业，有时只是情绪推动；真正更能代表行业状态的，往往是那些规模、盈利、成长和市场关注度都更稳的公司。传统龙头企业识别也大多沿着这个思路，从市值规模、产业地位、盈利质量、成长能力、估值合理性和市场表现等多个维度综合判断。[3][5-6]",
            "项目里的做法也是如此：先把规模、盈利、成长、估值和交易信号放到一起，再看它们在同一行业内的相对位置。这样筛出来的结果不一定是短期最活跃的股票，但通常更容易解释，也更接近研究场景下“代表性公司”的含义。换句话说，本文希望筛出来的是能够代表行业结构和市场确认状态的标的，而不是一次性情绪冲高的样本。",
        ],
    )

    replace_section_body(
        doc,
        "3.3 非功能需求分析",
        "3.4 系统总体架构设计",
        [
            "从实际使用感受看，行业模块的非功能问题首先体现在等待时间上。用户切到行业页时，如果每次都重新抓数据、重算排行、再补详情，页面几秒内就会变得很拖沓，所以系统才把缓存拆到分析层和接口层，用来挡掉重复计算和重复请求。",
            "另一个很现实的问题是外部接口并不稳定。行业目录、资金流和个股字段只要有一个来源短时抖动，页面就可能出现空值或局部缺口，因此系统必须允许主路径失败后继续回退，并让热力图、排行榜和详情页尽量保持可用。再往后，如果还要继续接新的指标或研究视图，这套结构也不能每扩一块就大动一次，所以可扩展性同样是非功能需求的一部分。",
        ],
    )

    replace_section_body(
        doc,
        "3.4 系统总体架构设计",
        "3.5 数据流程设计",
        [
            "如图 3.1 所示，系统总体上采用四层结构：表现层、服务层、分析层和数据层。这样拆分不是为了把架构图画得更复杂，而是因为行业研究页面从请求发出到结果落地，确实会依次经过这四层。表现层主要是前端行业主页面、热力图、排行榜以及行业详情和龙头股详情弹窗，回放、观察列表和偏好配置等功能则作为辅助研究交互存在；服务层由 FastAPI 行业接口构成，负责请求接收、参数校验、缓存与响应封装；分析层由行业分析器和龙头股评分器组成，真正完成行业综合评分、龙头股筛选和评分拆解；数据层则以 THS-first 适配器为核心，统一协调同花顺、AKShare、新浪和腾讯等数据源。",
            "这样分层之后，每一层要解决的问题会清楚很多。表现层只需要关心图表交互和结果展示，服务层负责把分析结果组织成统一响应，分析层专注评分计算与结果解释，数据层则通过名称映射、节点回退、符号缓存和过期缓存保障等机制提高数据可用性。后面如果要替换局部数据源，或者微调评分权重，改动也大多集中在分析层和数据层，不必把前端页面整体重写一遍。",
            "和那种只依赖单一接口的数据抓取脚本相比，这套架构更适合支撑准实时行业研究。一方面，多源适配提高了行业目录、资金流、成分股、估值和历史走势等字段的覆盖率；另一方面，缓存和分层封装让页面响应速度与结果口径更容易保持一致。对论文写作来说，这一点也很重要，因为只有系统本身运行得足够稳定，后面拿到的快照样本和案例分析才有说服力。",
        ],
    )

    replace_section_body(
        doc,
        "3.6 存储设计",
        "热门行业识别与龙头股遴选模型设计",
        [
            "行业子系统现在采用的是“文件快照加浏览器本地状态”的持久化组合。热力图历史直接写入 data/industry/heatmap_history.json，观察行业与阈值配置按 profile 写入 data/industry_preferences/<profile>.json，龙头股财务缓存保存在 cache/financial_cache.json；前端页面再把回放所需的快照片段和当前选中状态留在 localStorage。",
            "这样处理首先是因为当前数据规模和使用方式都比较明确。答辩展示、论文复核和本地调试经常需要回看某个固定样本时点，直接读取这些文件会比额外再搭一层存储服务更省步骤；同时文件路径也更方便和脚本、截图、附录材料保持对应关系。对这套毕业设计原型来说，先把样例可复核和页面可回放做好，比把存储层做成复杂部署更重要。",
        ],
    )

    replace_section_body(
        doc,
        "6.5 对毕业设计目标的达成情况",
        "结 论",
        [
            "回到任务书要求来看，论文和系统已经把核心目标一一落到了实处：前两章完成了金融大数据、行业分析和企业筛选相关理论梳理，第四章把行业热度与龙头股模型说明清楚，第五章和第六章则把系统实现、样例快照和测试结果对应起来。换句话说，任务书要求的“理解方法、实现系统、展示结果”这条主线是闭合的。",
            "这套实现没有把重点放在额外扩充部署形态上，而是先把毕业设计真正需要的几件事做扎实：页面能稳定运行，固定样本能回看，评分结果能解释，论文里的表格和截图也能和项目对上。以当前课题的体量来说，这样的取舍更利于展示和复核，也更符合本科毕业设计的完成目标。",
        ],
    )

    replace_section_body(
        doc,
        "5.1 数据提供器与回退机制实现",
        "5.2 行业分析模块实现",
        [
            "行业子系统的数据入口虽然封装在 SinaIndustryAdapter 中，但它在项目里的职责已经不止是调用单一新浪接口，更像是一个行业数据适配中枢。实际运行时，系统优先从同花顺接口拿行业目录、行业摘要、资金流、领涨股和行业指数，再由 AKShare 补齐行业元数据、成分股、估值、财务与历史行情；新浪和腾讯则更多承担回退和字段补缺任务。通过这种分工，系统逐渐形成了“同花顺主导、AKShare 增强、新浪与腾讯补充”的运行方式。[1-2]",
            "适配层真正麻烦的地方，在于同一行业在不同来源里的命名和节点并不一致。项目里为此维护了名称映射、节点映射、代理节点、符号缓存和反向映射等机制；当主路径失败时，再配合过期缓存把结果尽量补齐。这样做的目的不是多加一道兜底本身，而是让行业目录和成分股匹配尽量不断链。",
            "从论文角度看，这套适配设计最大的价值，是把行业摘要、资金流、成分股、估值和财务字段收拢到统一入口下，后面的行业评分和龙头股筛选就不需要分别适配多套来源。对工程实现来说，它也明显降低了外部数据源短时波动对系统可用性的影响。",
        ],
    )

    replace_section_body(
        doc,
        "5.2 行业分析模块实现",
        "5.3 龙头股评分模块实现",
        [
            "IndustryAnalyzer 更像是一个把原始行业字段整理成研究结果的中间层。它先利用行业摘要、资金流和少量横截面指标把热力图与排行榜所需的数据跑出来，尽量不在首屏就逐行业拉全量成分股；等用户继续下钻时，再补趋势统计、覆盖率和解释字段。",
            "在这条链路里，change_pct 或 weighted_change 负责描述近期强弱，flow_strength 表示资金承接，avg_volume 拿不到时再退到 turnover_rate，industry_volatility 则交给历史波动率或代理值处理。最后输出给前端的，已经不是零散原始列，而是一组带 total_score、资金流、换手率和说明字段的结构化结果，所以热力图、排行榜和趋势面板才能共享同一套分析口径。",
        ],
    )

    replace_section_body(
        doc,
        "5.3 龙头股评分模块实现",
        "5.4 后端接口实现",
        [
            "LeaderStockScorer 负责的也不只是“给股票打个分”。在同一行业里，它既要输出列表排序，又要给详情页提供评分拆解和原始字段，所以模块同时保留了完整评分与快照快速评分两条链路。前者更适合龙头股详情和深度研究，后者则是为了让行业列表页先把候选股票尽快筛出来。",
            "模块还会把结果拆成 core 和 hot 两类榜单。core 更偏向六维综合质量筛选，hot 更强调短期涨幅和资金承接；两者共用同一套 raw_data 结构，但在无法拿到 ROE 或增长字段时，快速链路会用中性分处理缺口。这样做的好处是，页面响应速度和评分口径之间可以取得相对平衡，而不是二选一。",
        ],
    )

    replace_section_body(
        doc,
        "5.4 后端接口实现",
        "5.5 前端可视化实现",
        [
            "后端接口层在项目里承担的是“把分析能力组织成可稳定调用的服务”。热门行业列表、成分股、热力图、热力图历史、行业趋势、龙头股列表、龙头股详情和偏好配置这些接口，基本把前端行业工作区需要的数据都覆盖了；聚类和轮动接口则更多承担辅助分析作用。[1-2][9-10]",
            "真正影响使用体验的还有缓存和兜底逻辑。路由层维护了 3 分钟端点缓存、30 分钟 parity 缓存，以及完整版成分股的异步构建机制；必要时还会返回过期缓存，避免外部数据源短时波动时页面直接空掉。热力图历史数据也设置了记录数和文件大小上限，保证快照文件长期可控。",
        ],
    )

    replace_section_body(
        doc,
        "5.5 前端可视化实现",
        "5.6 偏好配置与持续跟踪实现",
        [
            "前端行业工作区是按研究动作顺序排的，而不是先做若干孤立图表再拼到一起。页面顶部先给出当前市场概况和筛选条件，中间区域同时摆放热力图与排行榜，右侧保留龙头股榜单，用户一般会先看板块分布，再点进某个行业，最后查看个股详情。IndustryDashboard 这一页承担的，就是把这条浏览路径压缩到一次切换里完成。",
            "具体交互也尽量贴近项目实际使用方式。热力图切换颜色维度时，用户能直接看到板块冷热变化；尺寸维度和市值来源切换更多是为了判断排序背后的口径差异；排行榜里的回看窗口、波动过滤和排序项则帮助用户快速缩小范围。等用户打开详情弹窗后，评分拆解、价格走势和财务字段会接着出现，所以这里更像一条连续的研究路径，而不是几张静态图并排展示。",
            "如图 5.1 所示，行业热度总览页面将热力图、行业排行榜、趋势面板与龙头股入口整合在同一研究界面中，便于研究者快速完成行业筛选、排序比较与详情联动。",
            "图 5.1 行业热度总览界面",
            "图片来源：系统运行截图（作者自制）",
            "如图 5.2 所示，行业热力图页面支持按不同维度观察行业强弱与结构分布，既可以用颜色突出短期热度，也可以通过尺寸和市值来源信息帮助用户理解当前排序结果的背景。",
            "图 5.2 行业热力图界面",
            "图片来源：系统运行截图（作者自制）",
            "如图 5.3 所示，龙头股详情页面展示综合得分、维度拆解、价格走势与关键财务字段，能够帮助用户理解候选股票被遴选出的具体依据。",
            "图 5.3 龙头股详情界面",
            "图片来源：系统运行截图（作者自制）",
        ],
    )

    replace_section_body(
        doc,
        "6.4 系统特征与不足分析",
        "6.5 对毕业设计目标的达成情况",
        [
            "如果只看当前仓库真正保留下来的行业模块，它最有用的地方在于同一套数据入口已经能支撑从热力图到个股详情的连续分析。用户先在页面里看到行业排序，再点进趋势、龙头股和评分拆解时，背后用的仍是同一条适配、评分和缓存链路，因此结果解释不会前后脱节。",
            "但它的边界也很明确。权重目前还是工程经验优先，部分行业在成分股映射不完整时仍会走降级路径；模块刷新主要依赖 REST、缓存和历史快照，不是持续流式的实时系统；行业识别结果和后续收益之间的量化验证也还可以继续补强。这些问题不会影响毕业设计展示，但确实是后续迭代最该继续打磨的地方。",
        ],
    )

    replace_section_body(
        doc,
        "结 论",
        "参考文献",
        [
            "本文以现有量化研究平台中的行业热度子系统为依托，围绕热门行业识别与龙头股遴选这一毕业设计主题，完成了系统分析、模型设计、工程实现和结果总结。通过梳理项目中的 THS-first 数据适配器、行业分析器、龙头股评分器、后端接口层以及前端行业仪表盘页面，本文构建了一条从多源数据获取到可视化展示的完整研究主线。",
            "在模型方面，本文总结并实现了以动量、资金流、活跃度和波动率代理为核心的行业热度评分模型，以及以规模、估值、盈利、成长、动量和活跃度为核心的龙头股综合评分模型。行业热度部分采用横截面标准化与加权合成的方法，并进一步压缩到便于展示的相对得分区间；龙头股部分则同时支持完整评分与快照快速评分两条链路，在保证口径一致的前提下兼顾分析完整性与页面响应效率。",
            "在工程实现方面，本文说明了 THS-first 多源数据回退、分析层与路由层缓存、热力图历史快照、财务缓存以及按 profile 偏好持久化的协同工作方式。第六章结合项目当前保留的五日热力图快照、龙头股双榜单样例和测试结果说明，该系统能够识别样本时点的阶段性强势行业，并进一步给出行业内部具有代表性的龙头股候选结果，具有较好的结果解释性与展示性。",
            "未来工作可以从以下方向展开：第一，引入舆情、政策文本和产业链数据，增强行业识别的前瞻性；第二，采用熵权法、层次分析法或机器学习方法优化权重；第三，完善行业识别结果与后续收益表现之间的回测验证；第四，继续提高成分股映射完整度并优化核心行业分析链路。总体而言，本文所完成的工作已经能够满足本科毕业设计对理论分析、系统实现与应用展示的综合要求。",
        ],
    )

    test_heading = next((p for p in doc.paragraphs if p.text.strip() == "6.2 功能测试"), None)
    if test_heading is not None:
        next_element = test_heading._element.getnext()
        intro_text = (
            "当前仓库保留的验证方式并不只有人工点页面这一种。分析层有行业评分与快路径回退相关单测，接口层有"
            "名称映射、偏好服务和龙头股列表/详情的返回结构检查，前端还保留了热力图切换、行业搜索和详情弹窗"
            "闭环的端到端脚本。表 6.1 汇总的是这些验证里与毕业设计主链路最相关的部分，因此更关注评分是否可"
            "解释、接口是否连通、页面操作是否能闭环，而不是生产环境压测。"
        )
        if next_element is not None and next_element.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph

            next_para = Paragraph(next_element, test_heading._parent)
            if next_para.text.strip().startswith("功能测试主要分为三类"):
                replace_paragraph_text(next_para, intro_text)
            elif next_para.text.strip() != "表 6.1 主要功能测试结果":
                replace_paragraph_text(next_para, intro_text)
            else:
                intro_para = insert_paragraph_after(test_heading, intro_text)
                intro_para.paragraph_format.keep_with_next = True

    function_table = find_table_containing_text(doc, "模块")
    if function_table is not None and len(function_table.rows) >= 6 and len(function_table.columns) >= 3:
        function_table.cell(1, 1).text = "获取 THS 行业目录、行业摘要、成分股与财务等数据"
        function_table.cell(1, 2).text = "THS-first 适配器主导，AKShare/Sina/腾讯补齐"
        function_table.cell(2, 2).text = "横截面评分、波动率代理、聚类与轮动分析"
        function_table.cell(4, 2).text = "React 仪表盘、热力图与详情联动"
        function_table.cell(5, 2).text = "按 profile 的 JSON 持久化与浏览器缓存"

    sample_table = find_table_containing_text(doc, "资金流(元)")
    if sample_table is None:
        sample_table = find_table_containing_text(doc, "资金流(亿元)")
    update_heatmap_sample_table(sample_table, heatmap_snapshot)

    test_table = find_table_containing_text(doc, "测试项目")
    if test_table is None:
        test_table = find_table_containing_text(doc, "输入或操作")
    if test_table is not None and len(test_table.rows) >= 6 and len(test_table.columns) >= 4:
        test_table.cell(0, 0).text = "测试项目"
        row_values = [
            ("行业评分计算与回退", "运行行业评分逻辑并验证快路径与字段回退", "快速评分链路可输出 20-95 展示得分，代理波动率与字段回退生效", "满足预期"),
            ("THS-first 适配器映射", "验证行业名称映射和多源回退", "THS 主源可用，AKShare/Sina/腾讯补齐链路与缓存兜底正常", "满足预期"),
            ("龙头股列表与详情接口", "调用龙头股列表与详情接口", "core/hot 榜单与详情接口均返回综合得分、维度拆解和原始字段", "满足预期"),
            ("偏好配置持久化", "保存并重置观察行业与阈值配置", "JSON 与浏览器状态保持一致", "满足预期"),
            ("前端行业页面闭环", "切换热力图周期、搜索行业并打开详情", "热力图、排行榜与详情弹窗联动正常", "满足预期"),
        ]
        for row_index, values in enumerate(row_values, start=1):
            for col_index, value in enumerate(values):
                test_table.cell(row_index, col_index).text = value

    ensure_section_trailing_paragraph(
        doc,
        "6.4 系统特征与不足分析",
        "进一步结合 ",
        leader_case_text,
    )

    insert_architecture_figure(doc)
    insert_task_completion_table(doc)


def find_paragraph_by_text(doc: Document, text: str):
    for paragraph in doc.paragraphs:
        if paragraph.text.strip() == text:
            return paragraph
    raise RuntimeError(f"Paragraph not found: {text}")


def find_last_paragraph_by_text(doc: Document, text: str):
    for paragraph in reversed(doc.paragraphs):
        if paragraph.text.strip() == text:
            return paragraph
    raise RuntimeError(f"Paragraph not found: {text}")


def find_previous_drawing_paragraph(doc: Document, anchor_paragraph):
    paragraphs = doc.paragraphs
    anchor_index = None
    for idx, paragraph in enumerate(paragraphs):
        if paragraph._element is anchor_paragraph._element:
            anchor_index = idx
            break
    if anchor_index is None:
        raise RuntimeError(f"Anchor paragraph not found in document: {anchor_paragraph.text}")
    for idx in range(anchor_index - 1, -1, -1):
        paragraph = paragraphs[idx]
        if "w:drawing" in paragraph._element.xml:
            return paragraph
    raise RuntimeError(f"Drawing paragraph not found before: {anchor_paragraph.text}")


def ensure_figure_source_paragraph(caption):
    next_element = caption._element.getnext()
    if next_element is not None and next_element.tag == qn("w:p"):
        from docx.text.paragraph import Paragraph

        next_para = Paragraph(next_element, caption._parent)
        if next_para.text.strip().startswith("图片来源："):
            replace_paragraph_text(next_para, SOURCE_NOTE)
            return next_para
    return insert_paragraph_after(caption, SOURCE_NOTE)


def ensure_figure_intro_paragraph(image_para, intro_text: str):
    from docx.text.paragraph import Paragraph

    figure_match = re.match(r"^(如图\s*\d+\.\d+)\s*所示", intro_text)
    figure_prefix = figure_match.group(1) if figure_match else None
    previous = image_para._element.getprevious()
    while previous is not None:
        if previous.tag != qn("w:p"):
            previous = previous.getprevious()
            continue
        previous_para = Paragraph(previous, image_para._parent)
        previous_text = previous_para.text.strip()
        if not previous_text:
            previous = previous.getprevious()
            continue
        if previous_text == intro_text or (figure_prefix and previous_text.startswith(figure_prefix)):
            replace_paragraph_text(previous_para, intro_text)
            return previous_para
        break

    intro_para = insert_paragraph_before_element(image_para._element, image_para._parent)
    intro_para.add_run(intro_text)
    return intro_para


def relayout_figures(doc: Document) -> None:
    body_section = doc.sections[-1]
    max_body_width = body_section.page_width - body_section.left_margin - body_section.right_margin
    TMP_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for title, config in FIGURE_IMAGES.items():
        caption = find_paragraph_by_text(doc, title)
        previous_element = caption._element.getprevious()
        image_para = None
        if previous_element is not None and previous_element.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph

            previous_para = Paragraph(previous_element, caption._parent)
            if "w:drawing" in previous_para._element.xml and not previous_para.text.strip():
                image_para = previous_para
        if image_para is None:
            image_para = insert_paragraph_before_element(caption._element, caption._parent)

        previous = image_para._element.getprevious()
        if previous is not None and previous.tag == qn("w:p") and 'w:type="page"' in previous.xml:
            previous.getparent().remove(previous)
        source_path = Path(config["path"])
        crop_box = config["crop"]
        output_path = TMP_ASSET_DIR / f"{config['slug']}.png"
        with Image.open(source_path) as img:
            cropped = img.crop(crop_box)
            bordered = ImageOps.expand(cropped, border=4, fill="#C9D4E0")
            bordered.save(output_path)
        clear_paragraph(image_para)
        image_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        image_para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        image_para.paragraph_format.line_spacing = 1.0
        image_para.paragraph_format.space_before = Pt(0)
        image_para.paragraph_format.space_after = Pt(0)
        image_para.paragraph_format.first_line_indent = Pt(0)
        remove_page_break_before_flag(image_para)
        width_scale = config.get("width_scale", 0.97)
        target_width = Emu(int(max_body_width * width_scale))
        image_para.add_run().add_picture(str(output_path), width=target_width)
        intro_text = FIGURE_INTRO_PARAGRAPHS.get(title)
        if intro_text:
            intro_para = ensure_figure_intro_paragraph(image_para, intro_text)
            intro_para.paragraph_format.keep_with_next = True
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.paragraph_format.first_line_indent = Pt(0)
        caption.paragraph_format.space_before = Pt(3)
        caption.paragraph_format.space_after = Pt(0)
        caption.paragraph_format.keep_with_next = True
        image_para.paragraph_format.keep_with_next = True
        source_para = ensure_figure_source_paragraph(caption)
        source_para.paragraph_format.space_before = Pt(0)
        source_para.paragraph_format.space_after = Pt(3)
        source_para.paragraph_format.keep_with_next = False


def _set_row_no_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = tr_pr.find(qn("w:cantSplit"))
    if cant_split is None:
        cant_split = OxmlElement("w:cantSplit")
        tr_pr.append(cant_split)


def set_table_borders(table, top: bool, header_bottom: bool, bottom: bool) -> None:
    rows = table.rows
    for row_idx, row in enumerate(rows):
        _set_row_no_split(row)
        for cell in row.cells:
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_borders = tc_pr.find(qn("w:tcBorders"))
            if tc_borders is None:
                tc_borders = OxmlElement("w:tcBorders")
                tc_pr.append(tc_borders)
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                node = tc_borders.find(qn(f"w:{edge}"))
                if node is None:
                    node = OxmlElement(f"w:{edge}")
                    tc_borders.append(node)
                enabled = False
                if edge == "top" and top and row_idx == 0:
                    enabled = True
                elif edge == "bottom" and header_bottom and row_idx == 0:
                    enabled = True
                elif edge == "bottom" and bottom and row_idx == len(rows) - 1:
                    enabled = True
                if enabled:
                    node.set(qn("w:val"), "single")
                    node.set(qn("w:sz"), "8")
                    node.set(qn("w:space"), "0")
                    node.set(qn("w:color"), "000000")
                else:
                    node.set(qn("w:val"), "nil")


def set_table_column_widths(table, widths: tuple[Emu | Cm, ...]) -> None:
    table.autofit = False
    for col_idx, width in enumerate(widths):
        for row in table.rows:
            if col_idx < len(row.cells):
                row.cells[col_idx].width = width


def format_data_tables(doc: Document) -> None:
    for table in doc.tables:
        text = "\n".join(cell.text for row in table.rows for cell in row.cells)
        if "姓    名：" in text or "论文题目：" in text:
            continue
        if "行业热力图 / 行业排行榜" in text and "THS 主数据 / AKShare 增强" in text:
            continue
        if "Sindustry" in text or "Sleader" in text or "m:oMath" in table._tbl.xml:
            continue
        if not table.rows:
            continue
        is_main_test_table = "行业评分计算与回退" in text and "前端行业页面闭环" in text
        if is_main_test_table:
            set_table_column_widths(table, (Cm(2.9), Cm(3.4), Cm(6.1), Cm(2.2)))
        set_table_borders(table, top=True, header_bottom=True, bottom=True)
        for row_index, row in enumerate(table.rows):
            for cell_index, cell in enumerate(row.cells):
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                for paragraph in cell.paragraphs:
                    if row_index == 0 or (is_main_test_table and cell_index == 3):
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    else:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    paragraph.paragraph_format.first_line_indent = Pt(0)
                    paragraph.paragraph_format.line_spacing = Pt(15) if is_main_test_table else Pt(20)
                    paragraph.paragraph_format.space_before = Pt(0)
                    paragraph.paragraph_format.space_after = Pt(0)
                    for run in paragraph.runs:
                        run.font.bold = row_index == 0
                        font_size = Pt(9) if is_main_test_table and row_index != 0 else Pt(10.5)
                        set_run_text_font(run, "宋体", font_size)


def append_omml_equation(paragraph, equation_text: str, font_half_points: int = 20) -> None:
    omath_para = OxmlElement("m:oMathPara")
    omath = OxmlElement("m:oMath")
    math_run = OxmlElement("m:r")
    math_run_props = OxmlElement("m:rPr")
    for tag in ("w:sz", "w:szCs"):
        size_node = OxmlElement(tag)
        size_node.set(qn("w:val"), str(font_half_points))
        math_run_props.append(size_node)
    math_run.append(math_run_props)
    math_text = OxmlElement("m:t")
    math_text.text = equation_text
    math_run.append(math_text)
    omath.append(math_run)
    omath_para.append(omath)
    paragraph._p.append(omath_para)


def replace_formula_block(doc: Document, keyword: str, equation_text: str, equation_number: str) -> None:
    stale_formula_paragraphs = [
        paragraph
        for paragraph in doc.paragraphs
        if paragraph.text.strip().startswith(keyword) or paragraph.text.strip() == equation_number
    ]
    anchor_element = None
    anchor_parent = None
    target_table = find_table_containing_text(doc, keyword)
    if target_table is None:
        target_table = next((table for table in doc.tables if keyword in table._tbl.xml), None)
    if target_table is not None:
        anchor_element = target_table._element
        anchor_parent = target_table._parent
    else:
        first_stale_paragraph = stale_formula_paragraphs[0] if stale_formula_paragraphs else None
        if first_stale_paragraph is not None:
            anchor_element = first_stale_paragraph._element
            anchor_parent = first_stale_paragraph._parent

    if anchor_element is None or anchor_parent is None:
        return

    equation_para = insert_paragraph_before_element(anchor_element, anchor_parent)
    equation_para.style = "Normal"
    equation_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    equation_para.paragraph_format.first_line_indent = Pt(0)
    equation_para.paragraph_format.space_before = Pt(6)
    equation_para.paragraph_format.space_after = Pt(0)
    equation_para.paragraph_format.line_spacing = BODY_LINE_SPACING
    equation_run = equation_para.add_run(equation_text)
    equation_run.font.name = "Times New Roman"
    equation_run.font.size = Pt(10.5)
    set_east_asia_font(equation_run, "Times New Roman")

    number_para = insert_paragraph_after(equation_para)
    number_para.style = "Normal"
    number_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    number_para.paragraph_format.first_line_indent = Pt(0)
    number_para.paragraph_format.space_before = Pt(0)
    number_para.paragraph_format.space_after = Pt(6)
    number_para.paragraph_format.line_spacing = BODY_LINE_SPACING
    number_run = number_para.add_run(equation_number)
    number_run.font.name = "Times New Roman"
    number_run.font.size = Pt(10.5)
    set_east_asia_font(number_run, "Times New Roman")

    anchor_element.getparent().remove(anchor_element)
    keep_elements = {equation_para._element, number_para._element}
    for paragraph in list(doc.paragraphs):
        stripped = paragraph.text.strip()
        if paragraph._element in keep_elements:
            continue
        if stripped.startswith(keyword) or stripped == equation_number:
            paragraph._element.getparent().remove(paragraph._element)


def replace_formula_tables(doc: Document) -> None:
    replace_formula_block(
        doc,
        "Sindustry",
        "Sindustry=0.35×Zm+0.35×Zf+0.15×Zv-0.15×Zr",
        "（4.2.1）",
    )
    replace_formula_block(
        doc,
        "Sleader",
        "Sleader=100×(0.20×s1+0.15×s2+0.25×s3+0.20×s4+0.10×s5+0.10×s6)",
        "（4.4.1）",
    )


def normalize_reference_entries(doc: Document) -> None:
    entries = [
        "[1] 孟小峰, 慈祥. 大数据管理：概念、技术与挑战[J]. 计算机学报, 2013, 36(3): 635-652.",
        "[2] 张晓琳, 王吉. 基于大数据的金融风险监测与预警研究[J]. 金融理论与实践, 2022(4): 58-64.",
        "[3] 李明, 刘强. 基于知识图谱的产业链核心企业识别方法研究[J]. 计算机集成制造系统, 2023, 29(5): 1650-1662.",
        "[4] 陈云, 赵刚. 行业轮动策略在量化投资中的应用研究：基于宏观经济数据的实证分析[J]. 投资研究, 2021, 40(9): 45-58.",
        "[5] 王赫. 基于 Python 的上市公司财务数据可视化分析系统的设计与实现[D]. 北京: 北京交通大学, 2020.",
        "[6] 韦韦. 机器学习在金融大数据挖掘中的应用场景探讨[J]. 现代信息科技, 2023, 7(12): 115-118.",
        [
            "[7] Cavalcante R C, Brasileiro R C, Souza V L, et al. Computational Intelligence and Financial Markets: A Survey and Future Directions[J].",
            "Expert Systems with Applications, 2016, 55: 194-211.",
        ],
        [
            "[8] Hasan M M, Popp J, Olah J. Current landscape and influence of big data on finance[J].",
            "Journal of Big Data, 2020, 7: 21.",
        ],
        [
            "[9] McKinney W. Python for Data Analysis: Data Wrangling with Pandas, NumPy, and IPython[M].",
            "3rd ed. Sebastopol: O'Reilly Media, 2022.",
        ],
        [
            "[10] Pedregosa F, Varoquaux G, Gramfort A, et al. Scikit-learn: Machine Learning in Python[J].",
            "Journal of Machine Learning Research, 2011, 12: 2825-2830.",
        ],
    ]
    start_index = next(
        (idx + 1 for idx, paragraph in enumerate(doc.paragraphs) if paragraph.text.strip() == "参考文献"),
        None,
    )
    if start_index is None:
        raise RuntimeError("Reference section anchor not found.")
    for offset, entry in enumerate(entries):
        paragraph = doc.paragraphs[start_index + offset]
        clear_paragraph(paragraph)
        if isinstance(entry, str):
            paragraph.add_run(entry)
            continue
        for index, line in enumerate(entry):
            run = paragraph.add_run(line)
            if index < len(entry) - 1:
                run.add_break(WD_BREAK.LINE)


def apply_minor_layout_overrides(doc: Document) -> None:
    target_heading = next(
        (paragraph for paragraph in doc.paragraphs if paragraph.text.strip() == "5.6 偏好配置与持续跟踪实现"),
        None,
    )
    if target_heading is not None:
        target_heading.paragraph_format.page_break_before = True
        target_heading.paragraph_format.keep_with_next = True
        next_element = target_heading._element.getnext()
        if next_element is not None and next_element.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph

            first_para = Paragraph(next_element, target_heading._parent)
            first_para.paragraph_format.keep_with_next = True
            second_element = next_element.getnext()
            if second_element is not None and second_element.tag == qn("w:p"):
                second_para = Paragraph(second_element, target_heading._parent)
                second_para.paragraph_format.keep_together = True

    completion_heading = next(
        (paragraph for paragraph in doc.paragraphs if paragraph.text.strip() == "6.5 对毕业设计目标的达成情况"),
        None,
    )
    if completion_heading is not None:
        completion_heading.paragraph_format.page_break_before = True
        completion_heading.paragraph_format.keep_with_next = True
        next_element = completion_heading._element.getnext()
        if next_element is not None and next_element.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph

            intro_para = Paragraph(next_element, completion_heading._parent)
            intro_para.paragraph_format.keep_with_next = True


def apply_superscript_citations(paragraph) -> None:
    text = paragraph.text
    if not text or "[" not in text or paragraph.text.strip().startswith("["):
        return
    matches = list(re.finditer(r"\[[0-9,\-，]+\]", text))
    if not matches:
        return
    clear_paragraph(paragraph)
    cursor = 0
    for match in matches:
        if match.start() > cursor:
            normal_run = paragraph.add_run(text[cursor:match.start()])
            format_body_run(normal_run)
        citation_run = paragraph.add_run(match.group(0))
        format_body_run(citation_run)
        citation_run.font.superscript = True
        cursor = match.end()
    if cursor < len(text):
        tail_run = paragraph.add_run(text[cursor:])
        format_body_run(tail_run)


def format_paragraphs(doc: Document) -> None:
    abstract_index = next(
        (idx for idx, paragraph in enumerate(doc.paragraphs) if paragraph.text.strip() == "摘  要"),
        0,
    )
    english_abstract_index = next(
        (idx for idx, paragraph in enumerate(doc.paragraphs) if paragraph.text.strip() == "ABSTRACT"),
        abstract_index,
    )
    toc_index = next(
        (idx for idx, paragraph in enumerate(doc.paragraphs) if paragraph.text.strip() == "目  录"),
        english_abstract_index,
    )
    for idx, paragraph in enumerate(doc.paragraphs):
        if idx < abstract_index:
            continue
        text = paragraph.text.strip()
        style_name = paragraph.style.name if paragraph.style is not None else ""

        if not text:
            continue
        if text == "摘  要":
            clear_paragraph(paragraph)
            run = paragraph.add_run("摘  要")
            paragraph.style = "Normal"
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = ABSTRACT_LINE_SPACING
            set_run_text_font(run, "黑体", Pt(18), bold=True)
            continue
        if text == "ABSTRACT":
            clear_paragraph(paragraph)
            run = paragraph.add_run("ABSTRACT")
            paragraph.style = "Normal"
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = ABSTRACT_LINE_SPACING
            set_run_text_font(run, "Times New Roman", Pt(18), bold=True)
            continue
        if text == "目  录":
            format_toc_title(paragraph)
            continue
        if style_name in {"toc 1", "toc 2"}:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = ABSTRACT_LINE_SPACING
            for run in paragraph.runs:
                set_run_text_font(run, "宋体", Pt(12), bold=False)
            continue
        if style_name == "Heading 1":
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(12)
            paragraph.paragraph_format.space_after = Pt(6)
            paragraph.paragraph_format.line_spacing = BODY_LINE_SPACING
            for run in paragraph.runs:
                set_run_text_font(run, "黑体", Pt(18), bold=True)
            continue
        if style_name == "Heading 2":
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(6)
            paragraph.paragraph_format.line_spacing = BODY_LINE_SPACING
            for run in paragraph.runs:
                set_run_text_font(run, "黑体", Pt(14), bold=True)
            continue
        if style_name == "Heading 3":
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(3)
            paragraph.paragraph_format.line_spacing = BODY_LINE_SPACING
            for run in paragraph.runs:
                set_run_text_font(run, "黑体", Pt(12), bold=True)
            continue
        if text in {"结 论", "参考文献", "致 谢"}:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(12)
            paragraph.paragraph_format.space_after = Pt(6)
            paragraph.paragraph_format.line_spacing = BODY_LINE_SPACING
            for run in paragraph.runs:
                set_run_text_font(run, "黑体", Pt(18), bold=True)
            continue
        if text.startswith("关键词："):
            content = text.split("：", 1)[1]
            clear_paragraph(paragraph)
            label_run = paragraph.add_run("关键词：")
            value_run = paragraph.add_run(content)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.5
            set_run_text_font(label_run, "宋体", Pt(12), bold=False)
            set_run_text_font(value_run, "宋体", Pt(12), bold=False)
            continue
        if text.startswith("Keywords:"):
            content = text[len("Keywords:"):].strip()
            clear_paragraph(paragraph)
            label_run = paragraph.add_run("Keywords:")
            spacer_run = paragraph.add_run(" ")
            value_run = paragraph.add_run(content)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.5
            set_run_text_font(label_run, "Times New Roman", Pt(12), bold=True)
            set_run_text_font(spacer_run, "Times New Roman", Pt(12), bold=False)
            set_run_text_font(value_run, "Times New Roman", Pt(12), bold=False)
            continue
        if re.match(r"^图\s*\d+\.\d+", text):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = Pt(20)
            for run in paragraph.runs:
                set_run_text_font(run, "黑体", Pt(12), bold=False)
            continue
        if text.startswith("图片来源："):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(6)
            paragraph.paragraph_format.line_spacing = Pt(18)
            for run in paragraph.runs:
                set_run_text_font(run, "宋体", Pt(10.5), bold=False)
            continue
        if re.match(r"^表\s*\d+\.\d+", text):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(6)
            paragraph.paragraph_format.line_spacing = Pt(20)
            for run in paragraph.runs:
                set_run_text_font(run, "黑体", Pt(12), bold=False)
            continue
        if text.startswith("Sindustry") or text.startswith("Sleader"):
            equation_text = "Sindustry=0.35×Zm+0.35×Zf+0.15×Zv-0.15×Zr"
            if text.startswith("Sleader"):
                equation_text = "Sleader=100×(0.20×s1+0.15×s2+0.25×s3+0.20×s4+0.10×s5+0.10×s6)"
            clear_paragraph(paragraph)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = BODY_LINE_SPACING
            run = paragraph.add_run(equation_text)
            set_run_text_font(run, "Times New Roman", Pt(10.5), bold=False)
            continue
        if text in {"（4.2.1）", "（4.4.1）"}:
            clear_paragraph(paragraph)
            run = paragraph.add_run(text)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(6)
            paragraph.paragraph_format.line_spacing = BODY_LINE_SPACING
            set_run_text_font(run, "Times New Roman", Pt(10.5), bold=False)
            continue
        if re.match(r"^\[\d+\]", text):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.first_line_indent = Cm(-1.27)
            paragraph.paragraph_format.left_indent = Cm(1.27)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = BODY_LINE_SPACING
            for run in paragraph.runs:
                set_run_text_font(run, "宋体", Pt(12), bold=False)
            continue
        if text.startswith("题   目：") or text.startswith("学    院：") or text.startswith("专    业："):
            continue

        paragraph.style = "Normal"
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        paragraph.paragraph_format.first_line_indent = BODY_FIRST_LINE_INDENT
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        if abstract_index < idx < english_abstract_index or english_abstract_index < idx < toc_index:
            paragraph.paragraph_format.line_spacing = ABSTRACT_LINE_SPACING
        else:
            paragraph.paragraph_format.line_spacing = BODY_LINE_SPACING
        for run in paragraph.runs:
            if english_abstract_index < idx < toc_index:
                set_run_text_font(run, "Times New Roman", Pt(12), bold=False)
            else:
                format_body_run(run)
        apply_superscript_citations(paragraph)


def configure_headers_and_footers(doc: Document) -> None:
    for index, section in enumerate(doc.sections):
        if index < 2:
            configure_section_header(section, None)
            configure_section_footer(section, False)
            continue
        configure_section_header(section, HEADER_TEXT)
        configure_section_footer(section, True)
    if len(doc.sections) >= 3:
        set_section_page_number_format(doc.sections[2], fmt="upperRoman", start=1)
    if len(doc.sections) >= 4:
        set_section_page_number_format(doc.sections[3], fmt="decimal", start=1)


def compute_toc_pages_from_pdf(pdf_path: Path) -> dict[str, str]:
    reader = PdfReader(str(pdf_path))
    raw_page_texts = [page.extract_text() or "" for page in reader.pages]
    page_texts = [normalize_search_text(text) for text in raw_page_texts]
    page_lines = [
        [normalize_search_text(line) for line in text.splitlines() if line.strip()]
        for text in raw_page_texts
    ]

    toc_start_index = next(
        (i for i, text in enumerate(page_texts) if text.count(".") > 100 and "1绪论" in text),
        None,
    )
    chapter_start_index = None
    if toc_start_index is not None:
        chapter_start_index = next(
            (
                i
                for i in range(toc_start_index + 1, len(page_texts))
                if page_texts[i].count(".") < 50 and "1绪论" in page_texts[i]
            ),
            None,
        )
    if chapter_start_index is None:
        chapter_start_index = next(
            (i for i, text in enumerate(page_texts) if text.count(".") < 50 and "1绪论" in text),
            None,
        )
    if chapter_start_index is None:
        raise RuntimeError("Failed to determine the first body page for TOC rebuilding.")

    toc_pages = {
        "摘  要": "I",
        "ABSTRACT": "II",
    }
    for _, title in TOC_BLUEPRINT:
        if title in toc_pages:
            continue
        normalized_title = normalize_search_text(title)
        for page_index in range(chapter_start_index, len(page_texts)):
            if normalized_title in page_lines[page_index]:
                toc_pages[title] = str(page_index - chapter_start_index + 1)
                break
    return toc_pages


def remove_page_break_paragraph_before(doc: Document, title: str) -> None:
    paragraphs = doc.paragraphs
    for idx, paragraph in enumerate(paragraphs):
        if paragraph.text.strip() != title:
            continue
        if idx == 0:
            return
        previous = paragraphs[idx - 1]
        if previous.text.strip() == "" and 'w:type="page"' in previous._element.xml:
            delete_paragraph(previous)
        paragraph.paragraph_format.page_break_before = True
        return


def normalize_major_breaks(doc: Document) -> None:
    heading_1_paragraphs = [paragraph for paragraph in doc.paragraphs if paragraph.style.name == "Heading 1"]
    for index, paragraph in enumerate(heading_1_paragraphs):
        previous = paragraph._element.getprevious()
        if previous is not None and previous.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph

            previous_para = Paragraph(previous, paragraph._parent)
            if previous_para.text.strip() == "" and 'w:type="page"' in previous_para._element.xml:
                delete_paragraph(previous_para)
        if index == 0:
            paragraph.paragraph_format.page_break_before = False
            remove_page_break_before_flag(paragraph)
        else:
            paragraph.paragraph_format.page_break_before = True

    for title in ["结 论", "参考文献", "致 谢"]:
        remove_page_break_paragraph_before(doc, title)


def harmonize_section_breaks(target_doc: Document, source_doc: Document) -> None:
    source_chapter_break = deepcopy(find_heading_break_paragraph(source_doc, "绪论")._element.pPr.find(qn("w:sectPr")))
    target_chapter_break_paragraph = find_heading_break_paragraph(target_doc, "绪论")
    target_chapter_break_ppr = target_chapter_break_paragraph._element.get_or_add_pPr()
    existing_target_break = target_chapter_break_ppr.find(qn("w:sectPr"))
    if existing_target_break is not None:
        target_chapter_break_ppr.remove(existing_target_break)
    target_chapter_break_ppr.append(source_chapter_break)

    heading_index = None
    for index, paragraph in enumerate(target_doc.paragraphs):
        if paragraph.text.strip() == "绪论":
            heading_index = index
            break
    if heading_index is None:
        raise RuntimeError("Failed to locate chapter heading for section cleanup.")

    for index in range(max(0, heading_index - 4), heading_index):
        paragraph = target_doc.paragraphs[index]
        if paragraph._element is target_chapter_break_paragraph._element:
            continue
        p_pr = paragraph._element.pPr
        if p_pr is None:
            continue
        sect_pr = p_pr.find(qn("w:sectPr"))
        if sect_pr is not None:
            p_pr.remove(sect_pr)

    target_body = target_doc._element.body
    target_body_sect = target_body.find(qn("w:sectPr"))
    if target_body_sect is not None:
        target_body.remove(target_body_sect)
    target_body.append(deepcopy(source_doc._element.body.find(qn("w:sectPr"))))


def compose_official_template(source_doc: Document, source_layout_doc: Document) -> Document:
    TMP_DOC_DIR.mkdir(parents=True, exist_ok=True)

    front_doc = Document(str(TEMPLATE_PATH))
    fill_cover(front_doc)
    fill_declaration_table(front_doc)
    remove_elements_from_paragraph(front_doc, "摘  要")

    remove_elements_before_paragraph(source_doc, "摘  要")

    composer = Composer(front_doc)
    composer.append(source_doc)
    composer.save(str(COMPOSED_TMP_PATH))

    composed_doc = Document(str(COMPOSED_TMP_PATH))
    harmonize_section_breaks(composed_doc, source_layout_doc)
    set_core_properties(composed_doc)
    return composed_doc


def export_submission_artifacts(doc_path: Path) -> Path:
    template_page_1, template_page_2 = ensure_template_pdf_pages()
    front_cover_png = TMP_FRONT_ASSET_DIR / "front_cover.png"
    declaration_png = TMP_FRONT_ASSET_DIR / "front_declaration.png"
    front_pdf = TMP_FRONT_ASSET_DIR / "front_pages.pdf"

    cover_render = render_cover_page(template_page_1, front_cover_png)
    declaration_asset, declaration_render = prepare_declaration_page_asset(template_page_2, declaration_png)
    build_front_pdf(front_cover_png, declaration_asset, front_pdf)

    body_pdf = export_docx_pdf(doc_path, TMP_DOCX_RENDER_DIR)
    merge_submission_pdf(front_pdf, body_pdf, OUTPUT_PDF_PATH)
    if LEGACY_DUPLICATE_PDF_PATH.exists():
        LEGACY_DUPLICATE_PDF_PATH.unlink()
    render_pdf_preview(OUTPUT_PDF_PATH, TMP_SUBMISSION_RENDER_DIR)
    validate_front_page_alignment(
        get_rendered_preview_page(TMP_SUBMISSION_RENDER_DIR, 1),
        cover_render["placements"],
        cover_render["image_size"],
    )
    if declaration_render is not None:
        validate_declaration_page_alignment(
            get_rendered_preview_page(TMP_SUBMISSION_RENDER_DIR, 2),
            declaration_render["placements"],
            declaration_render["label_boxes"],
            declaration_render["image_size"],
        )
    return OUTPUT_PDF_PATH


def main() -> None:
    source_layout_doc = Document(str(DOC_PATH))
    normalize_chapter_headings(source_layout_doc)
    update_body_content(source_layout_doc)
    replace_formula_tables(source_layout_doc)
    relayout_figures(source_layout_doc)
    normalize_major_breaks(source_layout_doc)

    composed_doc = compose_official_template(source_layout_doc, Document(str(DOC_PATH)))
    normalize_reference_entries(composed_doc)
    format_data_tables(composed_doc)
    configure_headers_and_footers(composed_doc)
    format_paragraphs(composed_doc)
    apply_minor_layout_overrides(composed_doc)
    composed_doc.save(str(DOC_PATH))

    pdf_path = export_submission_artifacts(DOC_PATH)
    toc_pages = compute_toc_pages_from_pdf(pdf_path)
    rebuild_toc(composed_doc, toc_pages)
    format_paragraphs(composed_doc)
    apply_minor_layout_overrides(composed_doc)
    composed_doc.save(str(DOC_PATH))

    pdf_path = export_submission_artifacts(DOC_PATH)
    verified_toc_pages = compute_toc_pages_from_pdf(pdf_path)
    if verified_toc_pages != toc_pages:
        rebuild_toc(composed_doc, verified_toc_pages)
        format_paragraphs(composed_doc)
        apply_minor_layout_overrides(composed_doc)
        composed_doc.save(str(DOC_PATH))
        export_submission_artifacts(DOC_PATH)


if __name__ == "__main__":
    main()
