"""Regression tests for the appendix-booklet TOC page-number contract.

The appendix booklet (``附录材料（另册）``) is the trailing toc-1 entry but
must remain unnumbered: the booklet lives in a separate volume, so its
title is not searchable inside the body PDF and its TOC line must omit the
trailing ``\\t<page>`` suffix that every other entry carries.

Two pieces of ``scripts/finalize_shu_thesis_docx.py`` cooperate to enforce
this:

1. ``write_toc_entry`` writes only the bare title — no tab, no page — when
   the resolved ``page`` argument is falsy. Without that branch the
   appendix line would still gain a stray trailing tab even though no page
   is known.
2. ``compute_toc_pages_from_pdf`` pre-seeds the page-number dictionary
   only with the Roman-numeral front-matter entries (``摘  要`` /
   ``ABSTRACT``). The appendix booklet is never pre-seeded, so when the
   body-PDF text search inevitably misses it the appendix falls through to
   the ``""`` default in ``rebuild_toc``'s ``resolved_pages.get(title, "")``.

Both halves are pinned here via AST extraction: the finalizer script does
``resolve_existing_path`` work at import time and is unsafe to import in
unit tests. The structural blueprint guard in
``test_thesis_toc_blueprint.py`` and the caption-regex guard in
``test_thesis_caption_rules.py`` cover orthogonal concerns and are not
duplicated here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

THESIS_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "finalize_shu_thesis_docx.py"
)
APPENDIX_BOOKLET_TITLE = "附录材料（另册）"


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(
        f"Function {name!r} not found at module level in finalize_shu_thesis_docx.py"
    )


def _find_assignment(func: ast.FunctionDef, target_name: str) -> ast.Assign:
    matches: list[ast.Assign] = []
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == target_name
        ):
            matches.append(node)
    if not matches:
        raise AssertionError(
            f"Assignment to {target_name!r} not found in {func.name}"
        )
    if len(matches) > 1:
        raise AssertionError(
            f"Multiple assignments to {target_name!r} in {func.name}; "
            f"this guard expects exactly one"
        )
    return matches[0]


@pytest.fixture(scope="module")
def thesis_tree() -> ast.Module:
    return ast.parse(THESIS_SCRIPT.read_text(encoding="utf-8"))


def test_write_toc_entry_drops_page_suffix_when_page_is_empty(
    thesis_tree: ast.Module,
) -> None:
    """When ``page`` is empty the entry text must equal the bare title.

    The appendix booklet always reaches ``write_toc_entry`` with
    ``page=""`` (it is never pre-seeded and never matched in the body
    PDF), so this branch is what keeps the rendered TOC line clean.
    Non-empty pages must still carry the ``\\t<page>`` suffix.
    """
    func = _find_function(thesis_tree, "write_toc_entry")
    assign = _find_assignment(func, "entry_text")

    value = assign.value
    assert isinstance(value, ast.IfExp), (
        "entry_text must use a conditional expression so empty page values "
        "render as the bare title"
    )
    assert isinstance(value.test, ast.Name) and value.test.id == "page", (
        "entry_text must branch on the truthiness of page"
    )
    assert isinstance(value.orelse, ast.Name) and value.orelse.id == "title", (
        "empty page values must render as the bare title, not a tab suffix"
    )
    assert isinstance(value.body, ast.JoinedStr), (
        "numbered TOC entries must be formatted from title, tab, and page"
    )
    formatted_parts = value.body.values
    assert len(formatted_parts) == 3, (
        "numbered TOC entry format must be exactly title + tab + page"
    )
    assert isinstance(formatted_parts[0], ast.FormattedValue) and isinstance(
        formatted_parts[0].value, ast.Name
    ) and formatted_parts[0].value.id == "title"
    assert isinstance(formatted_parts[1], ast.Constant) and formatted_parts[1].value == "\t"
    assert isinstance(formatted_parts[2], ast.FormattedValue) and isinstance(
        formatted_parts[2].value, ast.Name
    ) and formatted_parts[2].value.id == "page"


def test_compute_toc_pages_seed_excludes_appendix_booklet(
    thesis_tree: ast.Module,
) -> None:
    """The fixed page-number seed must not contain the appendix booklet.

    Pre-seeding the booklet would override the empty-string fallback in
    ``rebuild_toc`` and cause the booklet line to render with a spurious
    page number. Only the Roman-numeral front matter belongs in the seed.
    """
    func = _find_function(thesis_tree, "compute_toc_pages_from_pdf")
    seed = _find_assignment(func, "toc_pages")
    assert isinstance(seed.value, ast.Dict), (
        "Initial toc_pages assignment must be a dict literal"
    )

    seeded_keys: list[str] = []
    for key in seed.value.keys:
        assert isinstance(key, ast.Constant) and isinstance(key.value, str), (
            "toc_pages seed dict must use string-literal keys"
        )
        seeded_keys.append(key.value)

    assert APPENDIX_BOOKLET_TITLE not in seeded_keys, (
        f"Appendix booklet must not be pre-seeded with a page number; "
        f"seeded keys: {seeded_keys!r}"
    )
    assert set(seeded_keys) == {"摘  要", "ABSTRACT"}, (
        f"Only the Roman-numeral front matter should be pre-seeded, "
        f"got {seeded_keys!r}"
    )
