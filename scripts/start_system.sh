#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

BACKEND_HOST="${BACKEND_HOST:-localhost}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-localhost}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
INFRA_ENV_FILE="$LOG_DIR/infra-stack.env"
WORKER_PID_FILE="$LOG_DIR/celery-worker.pid"

INSTALL_DEPS=0
FORCE_PORT_CLEANUP=0
WITH_INFRA=0
BOOTSTRAP_PERSISTENCE=0
WITH_WORKER=0

BACKEND_PID=""
FRONTEND_PID=""
WORKER_PID=""
STARTED_BACKEND=0
STARTED_FRONTEND=0
STARTED_WORKER=0
BACKEND_HEALTH_FAILURES=0
BACKEND_HEALTH_FAILURE_THRESHOLD=3

usage() {
    cat <<'EOF'
用法: ./scripts/start_system.sh [--install] [--force-port-cleanup] [--with-infra] [--with-worker] [--bootstrap-persistence] [--help]

选项:
  --install             启动前安装/校验依赖（Python requirements + 前端依赖）
  --force-port-cleanup  如果 3000/8000 被占用，强制结束占用进程
  --with-infra          启动本地 TimescaleDB + Redis 基础设施栈
  --with-worker         启动本地 Celery worker（需要已配置 broker）
  --bootstrap-persistence  配合 --with-infra 使用，自动初始化 PostgreSQL / TimescaleDB schema
  --help                显示帮助
EOF
}

log_info() {
    echo "$1"
}

log_error() {
    echo "$1" >&2
}

require_command() {
    local cmd="$1"
    local hint="$2"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log_error "❌ 未找到命令: ${cmd}。${hint}"
        exit 1
    fi
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
        return 0
    fi

    kill "$pid" >/dev/null 2>&1 || true
    for _ in $(seq 1 10); do
        if ! process_alive "$pid"; then
            return 0
        fi
        sleep 1
    done

    log_info "⚠️  $label 未在预期时间内退出，执行强制停止..."
    kill -9 "$pid" >/dev/null 2>&1 || true
}

cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM

    if [[ "$STARTED_FRONTEND" -eq 1 && -n "$FRONTEND_PID" ]]; then
        graceful_stop_pid "$FRONTEND_PID" "前端服务"
    fi

    if [[ "$STARTED_WORKER" -eq 1 ]]; then
        "$PROJECT_ROOT/scripts/stop_celery_worker.sh" >/dev/null 2>&1 || true
    fi

    if [[ "$STARTED_BACKEND" -eq 1 && -n "$BACKEND_PID" ]]; then
        graceful_stop_pid "$BACKEND_PID" "后端服务"
    fi

    rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"

    if [[ $exit_code -eq 0 ]]; then
        log_info "✅ 系统已停止"
    fi
    exit "$exit_code"
}

wait_for_url() {
    local url="$1"
    local label="$2"
    local timeout_seconds="$3"

    for _ in $(seq 1 "$timeout_seconds"); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done

    log_error "❌ $label 在 ${timeout_seconds}s 内未就绪: $url"
    return 1
}

ensure_port_available() {
    local port="$1"
    local label="$2"
    local pid_file="$3"
    local listeners=""

    if ! command -v lsof >/dev/null 2>&1; then
        log_info "⚠️  未安装 lsof，跳过端口占用检查: $port"
        return 0
    fi

    listeners="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -z "$listeners" ]]; then
        log_info "✅ 端口 $port 可用"
        return 0
    fi

    if [[ -f "$pid_file" ]]; then
        local recorded_pid
        recorded_pid="$(cat "$pid_file" 2>/dev/null || true)"
        if [[ -n "$recorded_pid" ]] && echo "$listeners" | tr ' ' '\n' | grep -qx "$recorded_pid"; then
            log_info "⚠️  端口 ${port} 上存在上次启动残留进程 ${recorded_pid}，正在清理..."
            graceful_stop_pid "$recorded_pid" "$label"
            rm -f "$pid_file"
            sleep 1
            listeners="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
            if [[ -z "$listeners" ]]; then
                log_info "✅ 端口 $port 已释放"
                return 0
            fi
        fi
    fi

    local cleaned_project_processes=0
    while IFS= read -r pid; do
        [[ -n "$pid" ]] || continue
        if is_project_managed_process "$pid"; then
            if [[ "$cleaned_project_processes" -eq 0 ]]; then
                log_info "⚠️  端口 $port 上发现本项目残留进程，正在清理..."
                cleaned_project_processes=1
            fi
            graceful_stop_pid "$pid" "$label"
        fi
    done <<< "$listeners"

    if [[ "$cleaned_project_processes" -eq 1 ]]; then
        rm -f "$pid_file"
        sleep 1
        listeners="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
        if [[ -z "$listeners" ]]; then
            log_info "✅ 端口 $port 已释放"
            return 0
        fi
    fi

    if [[ "$FORCE_PORT_CLEANUP" -eq 1 ]]; then
        log_info "⚠️  端口 $port 被占用，执行强制清理: $listeners"
        while IFS= read -r pid; do
            [[ -n "$pid" ]] || continue
            graceful_stop_pid "$pid" "$label"
        done <<< "$listeners"
        sleep 1
        listeners="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
        if [[ -z "$listeners" ]]; then
            log_info "✅ 端口 $port 已释放"
            return 0
        fi
    fi

    log_error "❌ 端口 $port 当前被以下进程占用: $listeners"
    log_error "   如需强制清理，请重新运行并加上 --force-port-cleanup"
    exit 1
}

check_python_runtime_deps() {
    python3 - <<'PY' >/dev/null 2>&1
import fastapi  # noqa: F401
import uvicorn  # noqa: F401
import pydantic  # noqa: F401
PY
}

install_python_deps() {
    local install_log="$LOG_DIR/install-python.log"
    log_info "📦 安装 Python 依赖..."
    if pip3 install -r "$PROJECT_ROOT/requirements.txt" >"$install_log" 2>&1; then
        log_info "✅ Python 依赖安装完成"
    else
        log_error "❌ Python 依赖安装失败，请检查日志: $install_log"
        exit 1
    fi
}

install_frontend_deps() {
    local install_log="$LOG_DIR/install-frontend.log"
    log_info "📦 安装前端依赖..."
    if [[ -f "$FRONTEND_DIR/package-lock.json" ]]; then
        if (
            cd "$FRONTEND_DIR"
            npm ci
        ) >"$install_log" 2>&1; then
            log_info "✅ 前端依赖安装完成"
        else
            log_error "❌ 前端依赖安装失败，请检查日志: $install_log"
            exit 1
        fi
    else
        if (
            cd "$FRONTEND_DIR"
            npm install
        ) >"$install_log" 2>&1; then
            log_info "✅ 前端依赖安装完成"
        else
            log_error "❌ 前端依赖安装失败，请检查日志: $install_log"
            exit 1
        fi
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install)
            INSTALL_DEPS=1
            ;;
        --force-port-cleanup)
            FORCE_PORT_CLEANUP=1
            ;;
        --with-infra)
            WITH_INFRA=1
            ;;
        --with-worker)
            WITH_WORKER=1
            ;;
        --bootstrap-persistence)
            BOOTSTRAP_PERSISTENCE=1
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

cd "$PROJECT_ROOT"
mkdir -p "$LOG_DIR"

trap cleanup EXIT INT TERM

log_info "🚀 正在启动量化交易系统..."
log_info "=================================="

require_command python3 "请先安装 Python3"
require_command pip3 "请先安装 pip3"
require_command node "请先安装 Node.js"
require_command npm "请先安装 npm"
require_command curl "请先安装 curl"

if [[ ! -d "$FRONTEND_DIR" ]]; then
    log_error "❌ frontend 目录不存在: $FRONTEND_DIR"
    exit 1
fi

if [[ ! -f "$PROJECT_ROOT/requirements.txt" ]]; then
    log_error "❌ requirements.txt 不存在: $PROJECT_ROOT/requirements.txt"
    exit 1
fi

if [[ "$INSTALL_DEPS" -eq 1 ]]; then
    install_python_deps
else
    log_info "📦 检查 Python 运行时依赖..."
    if check_python_runtime_deps; then
        log_info "✅ Python 运行时依赖可用"
    else
        log_error "❌ Python 运行时依赖缺失。请先运行: ./scripts/start_system.sh --install"
        exit 1
    fi
fi

if [[ "$INSTALL_DEPS" -eq 1 ]]; then
    install_frontend_deps
elif [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    install_frontend_deps
else
    log_info "✅ 前端依赖已存在"
fi

if [[ "$BOOTSTRAP_PERSISTENCE" -eq 1 && "$WITH_INFRA" -ne 1 ]]; then
    log_error "❌ --bootstrap-persistence 需要与 --with-infra 一起使用"
    exit 1
fi

if [[ "$WITH_INFRA" -eq 1 ]]; then
    log_info "🐳 启动本地基础设施栈..."
    if [[ "$BOOTSTRAP_PERSISTENCE" -eq 1 ]]; then
        "$PROJECT_ROOT/scripts/start_infra_stack.sh" --bootstrap-persistence
    else
        "$PROJECT_ROOT/scripts/start_infra_stack.sh"
    fi
    if [[ -f "$INFRA_ENV_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$INFRA_ENV_FILE"
        export DATABASE_URL REDIS_URL CELERY_BROKER_URL CELERY_RESULT_BACKEND
        log_info "✅ 已导入 infra 运行时环境"
    else
        log_error "❌ infra 环境文件未生成: $INFRA_ENV_FILE"
        exit 1
    fi
fi

if [[ "$WITH_WORKER" -eq 1 ]]; then
    log_info "🧵 启动本地 Celery worker..."
    PREEXISTING_WORKER_PID=""
    if [[ -f "$WORKER_PID_FILE" ]]; then
        PREEXISTING_WORKER_PID="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
    fi
    "$PROJECT_ROOT/scripts/start_celery_worker.sh"
    if [[ -f "$WORKER_PID_FILE" ]]; then
        WORKER_PID="$(cat "$WORKER_PID_FILE" 2>/dev/null || true)"
        if [[ -n "$WORKER_PID" && "$WORKER_PID" != "$PREEXISTING_WORKER_PID" ]]; then
            STARTED_WORKER=1
        fi
        log_info "✅ Celery worker 已就绪 (PID: ${WORKER_PID:-unknown})"
    else
        log_error "❌ Celery worker pid 文件未生成: $WORKER_PID_FILE"
        exit 1
    fi
fi

ensure_port_available "$BACKEND_PORT" "后端服务" "$BACKEND_PID_FILE"
ensure_port_available "$FRONTEND_PORT" "前端服务" "$FRONTEND_PID_FILE"

log_info "🔧 启动后端服务..."
API_RELOAD=false python3 "$PROJECT_ROOT/scripts/start_backend.py" >"$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
STARTED_BACKEND=1
echo "$BACKEND_PID" > "$BACKEND_PID_FILE"

log_info "⏳ 等待后端服务启动..."
wait_for_url "http://${BACKEND_HOST}:${BACKEND_PORT}/health" "后端服务" 60
log_info "✅ 后端服务启动成功 (PID: $BACKEND_PID)"
log_info "   - API地址: http://${BACKEND_HOST}:${BACKEND_PORT}"
log_info "   - API文档: http://${BACKEND_HOST}:${BACKEND_PORT}/docs"

log_info "🎨 启动前端服务..."
(
    cd "$FRONTEND_DIR"
    BROWSER=none npm start
) >"$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
STARTED_FRONTEND=1
echo "$FRONTEND_PID" > "$FRONTEND_PID_FILE"

log_info "⏳ 等待前端服务启动..."
wait_for_url "http://${FRONTEND_HOST}:${FRONTEND_PORT}" "前端服务" 120

log_info "=================================="
log_info "🎉 系统启动完成！"
log_info ""
log_info "📊 服务信息:"
log_info "   - 前端地址: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
log_info "   - 后端地址: http://${BACKEND_HOST}:${BACKEND_PORT}"
log_info "   - API文档:  http://${BACKEND_HOST}:${BACKEND_PORT}/docs"
log_info ""
log_info "📝 进程信息:"
log_info "   - 后端进程 PID: $BACKEND_PID"
log_info "   - 前端进程 PID: $FRONTEND_PID"
if [[ "$WITH_WORKER" -eq 1 ]]; then
    log_info "   - Worker 进程 PID: ${WORKER_PID:-unknown}"
fi
log_info ""
log_info "📋 日志文件:"
log_info "   - 后端日志: $LOG_DIR/backend.log"
log_info "   - 前端日志: $LOG_DIR/frontend.log"
if [[ "$WITH_WORKER" -eq 1 ]]; then
    log_info "   - Worker 日志: $LOG_DIR/celery-worker.log"
fi
log_info ""
log_info "🛑 停止系统: 按 Ctrl+C 或运行 ./scripts/stop_system.sh"
if [[ "$WITH_INFRA" -eq 1 ]]; then
    log_info "🐳 停止 infra: ./scripts/stop_system.sh --with-infra"
fi
if [[ "$WITH_WORKER" -eq 1 ]]; then
    log_info "🧵 停止 worker: ./scripts/stop_system.sh --with-worker"
fi
log_info "=================================="

while true; do
    sleep 10

    if ! curl -fsS "http://${BACKEND_HOST}:${BACKEND_PORT}/health" >/dev/null 2>&1; then
        BACKEND_HEALTH_FAILURES=$((BACKEND_HEALTH_FAILURES + 1))
        log_error "⚠️  后端健康检查失败 (${BACKEND_HEALTH_FAILURES}/${BACKEND_HEALTH_FAILURE_THRESHOLD})"
        if [[ "$BACKEND_HEALTH_FAILURES" -ge "$BACKEND_HEALTH_FAILURE_THRESHOLD" ]]; then
            log_error "❌ 后端服务意外停止（健康检查连续失败）"
            exit 1
        fi
    else
        BACKEND_HEALTH_FAILURES=0
    fi

    if ! process_alive "$FRONTEND_PID"; then
        log_error "❌ 前端服务意外停止"
        exit 1
    fi
done
