# READ_FIRST_20260914_CN.md

**owner 验收必读**：本轮任务（commit a767740 → TESTED_CODE_SHA 50a18dd）的执行概要。

## 1. 一句话摘要

只读闭环复跑 + 4 个 Gap 关闭（run_once 接真实引擎 / 严格 E2E 正控制 / 真实数据 Stage A gate / 独立干净 checkout 重验），
OBSERVE_ONLY 维持，**未启动 paper / live，未推送远端**，等 owner 视觉验收 GitHub Actions 后再决定。

## 2. 阅读顺序（10 分钟）

1. **`ACCEPTANCE_MATRIX_20260914_CN.md`** — 六维验收矩阵（push 来源 / 双 SHA / nodeid 证据 / 真数据 / 隔离诊断 / 本批更新）
2. **`FINAL_VERDICT_20260914_CN.md`** — 一表说清 PASS/FAIL、本期 vs 残留 blockers
3. **`OBSERVE_ONLY_DECISION_RULES_CN.md`** — 5 条 hard gate + 允许/阻断动作清单
4. **`ACCEPTANCE_EVIDENCE_20260914_CN.md`** — pytest / audit_repro / 5 进程审计 / fresh checkout 原文
5. **`CONTINUOUS_AND_VARIANT_EVIDENCE_CN.md`** — 95 个 R1/R2-B～E 节点 nodeid + 证据；CONTINUOUS_RUN=NOT_APPLICABLE
6. **`BLOCKERS_20260914_RC_CN.csv`** — 4 Gap 已 RESOLVED + 5 残留 OPEN
7. **`PUSH_AUTHORIZATION_CN.md`** — push 授权范围 + pre-push 自查脚本
8. **`reports/lp_rh/STAGE_A_REALDATA_SNAPSHOT.json`** — 真数据 Stage A FAIL（不冒充 PASS）

## 3. 关键事实（直接抄送）

- HEAD = `50a18dd344fc39790e0371f422ed0fb9eeefe455`（**TESTED_CODE_SHA**，本任务候选 commit）
- BASELINE_SHA = `a7677405c2ecaaf100fe01124973ffec4511abfb`（双 SHA 分离，不混用）
- TASK_STARTED_MODE = `NONE`
- HOST_EXISTING_RH_READONLY_PROCESSES = `5`（PID 列表见 OBSERVE_ONLY_DECISION_RULES_CN.md §7）
- pytest 源仓 = `5219 passed / 0 failed / 14 skipped`（5191 基线 + 18 本任务新测试）
- pytest fresh checkout = `5145 passed / 49 failed / 29 skipped`（49 fail 全是 pre-existing env，与本任务无关）
- audit_repro = `defects=0, probe_errors=0`（fresh checkout 与源仓两边都通过）
- 真实数据 Stage A verdict = **FAIL**（COVERAGE_INSUFFICIENT + STAGE_A_KEY_FIELDS_INCOMPLETE；按设计报 FAIL，不冒充 PASS）
- CONTINUOUS_RUN = **NOT_APPLICABLE**（single-shot wrapper 不能冒 PASS）
- SINGLE_SHOT = **PASS**（NAV 1000→990、PnL=-10、对账 PASS）
- CORE_PAPER_ENGINEERING_GATE = `FAIL`（已知；详见 BLOCKERS.csv）

## 4. 立即可执行（无需 owner 批准）

- 阅读本目录所有 .md
- 在本地跑 `python3 -m pytest tests/ -q --tb=line -p no:cacheprovider`
- 跑 `python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head --json-out /tmp/x.json`
- 跑 `cat reports/lp_rh/STAGE_A_REQUALIFICATION.json` 复核 5 进程
- 跑 `ps -p 2271374,157737,119849,118592,2685886` 复核存活

## 5. 需 owner 决策

| 决策 | 推荐 |
|------|------|
| 是否推送本轮 commit | 是 |
| 是否继续 OBSERVE_ONLY | 是 |
| 是否扩 scope 到 R3 REWORK 余下分支 | 否（下次迭代） |
| 是否重启 5 个长跑进程 | 否 |
| 是否把 `tiny_live_authorized` 改 true | **否**（CLAUDE.md freeze 强约束） |

## 6. 不要做的事

- ❌ 删 `reports/lp_rh/scanner.db` 或触发 `_run_episode_persisted` 之外的手动 schema 改写
- ❌ 直接编辑 `reports/lp_rh/GRADUATION_VERDICT.json` 改 verdict 字段
- ❌ 关闭 GitHub Actions workflow
- ❌ 在 `git status` 之外手动 push 到 origin（除 `PUSH_AUTHORIZATION_CN.md` 明确放行的 feature commit/push 外）
- ❌ 跳过 single-shot 路径冒 `CONTINUOUS_RUN=PASS`（multi-round 必须由 5 长跑 RH daemon 实测 ≥ N round 才允许）
- ❌ 盲目重等 72h 真实数据（按现有真数据 snapshot 报 FAIL，不替评估器单测冒充 PASS）
- ❌ 扩 scope 到 STOCK/MEME/V4 / Live signer / verify_calldata 新范围（本任务显式 deny）