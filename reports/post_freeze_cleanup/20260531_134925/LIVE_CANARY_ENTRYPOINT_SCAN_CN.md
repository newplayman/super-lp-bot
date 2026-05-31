# Live / Canary 入口扫描

- scan file: `/Users/bendu/lp-bot/v3/reports/post_freeze_cleanup/20260531_134925/live_canary_entrypoint_scan.txt`
- total matched lines: `44`

重点结果：

- `docs/runbooks/base-canary-ops.md`
- `docs/runbooks/vps-shadow-deployment.md`
- `docs/ops/solana-meteora-dlmm-lp-preflight.md`
- `docs/ops/solana-pancake-lp-exit-lessons.md`
- `scripts/canary_cycle.sh`
- `scripts/canary_readiness_report.sh`
- `scripts/run_canary_with_env.sh`
- `scripts/live_readiness_check.sh`
- `README.md`

处理方式：

- 不删除历史文件。
- 不修改交易脚本。
- 只在 `/Users/bendu/lp-bot/v3/docs/LPBOT_RESEARCH_STATUS_CN.md` 和 `README.md` 增加冻结警示。

当前结论：

- 这些入口是历史 runbook / script 归档，不应被视为当前允许执行的操作入口。
- 当前 `tiny_canary_allowed = no`。
