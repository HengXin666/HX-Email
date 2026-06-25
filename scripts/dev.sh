#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${HX_EMAIL_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${HX_EMAIL_BACKEND_PORT:-8000}"
FRONTEND_HOST="${HX_EMAIL_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${HX_EMAIL_FRONTEND_PORT:-5173}"
API_TARGET="${HX_EMAIL_API_TARGET:-http://${BACKEND_HOST}:${BACKEND_PORT}}"

backend_pid=""
frontend_pid=""

cleanup() {
  if [[ -n "${frontend_pid}" ]] && kill -0 "${frontend_pid}" 2>/dev/null; then
    kill "${frontend_pid}" 2>/dev/null || true
  fi
  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

# 清理已占用的端口 (上次未正常退出的残留进程)
echo "==> Cleaning up stale processes"
for port in "${BACKEND_PORT}" "${FRONTEND_PORT}"; do
  if fuser "${port}/tcp" 2>/dev/null; then
    echo "    Killing process on port ${port}"
    fuser -k "${port}/tcp" 2>/dev/null || true
    sleep 0.5
  fi
done

echo "==> Migrating database"
(cd "${ROOT_DIR}/server" && uv run hx-email migrate)

echo "==> Starting backend at ${API_TARGET}"
(cd "${ROOT_DIR}/server" && uv run uvicorn hx_email.app:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" --reload) &
backend_pid="$!"

echo "==> Starting frontend at http://${FRONTEND_HOST}:${FRONTEND_PORT}"
(
  cd "${ROOT_DIR}/web"
  HX_EMAIL_API_TARGET="${API_TARGET}" npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}"
) &
frontend_pid="$!"

echo "==> HX Email is starting"
echo "    Backend:  ${API_TARGET}"
echo "    Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "    Press Ctrl+C to stop both services."

wait -n "${backend_pid}" "${frontend_pid}"
