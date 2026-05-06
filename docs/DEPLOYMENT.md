# 部署指南

## 开发环境

```bash
# Python 开发依赖
pip install -r requirements-dev.txt

# 前端依赖
cd frontend && npm install

# 一键启动
./scripts/start_system.sh
```

访问：
- 前端: `http://localhost:3000`
- 后端: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

## 配置来源

- 运行时配置入口是 `backend/app/core/config.py`
- `src/utils/config.py` 现在是兼容层
- 实际配置定义按域拆分在 `src/settings/`（`api.py`、`data.py`、`trading.py`、`performance.py`、`gui.py`）
- 后端启动时会自动读取项目根目录 `.env`
- shell 环境变量会覆盖 `.env` 中的同名值

## 生产环境（建议）

### 1. 基础要求
- Python 3.9+
- Node.js 16+
- npm 8+
- 反向代理（Nginx/Traefik 等）

### 2. 后端启动

建议先安装最小运行依赖：

```bash
pip install -r requirements.txt
```

推荐生产启动方式：
```bash
API_RELOAD=false python backend/main.py
```

如需由外部进程管理器直接托管 Uvicorn，可使用：
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 3. 前端构建

```bash
cd frontend
npm install
npm run build
```

### 4. 数据库迁移（首次部署）

后端使用 Alembic 管理 schema 版本（配置在 `backend/alembic.ini`）。

```bash
# 已有数据库（已经按 backend/app/db/timescale_schema.sql 建好）：
cd backend
alembic stamp head            # 把现有库标记为已经在 head 版本

# 或全新数据库：
psql "$DATABASE_URL" -f backend/app/db/timescale_schema.sql
cd backend && alembic stamp head

# 后续新增 schema 变更：
cd backend && alembic revision -m "add foo column"
# ... 编辑生成的 versions/*.py，然后 ...
cd backend && alembic upgrade head
```

> 当前 baseline (`0001_baseline`) 是 no-op，仅记录"DB 已经在 timescale_schema.sql 状态"。后续真正的 schema 变更必须通过新的 migration 脚本写入。

### 5. 环境变量

后端主要配置通过 `src/settings/` 读取，可通过项目根目录 `.env` 或环境变量覆盖：
- `API_HOST`（默认 `127.0.0.1`）
- `API_PORT`（默认 `8000`）
- `API_RELOAD`（默认 `True`）
- `DATA_CACHE_SIZE`（默认 `100`）
- `CACHE_TTL`（默认 `3600`）

前端通过 `frontend/.env*` 或构建环境变量设置（**v5.1 起改为 Vite 命名约定**，`REACT_APP_*` 旧名已废弃）：
- `VITE_API_URL`（默认 `http://localhost:8000`）
- `VITE_API_TIMEOUT`
- `VITE_API_TIMEOUT_ANALYSIS` / `VITE_API_TIMEOUT_STANDARD` / `VITE_API_TIMEOUT_DASHBOARD`
- `VITE_REALTIME_WS_TOKEN`（实时行情/交易 WS 鉴权 token，可选）

> **BREAKING（CRA→Vite 迁移）**：从 v5.1 起前端构建工具由 `react-scripts` 切换为 Vite，所有 `REACT_APP_*` 环境变量需改名为 `VITE_*`（含 `.env*` 文件、CI/CD 配置、Docker 注入）。变量语义和默认值保持不变。

## 前后端通信方式

- 开发环境：`frontend/vite.config.js` 中 `server.proxy` 把 `/api`、`/ws`、`/health` 转发到 `http://127.0.0.1:8000`
- 前端请求默认读取 `VITE_API_URL`，未设置时回退到 `http://localhost:8000`
- WebSocket 会基于同一个 `VITE_API_URL` 自动推导 `ws://` 或 `wss://`
- 生产环境推荐二选一：
  - 同域反向代理，前端静态资源和 API 由同一域名提供
  - 显式设置 `VITE_API_URL=https://your-domain.com/api`

### 6. 反向代理示例

如需同域代理，可将 API 绑定到 `/api`，并配置前端 `VITE_API_URL` 为 `https://your-domain.com/api`。

```conf
server {
    listen 80;
    server_name your-domain.com;

    location / {
        root /path/to/frontend/build;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 异步任务队列（Celery + Redis）

### 本地开发：可选

不配置 `CELERY_BROKER_URL` / `REDIS_URL` 时，所有异步入口（`/backtest/.../async`、行业刷新、Monte-Carlo、Walk-Forward 等）会**回退到当前进程同步执行**。这只适合单用户、短任务、本机开发场景。

### 生产环境：强烈建议（多数场景下事实上必需）

以下任一情况都应启用真正的 Celery worker：

- 单次回测耗时超过 ~2 秒（命中 SLA 上限），HTTP 连接会撑爆代理超时
- 多期 / Walk-Forward / 跨市场批量回测同时运行
- 行业热度、Sina/THS 数据源缓存的定时刷新
- 多用户并发使用（同步路径只能串行处理，会互相阻塞）

### Redis + worker 起步

```bash
# 1) Redis（最简单的 docker 方式）
docker run -d --name quant-redis -p 6379:6379 redis:7-alpine

# 2) 配置环境变量
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/1"

# 3) 起 worker（脚本读上面两个变量；日志写到 logs/celery-worker.log）
./scripts/start_celery_worker.sh

# 4) 验证
ls logs/celery-worker.pid && tail -n 5 logs/celery-worker.log
```

停止 worker：`./scripts/stop_celery_worker.sh`。

### 健康检查

`scripts/health_check.py` 会在没有 broker 配置或没有 worker PID 时报 warning。生产环境应保证两者都存在：

```bash
python3 scripts/health_check.py | grep -i celery
```

## 外部服务一览

| 能力 | 环境变量 | 未配置时行为 | 生产建议 |
|------|----------|--------------|----------|
| PostgreSQL / TimescaleDB | `DATABASE_URL` | 使用本地 SQLite fallback | 必备（参见上面 "数据库迁移"） |
| Redis / Celery broker | `REDIS_URL` 或 `CELERY_BROKER_URL` | 异步任务回退到本地同步执行 | 必备（参见上面 "异步任务队列"） |
| Celery result backend | `CELERY_RESULT_BACKEND` | 复用 broker 或使用本地状态 | 与 broker 同源 |

启动顺序示例：

```bash
cp .env.example .env

export DATABASE_URL="postgresql://user:password@host:5432/quant_research"
export CELERY_BROKER_URL="redis://host:6379/0"
export CELERY_RESULT_BACKEND="redis://host:6379/1"

# 数据库 baseline（首次）
cd backend && alembic stamp head && cd ..

# 可选：从本地 fallback 数据迁移
python3 ./scripts/migrate_infra_store.py --dry-run

# 启动 worker
./scripts/start_celery_worker.sh

# 启动前后端
./scripts/start_system.sh
```

---

**最后更新**: 2026-05-05
