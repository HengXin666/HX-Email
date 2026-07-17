#!/usr/bin/env bash
# PostToolUse: 仅清理本次工具写入文件中的不可见字符。
# 处理: 行尾空格/Tab、零宽字符(U+200B/U+FEFF等)、BOM标记
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
[[ ${#CHANGED[@]} -eq 0 ]] && exit 0

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

  # 行尾空格和Tab → 删除
  # 零宽空格(U+200B) → 删除
  # 零宽不连字(U+200C) → 删除
  # 零宽连字(U+200D) → 删除
  # BOM/零宽不换行空格(U+FEFF/65279) → 删除
  sed -i'' \
    -e 's/[ 	]\+$//g' \
    -e $'s/\xe2\x80\x8b//g' \
    -e $'s/\xe2\x80\x8c//g' \
    -e $'s/\xe2\x80\x8d//g' \
    -e $'s/\xef\xbb\xbf//g' \
    "$fpath" 2>/dev/null || true
done

exit 0
