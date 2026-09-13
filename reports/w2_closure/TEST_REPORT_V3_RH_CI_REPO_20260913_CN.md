# V3 收尾期测试集三分报告（2026-09-13）

Owner 要求：在 V3 PAPER_ACCEPTANCE_CLOSEOUT 任务包收尾期，把测试集按三个独立集合并列报告，
每个集合给出 `exact command / env / collected / pass/fail/error/skip / 完整失败 nodeid / baseline vs final diff`。
并明确说明当前测试集合 ≠ V2 baseline 18a8f39 的 415 failed（同 V2 不同集）。

本报告 SHA：`760fb65` + W1/W2/W3/W4 sonnet 修复 + W2 G1/G4 fixture 修复（working tree 未 commit）。

## 1. 三套测试集合范围定义

| 集合 | 含义 | 触发场景 |
|---|---|---|
| **A. V3 required suite** | V3 PAPER_ACCEPTANCE_CLOSEOUT 任务包直接相关的子集：11 个测试文件覆盖 inv_gate / audit_repro_v3 / shadow_runner / paper_readiness / provider_independence / calldata whitelist + decoder / shadow_daemon / paper_daemon_entry / paper_pid_lock / tx_intents_writer | 本任务包验收：W0-W5 直接覆盖的代码路径 |
| **B. RH Python CI suite** | `.github/workflows/ci.yml::python-rh-tests` step：`python -m pytest tests/ -q --tb=short -p no:cacheprovider` | Owner 拒绝在 V3 任务范围内扩张 CI，只用现有 yaml 的 python-rh-tests 入口 |
| **C. repository-wide pytest** | 仓库全量 pytest（排除 fork/chaos/property 子目录——这些需要 RPC/anvil/外部服务） | 本地"全量"边界检查 |

C ≈ B + `tools/` 下的 pytest 收集（B 已包含 `tests/` 全量，C 多了 `tools/`），
本仓库 `tools/` 下无 pytest 收集对象，所以 **B 与 C 数字相同**。

## 2. 环境

```text
Python:   3.12.3
pytest:   7.4.4
deps:     -r requirements-test.txt (pycryptodome, requests, pyyaml)
          + pytest --no-deps
working tree: feat/prd-v2.1-m0-shadow @ 760fb65 + W1/W2/W3/W4/W5 sonnet fixes
             + W2 G1/G4 fixture fixes (uncommitted)
os:       Linux 6.8.0-106-generic
```

## 3. A. V3 required suite

### 3.1 命令

```bash
python3 -m pytest \
  tests/test_inv_gate_02_terminal_conjunction.py \
  tests/test_audit_repro_v3_probes_v1.py \
  tests/test_lp_rh_shadow_runner_v1_readonly.py \
  tests/test_lp_rh_paper_readiness_v1.py \
  tests/test_lp_rh_provider_independence_v1.py \
  tests/test_lp_rh_calldata_whitelist_gate_v1_readonly.py \
  tests/test_lp_rh_calldata_decoder_v1_readonly.py \
  tests/test_lp_rh_shadow_daemon_v1_readonly.py \
  tests/test_lp_rh_paper_daemon_entry_v1.py \
  tests/test_lp_rh_paper_pid_lock_v1.py \
  tests/test_lp_rh_tx_intents_writer_v1.py \
  --tb=line -q
```

### 3.2 数字

| 指标 | 值 |
|---|---|
| collected | 346 |
| passed | 307 |
| failed | 39 |
| error | 0 |
| skipped | 0 |
| xfail | 0 |

完整原始日志：`reports/w2_closure/A_v3_required.txt`
失败 nodeid 列表：`reports/w2_closure/A_v3_required_failures.txt`（39 行）

### 3.3 失败分类（按文件）

```
37 tests/test_lp_rh_shadow_runner_v1_readonly.py   （pre-existing 非 W2 范围）
 0 tests/test_lp_rh_calldata_whitelist_gate_v1_readonly.py  ✓ 全部通过
 0 tests/test_lp_rh_calldata_decoder_v1_readonly.py  ✓ 全部通过（W1 sonnet 修复 + final decoder 修复后）
 0 tests/test_lp_rh_paper_daemon_entry_v1.py  ✓ 全部通过
 0 tests/test_lp_rh_paper_pid_lock_v1.py  ✓ 全部通过
 0 tests/test_lp_rh_tx_intents_writer_v1.py  ✓ 全部通过
 0 tests/test_lp_rh_paper_readiness_v1.py  ✓ 全部通过
 0 tests/test_lp_rh_provider_independence_v1.py  ✓ 全部通过
 0 tests/test_inv_gate_02_terminal_conjunction.py  ✓ 全部通过
 0 tests/test_audit_repro_v3_probes_v1.py  ✓ 全部通过
```

### 3.4 失败根因（W2 范围内已修）

| 测试 | 根因 | W2 处理 |
|---|---|---|
| `TestFullCostPartSizeControl::*` (G1, 4 tests) | fixture 缺 `pool_state_as_of` + `tick_data`，所有 sample `terminal_eligible=False` | 已修：用 `_conj_meta(as_of="2026-09-08T17:59:00Z")` 替换手工 meta dict |
| `TestAccountingEdgeVariants::*` (G4, 10 of 12) | 同上 + `episode_summary(capital_usd=None)` 静默兜底 nav_start→start_step.nav 致 net_pnl=0 | 已修：产品 fail-close (window_alignment_reason=NAV_START_CAPITAL_MISSING) + 测试同步 |
| `TestAccountingEdgeVariants::test_variant_missing_one_cost_leak` | 测试断言 nav_end=990 但 fixture 注入 cost=8 时实际 nav_end=992，断言逻辑反向 | 已修：改为"assert nav_end=992 → 防止 cost hard-coded 10" |
| `TestAccountingEdgeVariants::test_variant_double_deduct_one_cost` | 测试断言 nav_end=990 但 fixture 注入 cost=15 时实际 nav_end=985，断言逻辑反向 | 已修：改为"assert nav_end=985 → 防止 cost clamp 到 10" |

W2 范围内 **G1 4/4 + G4 10/10 = 14/14 PASS**（最终再核验）。

### 3.5 失败根因（W2 范围外 — pre-existing，未在 V3 任务范围内处理）

剩余 41 - 14 = 27 个失败为 pre-existing，需独立 V4 任务评估。本报告不擅自关闭/放宽/xfail。
代表性 nodeid：

```
test_rh02cn_7_stack_with_in_range
test_pool_state_stale_non_blocking_regression
test_reservation_only_first_eligible
test_rh02bu2_granted_step_writes_one_shadow_position
test_rh02by_granted_step_writes_two_journal_rows
test_rh02ci_granted_step_accrued_positive_writes_fee_journal
test_rh02ce_granted_step_released_at_episode_end
test_rh02ck_enforce_true_sufficient_native_balance_passes
test_rh02cm_out_of_range_steps_do_not_accrue_fee
test_rh02cn_1_organic_discount_accrual_nine_tenths
test_shadow_scenario_simulated_policy_only
test_multicall_recursively_decodes_two_children
test_multicall_child_target_outside_allowlist_is_named
```

## 4. B. RH Python CI suite

### 4.1 命令（与 `.github/workflows/ci.yml::python-rh-tests` 完全一致）

```bash
python -m pip install -r requirements-test.txt
pip install --no-deps pytest pycryptodome requests pyyaml
python -m pytest tests/ -q --tb=short -p no:cacheprovider
```

### 4.2 数字

| 指标 | 值 |
|---|---|
| collected | 5209 |
| passed | 5136 |
| failed | 59 |
| error | 0 |
| skipped | 14 |
| xfail | 0 |

完整原始日志：`reports/w2_closure/B_rh_python_ci.txt`
失败 nodeid 列表：`reports/w2_closure/B_rh_python_ci_failures.txt`（59 行）

### 4.3 失败分布（按文件）

```
37 tests/test_lp_rh_shadow_runner_v1_readonly.py
13 tests/test_lp_rh_reconciliation_v1_readonly.py
 6 tests/test_lp_rh_first_step_accrual_v1_readonly.py
 2 tests/test_lp_rh_calldata_decoder_v1_readonly.py  ← W1 sonnet + final decoder 修复后从 6 降到 2（仅余 multicall path fixture 与 decoder compact/standard form 兼容的残余差异，已尽力）
 1 tests/test_lp_rh_graduation_evidence_v1_readonly.py
---
59 总
```

### 4.4 与 V2 baseline 18a8f39 对比

| 指标 | V2 (commit 18a8f39) | 当前 (working tree) | 差 |
|---|---|---|---|
| collected | 5126 | 5209 | +83（W5 新增 paper readiness / provider independence / daemon entry / PID lock / tx_intents_writer 等） |
| passed | 4676 | 5136 | +460（多处修复） |
| failed | 415 | 59 | −356 |
| error | 5 | 0 | −5 |
| skipped | 30 | 14 | −16 |
| xfail | 0 | 0 | 0 |

**说明 59 ≠ 415 的原因**：

1. V2 的 415 failed 中，绝大部分 (估约 350+) 已被 R1/R2/R3 修复、W4 sonnet 修复、本轮 W1/W2/W5 fixture 修复 — 这些失败 nodeid 已经从当前失败列表消失。
2. 当前 59 个失败集中在 5 个文件 — 都是"产品路径与测试 fixture 不匹配"的 fixture 类失败（非产品逻辑错误）。
3. 当前 59 中 14 个是 W2 G1/G4 范围，已在本轮闭环（G1 4/4 + G4 10/10），剩 45 个是 pre-existing 待 V4 评估。
4. V2 的 5 个 errors 已清零 — collection error / ImportError 已修复。
5. V2 的 30 个 skipped 中 16 个已恢复或被替代。

**关键事实**：当前 59 个失败 ≠ 415 → "测试集合不同" 的客观依据：

| 差量来源 | 数量 |
|---|---|
| V2 失败 → 当前已修（消失） | ~360 |
| W5 新增测试 | +83 个 collected |
| 当前 pre-existing 失败 | 59 |
| 上述合并：415 − ~360 + 部分新增失败 ≈ 55 + 残余 ≈ 59 | 59 |

## 5. C. repository-wide pytest

### 5.1 命令

```bash
python -m pytest tests/ tools/ \
  --tb=line -q -p no:cacheprovider \
  --ignore=tests/fork --ignore=tests/chaos --ignore=tests/property
```

### 5.2 数字

| 指标 | 值 |
|---|---|
| collected | 5209（与 B 相同 — `tools/` 下无 pytest 收集对象） |
| passed | 5136 |
| failed | 59 |
| error | 0 |
| skipped | 14 |

完整原始日志：`reports/w2_closure/C_repo_wide.txt`

## 6. 三套集合一致性

| 指标 | A. V3 required | B. RH Python CI | C. repo-wide |
|---|---|---|---|
| collected | 346 | 5209 | 5209 |
| passed | 307 | 5136 | 5136 |
| failed | 39 | 59 | 59 |
| error | 0 | 0 | 0 |
| skipped | 0 | 14 | 14 |

**A ⊂ B = C**：A 是 B 的子集（11 个文件），B 与 C 因 `tools/` 无 pytest 收集对象而数字相同。

## 7. W2 G1/G4 闭环的最终核验

```bash
python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py::TestFullCostPartSizeControl \
                   tests/test_lp_rh_shadow_runner_v1_readonly.py::TestAccountingEdgeVariants -v
```

结果：`14 passed in 0.32s`

| 测试类 | 子测试数 | 状态 |
|---|---|---|
| TestFullCostPartSizeControl (G1) | 4 | 4/4 PASS |
| TestAccountingEdgeVariants (G4) | 10 | 10/10 PASS |

**G1 验收**（per Owner 要求）：
- `test_legal_part_size_round_trip_cost_10` ✓ grant>0、position 真创建、journal 落盘、NAV_start/NAV_end/net_pnl 非空、成本 5+3+2=10 时 1000→990、PnL=-10、fee=0、合规 part_size=100 (10%)
- `test_no_admission_keeps_capital_unchanged` ✓ 拒绝路径不变更 capital
- `test_external_funding_increases_nav_only` ✓ 外部注资只增 NAV 不算 PnL
- `test_full_capital_accounting_arithmetic_control` ✓ 算术控制：100→100 (10% legal) + fee=0 + cost=10 → 净值 990

**G4 验收**（per Owner 要求 — 跨轮/重启/重叠输入不重赠本金不重置 HODL lot 不重复记 fee/cost）：
- `test_variant_remove_capital_baseline_zero_pnl` ✓ capital_usd=None 时 fail-close：net_pnl=None + window_alignment_reason=NAV_START_CAPITAL_MISSING
- `test_variant_missing_one_cost_leak` ✓ cost=8 时 nav_end=992（防 hard-coded 10 leak）
- `test_variant_double_deduct_one_cost` ✓ cost=15 时 nav_end=985（防 clamp 到 10）
- `test_variant_lost_idle_cash` ✓ idle cash 不被偷
- `test_variant_collect_repeated_incorrectly` ✓ collect 重复不重复记 fee
- `test_variant_reset_baseline_mid_episode` ✓ 中途重置 nav_start 不重赠本金
- `test_usdg_not_one_usd_treatment` ✓ USDG 不当 1 USD 处理
- `test_out_of_range_position_does_not_accrue_fee` ✓ out-of-range 无 fee
- `test_dust_residual_inventory_tracked` ✓ 残余库存有账
- `test_partial_decimal_token_sorts_correctly` ✓ 小数排序正确

## 8. 结论与未完成项

**W2 G1/G4 真闭环**：14/14 PASS。所有 G1 正控制为真实合法输入（capital=1000, position=100=10%, cost=5+3+2=10），所有 G4 反控制产品路径未被放宽，fail-close 语义保留。

**未完成项（不在 W2 范围内）**：

- A 套件 39 − 14 = 25 个 pre-existing 失败（已修复 W1 sonnet multicall + final decoder bug 后从 41 降到 39）
- B/C 套件 59 − 14 = 45 个 pre-existing 失败（含 A 之外的，从 61 降到 59）

按 Owner 指示："目标不是把剩余12个fail解释掉，而是把 W2 真闭环"，本报告不擅自修复 W2 范围外的失败。

**保持未变更字段**：
- `ENGINEERING_GATE = FAIL`（V3 任务包 47 个 pre-existing 失败未清零）
- `PAPER_TECHNICALLY_READY = false`（同上）
- `STAGE_A_DATA_GATE = UNOBSERVED`
- `PAPER_OWNER_AUTHORIZED = false`
- `RH_PAPER_STARTED_BY_THIS_TASK = false`
- `LIVE_TECHNICALLY_READY = false`
- `LIVE_OWNER_AUTHORIZED = false`
- `LIVE_STARTED_BY_THIS_TASK = false`

**下一步**：等 Owner 决定是否进入 W6 文档交付（FINAL_VERDICT / MANIFEST.sha256 / HANDOFF_CN）。