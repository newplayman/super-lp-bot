# Telemetry Schema Review

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: I
- run_id: `20260602_144843`

## 5 个 schema files 设计

| 文件 | schema | written by | 字段数 |
|---|---|---|---|
| `entry_intent.json` | `lp_probe_execution_ledger_v1` | `write_telemetry_skeleton()` (内部 helper) | 17 |
| `preflight_checks.json` | `lp_probe_preflight_v1` | `write_telemetry_skeleton()` (内部 helper) | 24 |
| `stop_condition_checks.json` | `lp_probe_stop_condition_checks_v1` | `write_telemetry_skeleton()` (内部 helper) | 13 stops + overall |
| `unsigned_package.json` | `lp_probe_unsigned_package_v1` | `--mode print-unsigned` | candidate(12)+wallet(3)+notional(5)+approve(11)+approve_weth(2)+mint(12)+4 flags |
| `approval_validation.json` | `lp_probe_approval_validation_v1` | `--mode validate-approval` | 7 |

## 本 review 实际生成的文件

| 文件 | 字节 | 触发命令 |
|---|---|---|
| `preflight_result.json` | 3845 | `--mode preflight` |
| `unsigned_package.json` | 3149 | `--mode print-unsigned` |
| `approval_validation.json` | 530 | `--mode validate-approval` |

3/5 文件由 CLI mode 自动生成；2/5（`entry_intent.json`、`stop_condition_checks.json`）由内部 helper `write_telemetry_skeleton()` 生成，**未**绑到 CLI mode（与上一阶段 Phase G 设计一致：它们是 skeleton placeholder，未来 execution stage 才会调用 helper）。

## 6 项检查

| # | 检查 | 结果 | 证据 |
|---|---|---|---|
| 1 | 只写 reports dir | **PASS** | writes_path_prefix = `reports/lp_base_10u_probe_execution_runtime/<run_id>/` |
| 2 | 不写 production DB | **PASS** | 无 SQL / cursor / DB driver imports；仅 json + urllib.request + pathlib |
| 3 | 不写 shadow 表 | **PASS** | 无 `shadow_*` 表写入；`lp_probe_*_v1` 是 schema 提案（不是实际表） |
| 4 | 不写 positions | **PASS** | 无 'position' / 'ledger' / 'trade' 文件写入（reports 之外） |
| 5 | 全部文件在 local reports dir | **PASS** | 都在 `reports/lp_base_10u_probe_execution_runtime/20260602_144843/` |
| 6 | 无 sensitive data leak | **PASS** | 只含公开地址 / 余额 / tick / 金额 / hex call data；无 private_key / mnemonic / seed |

## Future execution stage 期望

- 在执行时点调用 `write_telemetry_skeleton()` 来 seed `entry_intent.json` 和 `stop_condition_checks.json`
- 已有的 3 个文件（`preflight_result.json`, `unsigned_package.json`, `approval_validation.json`）作为 runtime telemetry substrate

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
```
