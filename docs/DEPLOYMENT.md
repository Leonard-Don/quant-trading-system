# 部署指南

## 开发环境

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt

cd frontend && npm install

# 一键启动
./scripts/start_system.sh
```

访问：
- 前端: `http://localhost:3000`
- 后端: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

## 生产环境（建议）

### 1. 基础要求
- Python 3.8+
- Node.js 16+
- 反向代理（Nginx/Traefik 等）

### 2. 后端启动

建议使用进程管理器启动：
```bash
python backend/main.py
```

或通过 Uvicorn：
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

后端主要配置在 `src/utils/config.py`，可通过环境变量覆盖：
- `API_HOST`（默认 `127.0.0.1`）
- `API_PORT`（默认 `8000`）
- `API_RELOAD`（默认 `True`）
- `DATA_CACHE_SIZE`（默认 `100`）
- `CACHE_TTL`（默认 `3600`）

前端通过 `.env` 设置：
- `REACT_APP_API_URL`（默认 `http://localhost:8000`）
- `REACT_APP_API_TIMEOUT`

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

---

**最后更新**: 2026-02-05
