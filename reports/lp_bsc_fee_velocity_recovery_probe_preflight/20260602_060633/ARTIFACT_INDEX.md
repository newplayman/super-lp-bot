# Artifact Index — `20260602_060633`

Stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
Status: **`PASS`**
Recommended next stage: `LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`

## 报告文件

| 文件 | 用途 |
|---|---|
| `FINAL_VERDICT.json` | 顶层汇总 verdict |
| `ONEPAGE_CN.md` | 单页总览 |
| `CURRENT_RUN_FINALIZER_CN.md` / `current_run_finalizer.json` | Phase 1 上一轮 overnight 收尾 |
| `STOPPED_STALE_READONLY_RUN_CN.md` | Phase 1 安全停止旧 run 的取证记录 |
| `BSC_RPC_ETH_GETLOGS_CAPABILITY_MATRIX_CN.md` / `*.csv` / `*.json` | Phase 2 BSC RPC eth_getLogs 能力矩阵 |
| `BSC_FEE_VELOCITY_1POOL_24H_SMOKE_CN.md` / `*.csv` / `*.json` | Phase 3 1池 24h smoke |
| `BSC_FEE_VELOCITY_SHORT_BACKFILL_RESULTS_CN.md` / `*.csv` / `*.json` | Phase 4 8池 × 24h/72h/7d 回填 |
| `bsc_swap_logs_decoded_short.csv` | Phase 4 解码 swap 样本 |
| `BSC_REALDATA_ECONOMICS_WITH_RECOVERED_FEE_CN.md` / `*.csv` / `*.json` | Phase 5 economics preview |
| `BSC_10_20U_PROBE_PREFLIGHT_DESIGN_CN.md` / `*.json` | Phase 6 10/20U probe preflight 设计（仅设计，不执行） |

## 工具脚本（仓库 `scripts/`）

- `scripts/lp_bsc_rpc_eth_getlogs_capability_matrix_v1_readonly.py`
- `scripts/lp_bsc_fee_velocity_smoke_v1_readonly.py`
- `scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py`
- `scripts/lp_bsc_realdata_economics_with_recovered_fee_v1_readonly.py`
- `scripts/lp_bsc_10_20u_probe_preflight_design_v1_readonly.py`
- `scripts/lp_bsc_recovery_final_verdict_v1_readonly.py`（本脚本）

## 测试（仓库 `tests/`）

- `tests/test_lp_bsc_fee_velocity_recovery_probe_preflight_v1_readonly.py`
