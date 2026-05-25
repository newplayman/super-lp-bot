# Live Readiness 报告

当前文件作为占位模板存在。实际检查请运行：

```bash
./scripts/live_readiness_check.sh
```

脚本默认会覆盖本文件，并检查：

- 当前 commit 是否符合预期
- 必需环境变量是否齐全
- PostgreSQL schema 是否完整
- `portfolio_snapshots` 是否有最新记录
- blocker 计数是否为 0
- `shadow_outcome_labels` 是否已开始累计样本

## PASS / WARN / FAIL 语义

- `PASS`
  - commit / env / schema 全部通过
  - snapshot 也存在且可读取
- `WARN`
  - 硬门禁未失败，但 snapshot 缺失或还不新鲜，需要继续观察
- `FAIL`
  - commit 不匹配、关键环境变量缺失、schema 缺表，或其他硬门禁失败

一旦进入 `FAIL`，后续的 snapshot 问题不能把状态降级回 `WARN`。
