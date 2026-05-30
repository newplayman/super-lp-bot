# VPS DB Readiness

- workspace: `/opt/lpbot/lp-bot-v3-origin-check`
- data_source: `vps_postgres`
- runtime_env_file: `.runtime.shadow.env`
- POSTGRES_DSN_PRESENT: `no`
- DATABASE_URL_PRESENT: `yes`
- db_connectivity: `PASS`
- db_name: `lpbot_shadow`
- db_user: `lpbot`
- vps_git_fetch_required: `no`
- note: 本轮 materialization 直接使用 VPS runtime env + Postgres，只读查询后写入独立 research 表 `shadow_position_lifecycle_proof_v2`。
