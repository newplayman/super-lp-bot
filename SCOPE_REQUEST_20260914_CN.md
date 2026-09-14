# SCOPE_REQUEST_20260914_CN.md

## 1. 本期变更请求（owner 审批）

只读闭环复跑 + B/C/D/E/F 任务交付。**无**新业务面、**无**新 daemon、
**无**与 main 的同步变更。

### 1.1 修改文件清单（已实际改动）

| 路径 | 改动类型 | 关联任务 |
|------|---------|---------|
| `.github/workflows/audit-regression.yml` | M | B |
| `.github/workflows/ci.yml` | M | B |
| `scripts/lp_rh_shadow_runner_v1_readonly.py` | M | C |
| `tests/test_lp_rh_first_step_accrual_v1_readonly.py` | M | C |
| `tests/test_lp_rh_graduation_evidence_v1_readonly.py` | M | C |
| `tests/test_lp_rh_reconciliation_v1_readonly.py` | M | C |
| `tests/test_lp_rh_shadow_runner_v1_readonly.py` | M | C |
| `tools/audit_repro/audit_repro.py` | M | B |

### 1.2 新增文件清单

| 路径 | 关联任务 |
|------|---------|
| `tests/test_lp_rh_terminal_to_ledger_e2e_v1_readonly.py` | D |
| `OBSERVE_ONLY_DECISION_RULES_CN.md` | F |
| `BLOCKERS_20260914_CN.csv` | G |
| `ACCEPTANCE_EVIDENCE_20260914_CN.md` | G |
| `CI_EVIDENCE_20260914_CN.md` | G |
| `VULNERABILITY_RESOLUTION_20260914_CN.md` | G |
| `READ_FIRST_20260914_CN.md` | G |
| `FINAL_VERDICT_20260914_CN.md` | G |
| `HANDOFF_20260914_CN.md` | G |
| `reports/lp_rh/STAGE_A_REQUALIFICATION.json` | E |
| `reports/lp_rh/audit_repro_20260914.json` | G |
| `reports/lp_rh/pytest_summary_20260914.txt` | G |

## 2. 申请 owner 决策（按优先级）

| 决策 | 推荐 | 依据 |
|------|------|------|
| 是否推送本轮 commit 到 origin | **是** | 验收物已就位；CI 闭环依赖远端 Actions 跑最终 SHA |
| 是否批准 OBSERVE_ONLY 持续运行 | **是** | 5 个长跑进程是审计基础，shutdown 需 owner 显式 |
| 是否扩大 RH 测试到 R3 REWORK 余下分支 | 否 | 不在本期 scope；下次迭代提议 |
| 是否修改 main | **否** | main 须显式同步，CLAUDE.md freeze |
| 是否重启 5 个长跑进程 | **否** | 本任务硬约束 |

## 3. 不在本期 scope 的事项（owner 显式 reopen 才做）

- 启动 paper daemon / 修改 `live_allowed` / 修 daemon 内部 cfg
- 新增采集器 / 新增 RPC provider / 修改 oracle 路径
- 修改 main 分支 / 触发 release / 关停 github action
- 把 GRADUATION_VERDICT.json verdict 字段改为 SHADOW_VALIDATED 等

## 4. 与既有交付物的一致性

- 与 `7dd4e64` (golangci-lint v2.10.0)、`fd0ffa6` (CI closeout)、
  `b7ed6f6` (READ_FIRST + W2 + BLOCKERS + OBSERVE_ONLY request)、
  `c7f692b` (register observed long-running readonly processes)、
  `4da8bc0` (W5 paper-package source + fixtures + config + ops runbook)
  无冲突；本任务在这之上**只**做：
  - B：补 schema contract（任务起点已 missing 的 schema 字段）
  - C：补 59 B-series CORE 业务失败
  - D：补真实 E2E 正控制
  - E：补只读审计 snapshot
  - F：补 OBSERVE_ONLY 决策规则
  - G：本任务闭环交付

## 5. 验收门

1. owner 视觉确认 `git diff --stat` 仅命中 §1.1 列出的 8 个文件
2. owner 视觉确认 5 个 PID 健康（`ps -p <PID>` 验证）
3. owner 在 GitHub 网页目视最终 HEAD 的 Actions 结果为 PASS
4. owner 视觉确认本任务所有 §1.2 新增文件存在

通过 → ACCEPT → owner 决定是否推送 + 是否继续 OBSERVE_ONLY。