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

## Whole Repo Checks

```bash
npm test
npm run build
```

## Migration Scope

The rewrite preserves the first-phase core data model. Import/export is scoped
to the authenticated user's email accounts, usable emails, aliases, groups,
tags, platforms and platform bindings. Browser extension features, a full
public API, notifications, one-click updates, AI enhancements and plugin-based
temporary mail providers remain deferred follow-up capabilities.
