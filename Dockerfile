# syntax=docker/dockerfile:1
#
# Backend image for quant-trading-system (FastAPI + uvicorn).
# Build context is the repo ROOT. Pairs with docker-compose.yml.
# The same image runs both the API service and the Celery worker
# (the worker just overrides `command`).

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ENVIRONMENT=production

# Runtime/system deps:
#   - libgomp1     : OpenMP runtime required by scikit-learn / scipy wheels
#   - curl         : used by the HEALTHCHECK below
#   - build-essential : lets any sdist-only dependency compile if no wheel exists
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so the layer caches across source changes.
# Only the production requirement set (no dev/test tooling).
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Application source. .dockerignore keeps caches/tests/frontend/data out.
COPY backend ./backend
COPY src ./src
COPY scripts ./scripts
COPY pyproject.toml VERSION ./

# Runtime dirs (also bind-mounted by compose so state persists on the host).
# Run as a non-root user. NOTE: on Linux, bind-mounted ./data ./logs ./cache
# must be writable by uid 1000 (or set `user:` in compose); Docker Desktop
# (macOS/Windows) maps ownership automatically.
RUN mkdir -p data logs cache \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Production entrypoint: bind all interfaces, no autoreload.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
