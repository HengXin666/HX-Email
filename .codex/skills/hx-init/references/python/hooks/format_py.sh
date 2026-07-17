#!/usr/bin/env bash
# PostToolUse: 只格式化本次变更的 Python 文件。
# 设计为"不阻断"(exit 0): 格式化是辅助，真正的红线交给 Stop hook。
set -uo pipefail

PROJECT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
cd "$PROJECT_DIR" || exit 0
HOOK_INPUT="$(cat || true)"

extract_hook_paths() {
  local py
  py="$(command -v python3 || command -v python || true)"
  [[ -n "$py" ]] || return 0
  HOOK_INPUT="$HOOK_INPUT" "$py" - <<'PY'
import json
import os
import re

raw = os.environ.get("HOOK_INPUT", "")
try:
    data = json.loads(raw) if raw.strip() else {}
except json.JSONDecodeError:
    data = {}

paths = []

def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            lk = key.lower()
            if lk in {"file_path", "filepath", "path", "filename"} and isinstance(item, str):
                paths.append(item)
            elif lk in {"file_paths", "files", "paths"} and isinstance(item, list):
                for entry in item:
                    if isinstance(entry, str):
                        paths.append(entry)
                    else:
                        walk(entry)
            else:
                walk(item)
    elif isinstance(value, list):
        for item in value:
            walk(item)
    elif isinstance(value, str):
        for match in re.finditer(r"^\*\*\* (?:Add|Update) File: (.+)$", value, re.M):
            paths.append(match.group(1).strip())

walk(data)
for path in dict.fromkeys(paths):
    print(path)
PY
}

PY_FILES=()
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  if [[ "$file" = "$PROJECT_DIR"/* ]]; then
    rel="${file#"$PROJECT_DIR"/}"
  else
    rel="$file"
  fi
  [[ "$rel" = /* || "$rel" = ..* || "$rel" = *"/../"* ]] && continue
  [[ "$rel" = *.py && -f "$PROJECT_DIR/$rel" ]] && PY_FILES+=("$rel")
done < <(extract_hook_paths)

[[ ${#PY_FILES[@]} -eq 0 ]] && exit 0

if command -v uv &>/dev/null && [[ -f "pyproject.toml" || -f "uv.lock" ]]; then
  RUFF=(uv run ruff)
elif command -v ruff &>/dev/null; then
  RUFF=(ruff)
elif command -v python3 &>/dev/null; then
  RUFF=(python3 -m ruff)
elif command -v python &>/dev/null; then
  RUFF=(python -m ruff)
else
  exit 0
fi

"${RUFF[@]}" format "${PY_FILES[@]}" >/dev/null 2>&1 || true
"${RUFF[@]}" check --fix "${PY_FILES[@]}" >/dev/null 2>&1 || true
exit 0
