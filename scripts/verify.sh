#!/usr/bin/env bash
# 验证闭环 (uv 版): 给 Agent 明确 pass/fail 信号. Stop hook 复用本脚本.
set -euo pipefail
echo "==> [1/9] ruff check (含 PLC2401 中文命名拦截)"
uv run ruff check .
echo "==> [2/9] ruff format --check"
uv run ruff format --check .
echo "==> [3/9] type-check (mypy)"
(cd server && uv run mypy .)
echo "==> [4/9] arch-check (300行/文件数/_前缀/中文命名)"
uv run python scripts/check_arch.py server
echo "==> [5/9] react format/lint (biome)"
(cd web && npx @biomejs/biome check . --no-errors-on-unmatched)
echo "==> [6/9] react type-check (tsc)"
(cd web && npm run typecheck)
echo "==> [7/9] react dead-code (knip)"
(cd web && npx knip --no-progress)
echo "==> [8/9] deterministic tests (Vitest + pytest)"
npm test
echo "==> [9/9] browser S3 (Playwright + FastAPI + Vite preview)"
npm run test:e2e --prefix web
echo "ALL PASS"
