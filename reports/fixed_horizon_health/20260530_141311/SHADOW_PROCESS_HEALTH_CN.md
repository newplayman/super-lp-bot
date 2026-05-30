# Shadow Process Health

- lpbot-shadow running: `yes`
- PID: `3778947`
- uptime estimate: `since 2026-05-25 09:16:38 CEST`，约 `5 days`
- service state: `active (running)`
- recent restart events: `none observed`
- recent journal errors: `none observed in last 6 hours journal tail`
- live/canary process exists: `no`
- do_not_restart_recommendation: `yes`

process evidence:

- binary: `/opt/lpbot/lp-bot-v3/bin/lpbot-shadow --config=/opt/lpbot/lp-bot-v3/configs/config.shadow.toml`
- CPU time: `1h 55min 19.935s`
- memory: `32.6M`

结论：

- shadow daemon 本身在运行，不是当前 OOS flat 的直接根因。
- 当前不建议重启或恢复服务，应该继续查数据生产和 proof 覆盖链路。
