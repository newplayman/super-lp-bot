# Shadow Research Readiness 报告

当前文件作为占位模板存在。实际检查请运行：

```bash
./scripts/shadow_research_readiness_check.sh
```

脚本默认会覆盖本文件，并检查：

- 当前 commit 是否符合预期
- `POSTGRES_DSN / DATABASE_URL` 是否可用
- `BASE_RPC_PRIMARY` 是否存在
- `goose_db_version` 是否至少到 `000010`
- `shadow_decision_trace / shadow_position_marks / shadow_outcome_labels` 是否存在
- 研究表是否已经开始产生样本

## PASS / FAIL 语义

- `PASS`
  - commit / env / Postgres / goose / 研究表全部通过
  - 可以继续执行只读 `shadow outcome backfill/report`
- `FAIL`
  - commit 不匹配、基础 env 缺失、数据库不可读、迁移未到位，或研究表缺失

## 范围边界

本检查只面向 shadow research，不要求：

- `LIVE_WALLET_ADDRESS`
- `FLASHBOTS_RPC_URL`
- `WALLET_PASSPHRASE`
- `LPBOT_CONFIRM_LIVE`

如果这些 live 变量缺失，不影响只读研究链继续运行。
