# Stage A — Workspace 安全检查

- run_id: 20260604_130353
- repo: /opt/lpbot/lp-bot-v3-origin-check
- branch: feat/supabase-postgres-deployment
- HEAD: bc4791f research: staged run request long horizon readonly collector 20260604_123955
- 阶段: LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1

## git fetch

`git fetch origin` 已执行, HEAD 与 origin 同步, 无冲突回写. 当前 HEAD bc4791f
是上一阶段 staged_request 提交.

## git status --short 摘要

| 类型 | 路径 | 判定 | 处理 |
| --- | --- | --- | --- |
| ?? | .runtime.shadow.env | 历史部署期生成物（.gitignore 排除） | 不参与本任务；不 add |
| ?? | CLAUDE.md | 项目指令文件，未跟踪 | 不参与本任务；不 add |
| ?? | reports/lp_base_10u_probe_execution_runtime/20260602_*/ | 历史 runtime reports | 不参与本任务；不 add |
| ?? | reports/lp_base_10u_probe_final_execution_review/20260602_173525/ | 历史 review | 同上 |
| ?? | scripts/__pycache__/ | Python 缓存 | 不参与本任务；不 add |
| ?? | scripts/lp_long_horizon/{__pycache__,adapters/__pycache__,classify/__pycache__,storage/__pycache__,utils/__pycache__}/ | Python 缓存 | 不参与本任务；不 add |
| ?? | scripts/reports/ | 历史脚本输出 | 不参与本任务；不 add |
| ?? | tests/__pycache__/ | Python 缓存 | 不参与本任务；不 add |

## 结论

无与本任务冲突的"非本任务相关 dirty 文件". 本任务产生的所有新增写入均落在:
- `reports/lp_long_horizon_readonly_collector_6h_run/20260604_130353/`
- `data/lp_long_horizon/20260604_130353/`

不会污染其他任务产物.

## 关键保护（复核）

- 当前分支: `feat/supabase-postgres-deployment`
- 没有改动 cmd/lpbot / cmd/lpbot-live 入口
- 没有改动 configs/config.live.toml / configs/config.canary.toml
- 没有改动 internal/adapters/{chain/solana,wallet,mev} 执行侧
- 没有改动 migrations/postgres 生产迁移
- 没有启用 systemd / cron
- 6h 跑用 tmux 短期后台 (1 session, 6h 后杀 session), 不是 daemon
- 写路径严格限定 `reports/.../6h_run/20260604_130353/` + `data/lp_long_horizon/20260604_130353/`
- 不读取 .env / .runtime.shadow.env / *.keystore

Stage A 通过. 继续 Stage B.
