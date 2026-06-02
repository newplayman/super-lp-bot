# 输入证据审计

- stage: `LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`
- run_id: `20260602_092319`
- 上游 run_id: `20260602_060633`
- 上游 stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
- 上游 status: **`PASS`**
- 上游 recommended_next_stage: `LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`

## 9 份输入全部读取成功

| 文件 | 状态 |
|---|---|
| `FINAL_VERDICT.json` | ✓ |
| `ONEPAGE_CN.md` | ✓ |
| `BSC_10_20U_PROBE_PREFLIGHT_DESIGN_CN.md` | ✓ |
| `bsc_10_20u_probe_preflight_design.json` | ✓ |
| `BSC_REALDATA_ECONOMICS_WITH_RECOVERED_FEE_CN.md` | ✓ |
| `bsc_realdata_economics_with_recovered_fee.csv` | ✓ |
| `BSC_FEE_VELOCITY_SHORT_BACKFILL_RESULTS_CN.md` | ✓ |
| `bsc_fee_velocity_short_backfill_results.csv` | ✓ |
| `BSC_RPC_ETH_GETLOGS_CAPABILITY_MATRIX_CN.md` | ✓ |

## 上游关键字段（已逐项确认）

| 字段 | 值 |
|---|---|
| fee_ready_pool_count | **7** (8 中 7 个可用) |
| decoded_swap_log_count | **273,563** |
| positive_proxy_count_realistic | **0** |
| near_break_even_count | **394** |
| best_pool | `0x172fcd41e0913e95784454622d1c3724f546f849` |
| best_pair | `USDT/WBNB` |
| best_fee_tier | `100` (0.01%) |
| best_notional | `20` (USD) |
| best_hold_window | `15m` |
| best_net_ev_proxy_usd | `-0.015560` |
| probe_preflight_design_ready | **true** |
| can_run_probe_now | **false** |
| manual_approval_required_for_probe | **true** |
| edge_proven | **no** |
| actual_fee_ready | **false** |
| token_id_available | **false** |

## 本轮可做 / 不可做

**只允许**：
- 读取上游报告与链上 read-only 数据
- 设计 dry-run builder I/O / 人工审批门禁 / probe 遥测字段
- 生成审查报告与审批包
- commit / push

**绝对禁止**：
- 加载 wallet / 读取私钥 / 创建 signer
- approve / mint / increaseLiquidity / decreaseLiquidity / collect / swap
- 发送任何交易（eth_sendTransaction / eth_sendRawTransaction）
- 启动 live / canary / paper
- 把 preflight 变成执行
- 翻转 `can_run_probe_now` 或 `tiny_canary_allowed`

## 上游 verdict 字段一致性结论

```text
all expected fields present     = yes
status PASS                     = yes
can_run_probe_now = false       = yes
manual approval required        = yes
this round is preflight review  = yes
```
