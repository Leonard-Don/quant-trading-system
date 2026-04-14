#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$LOG_DIR/celery-worker.pid"

process_alive() {
    local pid="$1"
    kill -0 "$pid" >/dev/null 2>&1
}

graceful_stop_pid() {
    local pid="$1"
    if ! process_alive "$pid"; then
        return 0
    fi
    kill "$pid" >/dev/null 2>&1 || true
    for _ in $(seq 1 10); do
        if ! process_alive "$pid"; then
            return 0
        fi
        sleep 1
    done
    kill -9 "$pid" >/dev/null 2>&1 || true
}

echo "🛑 正在停止 Celery worker..."

if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$PID" ]]; then
        graceful_stop_pid "$PID"
        echo "✅ Celery worker 已停止 (PID: $PID)"
    fi
    rm -f "$PID_FILE"
else
    echo "⚠️  未找到 worker pid 文件，尝试按命令模式清理..."
fi

pkill -f "python3 -m celery -A backend.app.core.task_queue:celery_app worker" 2>/dev/null || true
pkill -f "celery -A backend.app.core.task_queue:celery_app worker" 2>/dev/null || true

echo "🏁 Celery worker 停止流程完成"
