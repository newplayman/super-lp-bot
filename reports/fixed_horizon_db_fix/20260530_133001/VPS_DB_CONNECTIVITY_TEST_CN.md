# VPS DB Connectivity Test

- POSTGRES_DSN_PRESENT: no
- DATABASE_URL_PRESENT: yes
- DSN_PRESENT: yes
- DB_CONNECT: ok
- DB_NAME: `lpbot_shadow`
- DB_USER: `lpbot`
- connection_mode: read-only

结论：VPS 已经能在不泄露 secret 的前提下只读连接 Postgres。
