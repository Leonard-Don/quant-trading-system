# Docker 部署指南

用 Docker Compose 一键拉起整套 `quant-trading-system`(后端 API + 前端 + Redis + Celery worker,TimescaleDB 可选)。

> ⚠️ 这套 Docker 配置(`Dockerfile`、`frontend/Dockerfile`、`docker-compose.yml`)是按现有运行机制编写的,但**尚未在本机做过 `docker build` / `docker compose up` 实跑验证**(作者机器上没有 Docker)。首次使用请预留一次 `docker compose up --build` 跑通的时间,如遇个别系统依赖缺失按提示补 `apt`/`apk` 包即可。

## 前置条件

- Docker Engine 24+ 与 Docker Compose v2
- 已复制环境变量文件:

```bash
cp .env.example .env        # compose 通过 env_file 读取它,必须存在
```

## 启动

```bash
# 后端 + 前端 + Redis + Celery worker
docker compose up --build

# 额外启动 TimescaleDB(默认关闭,见下文"数据库")
docker compose --profile db up --build

# 后台运行
docker compose up --build -d
```

启动后:

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:3000 |
| 后端 API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |

停止 / 清理:

```bash
docker compose down           # 停止
docker compose down -v         # 停止并删除命名卷(redis_data / tsdb_data)
```

## 组成

| 服务 | 镜像/构建 | 端口 | 说明 |
|------|-----------|------|------|
| `backend` | 根 `Dockerfile`(python:3.13-slim + uvicorn) | 8000 | `uvicorn backend.main:app`,生产模式无 reload |
| `celery-worker` | 同后端镜像 | — | `celery -A backend.app.core.task_queue:celery_app worker` |
| `frontend` | `frontend/Dockerfile`(vite 构建 → nginx) | 3000→80 | 静态 SPA;直连后端 |
| `redis` | redis:7-alpine | 6379 | Celery broker / result backend |
| `timescaledb` | timescale/timescaledb:2.17.2-pg16 | 5432 | **可选**,`--profile db` 开启 |

## 前后端如何连通

前端在**构建时**把 `VITE_API_URL` 烤进产物(它同时驱动 REST 的 `baseURL` 和 `ws://…/ws/*` 地址),浏览器**直连**后端,后端 CORS 默认已放行 `http://localhost:3000`,所以 nginx 只负责发静态文件,不做反代。

部署到非 localhost 的机器时,用目标后端地址重新构建前端:

```bash
VITE_API_URL=https://api.your-host docker compose build frontend
# 同时确保该来源在后端 CORS 白名单(FRONTEND_URL / CORS_ORIGINS)里
```

## 数据持久化

- `./data`、`./logs`、`./cache` 以 bind mount 挂进 `backend` 与 `celery-worker`——**你的研究档案、纸面账户状态、回测历史都留在宿主机 `data/`**,不会随容器销毁丢失。
- Redis、TimescaleDB 用命名卷(`redis_data` / `tsdb_data`)。
- Linux 下若 bind mount 出现写权限问题:容器内以 uid 1000 运行,可让宿主 `data/ logs/ cache/` 对该 uid 可写,或在 compose 里给 `backend`/`celery-worker` 加 `user: "${UID}:${GID}"`。Docker Desktop(macOS/Windows)无此问题。

## 数据库(可选)

后端默认用文件持久化即可运行,**无需** TimescaleDB。要启用:

```bash
docker compose --profile db up --build -d
```

并在 `.env` 里设置 `DATABASE_URL`(注意:`sqlalchemy` 目前在 `requirements-dev.txt` 而非 `requirements.txt`,启用 DB 路径前需把它加入生产依赖并重建镜像)。

## 后续可优化(未做)

- 后端镜像用多阶段构建(builder 装 `build-essential` 编 wheel,runtime 仅留运行库)进一步瘦身。
- 加 `docker compose` 健康依赖链与 `restart` 策略的生产化打磨、镜像漏洞扫描。
