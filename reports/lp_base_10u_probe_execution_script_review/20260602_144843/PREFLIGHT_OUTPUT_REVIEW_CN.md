# Preflight Output Review

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: E
- run_id: `20260602_144843`
- artifact: `reports/lp_base_10u_probe_execution_runtime/20260602_144843/preflight_result.json` (3845 bytes)

## 1. 关键字段审查

| 字段 | 期望 | 观察 | 通过 |
|---|---|---|---|
| chain_id | 8453 | 8453 | ✓ |
| block_number | (any) | 46811291 | ✓ |
| gas_price_wei | (any) | 7,362,833 (~0.0074 gwei) | ✓ |
| eth_native_wei | ≥ 9.0e-5 ETH = 9e13 wei | 9.047e13 wei (0.0000905 ETH ≈ $0.18) | ✓ (borderline) |
| weth_raw | (any) | 2,470,131,003,793,800 (0.00247 WETH ≈ $4.89) | ✓ |
| usdc_raw | ≥ 12,000,000 | 21,774,783 (21.775 USDC) | ✓ |
| usdc_allowance_raw | < 50,000,000 (no trigger) | 5,000,000 (5 USDC) | ✓ |
| weth_allowance_raw | < 1e24 (no trigger) | 2,470,131,003,793,800 | ✓ |
| sqrt_price_x96 | (any) | 3,490,920,925,004,229,405,272,501 | ✓ |
| current_tick | within 200 of -200443 | -200609 (drift 166 < 200) | ✓ |
| current_liquidity | > 1e15 | 6.21e17 | ✓ |
| preflight_status | PASS / WARN / FAIL | **PASS** | ✓ |
| stops_triggered_count | 0 | **0 / 13** | ✓ |

## 2. 偏差（deviation）

| 字段 | 偏差 | 原因 | 含义 |
|---|---|---|---|
| `mint_estimate_gas` | null (read_success=false) | publicnode 对 mint call revert（与上一阶段 dry-run 行为一致） | 未来 implementation stage 必须 (a) 用付费 RPC 或 (b) 继承 upstream real_cost_model CSV |
| `quoter_v2_live_read_status` | `skipped_or_revert_inherited` | publicnode 对 QuoterV2 revert | 继承自 upstream precise_quote CSV |

这两个偏差**不**影响 preflight 总体 PASS；但未来 implementation stage 必须解决。

## 3. 可能挡住未来执行的 stop conditions

| stop | 阈值 | 当前观察 | 当前是否会挡 |
|---|---|---|---|
| stop_tick_moved_outside_planned_range_before_entry | abs(tick - (-200443)) > 200 | drift 166 | **不挡**（166 < 200） |
| stop_gas_balance_below_threshold | < 9.0e-5 ETH | 9.047e-5 ETH | **不挡**（刚好过） |
| stop_usdc_balance_below_required | < 12 USDC | 21.775 | **不挡** |
| stop_pool_liquidity_drop | < 1e15 | 6.21e17 | **不挡** |
| stop_allowance_unexpected (USDC) | > 50M | 5M | **不挡** |
| stop_allowance_unexpected (WETH) | > 1e24 | 2.47e15 | **不挡** |
| stop_gas_estimate_too_high | > 360k | null (reverted) | **不挡**（revert 不算 estimate 太大） |

## 4. 13 个 stops 全部审查

| id | triggered | reason |
|---|---|---|
| stop_chain_id_mismatch | false | chain_id_observed=8453 |
| stop_gas_balance_below_threshold | false | eth_balance=9.05e-5 ETH ≥ 9e-5 |
| stop_usdc_balance_below_required | false | usdc=21.775 ≥ 12 |
| stop_weth_balance_below_required | false | weth=0.00247 ≥ 0 |
| stop_allowance_unexpected (USDC) | false | 5M < 50M |
| stop_allowance_unexpected (WETH) | false | 2.47e15 < 1e24 |
| stop_tick_moved_outside_planned_range_before_entry | false | drift 166 < 200 |
| stop_pool_liquidity_drop | false | 6.21e17 > 1e15 |
| stop_gas_estimate_too_high | false | null (reverted; not > 360k) |
| stop_quoter_v2_failure | false | skipped_or_revert_inherited (not 0) |
| stop_quote_slippage_above_threshold | false | slippage=None% (not > 5%) |
| stop_rpc_instability | false | no instability |
| stop_unknown_error | false | no unknown error |

## 5. Preflight 是否能提供足够信息给未来执行阶段？

**是。** 未来执行 stage 可以从 preflight_result.json 拿到：

- 当前 `block_number`（用于 staleness check）
- 余额（USDC, WETH, ETH native）
- allowance（USDC → NPM = 5 USDC，需要 ApproveExact 5+）
- 当前 `current_tick`（与 frozen -200443 偏差 166 ticks；future stage 需重判 range）
- `current_liquidity`（远高于 1e15 阈值）
- 13 个 stop 的 triggered/handling 状态
- 整体 `preflight_status`

**未提供**（需要 future stage 自取）：

- tokenId 捕获（mint 之后才有）
- actual fee accrual（hold 之后才有）
- 退出余额（decrease + collect 之后才有）

## 6. 安全

```text
no_signer_constructed    = true  (preflight output 无 Account / wallet client 引用)
no_tx_sent                = true  (只有 eth_call / eth_getBalance)
no_approve                = true  (只读 USDC.allowance)
no_mint                   = true  (没有 mint tx hash; 只有 reverted estimateGas)
no_send                   = true
```
