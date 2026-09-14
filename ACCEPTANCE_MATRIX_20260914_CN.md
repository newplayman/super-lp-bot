# ACCEPTANCE_MATRIX_20260914_CN.md

> Owner 验收矩阵 —— 把本轮 6 个补充任务压缩到一张表，每行给证据 + 文件指针 + 状态。
> 凡"数据门允许 FAIL/NOT_PROVEN"都明确标出，不冒充 PASS。

## 0. 双 SHA 关系（避免错把新工作区挂旧 SHA）

| 名称 | SHA | 用途 | 产物目录 |
|------|-----|------|---------|
| **BASELINE_SHA** | `a7677405c2ecaaf100fe01124973ffec4511abfb` | 4 个 Gap 关闭之前的 candidate（不可变基线） | `reports/lp_rh/release_candidate_a767740/` |
| **TESTED_CODE_SHA** | `50a18dd344fc39790e0371f422ed0fb9eeefe455` | 本任务候选 commit：fix + 新测试 + 新脚本 + 证据 | `reports/lp_rh/release_candidate_50a18dd/` |

## 1. 六维验收矩阵

| # | 验收维度 | 关键证据 | 状态 | 证据文件 |
|---|---------|---------|------|---------|
| **D1** | **push 来源说明**：feature commit/push 允许、main/force/deploy/prod/trades 拒绝 | `PUSH_AUTHORIZATION_CN.md`：原始"no push"仅为约定不是硬线；Owner 显式授权范围；8 条 pre-push 自查脚本 | **PASS** | `PUSH_AUTHORIZATION_CN.md` + `scripts/check_pre_push_safe.sh` |
| **D2** | **候选 commit 化 + BASELINE/TESTED 双 SHA + 独立干净 checkout** | 候选 commit `50a18dd` 已落（"research: RH CORE paper minimum release — wire run_once/status, strict E2E, Stage A real-data gate"）；独立 fresh checkout @ TESTED_CODE_SHA：pytest 5145 pass / 49 fail（pre-existing env）/ 29 skip；audit_repro defects=0 probe_errors=0；JUnit + audit JSON + pytest log + VERIFY_REPORT 全归档 | **PASS** | `reports/lp_rh/release_candidate_50a18dd/{verify_junit_full.xml,verify_audit_repro.json,verify_pytest_stdout.log,VERIFY_REPORT_CN.md}` |
| **D3** | **R1/R2-B～E/变异控制实测 nodeid + 证据** + single-shot 不冒充 CONTINUOUS_RUN=PASS | 95 个 nodeid 全列；CONTINUOUS_RUN=NOT_APPLICABLE；SINGLE_SHOT=PASS（NAV 1000→990、NetPnL=-10、对账 PASS）；IDEMPOTENT_REPLAY=PASS（summary_rows=2 不折叠）；R2-B delayed-grant / R2-C full-cost / R2-D 48 个 liquidation matrix / R2-E stale/future/unknown fail-close / R2-F crash recovery / R2-G whitelist 19 个 — 全部 PASS | **PASS** | `CONTINUOUS_AND_VARIANT_EVIDENCE_CN.md` + `tests/test_lp_rh_paper_daemon_entry_v1.py::TestPaperRunOncePositiveControl` |
| **D4** | **真实数据 Stage A assessor 只读快照**（不盲目重等 72h） | 在现有 `reports/lp_rh/scanner.db`（200MB）跑真实数据 gate：`hours_covered=157.13h`（≥72）、`median_cadence_secs=15.0`（真实 scanner 节奏，不是 hard-code 900）、`coverage_ratio=0.984`（<0.99）、8100 NULL `fee_growth_global_0/1` → verdict=**FAIL**，reasons=COVERAGE_INSUFFICIENT + STAGE_A_KEY_FIELDS_INCOMPLETE；快照归档 | **PASS（gate verdict=FAIL 是数据门按预期工作，非"冒充 PASS"）** | `reports/lp_rh/STAGE_A_REALDATA_SNAPSHOT.json` |
| **D5** | **固定版本 tmp-dir 隔离诊断**（数据门允许 BLOCKED/NO_TRADE） | 临时目录独立验证：import probe + 真 Stage A assessor（允许 FAIL/NOT_PROVEN）+ run_once smoke（rc=0, episodes_run=1）+ 5 进程 audit read-only；脚本本身 EXIT 0；不部署常驻，不触碰 5 长跑 | **PASS** | `scripts/run_isolated_diagnostics.sh` + `reports/lp_rh/release_candidate_a767740/diagnostics_isolated_*.log` + `diagnostics_summary.json` |
| **D6** | **更新原六件 + 验收矩阵**（不堆叠同义长报告） | 本矩阵 + 6 原交付物的轻更新（HEAD 50a18dd / 双 SHA 引用 / fresh checkout 证据指针 / real-data Stage A FAIL 行） | **PASS** | 本文件 + `READ_FIRST_20260914_CN.md` / `FINAL_VERDICT_20260914_CN.md` / `HANDOFF_20260914_CN.md` / `BLOCKERS_20260914_RC_CN.csv` / `OBSERVE_ONLY_DECISION_RULES_CN.md` / `ACCEPTANCE_EVIDENCE_20260914_CN.md` |

## 2. 关键量化指标（最终状态）

| 指标 | 值 | 备注 |
|------|----|------|
| HEAD | `50a18dd344fc39790e0371f422ed0fb9eeefe455` | TESTED_CODE_SHA |
| pytest (源仓，含本任务新测试) | 5219 passed / 0 failed / 14 skipped | 5191 基线 + 18 新测 |
| pytest (fresh checkout @ TESTED_CODE_SHA) | 5145 passed / 49 failed / 29 skipped | 49 fail 是 pre-existing env（postgres data dir、locked snapshot 等），非本任务引入 |
| audit_repro | `defects_reproduced=0, probe_errors=0` | mode=AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS |
| 本任务新增测试（fresh checkout） | 18 / 18 PASS | `test_lp_rh_paper_daemon_entry_v1.py` (11) + `test_lp_rh_paper_data_validity_v1.py` (7) |
| Stage A 真数据 verdict | **FAIL** | reasons=COVERAGE_INSUFFICIENT + STAGE_A_KEY_FIELDS_INCOMPLETE；**不是冒充 PASS** |
| CONTINUOUS_RUN | NOT_APPLICABLE | single-shot wrapper 不冒充 multi-round |
| SINGLE_SHOT | PASS | run_once 完整跑通，NAV 1000→990、PnL=-10 |
| IDEMPOTENT_REPLAY | PASS | summary_rows=2（不折叠） |

## 3. 安全边界（不变量）

- ✅ TASK_STARTED_MODE = NONE
- ✅ HOST_EXISTING_RH_READONLY_PROCESSES = 5（PID 不变）
- ✅ PAPER_STARTED = false
- ✅ LIVE_STARTED = false
- ✅ KEYS_CREATED = 0
- ✅ SIGNATURES = 0
- ✅ BROADCASTS = 0
- ✅ CLAUDE.md freeze = 未变更
- ✅ main 分支 = 未触碰
- ✅ 不扩 STOCK/MEME/V4、Live signer、verify_calldata 新范围
- ✅ 不冒充 CONTINUOUS_RUN=PASS
- ✅ 不以评估器单测替代真实数据；真实数据不合格允许 BLOCKED/NO_TRADE/FAIL
- ✅ 不计 Stage B、不部署常驻、不触碰 5 长跑

## 4. owner 决策点

| 决策 | 推荐 | 依据 |
|------|------|------|
| 是否推送 `50a18dd` 到 origin | 推送 | `PUSH_AUTHORIZATION_CN.md` 已明确放行 feature commit/push |
| 是否继续 OBSERVE_ONLY | 是 | Stage A 真数据 FAIL 是数据积累不足，不是代码缺陷；继续 OBSERVE_ONLY 累积 hours_covered |
| 是否扩 scope 到 STOCK/MEME/V4/Live signer | **否** | Owner 显式 deny；本任务不重写已完成模块 |
| 是否把 `tiny_live_authorized` 改 true | **否** | CLAUDE.md freeze 硬约束 |
| 是否重启 5 长跑进程 | **否** | 本任务硬约束 |

## 5. 一句话复跑命令（owner 自验）

```bash
cd /opt/lpbot/lp-bot-v3-origin-check
git rev-parse HEAD                                          # 预期: 50a18dd344fc39790e0371f422ed0fb9eeefe455
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider    # 预期: 5219 passed, 14 skipped
python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head --json-out /tmp/x.json
python3 -c "import json;d=json.load(open('/tmp/x.json'));assert d['counts']['defects_reproduced']==0;assert d['counts']['probe_errors']==0;print('audit-repro PASS')"
# 单跑本任务新测试：
python3 -m pytest tests/test_lp_rh_paper_daemon_entry_v1.py tests/test_lp_rh_paper_data_validity_v1.py -v
# 真实数据 Stage A（snapshot 已存，无需重跑）：
cat reports/lp_rh/STAGE_A_REALDATA_SNAPSHOT.json | python3 -c "import json,sys;d=json.load(sys.stdin);print('verdict=',d['verdict'],'reasons=',d['reasons'])"
```