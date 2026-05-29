# VPS_DB_NOT_READY

- reason: VPS active workspace does not expose POSTGRES_DSN or DATABASE_URL after sourcing .env and .env.chain.
- consequence: fixed-horizon VPS position lifecycle materialization cannot run safely.
- secondary issue: `git fetch origin` on VPS failed with `.git/FETCH_HEAD: Permission denied`.
- no reset / no pull / no overwrite was attempted.
- recommended_next_stage: FIXED_HORIZON_DB_OR_SCHEMA_FIX
- tiny_canary_allowed: no