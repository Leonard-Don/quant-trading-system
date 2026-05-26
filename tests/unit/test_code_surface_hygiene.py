from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ORPHAN_ANALYTICS_MODULES = (
    Path('src/analytics/structural_decay.py'),
    Path('src/analytics/macro_mispricing_thesis.py'),
)


def _tracked_python_files(root: Path = PROJECT_ROOT) -> list[Path]:
    return [path for path in root.rglob('*.py') if '.venv' not in path.parts and 'venv' not in path.parts]


def _prod_python_files(root: Path = PROJECT_ROOT) -> list[Path]:
    return [
        path
        for path in _tracked_python_files(root)
        if 'tests' not in path.relative_to(root).parts
    ]


def _has_production_import(module_path: Path) -> bool:
    module_name = module_path.with_suffix('').as_posix().replace('/', '.')
    package_import = module_name
    relative_import = f".{module_path.stem}"
    for path in _prod_python_files():
        if path.relative_to(PROJECT_ROOT) == module_path:
            continue
        text = path.read_text(encoding='utf-8')
        if f"import {package_import}" in text or f"from {package_import} import" in text:
            return True
        if f"from {relative_import} import" in text:
            return True
    return False


def test_pricing_research_analytics_modules_are_not_orphaned():
    for module_path in ORPHAN_ANALYTICS_MODULES:
        path = PROJECT_ROOT / module_path
        assert not path.exists() or _has_production_import(module_path), module_path


def test_production_test_only_helpers_are_exercised_by_tests():
    test_text = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in _tracked_python_files()
        if 'tests' in path.relative_to(PROJECT_ROOT).parts
    )
    offenders: list[str] = []
    for path in _prod_python_files():
        rel_path = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in tree.body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.endswith('_for_tests')
                and node.name not in test_text
            ):
                offenders.append(f'{rel_path}:{node.lineno}:{node.name}')
    assert offenders == []
