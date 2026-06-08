#!/usr/bin/env bash
# scripts/migrate-postgres.sh
#
# Canonical Postgres migration entry point for lp-bot shadow/test deployments.
#
# Resolution order for the DSN:
#   1. $POSTGRES_DSN (preferred)
#   2. $DATABASE_URL (fallback)
#   3. .env.postgres (auto-loaded from LPBOT_ROOT if present)
#   4. .env.canary    (auto-loaded from LPBOT_ROOT if present)
#
# Accepts both postgres:// and postgresql:// schemes; the underlying psql
# accepts both natively.
#
# Modes (selected by first arg):
#   apply  (default) — apply all *.sql in migrations/postgres in lexical order
#   plan             — list the migrations that would be applied (no apply)
#   status           — show to_regclass() presence of every required table
#
# Failure mode: any psql error returns non-zero, set -euo pipefail enabled.
#
# This script does NOT auto-migrate live. It is intended for shadow and test
# databases only. Live canary/live use deploy/systemd/lpbot-canary.service +
# scripts/canary_cycle.sh + manual review of FORBIDDEN_ACTIONS_LOCK.json
# (see reports/lp_long_horizon_r1_pause_and_freeze/20260607_191500/).

set -euo pipefail

ROOT_DIR="${LPBOT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MIGRATIONS_DIR="${ROOT_DIR}/migrations/postgres"
MODE="${1:-apply}"

load_env_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$file"
    set +a
  fi
}

cd "$ROOT_DIR"
load_env_file ./.env.postgres
load_env_file ./.env.canary

POSTGRES_DSN="${POSTGRES_DSN:-${DATABASE_URL:-}}"
if [[ -z "${POSTGRES_DSN}" ]]; then
  echo "[migrate-postgres] POSTGRES_DSN/DATABASE_URL is empty" >&2
  echo "[migrate-postgres] hint: copy .env.postgres.example to .env.postgres and fill DATABASE_URL" >&2
  exit 2
fi

# Reject obvious live/prod DSNs that don't belong in shadow/test contexts.
# This is a defensive guard only; shadow DSNs are typically local or
# 10.x.x.x. The intent is to prevent accidentally pointing at a real prod DB.
case "${POSTGRES_DSN}" in
  *supabase.co*|*rds.amazonaws.com*|*prod*|*production*)
    if [[ "${LPBOT_MIGRATE_ALLOW_LIVE:-NO}" != "YES" ]]; then
      echo "[migrate-postgres] DSN looks like a production endpoint: ${POSTGRES_DSN%%@*}@..." >&2
      echo "[migrate-postgres] refusing to migrate. Set LPBOT_MIGRATE_ALLOW_LIVE=YES if intentional." >&2
      exit 3
    fi
    ;;
esac

if [[ ! -d "${MIGRATIONS_DIR}" ]]; then
  echo "[migrate-postgres] missing migrations dir: ${MIGRATIONS_DIR}" >&2
  exit 2
fi

# Sanity: no lexical gap in the migration numbering. If a gap exists (e.g.
# 000010 -> 000012 with no 000011) it indicates a lost migration and we
# refuse to proceed without explicit override.
EXPECTED=""
ACTUAL=""
for f in "${MIGRATIONS_DIR}"/*.sql; do
  base=$(basename "$f")
  num="${base%%_*}"
  ACTUAL="${ACTUAL}${num}"$'\n'
done
prev=""
while IFS= read -r num; do
  if [[ -z "${prev}" ]]; then
    prev="${num}"
    continue
  fi
  if [[ $((10#${num} - 10#${prev} - 1)) -ne 0 ]] && [[ $((10#${num} - 10#${prev})) -ne 1 ]]; then
    if [[ "${LPBOT_MIGRATE_ALLOW_GAP:-NO}" != "YES" ]]; then
      echo "[migrate-postgres] migration numbering gap detected between ${prev} and ${num}" >&2
      echo "[migrate-postgres] refusing to apply. Set LPBOT_MIGRATE_ALLOW_GAP=YES if intentional." >&2
      exit 4
    fi
  fi
  prev="${num}"
done <<< "${ACTUAL}"

if [[ "${MODE}" == "plan" ]]; then
  echo "[migrate-postgres] plan mode — would apply the following migrations:"
  for migration in "${MIGRATIONS_DIR}"/*.sql; do
    [[ -f "${migration}" ]] || continue
    echo "  - $(basename "${migration}")"
  done
  exit 0
fi

if [[ "${MODE}" == "status" ]]; then
  echo "[migrate-postgres] status mode — checking required tables:"
  REQUIRED_TABLES=(
    "positions"
    "transactions"
    "execution_intents"
    "portfolio_snapshots"
    "position_marks"
    "canary_events"
    "pnl_ledger"
    "shadow_decision_trace"
    "shadow_outcome_labels"
    "pools"
    "pool_score_history"
    "risk_events"
    "kill_switch_state"
  )
  for tbl in "${REQUIRED_TABLES[@]}"; do
    if psql "${POSTGRES_DSN}" -tAc "SELECT to_regclass('public.${tbl}') IS NOT NULL" 2>/dev/null | grep -q '^t$'; then
      echo "  OK   ${tbl}"
    else
      echo "  MISS ${tbl}"
    fi
  done
  # required index
  if psql "${POSTGRES_DSN}" -tAc "SELECT to_regclass('public.idx_positions_one_active_per_pool') IS NOT NULL" 2>/dev/null | grep -q '^t$'; then
    echo "  OK   idx_positions_one_active_per_pool"
  else
    echo "  MISS idx_positions_one_active_per_pool"
  fi
  exit 0
fi

if [[ "${MODE}" != "apply" ]]; then
  echo "[migrate-postgres] unknown mode: ${MODE} (expected: apply|plan|status)" >&2
  exit 2
fi

# Apply mode
echo "[migrate-postgres] DSN host: $(echo "${POSTGRES_DSN}" | sed -E 's#.*@##; s#\/.*##')"
echo "[migrate-postgres] migrations dir: ${MIGRATIONS_DIR}"
echo "[migrate-postgres] applying migrations in lexical order:"

# Track applied migrations in a per-DB marker table so re-runs are idempotent
# (this also replaces goose-style version tracking for shadow/test use).
ensure_migration_marker_table() {
  psql "${POSTGRES_DSN}" -v ON_ERROR_STOP=1 -q -c "
    CREATE TABLE IF NOT EXISTS schema_migrations (
      filename TEXT PRIMARY KEY,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  " >/dev/null
}

ensure_migration_marker_table

for migration in "${MIGRATIONS_DIR}"/*.sql; do
  [[ -f "${migration}" ]] || continue
  fname=$(basename "${migration}")

  # Skip if already applied
  applied=$(psql "${POSTGRES_DSN}" -tAc "SELECT 1 FROM schema_migrations WHERE filename='${fname}'" 2>/dev/null | tr -d '[:space:]')
  if [[ "${applied}" == "1" ]]; then
    echo "  - ${fname} (already applied, skipping)"
    continue
  fi

  # Extract only the Up section between -- +goose Up and -- +goose Down
  # (psql runs the whole file otherwise, executing DROP TABLE etc.).
  up_sql=$(awk '
    /^-- \+goose Up[[:space:]]*$/ { in_up=1; next }
    /^-- \+goose Down[[:space:]]*$/ { in_up=0; next }
    in_up { print }
  ' "${migration}")

  echo "  - ${fname}"
  echo "${up_sql}" | psql "${POSTGRES_DSN}" -v ON_ERROR_STOP=1 -q

  if [[ $? -ne 0 ]]; then
    echo "[migrate-postgres] failed at ${fname}; aborting (no further migrations applied)" >&2
    exit 5
  fi

  psql "${POSTGRES_DSN}" -v ON_ERROR_STOP=1 -q -c "
    INSERT INTO schema_migrations(filename) VALUES ('${fname}');
  " >/dev/null
done
echo "[migrate-postgres] done."
echo "[migrate-postgres] done."
