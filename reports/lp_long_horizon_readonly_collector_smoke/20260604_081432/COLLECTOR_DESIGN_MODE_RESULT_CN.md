# Stage D — Design Mode 运行结果 (Design Mode Result)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`
- 阶段实际执行时间: `20260604_081808` (脚本自动派生 run_id)

## 0. 实际命令

```bash
python3 scripts/lp_long_horizon_readonly_collector_v1.py \
  --mode design \
  --out data/lp_long_horizon/20260604_081432/collector_design
```

任务规范里命令用了 `--run-id / --output-dir`, 实际脚本 CLI 是 `--out` (见 Stage C CLI 审查).
脚本用 `os.environ.get("LP_LONG_HORIZON_RUN_ID")` 或本地 timestamp 派生 run_id, 这里
未传 env, 走 timestamp 派生 (`20260604_081808`).

输出目录**强制**以 `data/lp_long_horizon/` 开头 (脚本 hard-reject 其它路径, exit 5).
本任务额外把 stdout/stderr 转写到 `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/collector_design_stdout.txt` 与 `collector_design_stderr.txt`.

## 1. 实际执行结果

| 字段 | 值 |
|---|---|
| exit_code | `0` |
| mode | `design` |
| run_id (auto) | `20260604_081808` |
| protocol_count | `5` |
| notional_levels | `[10, 20, 100, 500, 1000, 2000]` |
| rolling_windows | `('15m', '1h', '6h', '24h', '7d')` |
| regime_count | `7` |
| expected_smoke_cells | `30` (5 protocol × 1 pool × 6 notional) |
| output_root | `data/lp_long_horizon/20260604_081432/collector_design` |
| output_files_generated | (无, design mode 仅 print, 不写文件) |
| schema_files_generated | (无, design mode 仅 print schema preview) |

## 2. 安全 checklist

- [x] `no_network_calls = true` (design mode 不发任何 HTTP / RPC, 仅 print)
- [x] `no_wallet = true` (脚本不导入任何 wallet / signer / keypair)
- [x] `no_tx = true` (脚本不调用 sendTransaction / signTransaction)
- [x] `no_signer = true`
- [x] `no_daemon = true` (脚本执行完立即 exit 0)
- [x] `no_paid_rpc = true`
- [x] `no_paid_indexer = true`
- [x] safety self-check 通过 (import 时未触发 `SAFETY GUARD` SystemExit)
- [x] 4 个 source adapter 全部 stub (未触发 NotImplementedError, 因为 design mode 不调用)
- [x] 写路径约束通过 (`--out data/lp_long_horizon/...` 接受)

## 3. 输出文件

| 文件 | 用途 |
|---|---|
| `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/collector_design_stdout.txt` | design mode 完整 stdout |
| `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/collector_design_stderr.txt` | design mode 完整 stderr (空) |

注意: `data/lp_long_horizon/20260604_081432/collector_design/` 不存在, 因为 design
mode 不写文件. 这是预期行为, 不是 bug. design mode 的输出仅是 stdout 的 schema preview.

## 4. 结论

design mode 跑通, exit 0, 所有安全门禁通过. 接下来 Stage E 跑 smoke mode 1 pass,
验证 30 cells 实际写入.

Stage D 通过. 进入 Stage E.
