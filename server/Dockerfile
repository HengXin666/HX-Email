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

# Self-update: docker CLI + compose plugin so the backend can pull images and
# recreate containers through the mounted host docker socket (docker compose pull && up -d).
# The release pipeline passes APP_VERSION so version-check reports the real release tag.
ARG APP_VERSION=0.9.0
ENV HX_EMAIL_APP_VERSION=${APP_VERSION}

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    DOCKER_ARCH="$(dpkg --print-architecture)"; \
    case "$DOCKER_ARCH" in \
      amd64) DOCKER_ARCH="x86_64" ;; \
      arm64) DOCKER_ARCH="aarch64" ;; \
      armhf) DOCKER_ARCH="armhf" ;; \
    esac; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-27.5.1.tgz" -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /tmp; \
    install -m 0755 /tmp/docker/docker /usr/local/bin/docker; \
    mkdir -p /usr/local/lib/docker/cli-plugins; \
    curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-${DOCKER_ARCH}" -o /usr/local/lib/docker/cli-plugins/docker-compose; \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose; \
    rm -rf /tmp/docker /tmp/docker.tgz /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:${PATH}" \
    HX_EMAIL_DATA_DIR=/data

VOLUME ["/data"]
EXPOSE 18090

# HX_EMAIL_BIND_HOST: 0.0.0.0 for bridge networking; compose host-mode sets 127.0.0.1
CMD ["sh", "-c", "hx-email migrate && exec uvicorn hx_email.app:app --host ${HX_EMAIL_BIND_HOST:-0.0.0.0} --port ${HX_EMAIL_BACKEND_PORT:-18090}"]
