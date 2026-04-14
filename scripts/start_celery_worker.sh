#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$LOG_DIR/celery-worker.pid"
LOG_FILE="$LOG_DIR/celery-worker.log"
INFRA_ENV_FILE="$LOG_DIR/infra-stack.env"

LOG_LEVEL="${CELERY_LOGLEVEL:-info}"
CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-1}"
POOL="${CELERY_WORKER_POOL:-solo}"
USE_INFRA_ENV=1

usage() {
    cat <<'EOF'
用法: ./scripts/start_celery_worker.sh [--no-infra-env] [--loglevel LEVEL] [--concurrency N] [--pool NAME] [--help]

选项:
  --no-infra-env     不自动读取 logs/infra-stack.env
  --loglevel LEVEL   Celery 日志级别，默认 info
  --concurrency N    Worker 并发数，默认 1
  --pool NAME        Worker pool，默认 solo（适合本地开发）
  --help             显示帮助
EOF
}

log_info() {
    echo "$1"
}

log_error() {
    echo "$1" >&2
}

process_alive() {
    local pid="$1"
    kill -0 "$pid" >/dev/null 2>&1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-infra-env)
            USE_INFRA_ENV=0
            ;;
        --loglevel)
            LOG_LEVEL="${2:-info}"
            shift
            ;;
        --concurrency)
            CONCURRENCY="${2:-1}"
            shift
            ;;
        --pool)
            POOL="${2:-solo}"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            log_error "❌ 未知参数: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

mkdir -p "$LOG_DIR"

if [[ "$USE_INFRA_ENV" -eq 1 && -f "$INFRA_ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$INFRA_ENV_FILE"
    export DATABASE_URL REDIS_URL CELERY_BROKER_URL CELERY_RESULT_BACKEND
fi

if [[ -f "$PID_FILE" ]]; then
    EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$EXISTING_PID" ]] && process_alive "$EXISTING_PID"; then
        log_info "✅ Celery worker 已在运行 (PID: $EXISTING_PID)"
        log_info "   - 日志文件: $LOG_FILE"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

if [[ -z "${CELERY_BROKER_URL:-}" ]]; then
    log_error "❌ 未配置 CELERY_BROKER_URL。可先运行 ./scripts/start_infra_stack.sh 或导出 broker 环境变量。"
    exit 1
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import celery  # noqa: F401
PY
then
    log_error "❌ 当前 Python 环境未安装 celery。请先运行 ./scripts/start_system.sh --install"
    exit 1
fi

log_info "🧵 启动 Celery worker..."
log_info "   - Broker: ${CELERY_BROKER_URL}"
log_info "   - Pool: ${POOL}"
log_info "   - Concurrency: ${CONCURRENCY}"

(
    cd "$PROJECT_ROOT"
    PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}" \
    nohup python3 -m celery -A backend.app.core.task_queue:celery_app worker \
        --loglevel="$LOG_LEVEL" \
        --concurrency="$CONCURRENCY" \
        --pool="$POOL" \
        >"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
)

sleep 3
WORKER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "$WORKER_PID" ]] || ! process_alive "$WORKER_PID"; then
    log_error "❌ Celery worker 启动失败，请查看日志: $LOG_FILE"
    exit 1
fi

log_info "✅ Celery worker 已启动 (PID: $WORKER_PID)"
log_info "   - 日志文件: $LOG_FILE"
log_info "   - 停止命令: ./scripts/stop_celery_worker.sh"
