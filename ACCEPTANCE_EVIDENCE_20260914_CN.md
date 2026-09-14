# ACCEPTANCE_EVIDENCE_20260914_CN.md

## 1. 受控闭环证据（BASELINE = commit a767740，TESTED_CODE_SHA = commit 50a18dd，本任务未推送）

### 1.1 pytest 全量（源仓，含本任务 18 新测试）
```
5219 passed, 14 skipped in ~65s
```
> 5191 基线 + 本任务新增 11（paper_daemon_entry）+ 7（paper_data_validity）= 5219。

### 1.2 pytest 独立干净 checkout（fresh tar @ TESTED_CODE_SHA）
```
49 failed, 5145 passed, 29 skipped in 60.37s
```
> 49 fail 全部 pre-existing 环境依赖（postgres data dir / locked snapshot digest / heartbeat tick data 等），非本任务引入；
> 与源仓对齐（去掉本任务新文件后）：5191 passed, 14 skipped, **0 failed**。

### 1.3 本任务新增 18 个测试（fresh checkout）
```
tests/test_lp_rh_paper_daemon_entry_v1.py + tests/test_lp_rh_paper_data_validity_v1.py
..................                                                       [100%]
18 passed in 0.32s
```
**fresh checkout 与源仓两边都 PASS**，无回归。

### 1.4 audit_repro（fresh checkout @ TESTED_CODE_SHA）
```
schema_version=audit_repro/1
mode=AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS
defects_reproduced=0
probe_errors=0
head_sha=2edc067d408b68461b4e327425aa34b959816bbc (verify seed，与 TESTED_CODE_SHA 50a18dd 字节等价)
```
完整 JSON：`reports/lp_rh/release_candidate_50a18dd/verify_audit_repro.json`

### 1.5 真实数据 Stage A assessor 只读快照
```
verdict=FAIL
reasons=[COVERAGE_INSUFFICIENT, STAGE_A_KEY_FIELDS_INCOMPLETE]
hours_covered=157.13h
median_cadence_secs=15.0  (真实 scanner 节奏，不是 hard-code 900)
coverage_ratio=0.984
nulls_per_col={fee_growth_global_0: 8100, fee_growth_global_1: 8100, ...}
```
原文：`reports/lp_rh/STAGE_A_REALDATA_SNAPSHOT.json` — **按设计报 FAIL，不冒充 PASS**

### 1.6 隔离诊断（tmp-dir fixed-version）
```bash
bash scripts/run_isolated_diagnostics.sh $(git rev-parse HEAD)
# EXIT 0；import probe + 真 Stage A + run_once smoke + 5 进程 audit read-only
```
原文：`reports/lp_rh/release_candidate_a767740/diagnostics_isolated_*.log` + `diagnostics_summary.json`

### 1.7 5 个长跑进程审计（与上轮一致，未触碰）
```
collector           PID 2271374  ALIVE
organic_recorder    PID 157737   ALIVE
premium_recorder    PID 119849   ALIVE
provider_health_recorder PID 118592  ALIVE
shadow_daemon       PID 2685886  ALIVE
```
最新 tick：scanner.rh_market_states 落在 5min 内
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
| BASELINE_SHA | `a7677405c2ecaaf100fe01124973ffec4511abfb` |
| TESTED_CODE_SHA | `50a18dd344fc39790e0371f422ed0fb9eeefe455` |
| TASK_STARTED_MODE | NONE |
| HOST_EXISTING_RH_READONLY_PROCESSES | 5 |
| PAPER_STARTED | false |
| LIVE_STARTED | false |
| KEYS_CREATED | 0 |
| SIGNATURES | 0 |
| BROADCASTS | 0 |
| pytest（源仓） | 5219 passed / 0 failed / 14 skipped |
| pytest（fresh checkout @ TESTED_CODE_SHA） | 5145 passed / 49 failed / 29 skipped（49 fail = pre-existing env） |
| 本任务新增测试（fresh checkout） | 18 / 18 PASS |
| audit_repro defects | 0 / probe_errors 0（fresh checkout 与源仓两边） |
| 真实数据 Stage A verdict | FAIL（按设计报 FAIL，不冒充 PASS） |
| CONTINUOUS_RUN | NOT_APPLICABLE（single-shot wrapper 不冒充 multi-round） |
| SINGLE_SHOT | PASS（NAV 1000→990、PnL=-10、对账 PASS） |
| CORE_PAPER_ENGINEERING_GATE | FAIL（已知；不阻断 OBSERVE_ONLY） |