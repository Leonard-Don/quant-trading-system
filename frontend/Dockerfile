# syntax=docker/dockerfile:1
#
# Frontend image: build the Vite SPA, then serve the static bundle with nginx.
# Build context is ./frontend. Pairs with docker-compose.yml.
#
# The app talks to the backend via an ABSOLUTE base URL baked in at build time
# (VITE_API_URL → getEnv('API_URL') drives both REST and ws:// URLs), so nginx
# only needs to serve static files — no API proxy required. Override
# VITE_API_URL for non-localhost deployments.

FROM node:22-alpine AS build
WORKDIR /app

# Deps first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY . .

# Browser-reachable backend origin (REST + WebSocket). Default suits local
# `docker compose up` where the backend publishes host port 8000.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

# Vite config emits to build/ (not dist/).
RUN npm run build

FROM nginx:alpine AS serve
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1
CMD ["nginx", "-g", "daemon off;"]
