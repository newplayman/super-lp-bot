# Mode Behavior Review

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: D
- run_id: `20260602_150957`

## 11 个 case 全部通过

| # | command | expected exit | actual exit | result | notes |
|---|---|---|---|---|---|
| D1 | `--mode preflight` | 0 | 0 | **PASS** | preflight_status=**WARN**, 1/13 stops (tick drift > 200); 见下 |
| D2 | `--mode print-unsigned` | 0 | 0 | **PASS** | unsigned_only / no_signature / no_send / execution_not_authorized 全 true |
| D3 | `--mode validate-approval` (valid) | 0 | 0 | **PASS** | valid=True, **executes_now=False, authorization_granted=False** |
| D4a | `--mode validate-approval` (20U) | 0 | 0 | **PASS** | regex 不匹配 (notional=20) |
| D4b | `--mode validate-approval` (30m) | 0 | 0 | **PASS** | dangerous word `\b30m\b` |
| D4c | `--mode validate-approval` (wrong wallet) | 0 | 0 | **PASS** | cross-check: wallet != frozen |
| D4d | `--mode validate-approval` (wrong pool) | 0 | 0 | **PASS** | cross-check: pool != frozen |
| D4e | `--mode validate-approval` (EXECUTE) | 0 | 0 | **PASS** | regex 不匹配 (prefix 错) |
| D5 | `--mode execute-disabled` | **1** | **1** | **PASS** | EXECUTION_DISABLED_IN_BUILD_STAGE |
| D6 | `--mode execute` | non-zero (2) | 2 | **PASS** | argparse invalid choice |
| D7 | `--mode preflight --execute` | **3** | **3** | **PASS** | defense-in-depth abort |

## ⚠️ D1 重要发现（与上一轮 review 不同）

| 字段 | 上一轮 (20260602_144843) | 本轮 (20260602_150957) | 差 |
|---|---|---|---|
| block_number | 46811291 | 46811930 | +639 blocks (~3-4 min) |
| current_tick | -200609 | **-200662** | **-53 ticks** |
| drift from frozen -200443 | 166 ticks | **219 ticks** | +53 ticks |
| triggered stop | (none) | **stop_tick_moved_outside_planned_range_before_entry** | (1 new) |
| preflight_status | PASS | **WARN** | WARN |

### 这个发现的意义

- **不是脚本 bug**。这是 executor 的 stop condition engine **正确检测到** tick range proposal 不再适合当前链上状态。
- tick drift > 200 ticks 触发 `manual_intervention_required`（不是 `abort_before_entry`），所以 preflight_status = WARN 而不是 FAIL。
- 未来执行 stage 在执行时点需要：**重新计算 tick range**（例如 lower_tick 改成 < -200862，upper_tick 改成 > -200462），并**走新的审批短语**才能继续。

### 这证明 stop condition engine 工作正常

如果脚本没有 stop_tick_moved_outside_planned_range_before_entry 这个 check，operator 可能盲目按 frozen range 执行，导致 15m 内大概率 out-of-range。**有 stop 检查 = 安全**。

## 关键观察

### D3 (validate-approval valid)
- valid=True（phrase 格式正确、cross-check 通过）
- **executes_now=False** ← 关键：成功校验**不**授权执行
- **authorization_granted=False** ← 关键：成功校验**不**视为已批准

### D5 (execute-disabled)
- exit_code=1
- `error: EXECUTION_DISABLED_IN_BUILD_STAGE`
- 永远不会调用任何真实执行

### D6 + D7 (--mode execute 双层防御)
- D6: argparse invalid choice → exit 2
- D7: 即使绕过 argparse（例如改 main() 顺序），`if args.execute or args.mode == "execute": exit 3` 仍兜底

## 与上一轮 review 对比

| 维度 | 上一轮 | 本轮 | 状态 |
|---|---|---|---|
| D1 preflight_status | PASS | WARN | **delta（tick drift 触发 stop）** |
| D2-D7 | (一致) | (一致) | identical |
| all 11 cases | pass | pass | all pass |

## 安全

```text
no_tx_sent                  = true
no_approval_executed        = true (D3 valid=True 但 executes_now=False)
no_mint_executed            = true
no_collect_executed         = true
no_swap_executed            = true
no_bridge_initiated         = true
executor_will_run_this_round = false (脚本只跑 read-only 模式)
wallet_or_tx_touched         = false
can_run_probe_now            = false
tiny_canary_allowed          = no
```
