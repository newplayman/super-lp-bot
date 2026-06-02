# 输入证据审计

- stage: `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- run_id: `20260602_094727`

## 上游：`LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`（已 PASS）

| 字段 | 值 |
|---|---|
| source_run_id | `20260602_092319` |
| status | **`PASS`** |
| dry_run_builder_allowed_next | **true** |
| can_run_probe_now | **false** |
| manual_approval_required_for_probe | **true** |
| realistic_positive_ev | **false** |
| near_break_even | **true** |
| actual_fee_ready | **false** |
| token_id_available | **false** |
| recommended_next_stage | `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1` |

## 上游 (recovery)：候选池经济回顾

| 字段 | 值 |
|---|---|
| best_pool | `0x172fcd41e0913e95784454622d1c3724f546f849` |
| best_pair | USDT/WBNB |
| best_fee_tier | 100 (0.01%) |
| best_notional | 20 USD |
| best_hold_window | 15m |
| best_net_ev_proxy_usd | -$0.0156 |

## 10 份输入全部读取

| 文件 | 状态 |
|---|---|
| preflight/FINAL_VERDICT.json | ✓ |
| preflight/ONEPAGE_CN.md | ✓ |
| preflight/BSC_10_20U_PROBE_APPROVAL_PACKET_CN.md | ✓ |
| preflight/bsc_10_20u_probe_approval_packet.json | ✓ |
| preflight/BSC_PROBE_DRY_RUN_BUILDER_SPEC_CN.md | ✓ |
| preflight/bsc_probe_dry_run_builder_spec.json | ✓ |
| preflight/BSC_PROBE_REQUIRED_TELEMETRY_CN.md | ✓ |
| preflight/bsc_probe_required_telemetry.json | ✓ |
| recovery/FINAL_VERDICT.json | ✓ |
| recovery/bsc_realdata_economics_with_recovered_fee.csv | ✓ |

## 本轮可做 / 不可做

**只允许**：
- `eth_call` / `staticcall` (read-only)
- read-only QuoterV2 quote
- read-only pool state (slot0 / liquidity / fee / tickSpacing / ticks)
- read-only token metadata
- 计算 tickLower / tickUpper 提案
- 计算 10U / 20U 的 token0 / token1 数量
- 构造 unsigned calldata（**JSON 描述**，不签名不发送）
- 输出人工审批 packet

**绝对禁止**：
- 发送任何交易（`eth_sendTransaction` / `eth_sendRawTransaction`）
- 读取私钥 / wallet seed
- 创建 signer
- 执行 approve / mint / increaseLiquidity / decreaseLiquidity / collect / swap / burn
- 写 production positions
- 覆盖 shadow 表
- 自动触发下一阶段
- 翻转 `can_run_probe_now` 或 `tiny_canary_allowed`

## 通过条件

```text
all_inputs_verified        = true
all_upstream_gates_aligned = true
proceed_to_phase_C         = true
```
