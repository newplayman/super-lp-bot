# CONTINUOUS_AND_VARIANT_EVIDENCE_CN.md

R1 连续运行 / R2-B～E / 变异控制 实际 nodeid 与证据。

## 1. 原则

- **single-shot 不能冒充 CONTINUOUS_RUN=PASS**。`run_once()` 是单次触发，连续性必须由 multi-round 实测给出。
- 已完成项目直接引用 nodeid，未完成只补原缺口。

## 2. R1 — 连续运行 / 恢复 证据

| 测试 / 资产 | nodeid | 当前状态 | 说明 |
|------------|--------|---------|------|
| `scripts/lp_rh_shadow_daemon_v1_readonly.py::run_one_round`（持续运行入口） | （代码路径，非 pytest nodeid） | 实测 PASS | 单 round 调 `_run_episode_persisted` + `episode_summary` + `persist_episode`；连续性靠外层 `loop` 在 `cmd/lpbot`（5 长跑 daemon） |
| 多 round 不冲突（rh_episode_summary PK=episode_id） | `tests/test_lp_rh_paper_daemon_entry_v1.py::TestPaperRunOncePositiveControl::test_run_once_idempotent_on_replay` | **PASS** | 两次 `run_once` → `summary_rows == 2`（不是 INSERT OR REPLACE 折叠），`status.episodes_run == 2` |
| Crash 恢复（journal / reservation / mark 不重复） | `tests/test_paper_f_crash_recovery.py::test_paper_f_crash_recovery_mid_episode` | **PASS** | `rh_journal` 无重复 debit/credit，`rh_bucket_reservations` 唯一 intent_id |
| Reservation 在 crash 后恢复 | `tests/test_paper_f_crash_recovery.py::test_paper_f_reservation_recovery_after_crash` | **PASS** | BROADCAST_UNKNOWN 即使重跑仍保留 |
| Episode 重放同 decision_id 计数 | `tests/test_lp_rh_terminal_to_ledger_e2e_v1_readonly.py::test_d6_negative_replay_collides_on_decision_id_and_counted` | **PASS** | `dup_rows ≥ 1`，scratch 回滚路径可恢复 |

**CONTINUOUS_RUN 实测 verdict（当前 single-shot 路径）**：

| 项 | 值 | 依据 |
|----|----|------|
| CONTINUOUS_RUN | **NOT_APPLICABLE** | single-shot wrapper 不假装 multi-round 证据；multi-round 需 5 长跑 RH daemon 持续运行（owner 显式批准 OBSERVE_ONLY 退出才启动） |
| SINGLE_SHOT | **PASS** | `run_once` 完整跑一个 episode → ledger 行齐全，NAV 1000→990、PnL=-10、对账 PASS |
| IDEMPOTENT_REPLAY | **PASS** | 同 fixture 两次 `run_once` 不丢行、不重计 NAV |

> **single-shot 路径禁止冒 `CONTINUOUS_RUN=PASS`**——只有 5 个长跑 RH daemon 持续多 round 实际写入 `rh_episode_summary` ≥ N 条（N 待 owner 定）且间隔符合预期才允许 CONTINUOUS_RUN=PASS。

## 3. R2-B～E 节点证据

### R2-B — Delayed grant

| nodeid | 当前 | 说明 |
|--------|------|------|
| `tests/test_paper_b_delayed_grant.py::test_paper_b_delayed_grant_locks_price_ticks_and_inventory` | **PASS** | 拒绝步价格 2000 + grant 步 2200 → entry_price==2200、tick_lower/upper 对应 2200、prev_fee_growth==2200 时刻、inventory.liquidity_raw 对应 2200 仓位 |

### R2-C — Full cost flat price

| nodeid | 当前 | 说明 |
|--------|------|------|
| `tests/test_paper_c_full_cost_flat.py::test_paper_c_full_cost_flat_nav_and_pnl_window` | **PASS** | 价格不变、fee/reward=0、round-trip cost=10 → net_pnl ≈ -10（精确），nav_start==1000，steps[0].nav==990 |

### R2-D — Liquidation unit matrix

| nodeid | 当前 | 说明 |
|--------|------|------|
| `tests/test_paper_d_liquidation_matrix.py::test_paper_d_ast_zero_numeric_threshold_branch` | **PASS** | AST 检查 `compute_liquidation_nav` 函数体内无阈值分支（per R3 Package E） |
| `tests/test_paper_d_liquidation_matrix.py::test_paper_d_liquidation_nav_matrix[*]` | **48 PASS** | $1/$10/$50/$1000 × (18,6)/(6,18)/(18,18) decimals × range_pct ∈ {5,10,50,90} 全部相对误差 ≤ 1e-10 |

### R2-E — Pool state fail-close

| nodeid | 当前 | 说明 |
|--------|------|------|
| `tests/test_paper_e_pool_state.py::test_paper_e_pool_state_fail_close_and_invalidates_paper[STALE-2026-09-08T10:00:00Z-POOL_STATE_STALE]` | **PASS** | stale pool_state → terminal_eligible=False + invalid_for_paper_evaluation=True |
| `tests/test_paper_e_pool_state.py::test_paper_e_pool_state_fail_close_and_invalidates_paper[FUTURE-2026-09-08T19:00:00Z-POOL_STATE_AS_OF_IN_FUTURE]` | **PASS** | future as_of → fail-close |
| `tests/test_paper_e_pool_state.py::test_paper_e_pool_state_fail_close_and_invalidates_paper[UNKNOWN-None-POOL_STATE_AS_OF_UNAVAILABLE]` | **PASS** | unknown → fail-close |

### R2-F — Crash recovery / replay

| nodeid | 当前 | 说明 |
|--------|------|------|
| `tests/test_paper_f_crash_recovery.py::test_paper_f_crash_recovery_mid_episode` | **PASS** | journal/mark/reservation 唯一性 |
| `tests/test_paper_f_crash_recovery.py::test_paper_f_duplicate_episode_replay` | **PASS** | 同 episode_id 重跑不引入重复 |
| `tests/test_paper_f_crash_recovery.py::test_paper_f_reservation_recovery_after_crash` | **PASS** | BROADCAST_UNKNOWN 状态保留 |

### R2-G — Whitelist gate（已完成，非本任务新加）

| nodeid | 当前 | 说明 |
|--------|------|------|
| `tests/test_paper_g_whitelist_gate.py` (19 tests) | **全部 PASS** | evil target / recipient / selector / value / chain / calldata hash / deadline / multicall inner 等白名单拦截 |

## 4. 变异控制 / Mutation witness 证据

| nodeid | 当前 | 说明 |
|--------|------|------|
| `tests/test_inv_gate_02_terminal_conjunction.py::test_inv_gate_02_mutation_witness_detects_each_deliberately_omitted_gate[entry_eligible]` | **PASS** | 删 entry_eligible 闸 → witness 捕获 |
| `tests/test_inv_gate_02_terminal_conjunction.py::test_inv_gate_02_mutation_witness_detects_each_deliberately_omitted_gate[netcover_pass]` | **PASS** | 删 netcover_pass → witness 捕获 |
| `tests/test_inv_gate_02_terminal_conjunction.py::test_inv_gate_02_mutation_witness_detects_each_deliberately_omitted_gate[position_cap_pass]` | **PASS** | 删 position_cap_pass → witness 捕获 |
| `tests/test_inv_gate_02_terminal_conjunction.py::test_inv_gate_02_mutation_witness_detects_each_deliberately_omitted_gate[vetted]` | **PASS** | 删 vetted → witness 捕获 |
| `tests/test_inv_gate_02_terminal_conjunction.py::test_inv_gate_02_enforce_rejects_each_false_gate[*]` (4) | **全部 PASS** | enforce 路径逐闸拒绝 |
| `tests/test_inv_gate_02_terminal_conjunction.py::test_inv_gate_02_score_row_rejects_each_false_gate[*]` (4) | **全部 PASS** | score_row 路径逐闸拒绝 |
| `tests/test_inv_gate_02_terminal_conjunction.py::test_inv_gate_02_terminal_conjunction_source_shape_is_complete` | **PASS** | source 完整性 |

## 5. 本任务新加 nodeid（保留已完成 + 补原缺口）

| nodeid | 当前 | 说明 |
|--------|------|------|
| `tests/test_lp_rh_paper_daemon_entry_v1.py::TestPaperRunOncePositiveControl::test_run_once_real_episode_nav_1000_to_990_pnl_minus_10` | **PASS** | 本任务新加；严格 E2E 正控制 |
| `tests/test_lp_rh_paper_daemon_entry_v1.py::TestPaperRunOncePositiveControl::test_run_once_idempotent_on_replay` | **PASS** | 本任务新加；连续 replay 不重计 |
| `tests/test_lp_rh_paper_daemon_entry_v1.py::TestDaemon::test_daemon_runs_single_shot_episode` | **PASS** | 本任务新加；run_daemon 改为 single-shot（NotImplementedError 守护长跑 loop） |
| `tests/test_lp_rh_paper_data_validity_v1.py::TestForwardPaperDataValidity::*` (7) | **全部 PASS** | 本任务新加；数据门禁止 PID/tick/row-count 代理 |

## 6. 未完成项（owner 决定补什么）

| 项 | 当前 | 下一步 |
|----|------|--------|
| multi-round CONTINUOUS_RUN 实测 | NOT_APPLICABLE（single-shot wrapper） | owner 批准 OBSERVE_ONLY 退出后，启动 5 长跑 daemon，验证 N round 后 `rh_episode_summary.N ≥ 阈值` + 间隔符合 `expected_interval_secs` |
| verify_calldata=True 路径 | 默认 False（与 D1 一致） | owner 显式批准 W2 工程后接 TxIntentWriter + 白名单；当前白名单测试已 PASS，但 paper 入口未接白名单 writer |
| Live provider 双独立 | STRING 字面量阻断 | freeze 解除后才允许修 |

## 7. 全部 95 个相关 nodeid 一键复跑

```bash
python3 -m pytest \
  tests/test_lp_rh_terminal_to_ledger_e2e_v1_readonly.py \
  tests/test_paper_a_no_grant.py \
  tests/test_paper_b_delayed_grant.py \
  tests/test_paper_c_full_cost_flat.py \
  tests/test_paper_d_liquidation_matrix.py \
  tests/test_paper_e_pool_state.py \
  tests/test_paper_f_crash_recovery.py \
  tests/test_inv_gate_02_terminal_conjunction.py \
  tests/test_lp_rh_paper_daemon_entry_v1.py \
  tests/test_lp_rh_paper_data_validity_v1.py \
  --tb=line -q
# 预期：95 passed
```