# VPS DB READY CHECK FAILED

- check_time_utc: 2026-05-31T03:48:33Z
- stage: FIXED_HORIZON_COMPLETED_SAMPLE_STAGNATION_V1
- workspace: /opt/lpbot/lp-bot-v3-origin-check
- command: check POSTGRES_DSN / DATABASE_URL in .env / .env.chain

## Result
- POSTGRES_DSN_PRESENT: no
- DATABASE_URL_PRESENT: no

## Impact
- 无法连接或发现 VPS Postgres DSN，不能继续执行 VPS-only fixed-horizon stagnation proof 物化与样本统计。
- 按任务约束，必须停在该点，先补齐 DB 环境后继续。

## 依赖约束核对
- tiny_canary_allowed: no
- 不允许进行交易/写入生产表/策略路径变更

## 下一步建议
- 补齐 VPS 运行时环境中的数据库连接变量（POSTGRES_DSN 或 DATABASE_URL）。
- 建议从部署环境的 secrets 管理恢复数据库 DSN，不在仓库内明文持久化。
- 恢复后重新执行本任务。
