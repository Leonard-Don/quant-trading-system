#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.quant-infra.yml"
ENV_OUTPUT_FILE="$LOG_DIR/infra-stack.env"

BOOTSTRAP_PERSISTENCE=0
WAIT_FOR_SERVICES=1
PRINT_ENV_ONLY=0

TIMESCALE_DB="${TIMESCALE_DB:-quant_research}"
TIMESCALE_USER="${TIMESCALE_USER:-quant}"
TIMESCALE_PASSWORD="${TIMESCALE_PASSWORD:-quant_dev_password}"
TIMESCALE_PORT="${TIMESCALE_PORT:-5432}"
REDIS_PORT="${REDIS_PORT:-6379}"

DATABASE_URL_DEFAULT="postgresql://${TIMESCALE_USER}:${TIMESCALE_PASSWORD}@127.0.0.1:${TIMESCALE_PORT}/${TIMESCALE_DB}"
REDIS_URL_DEFAULT="redis://127.0.0.1:${REDIS_PORT}/0"

DATABASE_URL="${DATABASE_URL:-$DATABASE_URL_DEFAULT}"
REDIS_URL="${REDIS_URL:-$REDIS_URL_DEFAULT}"
CELERY_BROKER_URL="${CELERY_BROKER_URL:-$REDIS_URL}"
CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-$REDIS_URL}"

COMPOSE_CMD=()

usage() {
    cat <<'EOF'
用法: ./scripts/start_infra_stack.sh [--bootstrap-persistence] [--no-wait] [--print-env] [--help]

选项:
  --bootstrap-persistence  在 TimescaleDB 就绪后自动执行研究表 bootstrap
  --no-wait                仅触发 docker compose up，不等待服务健康
  --print-env              仅输出建议的运行时环境变量，不启动容器
  --help                   显示帮助
EOF
}

log_info() {
    echo "$1"
}

log_error() {
    echo "$1" >&2
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

write_env_file() {
    mkdir -p "$LOG_DIR"
    {
        printf 'export TIMESCALE_DB=%q\n' "$TIMESCALE_DB"
        printf 'export TIMESCALE_USER=%q\n' "$TIMESCALE_USER"
        printf 'export TIMESCALE_PASSWORD=%q\n' "$TIMESCALE_PASSWORD"
        printf 'export TIMESCALE_PORT=%q\n' "$TIMESCALE_PORT"
        printf 'export REDIS_PORT=%q\n' "$REDIS_PORT"
        printf 'export DATABASE_URL=%q\n' "$DATABASE_URL"
        printf 'export REDIS_URL=%q\n' "$REDIS_URL"
        printf 'export CELERY_BROKER_URL=%q\n' "$CELERY_BROKER_URL"
        printf 'export CELERY_RESULT_BACKEND=%q\n' "$CELERY_RESULT_BACKEND"
    } >"$ENV_OUTPUT_FILE"
}

print_env_exports() {
    cat "$ENV_OUTPUT_FILE"
}

masked_database_url() {
    if [[ -n "$TIMESCALE_PASSWORD" ]]; then
        echo "${DATABASE_URL//$TIMESCALE_PASSWORD/******}"
    else
        echo "$DATABASE_URL"
    fi
}

wait_for_postgres() {
    for _ in $(seq 1 40); do
        if "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" exec -T timescaledb \
            pg_isready -U "$TIMESCALE_USER" -d "$TIMESCALE_DB" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

wait_for_redis() {
    for _ in $(seq 1 30); do
        if "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" exec -T redis \
            redis-cli ping >/tmp/quant-redis-ping.$$ 2>/dev/null; then
            if grep -q "PONG" /tmp/quant-redis-ping.$$ 2>/dev/null; then
                rm -f /tmp/quant-redis-ping.$$
                return 0
            fi
        fi
        sleep 2
    done
    rm -f /tmp/quant-redis-ping.$$ 2>/dev/null || true
    return 1
}

bootstrap_persistence() {
    (
        cd "$PROJECT_ROOT"
        DATABASE_URL="$DATABASE_URL" python3 - <<'PY'
import os
import sys

project_root = os.getcwd()
sys.path.insert(0, project_root)

from backend.app.core.persistence import PersistenceManager

manager = PersistenceManager(database_url=os.environ["DATABASE_URL"])
result = manager.bootstrap_postgres(enable_timescale_schema=True)
print(f"bootstrapped={bool(result.get('post_bootstrap', {}).get('timescale_ready'))}")
print(f"tables={','.join(result.get('post_bootstrap', {}).get('tables') or [])}")
print(f"hypertables={','.join(result.get('post_bootstrap', {}).get('hypertables') or [])}")
PY
    )
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bootstrap-persistence)
            BOOTSTRAP_PERSISTENCE=1
            ;;
        --no-wait)
            WAIT_FOR_SERVICES=0
            ;;
        --print-env)
            PRINT_ENV_ONLY=1
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

write_env_file

if [[ "$PRINT_ENV_ONLY" -eq 1 ]]; then
    print_env_exports
    exit 0
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    log_error "❌ 未找到 compose 文件: $COMPOSE_FILE"
    exit 1
fi

if ! resolve_compose_command; then
    log_error "❌ 未检测到 docker compose。请安装 Docker Desktop 或 docker-compose。"
    exit 1
fi

mkdir -p "$LOG_DIR"

log_info "🐳 启动本地基础设施栈..."
log_info "   - Compose: $COMPOSE_FILE"
log_info "   - Database: $(masked_database_url)"
log_info "   - Redis: $REDIS_URL"

"${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" up -d

if [[ "$WAIT_FOR_SERVICES" -eq 1 ]]; then
    log_info "⏳ 等待 TimescaleDB 健康..."
    if wait_for_postgres; then
        log_info "✅ TimescaleDB 已就绪"
    else
        log_error "❌ TimescaleDB 未在预期时间内就绪"
        exit 1
    fi

    log_info "⏳ 等待 Redis 健康..."
    if wait_for_redis; then
        log_info "✅ Redis 已就绪"
    else
        log_error "❌ Redis 未在预期时间内就绪"
        exit 1
    fi
fi

if [[ "$BOOTSTRAP_PERSISTENCE" -eq 1 ]]; then
    log_info "🗄️  执行 PostgreSQL / TimescaleDB bootstrap..."
    bootstrap_persistence
fi

log_info "✅ 本地 infra stack 已启动"
log_info "   - 运行时环境文件: $ENV_OUTPUT_FILE"
log_info "   - 导入命令: source \"$ENV_OUTPUT_FILE\""
log_info "   - 停止命令: ./scripts/stop_infra_stack.sh"
