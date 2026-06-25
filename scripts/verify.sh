#!/usr/bin/env bash
# 验证闭环 (uv 版): 给 Agent 明确 pass/fail 信号. Stop hook 复用本脚本.
set -euo pipefail
echo "==> [1/4] ruff check (含 PLC2401 中文命名拦截)"
uv run ruff check .
echo "==> [2/4] ruff format --check"
uv run ruff format --check .
echo "==> [3/4] type-check (mypy)"
(cd server && uv run mypy .)
echo "==> [4/4] arch-check (300行/文件数/_前缀/中文命名)"
uv run python scripts/check_arch.py server
echo "ALL PASS"
