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

### 4. 环境变量

后端主要配置通过 `src/settings/` 读取，可通过项目根目录 `.env` 或环境变量覆盖：
- `API_HOST`（默认 `127.0.0.1`）
- `API_PORT`（默认 `8000`）
- `API_RELOAD`（默认 `True`）
- `DATA_CACHE_SIZE`（默认 `100`）
- `CACHE_TTL`（默认 `3600`）

前端通过 `frontend/.env*` 或构建环境变量设置：
- `REACT_APP_API_URL`（默认 `http://localhost:8000`）
- `REACT_APP_API_TIMEOUT`

## 前后端通信方式

- 开发环境：`frontend/package.json` 里保留了 `proxy=http://localhost:8000`
- 前端请求默认读取 `REACT_APP_API_URL`，未设置时回退到 `http://localhost:8000`
- WebSocket 会基于同一个 `REACT_APP_API_URL` 自动推导 `ws://` 或 `wss://`
- 生产环境推荐二选一：
  - 同域反向代理，前端静态资源和 API 由同一域名提供
  - 显式设置 `REACT_APP_API_URL=https://your-domain.com/api`

### 5. 反向代理示例

如需同域代理，可将 API 绑定到 `/api`，并配置前端 `REACT_APP_API_URL` 为 `https://your-domain.com/api`。

```nginx
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

## Docker 支持

当前仓库已提供本地研究环境专用的基础设施编排文件 [`docker-compose.quant-infra.yml`](../docker-compose.quant-infra.yml)，用于一键启动：

- `PostgreSQL + TimescaleDB`
- `Redis`

推荐的本地启动顺序如下：

```bash
cp .env.example .env
./scripts/start_infra_stack.sh --bootstrap-persistence
source ./logs/infra-stack.env
./scripts/start_celery_worker.sh
python3 ./scripts/migrate_infra_store.py
./scripts/start_system.sh
```

如果希望一次性把基础设施和前后端一起拉起，可以直接使用：

```bash
./scripts/start_system.sh --with-infra --with-worker --bootstrap-persistence
```

停止命令：

```bash
./scripts/stop_system.sh --with-infra --with-worker
```

如需连同数据库和 Redis 数据卷一起删除：

```bash
./scripts/stop_system.sh --with-infra --remove-infra-volumes
```

说明：

- `start_infra_stack.sh` 会在 `logs/infra-stack.env` 中生成推荐的 `DATABASE_URL / REDIS_URL / CELERY_*` 运行时环境。
- `start_celery_worker.sh` 默认会复用 `logs/infra-stack.env` 中的 broker 配置，并以本地开发更稳妥的 `solo` pool 启动 worker。
- `migrate_infra_store.py` 可先做 dry-run 预览，再使用 `--apply` 将原 SQLite fallback 的 records / timeseries 迁移到 PostgreSQL。
- `--bootstrap-persistence` 会在 TimescaleDB 就绪后自动执行 `backend/app/db/timescale_schema.sql` 对应的 bootstrap 流程。
- 若当前机器未安装 Docker / docker compose，系统仍可继续使用 SQLite + 本地执行器降级运行。

---

**最后更新**: 2026-03-20
