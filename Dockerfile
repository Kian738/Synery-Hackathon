# Floorwise: one container = FastAPI backend + built React app.
# Works on Hugging Face Spaces (Docker SDK, port 7860) and Render/Koyeb (they set $PORT).

# ---- stage 1: build the web app ----
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# vite build only (no tsc -b) so an in-progress type error elsewhere cannot block a pitch deploy
RUN npx vite build

# ---- stage 2: python runtime ----
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
# glib for opencv-headless
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 PORT=7860 FLOORWISE_WEB_DIST=/app/web/dist

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=user:user . .
COPY --from=web --chown=user:user /web/dist /app/web/dist
RUN uv sync --frozen --no-dev && mkdir -p /app/runs && chown -R user:user /app

USER user
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"7860\")}/healthz')"
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]
