# Telemetry Writer Skeleton Spec

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- phase: G
- run_id: `20260602_135824`

## 输出目录

```text
reports/lp_base_10u_probe_execution_runtime/<run_id>/
```

**仅写本地 reports 目录**。不写 production DB / shadow 原始表 / 任何 production positions。

## 5 个 schema files

| 文件 | schema 名 | 用途 |
|---|---|---|
| `entry_intent.json` | `lp_probe_execution_ledger_v1` | skeleton entry intent（frozen candidate + deadline placeholder + fabrication_blocked） |
| `preflight_checks.json` | `lp_probe_preflight_v1` | skeleton placeholder；真实结果由 `--mode preflight` 写 |
| `stop_condition_checks.json` | `lp_probe_stop_condition_checks_v1` | skeleton placeholder for stop condition evaluation |
| `unsigned_package.json` | `lp_probe_unsigned_package_v1` | `run_print_unsigned()` 输出；含 `unsigned_only` / `no_signature` / `no_send` / `execution_not_authorized` |
| `approval_validation.json` | `lp_probe_approval_validation_v1` | `run_validate_approval()` 输出；含 `executes_now=false` / `authorization_granted=false` |

## 不写

- `lp_probe_execution_ledger_v1` 表
- `lp_probe_hold_monitor_v1` 表
- `lp_probe_position_fee_trace_v1` 表
- `lp_probe_exit_trace_v1` 表
- `lp_probe_post_exit_v1` 表
- `lp_probe_actual_pnl_v1` 表
- 任何 `shadow_*` 表
- 任何 production positions

（这些 schema 是**设计稿**；写 production 表是未来独立 stage 的事，必须 post-freeze、被批准。）

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
```
