#!/usr/bin/env bash
# deploy_shadow_release.sh
# Deploy/rollback helper for VPS lp-bot shadow service.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ACTION="${1:-deploy}"
TARGET_REF_INPUT="${2:-}"

HOST="${LPBOT_HOST:-lpbot@157.173.123.24}"
KEY="${LPBOT_KEY:-$HOME/.ssh/lpbot_ed25519}"
REMOTE_ROOT="${LPBOT_ROOT:-/opt/lpbot/lp-bot-v3}"
TARGET_BRANCH="${LPBOT_BRANCH:-feat/supabase-postgres-deployment}"
SERVICE_NAME="${LPBOT_SERVICE:-lpbot-shadow}"
REMOTE_NAME="${LPBOT_REMOTE_NAME:-origin}"
SUDO="${SUDO:-sudo}"
SKIP_BUILD="${LPBOT_SKIP_BUILD:-0}"
RUN_AUDIT="${LPBOT_RUN_AUDIT:-1}"
AUDIT_WINDOW_SEC="${LPBOT_AUDIT_WINDOW_SEC:-180}"
AUDIT_SAMPLE_SEC="${LPBOT_AUDIT_SAMPLE_SEC:-15}"
RESTART_TIMEOUT_SECONDS="${LPBOT_SHADOW_RESTART_TIMEOUT_SECONDS:-120}"
CONFIRM="${LPBOT_CONFIRM_DEPLOYMENT:-YES}"
STATE_DIR="${LPBOT_RELEASE_STATE_DIR:-$HOME/.lpbot-ops/releases}"
TELEGRAM_BOT_TOKEN="${LPBOT_TELEGRAM_BOT_TOKEN:?ERROR: LPBOT_TELEGRAM_BOT_TOKEN is required}"
TELEGRAM_CHAT_ID="${LPBOT_TELEGRAM_CHAT_ID:?ERROR: LPBOT_TELEGRAM_CHAT_ID is required}"

log() {
  printf '%s\n' "$*"
}

fatal() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

notify_telegram() {
  local message="$1"
  if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    return 0
  fi
  /usr/bin/curl -fsSL -X POST \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"${TELEGRAM_CHAT_ID}\",\"text\":\"${message}\",\"disable_web_page_preview\":true}" \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" >/dev/null || true
}

require_confirmation() {
  if [ "$CONFIRM" != "YES" ]; then
    fatal "LPBOT_CONFIRM_DEPLOYMENT must be YES for execution"
  fi
}

run_ssh() {
  ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=20 "$HOST" "$@"
}

validate_local() {
  local status
  status="$(git -C "$ROOT_DIR" status --short || true)"
  if [ -n "$status" ]; then
    if [ "${LPBOT_ALLOW_DIRTY_WORKTREE:-NO}" != "YES" ]; then
      log "local worktree has uncommitted changes and LPBOT_ALLOW_DIRTY_WORKTREE is not YES"
      return 1
    fi
  fi
  if [ ! -f "$KEY" ]; then
    fatal "ssh key missing: $KEY"
  fi
  return 0
}

run_remote_release() {
  local target_ref="$1"
  local result
  local remote_script_file

  remote_script_file="$(mktemp)"
  trap '/bin/rm -f "$remote_script_file"' RETURN

  cat <<'REMOTE_SCRIPT' > "$remote_script_file"
set -euo pipefail

if [ ! -d "$REMOTE_ROOT/.git" ]; then
  echo "remote repository not found: $REMOTE_ROOT/.git" >&2
  exit 1
fi

cd "$REMOTE_ROOT"
git fetch --all --prune --tags

if [ -z "$TARGET_REF" ] || [ "$TARGET_REF" = "$TARGET_BRANCH" ]; then
  git checkout "$TARGET_BRANCH"
  git reset --hard "$REMOTE_NAME/$TARGET_BRANCH"
else
  case "$TARGET_REF" in
    [0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]*)
      if ! git rev-parse -q --verify "${TARGET_REF}^{commit}" >/dev/null 2>&1; then
        echo "cannot resolve commit ${TARGET_REF}" >&2
        exit 1
      fi
      git checkout --detach "$TARGET_REF"
      ;;
    *)
      if git show-ref --verify --quiet "refs/heads/${TARGET_REF}"; then
        git checkout "$TARGET_REF"
      elif git show-ref --verify --quiet "refs/remotes/$REMOTE_NAME/${TARGET_REF}"; then
        git checkout -B "$TARGET_REF" "$REMOTE_NAME/$TARGET_REF"
      else
        if ! git fetch --quiet "$REMOTE_NAME" "${TARGET_REF}:${TARGET_REF}"; then
          echo "cannot resolve ref ${TARGET_REF}" >&2
          exit 1
        fi
        git checkout "$TARGET_REF"
      fi
      ;;
  esac
fi

git status --short

if [ "$SKIP_BUILD" != "1" ]; then
  make build-shadow
fi

$SUDO systemctl daemon-reload
$SUDO systemctl enable --now "$SERVICE_NAME"
$SUDO systemctl restart "$SERVICE_NAME"

attempts=$((RESTART_TIMEOUT_SECONDS / 3))
if [ "$attempts" -lt 1 ]; then
  attempts=1
fi
i=0
while [ "$i" -lt "$attempts" ]; do
  if $SUDO systemctl is-active --quiet "$SERVICE_NAME"; then
    break
  fi
  i=$((i + 1))
  sleep 3
done

if ! $SUDO systemctl is-active --quiet "$SERVICE_NAME"; then
  $SUDO systemctl status "$SERVICE_NAME" --no-pager --full || true
  echo "service did not become active: $SERVICE_NAME" >&2
  exit 1
fi

if [ "$RUN_AUDIT" = "1" ] && [ -x "$REMOTE_ROOT/scripts/audit_shadow_vps.sh" ]; then
  "$REMOTE_ROOT/scripts/audit_shadow_vps.sh" "$AUDIT_WINDOW_SEC" "$AUDIT_SAMPLE_SEC" || true
fi

echo "REMOTE_REF=$(git rev-parse --short HEAD)"
echo "REMOTE_BRANCH=$(git rev-parse --abbrev-ref HEAD)"
REMOTE_SCRIPT

  result="$(
    run_ssh env \
      REMOTE_ROOT="$REMOTE_ROOT" \
      TARGET_REF="$target_ref" \
      TARGET_BRANCH="$TARGET_BRANCH" \
      SERVICE_NAME="$SERVICE_NAME" \
      REMOTE_NAME="$REMOTE_NAME" \
      SUDO="$SUDO" \
      SKIP_BUILD="$SKIP_BUILD" \
      RUN_AUDIT="$RUN_AUDIT" \
      AUDIT_WINDOW_SEC="$AUDIT_WINDOW_SEC" \
      AUDIT_SAMPLE_SEC="$AUDIT_SAMPLE_SEC" \
      RESTART_TIMEOUT_SECONDS="$RESTART_TIMEOUT_SECONDS" \
      bash -s < "$remote_script_file"
  )"
  echo "$result"
}

record_release() {
  local mode="$1"
  local ref="$2"
  local branch="$3"
  mkdir -p "$STATE_DIR"
  printf '%s\t%s\t%s\t%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$mode" \
    "$ref" \
    "$branch" >> "$STATE_DIR/shadow-release.log"
}

deploy() {
  local target_ref="${1:-$TARGET_BRANCH}"
  local output
  local ref branch

  require_confirmation
  validate_local
  log "deploy start: target_ref=${target_ref} host=${HOST} root=${REMOTE_ROOT}"

  if ! output="$(run_remote_release "$target_ref")"; then
    notify_telegram "🚨 LP-Bot shadow deploy failed (host=$HOST, target=$target_ref)"
    fatal "remote release failed"
  fi

  ref="$(printf '%s\n' "$output" | awk -F= '/^REMOTE_REF=/{print $2}')"
  branch="$(printf '%s\n' "$output" | awk -F= '/^REMOTE_BRANCH=/{print $2}')"
  if [ -z "$ref" ]; then
    ref="unknown"
  fi
  if [ -z "$branch" ]; then
    branch="unknown"
  fi

  record_release "deploy" "$ref" "$branch"
  log "deploy complete: ${ref} (${branch})"
  notify_telegram "✅ LP-Bot shadow deploy complete: ${ref} (${branch}) on ${HOST}"
}

rollback() {
  local target_ref="${1:-}"
  local output

  require_confirmation
  if [ -z "$target_ref" ]; then
    target_ref="$(run_ssh bash -lc "cd '$REMOTE_ROOT' && git rev-parse --short HEAD~1")"
  fi
  if [ -z "$target_ref" ]; then
    fatal "rollback target reference is empty"
  fi
  log "rollback start: target_ref=${target_ref} host=${HOST}"
  deploy "$target_ref"
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/deploy_shadow_release.sh deploy [ref]
  ./scripts/deploy_shadow_release.sh rollback [commit-or-tag]

Examples:
  LPBOT_CONFIRM_DEPLOYMENT=YES ./scripts/deploy_shadow_release.sh deploy
  LPBOT_CONFIRM_DEPLOYMENT=YES ./scripts/deploy_shadow_release.sh deploy feat/supabase-postgres-deployment
  LPBOT_CONFIRM_DEPLOYMENT=YES ./scripts/deploy_shadow_release.sh rollback
  LPBOT_CONFIRM_DEPLOYMENT=YES ./scripts/deploy_shadow_release.sh rollback abcd123
EOF
}

case "$ACTION" in
  deploy|release)
    deploy "$TARGET_REF_INPUT"
    ;;
  rollback|undo)
    rollback "$TARGET_REF_INPUT"
    ;;
  *)
    usage
    exit 2
    ;;
esac
