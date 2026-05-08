"""Regression guard pinning the ``rebuild_toc`` → ``write_toc_entry`` wiring.

``rebuild_toc`` in ``scripts/finalize_shu_thesis_docx.py`` is responsible
for emitting one TOC paragraph per ``TOC_BLUEPRINT`` entry. Each
``(style_name, title)`` pair must be routed through ``write_toc_entry``
so that styling, font, line-spacing, and the empty-page fallback remain
in a single helper. A refactor that hardcodes a style, swaps the
argument order, calls a different helper, or iterates a sliced/reversed
copy of the blueprint silently regresses the rendered TOC (e.g. all
entries lose the ``toc 2`` indent, or the appendix booklet line gains a
spurious page number).

This guard pins the wiring via AST extraction. It is deliberately
orthogonal to the existing thesis test suite:

* ``test_thesis_toc_blueprint.py`` — structural contract on
  ``TOC_BLUEPRINT`` itself (uniqueness, ordering, allowed styles,
  appendix-booklet trailing position).
* ``test_thesis_toc_appendix_pages.py`` — the conditional in
  ``write_toc_entry`` that drops the page suffix for the booklet and the
  page-number seed dict that excludes it.
* ``test_thesis_caption_rules.py`` — figure/table caption regexes.

The finalizer script does ``resolve_existing_path`` work at import time
and is unsafe to import in unit tests, so the function bodies are
parsed via ``ast`` instead. No ``eval``/``exec`` is used.
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


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(
        f"Function {name!r} not found at module level in finalize_shu_thesis_docx.py"
    )


def _blueprint_for_loops(func: ast.FunctionDef) -> list[ast.For]:
    """Return every ``for ... in TOC_BLUEPRINT:`` *statement* inside ``func``.

    Comprehensions (e.g. ``{title: "" for _, title in TOC_BLUEPRINT}``)
    are intentionally excluded — they iterate the blueprint to derive
    the empty-page fallback dict and are not the rendering loop.
    """
    return [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Name)
        and node.iter.id == "TOC_BLUEPRINT"
    ]


def _write_toc_entry_calls(scope: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(scope)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "write_toc_entry"
    ]


@pytest.fixture(scope="module")
def thesis_tree() -> ast.Module:
    return ast.parse(THESIS_SCRIPT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rebuild_toc_func(thesis_tree: ast.Module) -> ast.FunctionDef:
    return _find_function(thesis_tree, "rebuild_toc")


def test_rebuild_toc_iterates_toc_blueprint_with_style_and_title_unpacking(
    rebuild_toc_func: ast.FunctionDef,
) -> None:
    """``rebuild_toc`` must iterate ``TOC_BLUEPRINT`` directly, exactly
    once at the statement level, unpacking into ``(style_name, title)``.

    Iterating a sliced/reversed copy or unpacking in the wrong order
    would silently rewrite the TOC with wrong styles or missing entries.
    """
    loops = _blueprint_for_loops(rebuild_toc_func)
    assert len(loops) == 1, (
        f"rebuild_toc must contain exactly one `for ... in TOC_BLUEPRINT:` "
        f"statement; found {len(loops)}"
    )
    loop = loops[0]

    assert isinstance(loop.target, ast.Tuple) and len(loop.target.elts) == 2, (
        "TOC_BLUEPRINT loop must unpack each entry into a 2-name tuple "
        "(style_name, title)"
    )
    target_names = [
        elt.id if isinstance(elt, ast.Name) else None for elt in loop.target.elts
    ]
    assert target_names == ["style_name", "title"], (
        f"TOC_BLUEPRINT loop must unpack into (style_name, title); "
        f"got {target_names!r}"
    )


def test_rebuild_toc_calls_write_toc_entry_once_per_blueprint_entry(
    rebuild_toc_func: ast.FunctionDef,
) -> None:
    """Inside the blueprint loop, ``write_toc_entry`` must be called
    exactly once with the loop variables ``style_name`` (positional 2)
    and ``title`` (positional 3).

    A literal style or title here would erase the toc-1/toc-2 distinction
    or pin every entry to the same heading.
    """
    loops = _blueprint_for_loops(rebuild_toc_func)
    assert len(loops) == 1
    loop = loops[0]

    calls = _write_toc_entry_calls(loop)
    assert len(calls) == 1, (
        f"TOC_BLUEPRINT loop must call write_toc_entry exactly once; "
        f"got {len(calls)}"
    )
    call = calls[0]

    assert not call.keywords, (
        "write_toc_entry call must use positional arguments only; the wiring "
        "guard checks positional indexes 1 and 2"
    )
    assert len(call.args) == 4, (
        f"write_toc_entry must receive 4 positional args (paragraph, "
        f"style_name, title, page); got {len(call.args)}"
    )

    style_arg = call.args[1]
    title_arg = call.args[2]
    assert isinstance(style_arg, ast.Name) and style_arg.id == "style_name", (
        "write_toc_entry's 2nd positional arg must be the loop's style_name "
        "variable, not a literal or a different name"
    )
    assert isinstance(title_arg, ast.Name) and title_arg.id == "title", (
        "write_toc_entry's 3rd positional arg must be the loop's title "
        "variable, not a literal or a different name"
    )


def test_rebuild_toc_has_no_write_toc_entry_calls_outside_blueprint_loop(
    rebuild_toc_func: ast.FunctionDef,
) -> None:
    """Every ``write_toc_entry`` call inside ``rebuild_toc`` must live
    inside the ``TOC_BLUEPRINT`` loop — no out-of-band TOC writes that
    would bypass the blueprint.
    """
    loops = _blueprint_for_loops(rebuild_toc_func)
    in_loop_call_ids: set[int] = set()
    for loop in loops:
        for call in _write_toc_entry_calls(loop):
            in_loop_call_ids.add(id(call))

    all_calls = _write_toc_entry_calls(rebuild_toc_func)
    out_of_loop = [c for c in all_calls if id(c) not in in_loop_call_ids]
    assert not out_of_loop, (
        f"write_toc_entry must only be called inside the TOC_BLUEPRINT "
        f"loop in rebuild_toc; found {len(out_of_loop)} call(s) outside it"
    )
