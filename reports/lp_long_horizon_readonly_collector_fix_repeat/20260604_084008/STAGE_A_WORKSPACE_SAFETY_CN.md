# Stage A — Workspace 安全检查

- run_id: 20260604_084008
- repo: /opt/lpbot/lp-bot-v3-origin-check
- branch: feat/supabase-postgres-deployment
- HEAD: 44954ba research: smoke long horizon readonly collector 20260604_081432
- 阶段: LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1

## git fetch

`git fetch origin` 已执行, HEAD 与 origin/main + feat/supabase-postgres-deployment
同步, 无冲突回写. 当前 HEAD 44954ba 是上一阶段 smoke_v1 提交.

## git status --short 摘要

| 类型 | 路径 | 判定 | 处理 |
| --- | --- | --- | --- |
| ?? | .runtime.shadow.env | 历史部署期生成物（.gitignore 排除） | 不参与本任务；不 add |
| ?? | CLAUDE.md | 项目指令文件，未跟踪 | 不参与本任务；不 add |
| ?? | reports/lp_base_10u_probe_execution_runtime/20260602_*/ | 历史 runtime reports | 不参与本任务；不 add |
| ?? | reports/lp_base_10u_probe_final_execution_review/20260602_173525/ | 历史 review | 同上 |
| ?? | scripts/__pycache__/ | Python 缓存 | 不参与本任务；不 add |
| ?? | scripts/reports/ | 历史脚本输出 | 不参与本任务；不 add |
| ?? | tests/__pycache__/ | Python 缓存 | 不参与本任务；不 add |

## 结论

无与本任务冲突的"非本任务相关 dirty 文件". 本任务产生的所有新增写入均落在
`reports/lp_long_horizon_readonly_collector_fix_repeat/20260604_084008/` 与
`data/lp_long_horizon/20260604_084008/`. 不会污染其他任务产物.

## 关键保护（复核）

- 当前分支: `feat/supabase-postgres-deployment`
- 没有改动 cmd/lpbot / cmd/lpbot-live 入口
- 没有改动 configs/config.live.toml / configs/config.canary.toml
- 没有改动 internal/adapters/{chain/solana,wallet,mev} 执行侧
- 没有改动 migrations/postgres 生产迁移
- 本任务新增 4 个 lib (lp_long_horizon/{adapters,utils,storage,classify}) +
  1 个 runner (lp_long_horizon_readonly_real_data_smoke_v1.py) +
  1 个 pytest
- 写路径严格限定 `data/lp_long_horizon/20260604_084008/` + `reports/lp_long_horizon_readonly_collector_fix_repeat/20260604_084008/`
- 不启动 daemon, 不跑 7d/14d/30d

Stage A 通过. 继续 Stage B.
