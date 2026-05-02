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

## Docker 一键部署(全栈)

仓库根目录的 [`docker-compose.yml`](../docker-compose.yml) 提供 **TimescaleDB + Redis + Backend + Frontend** 四个 service 的一键部署能力,适用于本地完整体验和最小化生产部署。

### 镜像构成

| 服务 | 镜像来源 | 端口 |
|------|---------|------|
| `timescaledb` | `timescale/timescaledb:latest-pg16` | `5432` |
| `redis` | `redis:7-alpine` | `6379` |
| `backend` | 仓内 [`Dockerfile.backend`](../Dockerfile.backend) 多阶段构建,Python 3.13-slim,non-root user | `8000` |
| `frontend` | 仓内 [`Dockerfile.frontend`](../Dockerfile.frontend) (node:22-alpine 构建 → nginx:1.27-alpine 提供静态产物 + `/api` 反向代理) | `3000 → 80` |

### 启动

```bash
# 1. 准备 .env(必须设置真实 AUTH_SECRET)
cp .env.example .env
sed -i.bak 's/AUTH_SECRET=.*/AUTH_SECRET="please-replace-with-32-byte-random"/' .env

# 2. 一次性构建并启动
docker compose up -d --build

# 3. 跟踪日志
docker compose logs -f backend frontend

# 4. 健康检查
curl http://localhost:8000/health
curl http://localhost:3000/healthz
```

### 镜像版本固定

`docker-compose.yml` 顶部支持以下变量(在 `.env` 中设置):

| 变量 | 默认值 | 用途 |
|------|--------|------|
| `IMAGE_TAG` | `dev` | 给 backend / frontend 镜像打 tag |
| `TIMESCALE_TAG` | `latest-pg16` | 升级前固定到具体版本 |
| `REDIS_TAG` | `7-alpine` | 同上 |
| `PYTHON_VERSION` | `3.13` | 通过 `--build-arg` 传给 `Dockerfile.backend` |
| `NODE_VERSION` | `22` | 同上,传给 `Dockerfile.frontend` |

### 数据持久化

四个命名卷:`timescale_data` / `redis_data` / `backend_logs` / `backend_cache` / `backend_data`。

```bash
# 备份 TimescaleDB
docker compose exec timescaledb pg_dump -U quant quant_research > backup-$(date +%F).sql

# 完整下线 + 数据卷一并清除(危险)
docker compose down -v
```

### 反向代理建议

`Dockerfile.frontend` 已经把 `/api` 和 `/ws` 在 nginx 内部代理到 backend,所以前端容器自带"网关"。如要部署到公网域名,只需把外层反向代理(traefik / cloudflared / 自建 nginx)指向前端容器的 `80` 端口,即可同时拿到静态资源 + API + WebSocket。

如果使用 Traefik,可通过 labels 自动暴露:

```yaml
frontend:
  labels:
    - traefik.enable=true
    - traefik.http.routers.quant.rule=Host(`quant.example.com`)
    - traefik.http.routers.quant.entrypoints=websecure
    - traefik.http.routers.quant.tls.certresolver=letsencrypt
```

### 单独启动基础设施(开发模式)

如果仍想在宿主机直接 `python backend/main.py + npm start` 调试,只跑 infra:

```bash
# 用 infra-only 编排
docker compose -f docker-compose.quant-infra.yml up -d
```

---

## (旧)仅基础设施部署

当前仓库还保留独立的 [`docker-compose.quant-infra.yml`](../docker-compose.quant-infra.yml) 用于一键启动:

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
