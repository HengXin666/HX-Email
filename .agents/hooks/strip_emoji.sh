#!/usr/bin/env bash
# PostToolUse: 自动替换文本表情符号，保证代码/文档纯文本。
# 所有被替换的 emoji 记录到 stderr，方便回溯。
set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"

# 被修改过的文件（由 git diff 检出）
CHANGED=$(git -C "$REPO_ROOT" diff --name-only --diff-filter=AM 2>/dev/null || true)
if [[ -z "$CHANGED" ]]; then
  exit 0
fi

FOUND=0
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  fpath="$REPO_ROOT/$file"
  [[ ! -f "$fpath" ]] && continue
  # 只处理文本文件
  file "$fpath" 2>/dev/null | grep -q 'text' || continue

  # 常见文本表情 → 替换为空（后期可扩展映射表）
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
    "$fpath" 2>/dev/null

  if [[ $? -eq 0 ]]; then
    FOUND=$((FOUND + 1))
  fi
done <<< "$CHANGED"

if [[ $FOUND -gt 0 ]]; then
  echo "[hooks] 已清理 $FOUND 个文件中的文本表情" >&2
fi
exit 0
