# VPS DB Quick Check

- workspace: `/opt/lpbot/lp-bot-v3-origin-check`
- data_source: `vps_postgres`
- env_source: `.runtime.shadow.env`
- db_connect: `ok`
- db_name: `lpbot_shadow`
- db_user: `lpbot`
- secret_leak_in_report: `no`
- note:
  - 本报告只确认 VPS Postgres 链路可用。
  - 未在本地报告中写入 `DATABASE_URL` / `POSTGRES_DSN` 明文。
