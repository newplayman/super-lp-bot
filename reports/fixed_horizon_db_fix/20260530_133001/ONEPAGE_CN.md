# One Page

- vps_git_fetch_fixed = no
- postgres_dsn_found = yes
- postgres_dsn_loaded_without_leak = yes
- db_connectivity = PASS
- schema_audit_ready = yes
- can_materialize_fixed_horizon_next = no
- recommended_next_stage = FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT
- tiny_canary_allowed = no

本轮已经打通了 VPS 只读 DB 链路和 schema 审计，但还没打通 VPS `git fetch origin` 的远端认证。
