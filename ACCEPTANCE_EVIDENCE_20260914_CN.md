# ACCEPTANCE_EVIDENCE_20260914_CN.md

## 1. 受控闭环证据（基线 = commit 4da8bc0，本任务未推送）

### 1.1 pytest 全量
```
5201 passed, 14 skipped in 64.85s (0:01:04)
```
详细原文：`reports/lp_rh/pytest_summary_20260914.txt`

### 1.2 audit_repro
```
schema_version=audit_repro/1
run_id=430264c0-a72b-4d68-944e-2f0cec24c508
head_sha=4da8bc0d68b4d052b49bd0d2281198dcdb1e5944
mode=AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS
defects_reproduced=0
probe_errors=0
github=null  (本地运行；CI 上由 GITHUB_SHA env 注入)
```
原文：`reports/lp_rh/audit_repro_20260914.json`

### 1.3 5 个长跑进程审计
```
collector           PID 2271374  etime 3-11:07  ALIVE
organic_recorder    PID 157737   etime 5-12:29  ALIVE
premium_recorder    PID 119849   etime 5-14:04  ALIVE
provider_health_recorder PID 118592  etime 5-14:07  ALIVE
shadow_daemon       PID 2685886  etime 3-02:58  ALIVE
```
最新 tick：scanner.rh_market_states=2026-09-14T16:17:50Z，< 5min
原文：`reports/lp_rh/STAGE_A_REQUALIFICATION.json`

## 2. 本任务引入的 6 个新测试

| 文件 | 测试 | 用途 |
|------|------|------|
| `tests/test_lp_rh_terminal_to_ledger_e2e_v1_readonly.py` | test_d1 | 正控制：capital=1000, position=100, NAV 1000→990, NetPnL=-10 |
| 同上 | test_d2 | 负控制 1：direct run_episode 不写 rh_tx_intents |
| 同上 | test_d3 | 负控制 2：absolute_profit_pass=False 阻断 → 无 reservation |
| 同上 | test_d4 | 负控制 3：stale pool_state (7h) → POOL_STATE_STALE |
| 同上 | test_d5 | 负控制 4：capital_usd=None 显式 → window_alignment_reason=NAV_START_CAPITAL_MISSING |
| 同上 | test_d6 | 负控制 5：同 episode_id 重放 → dup_rows≥1, gate_decisions 仍 3 行 |

## 3. 修复/引入的关键代码改动

- `scripts/lp_rh_shadow_runner_v1_readonly.py`
  - 新增 `_CAPITAL_USD_UNSET` sentinel（区分「kwarg 未传」与「显式 None fail-close」）
  - `episode_summary` 保留两条 fallback：
    - kwarg 未传 → nav_start = first_step.nav（legacy）
    - 显式 None → nav_start=None + window_alignment_reason=NAV_START_CAPITAL_MISSING
  - pool_state_fault 恢复为 blocking（per R3 / Package D 权威）
- `tests/test_lp_rh_shadow_runner_v1_readonly.py`
  - `_run()` 注入 pool_meta 默认（as_of 6h freshness）
  - `_passing_sample()` 满足 R3 / Package D 修复后的 conjunction
- `tests/test_lp_rh_graduation_evidence_v1_readonly.py`
  - `_init_test_db()` 样本时间对齐 judgment window（2026-09-13T05/06）
- `tools/audit_repro/audit_repro.py`
  - 顶层 schema_version/run_id/head_sha/mode/github.sha 五字段（per 任务 B）
- `.github/workflows/audit-regression.yml` / `.github/workflows/ci.yml`
  - 同步上述 schema 注入（local fallback → env override）

## 4. 阻断项目 vs 允许项目（与 OBSERVE_ONLY_DECISION_RULES_CN.md §3/§4 对齐）

- ✅ 允许：pytest、audit_repro、读 ledger、写 audit 报告、测试内 _run_episode_persisted（tmp db）
- ❌ 阻断：起新 daemon / kill / restart / 修改 5 个长跑进程 / 签 / 广播 / 放宽 live_allowed

## 5. GitHub Actions 状态

本任务**未推送**到 origin，所有本轮改动在本地 working tree。
owner 验收时需：
1. 检查 `git status --short`（应有 8 modified + 4 untracked）
2. 推送后由 CI 对最终 HEAD 跑 audit-regression 与 python-rh-tests，
   通过方可认为本轮闭环。

## 6. 关键指标最终值

| 指标 | 值 |
|------|---|
| TASK_STARTED_MODE | NONE |
| HOST_EXISTING_RH_READONLY_PROCESSES | 5 |
| PAPER_STARTED | false |
| LIVE_STARTED | false |
| KEYS_CREATED | 0 |
| SIGNATURES | 0 |
| BROADCASTS | 0 |
| pytest | 5201 passed / 0 failed / 14 skipped |
| audit_repro defects | 0 / probe_errors 0 |
| CORE_PAPER_ENGINEERING_GATE | FAIL（已知） |