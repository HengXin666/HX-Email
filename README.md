# HX-Email

HX Email is being rewritten as a FastAPI backend plus a React, TypeScript,
shadcn/ui and Tailwind frontend. The first slice provides a runnable skeleton
for later 可用邮箱, 验证码读取 and 平台绑定 work.

## Requirements

- Python 3.12+ with `uv`
- Node.js 24+ with npm

## Backend

```bash
cd server
uv run pytest
uv run hx-email migrate
uv run uvicorn hx_email.app:app --reload
```

The FastAPI app exposes:

- `GET /health` for health checks
- `hx-email migrate` for the initial SQLite migration entrypoint
- `GET /data/export` and `POST /data/import` for core first-phase data backup
  and migration. The payload covers email accounts, usable emails, aliases,
  groups, tags, platforms and platform bindings for the authenticated user only.

Mail automation supports settings-driven polling, per-group polling and
delivery controls, SMTP forwarding, Telegram, webhook callbacks, browser
notifications, and custom `.sh` pipelines. The event and external mailbox-pool
contracts are documented in [docs/mail-automation.md](docs/mail-automation.md).

Configuration is loaded from `.env`. Copy `.env.example` before first startup:

```bash
cp .env.example .env
```

The initial admin login defaults to:

- username: `admin`
- password: `admin`

Configure it in `.env`:

```dotenv
HX_EMAIL_ADMIN_USERNAME=your-admin
HX_EMAIL_ADMIN_PASSWORD=your-password
```

These admin credentials are used only when the SQLite database creates the
initial admin user. Changing `.env` after the database already exists does not
reset an existing admin password; use the account settings screen to change it.

The SQLite data directory defaults to `data`; configure it in `.env`:

```dotenv
HX_EMAIL_DATA_DIR=data
```

## Frontend

```bash
cd web
npm install
npm test
npm run build
npm run dev
```

## Local Development

Start the backend and frontend together from the repository root:

```bash
./scripts/dev.sh
```

Defaults:

- backend: `http://127.0.0.1:8000`
- frontend: `http://0.0.0.0:5173`

Override ports or hosts when needed:

```bash
HX_EMAIL_BACKEND_PORT=8010 HX_EMAIL_FRONTEND_PORT=5174 ./scripts/dev.sh
```

The frontend uses React + TypeScript + Tailwind and starts in dark mode. Its
entry screen follows the login-card direction from `ref/HX-ANiMe` while keeping
the task-1 scope to a usable route shell.

## Docker 一键部署

Linux (推荐, host 网络模式):

```bash
docker compose up -d --build
```

打开 `http://127.0.0.1:8080`,默认账号 `admin` / `admin`(生产环境请先在
`.env` 中修改 `HX_EMAIL_ADMIN_*` 与 `HX_EMAIL_SECRET_KEY`)。

**代理兼容说明**:系统中的分组代理 / Telegram 代理经常填
`http://127.0.0.1:7890` 这类宿主机本地代理(Clash / V2Ray 等)。默认
compose 使用 host 网络模式,容器与宿主机共享网络栈,这类代理填写
`127.0.0.1:xxx` 可直接生效。后端仅监听 `127.0.0.1`,只有 nginx 前端
(`HX_EMAIL_HTTP_PORT`,默认 8080)对外暴露。

Mac / Windows(Docker Desktop)使用桥接版:

```bash
docker compose -f docker-compose.bridge.yml up -d --build
```

桥接模式下容器内的 `127.0.0.1` 指向容器自身,宿主机代理请改填
`http://host.docker.internal:7890`(compose 已通过 `host-gateway` 映射)。

数据(SQLite 与静态图片)持久化在仓库根目录 `./data`,与本地开发共用同一
目录;备份即拷贝该目录。端口可通过 `.env` 中的 `HX_EMAIL_HTTP_PORT` /
`HX_EMAIL_BACKEND_PORT` 覆盖。

## Whole Repo Checks

```bash
bash scripts/verify.sh
```

This single local/CI gate runs Python and React static checks, type checks,
architecture checks, dead-code analysis, Vitest, pytest, and the Playwright S3
browser flow. Install its local Chromium runtime once with:

```bash
cd web
npx playwright install chromium
```

The S3 flow starts an isolated FastAPI database and a Vite production preview,
then verifies authentication rejection, recovery, protected navigation, and
logout in Chromium. Real OAuth, Graph, IMAP, SMTP, and temporary-mail provider
canaries stay outside the PR gate.

## Migration Scope

The rewrite preserves the first-phase core data model. Import/export is scoped
to the authenticated user's email accounts, usable emails, aliases, groups,
tags, platforms and platform bindings. Browser extension features, closed-page
VAPID push, one-click updates and plugin-based temporary mail providers remain
deferred follow-up capabilities.
