#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"
WITH_INFRA=0
REMOVE_INFRA_VOLUMES=0
WITH_WORKER=0

usage() {
    cat <<'EOF'
用法: ./scripts/stop_system.sh [--with-infra] [--with-worker] [--remove-infra-volumes] [--help]

选项:
  --with-infra           停止前后端后，同时停止本地 TimescaleDB + Redis 容器
  --with-worker          停止本地 Celery worker
  --remove-infra-volumes 与 --with-infra 搭配使用，额外删除容器数据卷
  --help                 显示帮助
EOF
}

process_alive() {
    local pid="$1"
    kill -0 "$pid" >/dev/null 2>&1
}

process_command() {
    local pid="$1"
    ps -p "$pid" -o command= 2>/dev/null || true
}

process_cwd() {
    local pid="$1"
    if ! command -v lsof >/dev/null 2>&1; then
        return 0
    fi
    lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | awk 'BEGIN { FS="n" } /^n/ { print $2; exit }'
}

is_project_managed_process() {
    local pid="$1"
    local command
    local cwd
    command="$(process_command "$pid")"
    cwd="$(process_cwd "$pid")"
    [[ -n "$command" && ( "$command" == *"$PROJECT_ROOT/"* || "$command" == *"$FRONTEND_DIR/"* || "$command" == *"scripts/start_backend.py"* ) ]] || \
        [[ -n "$cwd" && ( "$cwd" == "$PROJECT_ROOT" || "$cwd" == "$FRONTEND_DIR" ) ]]
}

graceful_stop_pid() {
    local pid="$1"
    local label="$2"

    if ! process_alive "$pid"; then
        echo "⚠️  $label 已经停止"
        return 0
    fi

    kill "$pid" >/dev/null 2>&1 || true
    for _ in $(seq 1 10); do
        if ! process_alive "$pid"; then
            echo "✅ $label 已停止 (PID: $pid)"
            return 0
        fi
        sleep 1
    done

    echo "⚠️  $label 未及时退出，执行强制停止..."
    kill -9 "$pid" >/dev/null 2>&1 || true
    echo "✅ $label 已强制停止 (PID: $pid)"
}

stop_from_pid_file() {
    local pid_file="$1"
    local label="$2"

    if [[ ! -f "$pid_file" ]]; then
        return 0
    fi

    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
        graceful_stop_pid "$pid" "$label"
    fi
    rm -f "$pid_file"
}

stop_project_listeners_on_port() {
    local port="$1"
    local label="$2"
    local pids=""

    if ! command -v lsof >/dev/null 2>&1; then
        return 0
    fi

    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    while IFS= read -r pid; do
        [[ -n "$pid" ]] || continue
        if is_project_managed_process "$pid"; then
            graceful_stop_pid "$pid" "$label"
        fi
    done <<< "$pids"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-infra)
            WITH_INFRA=1
            ;;
        --with-worker)
            WITH_WORKER=1
            ;;
        --remove-infra-volumes)
            REMOVE_INFRA_VOLUMES=1
            WITH_INFRA=1
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

echo "🛑 正在停止量化交易系统..."

mkdir -p "$LOG_DIR"
stop_from_pid_file "$BACKEND_PID_FILE" "后端服务"
stop_from_pid_file "$FRONTEND_PID_FILE" "前端服务"
stop_project_listeners_on_port 8000 "后端服务"
stop_project_listeners_on_port 3000 "前端服务"

pkill -f "$PROJECT_ROOT/scripts/start_backend.py" 2>/dev/null || true
pkill -f "scripts/start_backend.py" 2>/dev/null || true
pkill -f "uvicorn.*backend.main:app" 2>/dev/null || true
pkill -f "react-scripts start" 2>/dev/null || true
pkill -f "node.*react-scripts" 2>/dev/null || true

if [[ "$WITH_WORKER" -eq 1 ]]; then
    "$PROJECT_ROOT/scripts/stop_celery_worker.sh"
fi

if [[ "$WITH_INFRA" -eq 1 ]]; then
    if [[ "$REMOVE_INFRA_VOLUMES" -eq 1 ]]; then
        "$PROJECT_ROOT/scripts/stop_infra_stack.sh" --remove-volumes
    else
        "$PROJECT_ROOT/scripts/stop_infra_stack.sh"
    fi
fi

echo "🏁 系统已完全停止"
