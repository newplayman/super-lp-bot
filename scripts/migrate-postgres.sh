#!/usr/bin/env bash
# scripts/migrate-postgres.sh
#
# Thin wrapper around the canonical Go-based Postgres migration runner
# (bin/lpbot-migrate-postgres, built from cmd/lpbot-migrate-postgres).
#
# This script is intentionally minimal: it does NOT parse SQL, does NOT
# call psql, does NOT maintain its own schema_migrations table, and does
# NOT auto-load .env.canary / .env.live. All migration semantics —
# ordering, transaction-per-file, checksum tracking, fail-closed on
# mismatch, canary/live DSN rejection — live in Go.
#
# Use one of the Makefile targets instead of running this script
# directly when possible:
#
#   make migrate-postgres          # apply
#   make migrate-postgres-plan     # show pending
#   make migrate-postgres-status   # show applied + pending
#
# Modes (selected by first arg, default: apply):
#   apply | plan | status
#
# Exit codes mirror the Go runner:
#   0 success / no-op
#   1 migration error
#   2 DSN / usage error
#   3 checksum mismatch

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${ROOT_DIR}/bin/lpbot-migrate-postgres"

if [[ ! -x "${BIN}" ]]; then
  echo "error: ${BIN} not built." >&2
  echo "hint:  run \`make build-migrate-postgres\` first (or \`make migrate-postgres\`)." >&2
  exit 2
fi

# Pass through all arguments. The Go runner is the single source of truth
# for which env vars are read (POSTGRES_DSN, DATABASE_URL) and which are
# forbidden (LPBOT_CANARY, LPBOT_LIVE, CANARY_DSN, LIVE_DSN, plus DSN
# strings containing the "canary" or "live" token). This wrapper does
# not source any .env file on the operator's behalf.
exec "${BIN}" "$@"
