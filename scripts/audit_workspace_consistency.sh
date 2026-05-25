#!/usr/bin/env bash
# audit_workspace_consistency.sh
# Compares local v3, Git origin, and the VPS deployment checkout without mutating code.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${LPBOT_HOST:-${LPBOT_VPS_HOST:-lpbot@157.173.123.24}}"
KEY="${LPBOT_KEY:-${LPBOT_VPS_KEY:-$HOME/.ssh/lpbot_ed25519}}"
REMOTE_ROOT="${LPBOT_ROOT:-/opt/lpbot/lp-bot-v3}"
TARGET_BRANCH="${LPBOT_BRANCH:-$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo feat/supabase-postgres-deployment)}"
CONNECT_TIMEOUT="${LPBOT_SSH_TIMEOUT:-10}"

PASS=0
WARN=0
FAIL=0

say() {
  printf '%s %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" "$*"
}

pass() {
  PASS=$((PASS + 1))
  printf 'PASS: %s\n' "$*"
}

warn() {
  WARN=$((WARN + 1))
  printf 'WARN: %s\n' "$*"
}

fail() {
  FAIL=$((FAIL + 1))
  printf 'FAIL: %s\n' "$*"
}

ssh_remote() {
  ssh \
    -i "$KEY" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout="$CONNECT_TIMEOUT" \
    "$HOST" "$@"
}

local_branch="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)"
local_commit="$(git -C "$ROOT_DIR" rev-parse HEAD)"
local_short="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
local_origin="$(git -C "$ROOT_DIR" remote get-url origin 2>/dev/null || true)"
local_status="$(git -C "$ROOT_DIR" status --short)"
origin_commit="$(git -C "$ROOT_DIR" ls-remote origin "refs/heads/$TARGET_BRANCH" | awk '{print $1}')"

say "Start workspace consistency audit"
say "ROOT_DIR=$ROOT_DIR"
say "TARGET_BRANCH=$TARGET_BRANCH"
say "HOST=$HOST"
say "REMOTE_ROOT=$REMOTE_ROOT"

if [ "$local_branch" = "$TARGET_BRANCH" ]; then
  pass "local branch matches target: $local_branch"
else
  fail "local branch mismatch current=$local_branch target=$TARGET_BRANCH"
fi

if [ -n "$local_origin" ]; then
  pass "local origin configured: $local_origin"
else
  fail "local origin missing"
fi

if [ -z "$local_status" ]; then
  pass "local worktree clean at $local_short"
else
  warn "local worktree has changes"
  printf '%s\n' "$local_status"
fi

if [ -n "$origin_commit" ]; then
  pass "origin branch found: $TARGET_BRANCH ${origin_commit:0:7}"
  if [ "$local_commit" = "$origin_commit" ]; then
    pass "local HEAD matches origin/$TARGET_BRANCH"
  else
    fail "local HEAD differs from origin/$TARGET_BRANCH local=$local_short origin=${origin_commit:0:7}"
  fi
else
  fail "origin branch not found: $TARGET_BRANCH"
fi

if [ ! -f "$KEY" ]; then
  warn "ssh key missing, skipping VPS audit: $KEY"
else
  remote_payload="$(ssh_remote "
    set -euo pipefail
    root='$REMOTE_ROOT'
    printf 'remote_root=%s\n' \"\$root\"
    if [ -d \"\$root/.git\" ]; then
      printf 'remote_repo=present\n'
      git -C \"\$root\" rev-parse --abbrev-ref HEAD | sed 's/^/remote_branch=/'
      git -C \"\$root\" rev-parse HEAD | sed 's/^/remote_commit=/'
      git -C \"\$root\" rev-parse --short HEAD | sed 's/^/remote_short=/'
      git -C \"\$root\" remote get-url origin 2>/dev/null | sed 's/^/remote_origin=/' || true
      status=\"\$(git -C \"\$root\" status --short)\"
      if [ -n \"\$status\" ]; then
        printf 'remote_dirty=1\n'
        printf '%s\n' \"\$status\" | sed 's/^/remote_status=/'
      else
        printf 'remote_dirty=0\n'
      fi
    else
      printf 'remote_repo=missing\n'
    fi
    for legacy in /opt/lpbot/v3 /opt/lpbot/lp-bot-mvp /opt/lpbot/lp-bot; do
      if [ -e \"\$legacy\" ]; then
        printf 'legacy_path=%s\n' \"\$legacy\"
      fi
    done
    systemctl is-active '${LPBOT_SERVICE:-lpbot-shadow}' 2>/dev/null | sed 's/^/service_active=/' || true
  " 2>&1)" || {
    warn "VPS audit unavailable"
    printf '%s\n' "$remote_payload"
    remote_payload=""
  }

  if [ -n "$remote_payload" ]; then
    printf '%s\n' "$remote_payload"
    remote_repo="$(printf '%s\n' "$remote_payload" | awk -F= '$1=="remote_repo"{print $2; exit}')"
    remote_branch="$(printf '%s\n' "$remote_payload" | awk -F= '$1=="remote_branch"{print $2; exit}')"
    remote_commit="$(printf '%s\n' "$remote_payload" | awk -F= '$1=="remote_commit"{print $2; exit}')"
    remote_short="$(printf '%s\n' "$remote_payload" | awk -F= '$1=="remote_short"{print $2; exit}')"
    remote_dirty="$(printf '%s\n' "$remote_payload" | awk -F= '$1=="remote_dirty"{print $2; exit}')"
    legacy_count="$(printf '%s\n' "$remote_payload" | awk -F= '$1=="legacy_path"{count++} END{print count+0}')"

    if [ "$remote_repo" = "present" ]; then
      pass "VPS git repository present"
    else
      fail "VPS git repository missing at $REMOTE_ROOT"
    fi

    if [ "$remote_branch" = "$TARGET_BRANCH" ]; then
      pass "VPS branch matches target: $remote_branch"
    else
      fail "VPS branch mismatch current=${remote_branch:-<empty>} target=$TARGET_BRANCH"
    fi

    if [ "$remote_dirty" = "0" ]; then
      pass "VPS worktree clean"
    else
      warn "VPS worktree has local changes"
    fi

    if [ -n "$remote_commit" ] && [ "$remote_commit" = "$local_commit" ]; then
      pass "VPS commit matches local HEAD: ${remote_short:-${remote_commit:0:7}}"
    else
      fail "VPS commit differs from local HEAD local=$local_short vps=${remote_short:-<empty>}"
    fi

    if [ "$legacy_count" = "0" ]; then
      pass "VPS legacy project paths absent"
    else
      warn "VPS legacy project paths still exist: $legacy_count"
    fi
  fi
fi

printf 'SUMMARY pass=%d warn=%d fail=%d\n' "$PASS" "$WARN" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf 'AUDIT_VERDICT=FAIL\n'
  exit 1
fi
if [ "$WARN" -gt 0 ]; then
  printf 'AUDIT_VERDICT=WARN\n'
  exit 0
fi
printf 'AUDIT_VERDICT=PASS\n'
