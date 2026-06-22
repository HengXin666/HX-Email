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

Configuration is loaded from environment variables with the `HX_EMAIL_` prefix.
The SQLite data directory defaults to `.data`; override it with:

```bash
HX_EMAIL_DATA_DIR=/path/to/data uv run hx-email migrate
```

## Frontend

```bash
cd web
npm install
npm test
npm run build
npm run dev
```

The frontend uses React + TypeScript + Tailwind and starts in dark mode. Its
entry screen follows the login-card direction from `ref/HX-ANiMe` while keeping
the task-1 scope to a usable route shell.

## Whole Repo Checks

```bash
npm test
npm run build
```
