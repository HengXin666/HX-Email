# HX-Email backend (FastAPI + uv)
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependency layer first so source edits don't re-resolve the lockfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}" \
    HX_EMAIL_DATA_DIR=/data

VOLUME ["/data"]
EXPOSE 18090

# HX_EMAIL_BIND_HOST: 0.0.0.0 for bridge networking; compose host-mode sets 127.0.0.1
CMD ["sh", "-c", "hx-email migrate && exec uvicorn hx_email.app:app --host ${HX_EMAIL_BIND_HOST:-0.0.0.0} --port ${HX_EMAIL_BACKEND_PORT:-18090}"]
