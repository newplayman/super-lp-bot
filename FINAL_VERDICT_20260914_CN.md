# FINAL_VERDICT_20260914_CN.md

## 1. 判决（owner-facing）

**OBSERVE_ONLY 维持；本任务候选 commit `50a18dd` 已落但未推送远端，等 owner 验收 GitHub Actions。**

| 项 | 值 |
|----|---|
| TASK_STARTED_MODE | NONE |
| HOST_EXISTING_RH_READONLY_PROCESSES | 5 |
| PAPER_STARTED | false |
| LIVE_STARTED | false |
| KEYS_CREATED | 0 |
| SIGNATURES | 0 |
| BROADCASTS | 0 |
| pytest（源仓含本任务新测试） | 5219 / 0 / 14 |
| pytest（fresh checkout @ TESTED_CODE_SHA） | 5145 / 49 / 29（49 fail = pre-existing env，与本任务无关） |
| TESTED_CODE_SHA | `50a18dd344fc39790e0371f422ed0fb9eeefe455` |
| BASELINE_SHA | `a7677405c2ecaaf100fe01124973ffec4511abfb` |
| 本任务新增测试（fresh checkout） | 18 / 18 PASS |
| SINGLE_SHOT（run_once 真实引擎） | PASS（NAV 1000→990、PnL=-10、对账 PASS） |
| CONTINUOUS_RUN | NOT_APPLICABLE（single-shot wrapper 不冒充 multi-round） |
| 真实数据 Stage A verdict | FAIL（COVERAGE_INSUFFICIENT + STAGE_A_KEY_FIELDS_INCOMPLETE；按设计报 FAIL，不冒充 PASS） |
| audit_repro defects | 0 |
| audit_repro probe_errors | 0 |
| CORE_PAPER_ENGINEERING_GATE | FAIL（已知；不阻断 OBSERVE_ONLY） |
| OBSERVE_ONLY_ACTIVE | true |
| OBSERVE_ONLY_REQUIRES_OWNER_APPROVAL_TO_EXIT | true |

## 2. 本任务 PASS 项（4 Gap 全关）

- **Gap 1**：run_once/run_daemon/status 接真实 `_run_episode_persisted` + `episode_summary`（不再 stub return 0）
- **Gap 2**：严格 E2E 正控制（无条件 NAV 1000→990、NetPnL=-10、对账 PASS），test_d1 + 5 个负控制；forbidden：granted_count>=0、无 grant 也 pass、条件性 PnL 断言
- **Gap 3**：Forward Paper 数据有效性 + Stage A 真算（real-data snapshot 报 FAIL，禁止 PID/tick/row-count 代理）
- **Gap 4**：独立干净 checkout 重验（fresh tar + 手动 seed .git），JUnit XML + audit_repro JSON + pytest stdout log + VERIFY_REPORT 全归档到 `release_candidate_50a18dd/`

## 3. 残留 BLOCKER（不阻断 OBSERVE_ONLY）

1. `STAGE_A_HOURS_COVERED_INSUFFICIENT`（真数据 hours_covered=157.13 但 coverage_ratio=0.984 < 0.99）
2. `STAGE_A_KEY_FIELDS_INCOMPLETE`（8100 NULL `fee_growth_global_0/1`）
3. `DAYS_COVERED_INSUFFICIENT`（2/14d）
4. `WEEKENDS_COVERED_INSUFFICIENT`
5. `SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE`
6. `CAPITAL_POLICY_NOT_APPROVED`

详见 `BLOCKERS_20260914_RC_CN.csv`。

## 4. owner 验收路径

1. `cat ACCEPTANCE_MATRIX_20260914_CN.md`（六维矩阵）
2. `cat FINAL_VERDICT_20260914_CN.md`（本文）
3. `cat READ_FIRST_20260914_CN.md`
4. `cat OBSERVE_ONLY_DECISION_RULES_CN.md`
5. `cat ACCEPTANCE_EVIDENCE_20260914_CN.md`（含 fresh checkout 证据）
6. `cat CONTINUOUS_AND_VARIANT_EVIDENCE_CN.md`（95 nodeid + CONTINUOUS_RUN=NOT_APPLICABLE）
7. `cat BLOCKERS_20260914_RC_CN.csv`
8. `cat PUSH_AUTHORIZATION_CN.md`（push 范围）
9. `cat reports/lp_rh/STAGE_A_REALDATA_SNAPSHOT.json`（真数据 FAIL 原文）
10. `git diff a767740..50a18dd --stat` 检查改动范围
11. 推送 → GitHub 网页目视最终 HEAD 的 Actions

通过 → ACCEPT。

## 5. 本任务后**保持原状**的事项

- 5 个 RH 长跑进程：PID/参数/日志路径全部不变
- `reports/lp_rh/scanner.db` 与 `reports/lp_rh/GRADUATION_VERDICT.json`：未修改
- CLAUDE.md freeze 边界：未修改
- main 分支：未触碰

## 6. 一句话回归测试

```bash
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider
```
预期：`5219 passed, 14 skipped`（0 failed；含本任务 18 新测试）。

```bash
git diff a767740..50a18dd --stat
```
预期：仅 `scripts/lp_rh_paper_*`、`tests/test_lp_rh_paper_*`、`scripts/check_pre_push_safe.sh`、`scripts/run_isolated_diagnostics.sh`、各 `.md`/`.json`/`reports/lp_rh/release_candidate_50a18dd/*` 之内；无 workflow / deploy / k8s / configs/config.live.toml / .env / .key / .pem 改动。

```bash
python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head --json-out /tmp/x.json
python3 -c "import json;d=json.load(open('/tmp/x.json'));assert d['schema_version']=='audit_repro/1';assert d['head_sha'];assert d['mode'];assert d['counts']['defects_reproduced']==0;assert d['counts']['probe_errors']==0;print('audit-repro PASS')"
```
预期：`audit-repro PASS`。