"""Regression tests for the thesis TOC blueprint structure.

The TOC blueprint in ``scripts/finalize_shu_thesis_docx.py`` drives the
generated table-of-contents entries. A recent change appended an appendix
booklet entry (``附录材料（另册）``) that has no page number, and this list
must remain structurally consistent: numbered sub-sections (``X.Y``) must
follow a chapter header with the matching prefix, no title may appear
twice, and the appendix booklet must remain the trailing toc-1 entry.

The blueprint is extracted via AST (rather than imported) because the
script performs path resolution at import time that is unsuitable for unit
tests. This file pins the structural contract independently of the caption
regex rules already covered by ``test_thesis_caption_rules.py``.
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

APPENDIX_BOOKLET_TITLE = "附录材料（另册）"


def _extract_toc_blueprint() -> list[tuple[str, str]]:
    tree = ast.parse(THESIS_SCRIPT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        if node.targets[0].id != "TOC_BLUEPRINT":
            continue
        if not isinstance(node.value, ast.List):
            continue
        entries: list[tuple[str, str]] = []
        for element in node.value.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
                raise AssertionError("TOC_BLUEPRINT entry is not a 2-tuple literal")
            style_node, title_node = element.elts
            if not (
                isinstance(style_node, ast.Constant)
                and isinstance(style_node.value, str)
                and isinstance(title_node, ast.Constant)
                and isinstance(title_node.value, str)
            ):
                raise AssertionError("TOC_BLUEPRINT entries must be string literals")
            entries.append((style_node.value, title_node.value))
        return entries
    raise AssertionError("TOC_BLUEPRINT assignment not found in finalize_shu_thesis_docx.py")


@pytest.fixture(scope="module")
def toc_blueprint() -> list[tuple[str, str]]:
    entries = _extract_toc_blueprint()
    assert entries, "TOC_BLUEPRINT must not be empty"
    return entries


def test_toc_styles_are_only_toc1_or_toc2(
    toc_blueprint: list[tuple[str, str]],
) -> None:
    allowed = {"toc 1", "toc 2"}
    bad = sorted({style for style, _ in toc_blueprint} - allowed)
    assert not bad, f"Unexpected TOC styles in blueprint: {bad}"


def test_toc_titles_are_unique(toc_blueprint: list[tuple[str, str]]) -> None:
    titles = [title for _, title in toc_blueprint]
    duplicates = sorted({t for t in titles if titles.count(t) > 1})
    assert not duplicates, f"Duplicate TOC titles: {duplicates}"


def test_toc_titles_have_no_leading_or_trailing_whitespace(
    toc_blueprint: list[tuple[str, str]],
) -> None:
    offenders = [title for _, title in toc_blueprint if title != title.strip()]
    assert not offenders, f"TOC titles with stray whitespace: {offenders}"


def test_appendix_booklet_is_last_toc1_entry(
    toc_blueprint: list[tuple[str, str]],
) -> None:
    last_style, last_title = toc_blueprint[-1]
    assert last_title == APPENDIX_BOOKLET_TITLE, (
        f"Last TOC entry must be the appendix booklet, got {last_title!r}"
    )
    assert last_style == "toc 1", (
        f"Appendix booklet must use toc 1 style, got {last_style!r}"
    )


def test_each_toc2_section_follows_matching_toc1_chapter(
    toc_blueprint: list[tuple[str, str]],
) -> None:
    """A ``X.Y …`` sub-section must be preceded (without intervening other
    chapter) by a ``X …`` toc-1 chapter heading with the same chapter
    prefix. This catches typos like a ``5.7`` orphaned under chapter 6.
    """
    section_pattern = re.compile(r"^(\d+)\.\d+\s")
    chapter_pattern = re.compile(r"^(\d+)\s")
    current_chapter: str | None = None
    for style, title in toc_blueprint:
        if style == "toc 1":
            chapter_match = chapter_pattern.match(title)
            current_chapter = chapter_match.group(1) if chapter_match else None
            continue
        # toc 2
        section_match = section_pattern.match(title)
        assert section_match is not None, (
            f"toc 2 entry must start with 'X.Y ': {title!r}"
        )
        chapter_prefix = section_match.group(1)
        assert chapter_prefix == current_chapter, (
            f"Sub-section {title!r} does not belong under current chapter "
            f"{current_chapter!r}"
        )


def test_unnumbered_toc1_back_matter_appears_after_chapters(
    toc_blueprint: list[tuple[str, str]],
) -> None:
    """The unnumbered back-matter entries (结 论 / 参考文献 / 致 谢 /
    appendix booklet) must come after every numbered chapter heading.
    """
    chapter_pattern = re.compile(r"^\d+\s")
    last_numbered_chapter_index = -1
    for index, (style, title) in enumerate(toc_blueprint):
        if style == "toc 1" and chapter_pattern.match(title):
            last_numbered_chapter_index = index
    expected_back_matter = {"结 论", "参考文献", "致 谢", APPENDIX_BOOKLET_TITLE}
    for index, (style, title) in enumerate(toc_blueprint):
        if title in expected_back_matter:
            assert index > last_numbered_chapter_index, (
                f"Back-matter entry {title!r} must follow all numbered chapters"
            )
