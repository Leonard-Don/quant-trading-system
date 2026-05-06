#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "== backend lint =="
python3 -m ruff check backend/app backend/tests

echo
echo "== backend tests =="
python3 -m pytest tests/unit tests/integration backend/tests -q

if [[ "${1:-}" == "--live" ]]; then
    echo
    echo "== live backend probes =="
    python3 - <<'PY'
import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

BASE_URL = "http://127.0.0.1:8000"
PATHS = [
    "/health",
    "/openapi.json",
    "/strategies",
    "/system/status",
    "/realtime/summary",
    "/realtime/quotes?symbols=%5EGSPC,%5EHSI,AAPL",
    "/industry/health",
    "/industry/bootstrap",
    "/backtest/history/stats",
    "/research-journal/snapshot?profile_id=backend-quality",
    "/infrastructure/status",
]
OPENER = build_opener(ProxyHandler({}))


def fetch(path: str) -> tuple[int, int]:
    with OPENER.open(f"{BASE_URL}{path}", timeout=15) as response:
        body = response.read()
        return response.status, len(body)


results = {}
for path in PATHS:
    try:
        status, size = fetch(path)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SystemExit(f"{path}: FAILED {exc}") from exc
    if status >= 400 or size <= 0:
        raise SystemExit(f"{path}: unexpected status={status} size={size}")
    results[path] = {"status": status, "bytes": size}

print(json.dumps(results, indent=2, ensure_ascii=False))
PY
fi
