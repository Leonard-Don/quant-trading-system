#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.quant-infra.yml"
REMOVE_VOLUMES=0
COMPOSE_CMD=()

usage() {
    cat <<'EOF'
用法: ./scripts/stop_infra_stack.sh [--remove-volumes] [--help]

选项:
  --remove-volumes  停止容器时同时删除 Timescale / Redis 数据卷
  --help            显示帮助
EOF
}

resolve_compose_command() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD=(docker compose)
        return 0
    fi
    if command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD=(docker-compose)
        return 0
    fi
    return 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --remove-volumes)
            REMOVE_VOLUMES=1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1" >&2
            usage
            exit 1
            ;;
    esac
    shift
done

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "⚠️  未找到 compose 文件，跳过 infra stack 停止" >&2
    exit 0
fi

if ! resolve_compose_command; then
    echo "❌ 未检测到 docker compose，无法停止 infra stack" >&2
    exit 1
fi

echo "🛑 正在停止本地基础设施栈..."
if [[ "$REMOVE_VOLUMES" -eq 1 ]]; then
    "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" down --remove-orphans --volumes
else
    "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" down --remove-orphans
fi
echo "✅ 本地 infra stack 已停止"
