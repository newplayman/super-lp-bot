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
