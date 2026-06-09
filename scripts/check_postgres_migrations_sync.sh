#!/usr/bin/env bash
# scripts/check_postgres_migrations_sync.sh
#
# Drift check for the two postgres migration directories:
#   1. migrations/postgres/  (source of truth, in VCS)
#   2. internal/adapters/store/postgres/migrator/sql/  (embedded by
#      the Go runner via go:embed; populated by `make sync-postgres-migrations`
#      or by every build target that depends on it)
#
# The Go runner cannot use a relative `..` path with go:embed, so the
# embed target is a real copy. This script is the CI guard that makes
# sure the copy stays in sync with the source of truth.
#
# Checks:
#   * both directories exist
#   * same file list (lexically sorted)
#   * same file count
#   * same SHA256 for every shared filename
#
# Exits 0 on full agreement, 1 on any drift. The exact drift is printed
# to stderr so CI logs are actionable.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/migrations/postgres"
EMB_DIR="${ROOT_DIR}/internal/adapters/store/postgres/migrator/sql"

err() { echo "drift: $*" >&2 ; }

if [[ ! -d "${SRC_DIR}" ]]; then
  err "missing source dir: ${SRC_DIR}"
  exit 1
fi
if [[ ! -d "${EMB_DIR}" ]]; then
  err "missing embed dir: ${EMB_DIR}"
  exit 1
fi

# List files (.sql only) in each directory, sorted.
src_files=$(cd "${SRC_DIR}" && ls -1 *.sql 2>/dev/null | sort)
emb_files=$(cd "${EMB_DIR}" && ls -1 *.sql 2>/dev/null | sort)

if [[ -z "${src_files}" ]]; then
  err "source dir ${SRC_DIR} has no .sql files"
  exit 1
fi
if [[ -z "${emb_files}" ]]; then
  err "embed dir ${EMB_DIR} has no .sql files"
  exit 1
fi

# Compare file lists.
if [[ "${src_files}" != "${emb_files}" ]]; then
  err "file list differs:"
  diff <(echo "${src_files}") <(echo "${emb_files}") >&2 || true
  exit 1
fi

# Compare SHA256 of every file.
src_hashes=$(cd "${SRC_DIR}" && sha256sum *.sql | sort)
emb_hashes=$(cd "${EMB_DIR}" && sha256sum *.sql | sort)

if [[ "${src_hashes}" != "${emb_hashes}" ]]; then
  err "sha256 mismatch (filenames match; contents differ):"
  diff <(echo "${src_hashes}") <(echo "${emb_hashes}") >&2 || true
  exit 1
fi

count=$(echo "${src_files}" | wc -l)
echo "sync OK: ${count} file(s) match between ${SRC_DIR}/ and ${EMB_DIR}/"
