#!/usr/bin/env python3
"""
同步项目统一版本号到前端元数据。
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PROJECT_ROOT / "VERSION"
FRONTEND_PACKAGE_FILE = PROJECT_ROOT / "frontend" / "package.json"
FRONTEND_VERSION_MODULE = PROJECT_ROOT / "frontend" / "src" / "generated" / "version.js"


def read_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError("VERSION 文件为空")
    return version


def sync_frontend_package(version: str) -> bool:
    package = json.loads(FRONTEND_PACKAGE_FILE.read_text(encoding="utf-8"))
    changed = package.get("version") != version
    package["version"] = version
    FRONTEND_PACKAGE_FILE.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return changed


def sync_frontend_version_module(version: str) -> bool:
    content = f"export const APP_VERSION = '{version}';\n"
    changed = (
        not FRONTEND_VERSION_MODULE.exists()
        or FRONTEND_VERSION_MODULE.read_text(encoding="utf-8") != content
    )
    FRONTEND_VERSION_MODULE.parent.mkdir(parents=True, exist_ok=True)
    FRONTEND_VERSION_MODULE.write_text(content, encoding="utf-8")
    return changed


def main() -> int:
    version = read_version()
    package_changed = sync_frontend_package(version)
    module_changed = sync_frontend_version_module(version)

    if package_changed or module_changed:
        print(f"已同步版本号到前端元数据: {version}")
    else:
        print(f"版本号已是最新: {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
