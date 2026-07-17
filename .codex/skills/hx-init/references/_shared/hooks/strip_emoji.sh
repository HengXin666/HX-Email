#!/usr/bin/env bash
# PostToolUse: 检测本次工具写入文件中的文本表情。
# 默认只记录, 不改内容; 设置 HX_HOOK_AUTOFIX_TEXT=1 才会自动删除。
set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
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

mapfile -t CHANGED < <(extract_hook_paths)
if [[ ${#CHANGED[@]} -eq 0 ]]; then
  exit 0
fi

log_dir() {
  if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    local git_path
    git_path="$(git -C "$REPO_ROOT" rev-parse --git-path hx-init/logs)"
    case "$git_path" in
      /*) echo "$git_path" ;;
      *) echo "$REPO_ROOT/$git_path" ;;
    esac
  else
    local key
    key="$(printf '%s' "$REPO_ROOT" | cksum | awk '{print $1}')"
    echo "${XDG_CACHE_HOME:-$HOME/.cache}/hx-init/logs/${key}"
  fi
}

LOG_DIR="$(log_dir)"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG_FILE="${LOG_DIR}/emoji-latest.log"
: >"$LOG_FILE" 2>/dev/null || true

FOUND=0
for file in "${CHANGED[@]}"; do
  [[ -z "$file" ]] && continue
  if [[ "$file" = "$REPO_ROOT"/* ]]; then
    rel="${file#"$REPO_ROOT"/}"
  else
    rel="$file"
  fi
  [[ "$rel" = /* || "$rel" = ..* || "$rel" = *"/../"* ]] && continue
  fpath="$REPO_ROOT/$rel"
  [[ ! -f "$fpath" ]] && continue
  file "$fpath" 2>/dev/null | grep -q 'text' || continue

  if grep -qE '✅|❎|❌|🚫|⭐|🔥|💡|📝|🎯|👍|⚠️|❗|❓|✨|🔴|🟡|📋|🔧|📌|📊|🏗️' "$fpath" 2>/dev/null; then
    FOUND=$((FOUND + 1))
    printf '%s\n' "$rel" >>"$LOG_FILE" 2>/dev/null || true
    if [[ "${HX_HOOK_AUTOFIX_TEXT:-0}" = "1" ]]; then
      sed -i'' -E \
        -e 's/✅//g' \
        -e 's/❎//g' \
        -e 's/❌//g' \
        -e 's/🚫//g' \
        -e 's/⭐//g' \
        -e 's/🔥//g' \
        -e 's/💡//g' \
        -e 's/📝//g' \
        -e 's/🎯//g' \
        -e 's/👍//g' \
        -e 's/⚠️//g' \
        -e 's/❗//g' \
        -e 's/❓//g' \
        -e 's/✨//g' \
        -e 's/🔴//g' \
        -e 's/🟡//g' \
        -e 's/📋//g' \
        -e 's/🔧//g' \
        -e 's/📌//g' \
        -e 's/📊//g' \
        -e 's/🏗️//g' \
        "$fpath" 2>/dev/null || true
    fi
  fi
done

if [[ $FOUND -gt 0 ]]; then
  echo "[hooks] detected emoji-like symbols in $FOUND edited file(s); log: $LOG_FILE" >&2
fi
exit 0
