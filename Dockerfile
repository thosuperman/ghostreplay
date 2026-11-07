# GhostReplay Lab — both labs and the dashboard behind one port.
#   docker build -t ghostreplay-lab .
#   docker run --rm -p 8100:8100 -v ghostreplay-data:/data ghostreplay-lab

# ---- dashboard build ----------------------------------------------------------------------
FROM node:24-slim AS dashboard
WORKDIR /src
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/dashboard/package.json apps/dashboard/
RUN corepack pnpm install --frozen-lockfile
COPY apps/dashboard apps/dashboard
RUN corepack pnpm --dir apps/dashboard build

# ---- python runtime -----------------------------------------------------------------------
FROM python:3.13-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY apps/support-agent apps/support-agent
COPY apps/devops-agent apps/devops-agent
RUN uv sync --frozen --no-dev --no-editable \
    && rm -rf /root/.cache
COPY --from=dashboard /src/apps/dashboard/dist /app/dashboard

RUN useradd --create-home --uid 10001 ghost \
    && mkdir -p /data && chown ghost:ghost /data
USER ghost

ENV PATH="/app/.venv/bin:$PATH" \
    GHOSTREPLAY_DB_DIR=/data \
    GHOSTREPLAY_DASHBOARD_DIR=/app/dashboard \
    PORT=8100
VOLUME ["/data"]
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8100\")}/healthz', timeout=4)"
CMD ["sh", "-c", "exec ghostreplay serve --host 0.0.0.0 --port ${PORT}"]
