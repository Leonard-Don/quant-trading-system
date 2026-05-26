from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from backend.app.api.v1.route_surface_registry import ROUTE_SURFACE_REGISTRY

ROOT = Path(__file__).resolve().parents[2]
API_MODULE = ROOT / "backend/app/api/v1/api.py"
ENDPOINTS_DIR = ROOT / "backend/app/api/v1/endpoints"
FRONTEND_SRC = ROOT / "frontend/src"

HTTP_METHODS = {"get", "post", "put", "delete", "patch"}
ALLOWED_STATUSES = {"frontend_entry", "deprecated_compat", "api_only", "internal_support"}


def _literal(node: ast.AST, default: Any = None) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return default


def _router_prefixes() -> dict[str, str]:
    tree = ast.parse(API_MODULE.read_text(encoding="utf-8"))
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "include_router":
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if not (isinstance(first_arg, ast.Attribute) and first_arg.attr == "router"):
            continue
        if not isinstance(first_arg.value, ast.Name):
            continue
        module_name = first_arg.value.id
        prefix = ""
        for keyword in node.keywords:
            if keyword.arg == "prefix":
                prefix = str(_literal(keyword.value, ""))
        prefixes[module_name] = prefix
    return prefixes


def _routes() -> list[dict[str, Any]]:
    prefixes = _router_prefixes()
    routes: list[dict[str, Any]] = []
    for endpoint in sorted(ENDPOINTS_DIR.glob("*.py")):
        module_name = endpoint.stem
        if module_name == "__init__":
            continue
        tree = ast.parse(endpoint.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr.lower()
                if method not in HTTP_METHODS:
                    continue
                path = str(_literal(decorator.args[0], "")) if decorator.args else ""
                deprecated = False
                for keyword in decorator.keywords:
                    if keyword.arg == "deprecated":
                        deprecated = bool(_literal(keyword.value, False))
                full_path = f"{prefixes.get(module_name, '')}{path}".replace("//", "/")
                routes.append(
                    {
                        "key": f"{method.upper()} {full_path}",
                        "path": full_path,
                        "deprecated": deprecated,
                    }
                )
    return routes


def _frontend_text() -> str:
    chunks: list[str] = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        if "__tests__" in path.parts or path.name.endswith((".test.js", ".test.jsx", ".spec.js", ".spec.jsx")):
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def _route_has_frontend_entry(route: dict[str, Any], frontend_text: str) -> bool:
    path = route["path"]
    static_prefix = path.split("{")[0].rstrip("/")
    candidates = {path, static_prefix}
    return any(candidate and candidate in frontend_text for candidate in candidates)


def test_public_backend_routes_without_frontend_entry_are_classified():
    frontend_text = _frontend_text()
    orphan_route_keys = {
        route["key"]
        for route in _routes()
        if not _route_has_frontend_entry(route, frontend_text)
    }

    assert orphan_route_keys <= set(ROUTE_SURFACE_REGISTRY)

    for route_key in orphan_route_keys:
        row = ROUTE_SURFACE_REGISTRY[route_key]
        assert row["status"] in ALLOWED_STATUSES
        assert row["owner"]
        assert row["entry_strategy"]
        assert row["removal_condition"]


def test_deprecated_routes_have_compatibility_exit_plan():
    frontend_text = _frontend_text()
    deprecated_without_frontend = {
        route["key"]
        for route in _routes()
        if route["deprecated"] and not _route_has_frontend_entry(route, frontend_text)
    }

    assert deprecated_without_frontend
    for route_key in deprecated_without_frontend:
        row = ROUTE_SURFACE_REGISTRY[route_key]
        assert row["status"] == "deprecated_compat"
        assert row["removal_condition"] != "keep indefinitely"


def test_route_surface_registry_has_no_stale_entries():
    route_keys = {route["key"] for route in _routes()}
    assert set(ROUTE_SURFACE_REGISTRY) <= route_keys


def test_etf_advanced_engines_now_have_frontend_service_entries():
    frontend_text = _frontend_text()
    assert "postEtfRotationBacktest" in frontend_text
    assert "postEtfRotationStrategyComparison" in frontend_text
    assert "postEtfRotationOptimizeParameters" in frontend_text
    assert "POST /etf-rotation/backtest" not in ROUTE_SURFACE_REGISTRY
    assert "POST /etf-rotation/strategy-comparison" not in ROUTE_SURFACE_REGISTRY
    assert "POST /etf-rotation/optimize-parameters" not in ROUTE_SURFACE_REGISTRY
