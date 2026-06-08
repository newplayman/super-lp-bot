#!/usr/bin/env bash
# scripts/check_shadow_env_consistency.sh
#
# Static consistency check for shadow / canary / live deployment artifacts:
#   - deploy/systemd/lpbot-shadow.service
#   - deploy/systemd/lpbot-canary.service
#   - configs/config.shadow.toml
#   - configs/config.canary.toml
#   - .env.example, .env.postgres.example, .env.redis.example,
#     .env.dashboard.example, .env.alerting.example,
#     .env.canary.example, .env.live.example
#   - docs/runbooks/vps-shadow-deployment.md
#
# The script does NOT modify any file. It exits non-zero on any inconsistency.
# Intended to be run from CI (or `make test` if added) before a shadow build.

set -euo pipefail

ROOT_DIR="${LPBOT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT_DIR"

FAILED=0

# 1. lpbot-shadow.service must NOT load .env.canary, .env.live, or any
#    canary/live-unlock env file. We allow the term to appear in comments
#    (lines starting with #), but FAIL if it appears as an actual config
#    directive (EnvironmentFile=, Environment=, or non-comment assignment).
SHADOW_UNIT="$ROOT_DIR/deploy/systemd/lpbot-shadow.service"
if [[ -f "$SHADOW_UNIT" ]]; then
  for forbidden in .env.canary .env.live WALLET_PASSPHRASE; do
    # Strip comment lines before checking.
    if grep -vE '^\s*#' "$SHADOW_UNIT" | grep -q "$forbidden"; then
      echo "FAIL: $SHADOW_UNIT references $forbidden (shadow must not load canary/live env)" >&2
      FAILED=$((FAILED+1))
    fi
  done
  # LPBOT_CONFIRM_LIVE must NOT appear as a real key=value assignment
  # (Environment=, Set=). The shadow service may mention it in comments
  # to document the lockdown.
  if grep -vE '^\s*#' "$SHADOW_UNIT" | grep -Eq "(^|Environment=)\s*LPBOT_CONFIRM_LIVE"; then
    echo "FAIL: $SHADOW_UNIT sets LPBOT_CONFIRM_LIVE (forbidden during freeze)" >&2
    FAILED=$((FAILED+1))
  fi
  # shadow should reference .env.postgres (DSN needed for store backend)
  if ! grep -q ".env.postgres" "$SHADOW_UNIT"; then
    echo "FAIL: $SHADOW_UNIT does not load .env.postgres (shadow cannot resolve \${DATABASE_URL})" >&2
    FAILED=$((FAILED+1))
  fi
else
  echo "FAIL: $SHADOW_UNIT not found" >&2
  FAILED=$((FAILED+1))
fi

# 2. lpbot-canary.service must load .env.canary (which must pin LPBOT_CONFIRM_LIVE=NO).
CANARY_UNIT="$ROOT_DIR/deploy/systemd/lpbot-canary.service"
if [[ -f "$CANARY_UNIT" ]]; then
  if ! grep -q ".env.canary" "$CANARY_UNIT"; then
    echo "FAIL: $CANARY_UNIT does not load .env.canary" >&2
    FAILED=$((FAILED+1))
  fi
  # Canary service must NOT pre-set LPBOT_CONFIRM_LIVE=YES as a config
  # directive. Comments are allowed.
  if grep -vE '^\s*#' "$CANARY_UNIT" | grep -Eq "LPBOT_CONFIRM_LIVE\s*=\s*YES"; then
    echo "FAIL: $CANARY_UNIT contains LPBOT_CONFIRM_LIVE=YES (forbidden during freeze)" >&2
    FAILED=$((FAILED+1))
  fi
else
  echo "FAIL: $CANARY_UNIT not found" >&2
  FAILED=$((FAILED+1))
fi

# 3. .env.canary.example must pin LPBOT_CONFIRM_LIVE=NO.
CANARY_ENV="$ROOT_DIR/.env.canary.example"
if [[ -f "$CANARY_ENV" ]]; then
  # Pin check: filter comments first, then require LPBOT_CONFIRM_LIVE=NO.
  if ! grep -vE '^\s*#' "$CANARY_ENV" | grep -Eq "LPBOT_CONFIRM_LIVE\s*=\s*NO"; then
    echo "FAIL: $CANARY_ENV must pin LPBOT_CONFIRM_LIVE=NO (non-comment line)" >&2
    FAILED=$((FAILED+1))
  fi
  # Forbid check: filter comments first, then forbid LPBOT_CONFIRM_LIVE=YES.
  if grep -vE '^\s*#' "$CANARY_ENV" | grep -Eq "LPBOT_CONFIRM_LIVE\s*=\s*YES"; then
    echo "FAIL: $CANARY_ENV must NOT contain LPBOT_CONFIRM_LIVE=YES (non-comment line)" >&2
    FAILED=$((FAILED+1))
  fi
else
  echo "FAIL: $CANARY_ENV not found" >&2
  FAILED=$((FAILED+1))
fi

# 4. .env.live.example must not have LPBOT_CONFIRM_LIVE=YES (template only).
LIVE_ENV="$ROOT_DIR/.env.live.example"
if [[ -f "$LIVE_ENV" ]]; then
  if grep -vE '^\s*#' "$LIVE_ENV" | grep -Eq "LPBOT_CONFIRM_LIVE\s*=\s*YES"; then
    echo "FAIL: $LIVE_ENV must NOT contain LPBOT_CONFIRM_LIVE=YES (non-comment line)" >&2
    FAILED=$((FAILED+1))
  fi
fi

# 5. config.shadow.toml must reference DATABASE_URL or POSTGRES_DSN.
SHADOW_TOML="$ROOT_DIR/configs/config.shadow.toml"
if [[ -f "$SHADOW_TOML" ]]; then
  if ! grep -Eq "postgres_dsn\s*=\s*\"\\\$\{(POSTGRES_DSN|DATABASE_URL)" "$SHADOW_TOML"; then
    echo "FAIL: $SHADOW_TOML must reference POSTGRES_DSN or DATABASE_URL" >&2
    FAILED=$((FAILED+1))
  fi
fi

# 6. config.canary.toml must be loadable but referenced in canary unit.
CANARY_TOML="$ROOT_DIR/configs/config.canary.toml"
if [[ -f "$CANARY_UNIT" ]] && [[ -f "$CANARY_TOML" ]]; then
  if ! grep -q "config.canary.toml" "$CANARY_UNIT"; then
    echo "FAIL: $CANARY_UNIT does not reference config.canary.toml" >&2
    FAILED=$((FAILED+1))
  fi
fi

# 7. Runbook mentions migrate-postgres.sh / make migrate-postgres.
RUNBOOK="$ROOT_DIR/docs/runbooks/vps-shadow-deployment.md"
if [[ -f "$RUNBOOK" ]]; then
  if ! grep -q "migrate-postgres" "$RUNBOOK"; then
    echo "FAIL: $RUNBOOK does not mention migrate-postgres entry point" >&2
    FAILED=$((FAILED+1))
  fi
  if ! grep -q "lpbot-shadow.service" "$RUNBOOK"; then
    echo "FAIL: $RUNBOOK does not mention lpbot-shadow.service template" >&2
    FAILED=$((FAILED+1))
  fi
fi

# 8. scripts/migrate-postgres.sh exists and is executable.
MIGRATE_SH="$ROOT_DIR/scripts/migrate-postgres.sh"
if [[ ! -x "$MIGRATE_SH" ]]; then
  echo "FAIL: $MIGRATE_SH missing or not executable" >&2
  FAILED=$((FAILED+1))
fi

# 9. New migration for shadow_decision_trace exists.
if [[ ! -f "$ROOT_DIR/migrations/postgres/000011_shadow_decision_trace.sql" ]]; then
  echo "FAIL: migrations/postgres/000011_shadow_decision_trace.sql missing" >&2
  FAILED=$((FAILED+1))
fi

if [[ "$FAILED" -eq 0 ]]; then
  echo "OK: shadow/env/runbook consistency check passed (9 checks)"
  exit 0
else
  echo "FAIL: $FAILED consistency check(s) failed" >&2
  exit 1
fi
