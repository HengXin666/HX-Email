#!/usr/bin/env bash
# PostToolUse: 静默清理不可见字符，无输出，不产生 git 噪音。
# 处理: 行尾空格/Tab、零宽字符(U+200B/U+FEFF等)、BOM标记
set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"

CHANGED=$(git -C "$REPO_ROOT" diff --name-only --diff-filter=AM 2>/dev/null || true)
[[ -z "$CHANGED" ]] && exit 0

while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  fpath="$REPO_ROOT/$file"
  [[ ! -f "$fpath" ]] && continue
  file "$fpath" 2>/dev/null | grep -q 'text' || continue

  # 行尾空格和Tab → 删除
  # 零宽空格(U+200B) → 删除
  # 零宽不连字(U+200C) → 删除
  # 零宽连字(U+200D) → 删除
  # BOM/零宽不换行空格(U+FEFF/65279) → 删除
  # U+0080-U+00A0 控制字符 → 删除
  sed -i'' \
    -e 's/[ 	]\+$//g' \
    -e $'s/\xe2\x80\x8b//g' \
    -e $'s/\xe2\x80\x8c//g' \
    -e $'s/\xe2\x80\x8d//g' \
    -e $'s/\xef\xbb\xbf//g' \
    -e $'s/[\x80-\xa0]//g' \
    "$fpath" 2>/dev/null || true
done <<< "$CHANGED"

exit 0
