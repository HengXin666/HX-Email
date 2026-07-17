#!/usr/bin/env bash
# Git commit-msg hook: enforce "[type] subject" messages.
# Default allowed types are conservative and can be overridden with HX_COMMIT_TYPES.
set -uo pipefail

MSG_FILE="${1:-}"
if [[ -z "$MSG_FILE" || ! -f "$MSG_FILE" ]]; then
  echo "[hx-init] commit-msg hook requires Git's commit message file path." >&2
  exit 1
fi

first_line="$(
  awk '
    /^[[:space:]]*(#|$)/ { next }
    {
      sub(/[[:space:]]+$/, "")
      print
      exit
    }
  ' "$MSG_FILE"
)"

allowed="${HX_COMMIT_TYPES:-feat fix docs style refactor perf test build ci chore revert release deps security}"
pattern_types="$(
  printf '%s\n' "$allowed" \
    | tr ',[:space:]' '\n' \
    | sed '/^$/d' \
    | sed 's/[][\\.^$*+?{}()|]/\\&/g' \
    | paste -sd'|' -
)"

if [[ -z "$first_line" ]]; then
  echo "[hx-init] Empty commit message." >&2
  echo "Expected: [feat] add user profile" >&2
  exit 1
fi

if [[ "$first_line" =~ ^\[($pattern_types)\][[:space:]][^[:space:]].* ]]; then
  exit 0
fi

cat >&2 <<EOF
[hx-init] Invalid commit message:
  $first_line

Expected format:
  [type] subject

Allowed types:
  $allowed

Examples:
  [feat] add hx-init installer
  [fix] handle empty hook input
  [docs] update usage notes

Fix it by re-running commit with a valid message:
  git commit -m "[feat] describe the change"

If you are amending the last commit:
  git commit --amend -m "[fix] describe the fix"
EOF

exit 1
