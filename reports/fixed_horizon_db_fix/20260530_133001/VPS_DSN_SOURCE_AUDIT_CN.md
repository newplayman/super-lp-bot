# VPS DSN Source Audit

- `.env`: missing
- `.env.chain`: missing
- `.env.local`: missing
- `.runtime.shadow.env` before fix: missing
- `configs/config.shadow.research.toml`: field name present, but no directly usable static DSN value
- `configs/config.shadow.toml`: field name present, but no directly usable static DSN value
- `systemd EnvironmentFile`: yes, 4 files configured
- running `lpbot-shadow` process env: PID found, but direct env extraction not relied on
- reusable DSN source: yes, from systemd EnvironmentFile chain

本轮没有打印真实 DSN。
