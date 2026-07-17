#!/usr/bin/env bash
# Optional installer for the hx-init commit-msg Git hook.
# It only writes .git/hooks/commit-msg after explicit opt-in.
set -euo pipefail

FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  bash .agents/hooks/install_commit_msg_hook.sh [--force]

Installs a local Git commit-msg hook that requires commit messages like:
  [feat] add installer
  [fix] repair hook parser

The installer does not overwrite an existing non-hx-init commit-msg hook unless
--force is provided.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "[hx-init] Not inside a Git repository; cannot install commit-msg hook." >&2
  exit 1
fi

check_hook="$repo_root/.agents/hooks/check_commit_msg.sh"
if [[ ! -f "$check_hook" ]]; then
  echo "[hx-init] Missing $check_hook; install shared hooks first." >&2
  exit 1
fi

hook_path="$(git -C "$repo_root" rev-parse --git-path hooks/commit-msg)"
case "$hook_path" in
  /*) ;;
  *) hook_path="$repo_root/$hook_path" ;;
esac

mkdir -p "$(dirname "$hook_path")"

if [[ -e "$hook_path" ]] && ! grep -q "hx-init managed commit-msg hook" "$hook_path" 2>/dev/null; then
  if [[ "$FORCE" -ne 1 ]]; then
    cat >&2 <<EOF
[hx-init] Existing commit-msg hook found:
  $hook_path

No changes made. Integrate manually or re-run with --force to replace it.
EOF
    exit 0
  fi
fi

cat >"$hook_path" <<'EOF'
#!/usr/bin/env bash
# hx-init managed commit-msg hook
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
exec bash "$repo_root/.agents/hooks/check_commit_msg.sh" "$@"
EOF

chmod 755 "$hook_path"
chmod 755 "$check_hook" 2>/dev/null || true

echo "[hx-init] Installed commit-msg hook -> $hook_path"
