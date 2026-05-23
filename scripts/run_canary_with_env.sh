#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_env_files=(
  ".env.postgres"
  ".env.redis"
  ".env.dashboard"
  ".env.canary"
)

for rel in "${required_env_files[@]}"; do
  if [[ ! -f "${ROOT_DIR}/${rel}" ]]; then
    echo "missing required env file: ${ROOT_DIR}/${rel}" >&2
    exit 1
  fi
done

if [[ $# -eq 0 ]]; then
  cat >&2 <<'EOF'
usage:
  scripts/run_canary_with_env.sh ./bin/lpbot-live --config configs/config.canary.toml ...

loads:
  .env.postgres
  .env.redis
  .env.dashboard
  .env.canary
EOF
  exit 1
fi

set -a
. "${ROOT_DIR}/.env.postgres"
. "${ROOT_DIR}/.env.redis"
. "${ROOT_DIR}/.env.dashboard"
. "${ROOT_DIR}/.env.canary"
set +a

cd "${ROOT_DIR}"
exec "$@"
