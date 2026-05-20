#!/usr/bin/env bash
# audit_shadow_vps.sh
# Audits lp-bot VPS shadow deployment end-to-end and prints a compact verdict.

set -euo pipefail

ROOT_DIR="${LPBOT_ROOT:-/opt/lpbot/lp-bot-v3}"
SERVICE_NAME="${LPBOT_SERVICE:-lpbot-shadow}"
TARGET_BRANCH="${LPBOT_BRANCH:-feat/supabase-postgres-deployment}"
DURATION_SEC="${1:-900}" # 15 minutes default
SAMPLE_INTERVAL_SEC="${2:-30}"
LPBOT_AUTOINSTALL_TOOLS="${LPBOT_AUTOINSTALL_TOOLS:-0}"

SUDO="${SUDO:-sudo}"
LOG_FILE="${TMPDIR:-/tmp}/lpbot-shadow-audit-$(date +%Y%m%d%H%M%S).log"

PASS=0
WARN=0
FAIL=0

timestamp() {
  date -u "+%Y-%m-%d %H:%M:%S UTC"
}

say() {
  echo "[$(timestamp)] $*"
}

pass() {
  PASS=$((PASS + 1))
  echo "PASS: $*"
}

warn() {
  WARN=$((WARN + 1))
  echo "WARN: $*"
}

fail() {
  FAIL=$((FAIL + 1))
  echo "FAIL: $*"
}

note() {
  echo "INFO: $*"
}

require_file() {
  if [ -f "$1" ]; then
    pass "$2 exists"
  else
    fail "$2 missing: $1"
  fi
}

require_dir() {
  if [ -d "$1" ]; then
    pass "$2 exists"
  else
    fail "$2 missing: $1"
  fi
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

ensure_tool() {
  local cmd="$1"
  local pkg="${2:-$cmd}"

  if has_command "$cmd"; then
    return 0
  fi

  if [ "$LPBOT_AUTOINSTALL_TOOLS" != "1" ]; then
    warn "$cmd missing (set LPBOT_AUTOINSTALL_TOOLS=1 to auto-install)"
    return 1
  fi

  note "attempting to auto-install $cmd ($pkg)"
  if has_command apt-get; then
    $SUDO apt-get update -y >/tmp/lpbot_apt_update.log 2>&1 || true
    if $SUDO apt-get install -y "$pkg" >>/tmp/lpbot_apt_update.log 2>&1; then
      pass "installed $cmd via apt-get package $pkg"
      return 0
    fi
  elif has_command dnf; then
    if $SUDO dnf install -y "$pkg" >/tmp/lpbot_dnf_install.log 2>&1; then
      pass "installed $cmd via dnf package $pkg"
      return 0
    fi
  elif has_command yum; then
    if $SUDO yum install -y "$pkg" >/tmp/lpbot_yum_install.log 2>&1; then
      pass "installed $cmd via yum package $pkg"
      return 0
    fi
  else
    warn "no package manager available to install $cmd"
    return 1
  fi

  fail "auto-install for $cmd failed"
  return 1
}

is_clean_output() {
  if [ -z "${1:-}" ]; then
    fail "empty output for $2"
  fi
}

expect_exact_match() {
  if [ "$1" = "$2" ]; then
    pass "$3 expected=$2 current=$1"
  else
    fail "$3 mismatch expected=$2 current=$1"
  fi
}

say "Start VPS shadow audit"
say "ROOT_DIR=$ROOT_DIR"
say "SERVICE_NAME=$SERVICE_NAME"
say "TARGET_BRANCH=$TARGET_BRANCH"
say "DURATION_SEC=$DURATION_SEC"
say "SAMPLE_INTERVAL_SEC=$SAMPLE_INTERVAL_SEC"
say "LOG_FILE=$LOG_FILE"

{
  echo "lpbot-shadow audit started at $(timestamp)"
  echo "ROOT_DIR=$ROOT_DIR"
  echo "SERVICE_NAME=$SERVICE_NAME"
  echo "TARGET_BRANCH=$TARGET_BRANCH"
  echo "DURATION_SEC=$DURATION_SEC"
  echo "SAMPLE_INTERVAL_SEC=$SAMPLE_INTERVAL_SEC"
} > "$LOG_FILE"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

{
  say "==== 1) deployment path and legacy leftovers ===="
  require_dir "$ROOT_DIR" "VPS deployment directory"
  if [ -d /opt/lpbot/v3 ]; then
    fail "legacy path exists: /opt/lpbot/v3"
  else
    pass "legacy path cleaned: /opt/lpbot/v3"
  fi
  if [ -d /opt/lpbot/lp-bot-mvp ]; then
    fail "legacy path exists: /opt/lpbot/lp-bot-mvp"
  else
    pass "legacy path cleaned: /opt/lpbot/lp-bot-mvp"
  fi
  if [ -d /opt/lpbot/lp-bot ]; then
    fail "legacy path exists: /opt/lpbot/lp-bot"
  else
    pass "legacy path cleaned: /opt/lpbot/lp-bot"
  fi
}

{
  say "==== 2) git branch / repo provenance ===="
  if [ -d "$ROOT_DIR/.git" ]; then
    pass "git repository exists"
    current_branch="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)"
    current_commit="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
    origin_url="$(git -C "$ROOT_DIR" remote get-url origin 2>/dev/null || true)"
    if [ -n "$origin_url" ]; then
      pass "git origin is configured: $origin_url"
    else
      fail "git origin not configured"
    fi
    if [ "$current_branch" = "$TARGET_BRANCH" ]; then
      pass "git branch is $TARGET_BRANCH (current=$current_branch/$current_commit)"
    else
      fail "git branch mismatch current=$current_branch expected=$TARGET_BRANCH"
    fi
    if git -C "$ROOT_DIR" status --short | grep -q .; then
      warn "working tree has local changes"
    else
      pass "working tree is clean"
    fi
  else
    fail "git repository not found in $ROOT_DIR"
  fi
}

{
  say "==== 3) systemd service binding and config paths ===="
  if $SUDO systemctl status "$SERVICE_NAME" >/dev/null 2>&1; then
    pass "systemd unit present and systemctl can read $SERVICE_NAME"
  else
    fail "systemd unit not accessible: $SERVICE_NAME"
  fi
  service_status="$($SUDO systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)"
  expect_exact_match "$service_status" "active" "$SERVICE_NAME active state"

  exec_start="$($SUDO systemctl show -p ExecStart "$SERVICE_NAME" --value 2>/dev/null || true)"
  if [[ "$exec_start" == *"/opt/lpbot/lp-bot-v3/bin/lpbot-shadow"* ]]; then
    pass "service ExecStart points to /opt/lpbot/lp-bot-v3/bin/lpbot-shadow"
  else
    fail "service ExecStart unexpected: ${exec_start:-<empty>}"
  fi

  cfg="$ROOT_DIR/configs/config.shadow.toml"
  require_file "$cfg" "config.shadow.toml"
  if grep -Eq 'backend[[:space:]]*=[[:space:]]*"postgres"' "$cfg"; then
    pass "config.shadow backend is postgres"
  else
    fail "config.shadow backend is not postgres"
  fi
  if grep -Eq '^postgres_dsn[[:space:]]*=[[:space:]]*"\$\{DATABASE_URL\}"' "$cfg"; then
    pass "config.shadow postgres_dsn uses DATABASE_URL"
  else
    fail "config.shadow postgres_dsn not from DATABASE_URL"
  fi
  if [ -f /etc/systemd/system/"$SERVICE_NAME".service.d/10-env.conf ]; then
    pass "drop-in 10-env.conf exists"
    if grep -Fq 'EnvironmentFile=/opt/lpbot/lp-bot-v3/.env.postgres' "/etc/systemd/system/$SERVICE_NAME.service.d/10-env.conf"; then
      pass "drop-in uses /opt/lpbot/lp-bot-v3/.env.postgres"
    else
      fail "drop-in does not load /opt/lpbot/lp-bot-v3/.env.postgres"
    fi
    if grep -Fq 'EnvironmentFile=/opt/lpbot/lp-bot-v3/.env.redis' "/etc/systemd/system/$SERVICE_NAME.service.d/10-env.conf"; then
      pass "drop-in uses /opt/lpbot/lp-bot-v3/.env.redis"
    else
      fail "drop-in does not load /opt/lp-bot/lp-bot-v3/.env.redis"
    fi
  else
    fail "drop-in /etc/systemd/system/$SERVICE_NAME.service.d/10-env.conf missing"
  fi
}

{
  say "==== 4) runtime env and connectivity ===="
  if [ -f "$ROOT_DIR/.env.postgres" ]; then
    pass ".env.postgres present"
  else
    fail ".env.postgres missing"
  fi
  if [ -f "$ROOT_DIR/.env.redis" ]; then
    pass ".env.redis present"
  else
    warn ".env.redis missing (optional placeholder only)"
  fi

  set +u
  if [ -f "$ROOT_DIR/.env.postgres" ]; then
    # shellcheck disable=SC1090
    set -a
    source "$ROOT_DIR/.env.postgres"
    set +a
  fi
  set -u

  if [ -n "${DATABASE_URL:-}" ]; then
    pass "DATABASE_URL is set in env file context"
  else
    fail "DATABASE_URL is empty"
  fi
  if [ -n "${REDIS_URL:-}" ]; then
    pass "REDIS_URL is set"
  else
    warn "REDIS_URL is empty (expected for later integration)"
  fi

  if has_command ss; then
    if ss -lnt | awk '{print $4}' | grep -q ':5432' && ss -lnt | awk '{print $4}' | grep -q ':54322'; then
      pass "ports 5432 and 54322 both listening"
    elif ss -lnt | awk '{print $4}' | grep -q ':54322'; then
      pass "supabase postgres port 54322 is listening"
      warn "local postgres 5432 is not listening"
    else
      fail "postgres service not listening on 54322"
    fi
  else
    warn "ss command not available, skip listener check"
  fi
}

{
  say "==== 5) DB/Redis connectivity ===="
  if ensure_tool psql postgresql-client && [ -n "${DATABASE_URL:-}" ]; then
    if psql "$DATABASE_URL" -tAc "select 1;" >/tmp/lpbot_audit_db_ok 2>&1; then
      pass "psql can connect using DATABASE_URL"
      db_name="$(psql "$DATABASE_URL" -tAc "select current_database();" 2>/dev/null | tr -d '[:space:]')"
      if [ -n "$db_name" ]; then
        pass "connected database: $db_name"
      else
        warn "could not resolve current_database()"
      fi
      for t in transactions positions pools pool_score_history pnl_ledger risk_events kill_switch_state config_snapshots; do
        if psql "$DATABASE_URL" -tAc "SELECT to_regclass('public.$t') IS NOT NULL;" 2>/dev/null | grep -q '^t'; then
          pass "table exists: public.$t"
        else
          fail "table missing: public.$t"
        fi
      done
    else
      fail "psql connect/check failed with DATABASE_URL"
    fi
  else
    warn "psql unavailable or DATABASE_URL empty; skip DB checks"
  fi

  if [ -n "${REDIS_URL:-}" ] && ensure_tool redis-cli redis-tools; then
    if redis-cli -u "${REDIS_URL}" ping | grep -q PONG; then
      pass "redis ping success"
    else
      fail "redis ping failed"
    fi
  elif [ -n "${REDIS_URL:-}" ]; then
    warn "redis-cli unavailable, cannot validate REDIS_URL"
  else
    warn "REDIS_URL empty, skip redis check"
  fi
}

{
  say "==== 6) process / log health snapshot ===="
  pgrep -af "$ROOT_DIR/bin/lpbot-shadow" >> "$LOG_FILE" 2>&1 || true
  pids="$(pgrep -fa "$ROOT_DIR/bin/lpbot-shadow" | awk '{print $1}')"
  if [ -n "$pids" ]; then
    pass "lpbot-shadow process exists"
  else
    fail "no lpbot-shadow process found"
  fi
  if has_command curl; then
    tmp_metrics="/tmp/lpbot-shadow-metrics.txt"
    metrics_http="$(curl -sS -o "$tmp_metrics" -w '%{http_code}' --max-time 5 http://127.0.0.1:9090/metrics || true)"
    if [ "${metrics_http}" = "200" ] && grep -q '^# HELP ' "$tmp_metrics" 2>/dev/null; then
      pass "metrics endpoint returns Prometheus payload"
    else
      warn "metrics endpoint unavailable (code=${metrics_http})"
    fi
  else
    warn "curl unavailable, skip metrics endpoint check"
  fi

  if has_command go; then
    pass "Go toolchain exists"
  else
    warn "Go toolchain unavailable"
  fi
}

{
  say "==== 7) service stability sampling ===="
  sample_count=0
  sample_fail=0
  iterations=$((DURATION_SEC / SAMPLE_INTERVAL_SEC))
  if [ "$iterations" -lt 1 ]; then
    iterations=1
  fi
  i=0
  while [ "$i" -lt "$iterations" ]; do
    if $SUDO systemctl is-active --quiet "$SERVICE_NAME"; then
      pass "sample $((i + 1))/$iterations active"
    else
      sample_fail=$((sample_fail + 1))
      fail "sample $((i + 1))/$iterations service not active"
    fi
    i=$((i + 1))
    sample_count=$((sample_count + 1))
    if [ "$i" -lt "$iterations" ]; then
      sleep "$SAMPLE_INTERVAL_SEC"
    fi
  done
  if [ "$sample_fail" -eq 0 ]; then
    pass "stability sampling no active-state flips (${sample_count} samples)"
  else
    fail "stability sampling had $sample_fail inactive samples"
  fi
}

{
  say "==== 8) log anomaly scan ===="
  if has_command journalctl; then
    since_ts=$(( $(date +%s) - DURATION_SEC ))
    recent=$(journalctl -u "$SERVICE_NAME" --since "@${since_ts}" --no-pager 2>/dev/null | grep -Ei "panic|fatal|error|failed|INVARIANT" || true)
    if [ -z "$recent" ]; then
      pass "no panic/fatal/error logs in last ${DURATION_SEC}s"
    else
      fail "log contains panic/fatal/error in last ${DURATION_SEC}s"
      echo "---- matched log lines ----"
      echo "$recent" | head -20
      echo "---- end matched log lines ----"
    fi
  else
    warn "journalctl unavailable, skip log scan"
  fi
}

{
  echo "==== audit summary ===="
  echo "PASS=$PASS WARN=$WARN FAIL=$FAIL"
  if [ "$FAIL" -eq 0 ]; then
    echo "AUDIT_VERDICT=PASS"
  elif [ "$FAIL" -le 1 ]; then
    echo "AUDIT_VERDICT=WARN"
  else
    echo "AUDIT_VERDICT=FAIL"
  fi
  echo "log: $LOG_FILE"
}

if [ "$FAIL" -eq 0 ]; then
  if [ "$WARN" -eq 0 ]; then
    say "Verdict: PASS"
    exit 0
  fi
  say "Verdict: PASS_WITH_WARNINGS"
  exit 0
fi
say "Verdict: FAIL"
exit 1
