#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATIONS_DIR="${ROOT_DIR}/migrations/postgres"

load_env_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    set -a
    . "$file"
    set +a
  fi
}

cd "$ROOT_DIR"
load_env_file ./.env.postgres
load_env_file ./.env.canary

POSTGRES_DSN="${POSTGRES_DSN:-${DATABASE_URL:-}}"
if [[ -z "${POSTGRES_DSN}" ]]; then
  echo "POSTGRES_DSN/DATABASE_URL is empty" >&2
  exit 2
fi

if [[ ! -d "${MIGRATIONS_DIR}" ]]; then
  echo "missing migrations dir: ${MIGRATIONS_DIR}" >&2
  exit 2
fi

for migration in "${MIGRATIONS_DIR}"/*.sql; do
  [[ -f "${migration}" ]] || continue
  echo "[migrate] applying $(basename "${migration}")"
  psql "${POSTGRES_DSN}" -v ON_ERROR_STOP=1 -f "${migration}"
done
