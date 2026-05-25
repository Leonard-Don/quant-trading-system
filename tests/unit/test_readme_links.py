from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"

MARKDOWN_LINK_RE = re.compile(
    r"!?\[(?:[^\[\]\n]|\[[^\]\n]*\])*\]"
    r"\(([^)\s]+)(?:\s+\"[^\"]*\")?\)"
)
IMAGE_LINK_RE = re.compile(r"!\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_LINK_RE = re.compile(r"\b(?:href|src)=[\"']([^\"']+)[\"']")


def _is_local_reference(target: str) -> bool:
    return not target.startswith(("#", "mailto:", "tel:", "data:")) and "://" not in target


def _normalize_local_path(target: str) -> str:
    path = target.split("#", 1)[0].split("?", 1)[0]
    return unquote(path.removeprefix("./"))


def _is_repo_path(path: Path) -> bool:
    return path.is_relative_to(REPO_ROOT.resolve())


def test_readme_local_links_resolve_to_repo_paths() -> None:
    """Keep GitHub landing-page links from drifting after file moves."""
    text = README.read_text(encoding="utf-8")
    broken: list[str] = []
    seen: set[tuple[int, str]] = set()

    for pattern in (MARKDOWN_LINK_RE, IMAGE_LINK_RE, HTML_LINK_RE):
        for match in pattern.finditer(text):
            target = match.group(1).strip()
            key = (match.start(), target)
            if key in seen:
                continue
            seen.add(key)
            if not _is_local_reference(target):
                continue
            path = _normalize_local_path(target)
            if not path:
                continue
            candidate = (REPO_ROOT / path).resolve(strict=False)
            if not _is_repo_path(candidate) or not candidate.exists():
                line = text.count("\n", 0, match.start()) + 1
                broken.append(f"line {line}: {target}")

    assert broken == []
