#!/usr/bin/env bash
# PostToolUse: 仅对变更的前端文本文件跑本地 formatter/linter。
# 设计为不阻断(exit 0): 真正的红线交给 Stop hook + lefthook pre-push。
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

FILES=()
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  if [[ "$file" = "$PROJECT_DIR"/* ]]; then
    rel="${file#"$PROJECT_DIR"/}"
  else
    rel="$file"
  fi
  [[ "$rel" = /* || "$rel" = ..* || "$rel" = *"/../"* ]] && continue
  [[ -f "$PROJECT_DIR/$rel" ]] || continue
  case "$rel" in
    *.ts|*.tsx|*.js|*.jsx|*.json|*.css|*.scss|*.md|*.yml|*.yaml) FILES+=("$rel") ;;
  esac
done < <(extract_hook_paths)

[[ ${#FILES[@]} -eq 0 ]] && exit 0

BIOME=()
if [[ -x "node_modules/.bin/biome" ]]; then
  BIOME=(./node_modules/.bin/biome)
elif command -v biome &>/dev/null; then
  BIOME=(biome)
elif command -v pnpm &>/dev/null && [[ -f "pnpm-lock.yaml" ]]; then
  BIOME=(pnpm exec biome)
elif command -v bunx &>/dev/null && { [[ -f "bun.lockb" ]] || [[ -f "bun.lock" ]]; }; then
  BIOME=(bunx biome)
elif command -v npx &>/dev/null; then
  BIOME=(npx --no-install @biomejs/biome)
fi

if [[ ${#BIOME[@]} -gt 0 ]]; then
  "${BIOME[@]}" check --write --no-errors-on-unmatched "${FILES[@]}" >/dev/null 2>&1 || true
fi

exit 0
