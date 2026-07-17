#!/usr/bin/env bash
set -euo pipefail

run_ruff() {
  if command -v uv >/dev/null 2>&1 && [[ -f "uv.lock" || -f "pyproject.toml" ]]; then
    uv run ruff "$@"
  elif command -v poetry >/dev/null 2>&1 && [[ -f "poetry.lock" ]]; then
    poetry run ruff "$@"
  elif command -v pdm >/dev/null 2>&1 && [[ -f "pdm.lock" ]]; then
    pdm run ruff "$@"
  elif command -v ruff >/dev/null 2>&1; then
    ruff "$@"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m ruff "$@"
  else
    python -m ruff "$@"
  fi
}

run_python() {
  if command -v uv >/dev/null 2>&1 && [[ -f "uv.lock" || -f "pyproject.toml" ]]; then
    uv run python "$@"
  elif command -v poetry >/dev/null 2>&1 && [[ -f "poetry.lock" ]]; then
    poetry run python "$@"
  elif command -v pdm >/dev/null 2>&1 && [[ -f "pdm.lock" ]]; then
    pdm run python "$@"
  elif command -v python3 >/dev/null 2>&1; then
    python3 "$@"
  else
    python "$@"
  fi
}

echo "==> [1/5] ruff check (含 PLC2401 中文命名拦截)"
run_ruff check .
echo "==> [2/5] ruff format --check"
run_ruff format --check .
echo "==> [3/5] type-check ({{CHECKER}})"
{{TYPE_CMD_VERIFY}}
echo "==> [4/5] tests"
{{TEST_CMD_VERIFY}}
echo "==> [5/5] arch-check advisory (300行/文件数/_前缀/中文命名)"
run_python scripts/check_arch.py {{SRC_DIR}}
echo "ALL PASS"
