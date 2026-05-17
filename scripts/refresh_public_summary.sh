#!/usr/bin/env bash
# Thin shell wrapper around scripts/export_public_summary.py.
#
# Drop-in convenience for cron / ops runbooks so the maintenance guide can
# refer to a single command name rather than the long python invocation.
# Activates the project's .venv when present (so the script doesn't depend
# on the operator's shell init having done it), then runs the exporter
# and writes the result to data/public/quant_summary.json.
#
# Usage:
#   ./scripts/refresh_public_summary.sh                  # write the file
#   ./scripts/refresh_public_summary.sh --print          # stdout instead
#
# Recommended cron (see docs/MAINTENANCE_GUIDE.md):
#   0 * * * * cd /opt/quant && ./scripts/refresh_public_summary.sh \
#       >> logs/export_public_summary.log 2>&1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Activate the project's venv if one exists. Don't fail if it doesn't —
# the operator may be running inside a system Python on a server.
if [[ -f "${PROJECT_ROOT}/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.venv/bin/activate"
fi

cd "${PROJECT_ROOT}"
exec python scripts/export_public_summary.py "$@"
