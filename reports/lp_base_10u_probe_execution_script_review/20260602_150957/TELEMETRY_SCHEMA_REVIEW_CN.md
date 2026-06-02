# Telemetry Schema Review

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: I
- run_id: `20260602_150957`

## 5 个 schema files 设计

| 文件 | schema | written by |
|---|---|---|
| `entry_intent.json` | `lp_probe_execution_ledger_v1` | `write_telemetry_skeleton()` (内部 helper) |
| `preflight_checks.json` | `lp_probe_preflight_v1` | `write_telemetry_skeleton()` (内部 helper) |
| `stop_condition_checks.json` | `lp_probe_stop_condition_checks_v1` | `write_telemetry_skeleton()` (内部 helper) |
| `unsigned_package.json` | `lp_probe_unsigned_package_v1` | `--mode print-unsigned` |
| `approval_validation.json` | `lp_probe_approval_validation_v1` | `--mode validate-approval` |

## 本 review 实际生成的文件

| 文件 | 字节 | 触发命令 |
|---|---|---|
| `preflight_result.json` | 3850 | `--mode preflight` |
| `unsigned_package.json` | 3149 | `--mode print-unsigned` |
| `approval_validation.json` | 530 | `--mode validate-approval` |

3/5 文件由 CLI mode 自动生成；2/5 由内部 helper `write_telemetry_skeleton()` 生成。

## 6 项检查

| # | 检查 | 结果 |
|---|---|---|
| 1 | 只写 reports dir | **PASS** |
| 2 | 不写 production DB | **PASS** |
| 3 | 不写 shadow 表 | **PASS** |
| 4 | 不写 positions | **PASS** |
| 5 | 全部文件在 local reports dir | **PASS** |
| 6 | 无 sensitive data leak | **PASS** |

## Future execution stage 期望

- 在执行时点调用 `write_telemetry_skeleton()` 来 seed `entry_intent.json` 和 `stop_condition_checks.json`
- 已有的 3 个文件作为 runtime telemetry substrate

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
```
