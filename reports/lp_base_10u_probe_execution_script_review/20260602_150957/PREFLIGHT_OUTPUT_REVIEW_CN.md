# Preflight Output Review

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: E
- run_id: `20260602_150957`

> ⚠️ **Delta from previous review**: preflight_status changed PASS → WARN because current_tick drifted past the 200-tick threshold. This is **correct behavior** of the stop condition engine.

## 1. 关键字段审查

| 字段 | 期望 | 观察 | 通过 |
|---|---|---|---|
| chain_id | 8453 | 8453 | ✓ |
| block_number | (any) | 46811930 | ✓ |
| gas_price_wei | (any) | 6,000,000 | ✓ |
| eth_native_wei | ≥ 9.0e-5 ETH | 9.047e13 wei | ✓ (borderline) |
| weth_raw | (any) | 2,470,131,003,793,800 | ✓ |
| usdc_raw | ≥ 12,000,000 | 21,774,783 | ✓ |
| usdc_allowance_raw | < 50M | 5,000,000 | ✓ |
| weth_allowance_raw | < 1e24 | 2.47e15 | ✓ |
| sqrt_price_x96 | (any) | 3,481,605,983,314,190,169,031,555 | ✓ |
| current_tick | within 200 of -200443 | **-200662** (drift **219** > 200) | **WARN_TRIGGERED** |
| current_liquidity | > 1e15 | 6.17e17 | ✓ |
| preflight_status | PASS / WARN / FAIL | **WARN** | (delta: was PASS) |
| stops_triggered_count | 0 | **1** (tick drift) | (delta: was 0) |

## 2. 偏差（deviation）

| 字段 | 偏差 | 原因 | 含义 |
|---|---|---|---|
| `current_tick = -200662` | drift 219 > 200 阈值 | WETH 价格漂移 | 触发 stop_tick_moved_outside_planned_range_before_entry |
| `mint_estimate_gas = null` | publicnode revert | (与上轮一致) | 继承 180k from upstream |
| `quoter_v2_live_read_status = skipped_or_revert_inherited` | publicnode revert | (与上轮一致) | 继承自 upstream |

## 3. ⚠️ 关键发现：tick drift 触发 stop

| 维度 | 上一轮 (20260602_144843) | 本轮 (20260602_150957) | 差 |
|---|---|---|---|
| block_number | 46811291 | 46811930 | +639 blocks |
| current_tick | -200609 | **-200662** | **-53 ticks** |
| drift from frozen -200443 | 166 ticks | **219 ticks** | +53 ticks |
| 触发 stop | (none) | **stop_tick_moved_outside_planned_range_before_entry** | (1 new) |
| preflight_status | PASS | **WARN** | (WARN, not FAIL: manual_intervention_required) |

### 这个发现证明

**executor 的 stop condition engine 工作正常**。在 ~13 分钟内 WETH 漂移了 53 ticks；累计漂移 219 ticks 触发了 manual_intervention_required stop。这正是该 stop 的设计目的：阻止 operator 盲目按 frozen range 执行。

### 未来执行 stage 必须做

- 重新计算 tick range（建议 lower_tick < -200862，upper_tick > -200462）
- 走**新审批短语**（新 session_id）才能继续
- 不应简单忽略 WARN 直接执行

## 4. 13 个 stops 全部审查

| id | triggered | reason |
|---|---|---|
| stop_chain_id_mismatch | false | chain_id=8453 |
| stop_gas_balance_below_threshold | false | eth=9.05e-5 ETH |
| stop_usdc_balance_below_required | false | usdc=21.775 |
| stop_weth_balance_below_required | false | weth=0.00247 |
| stop_allowance_unexpected (USDC) | false | 5M < 50M |
| stop_allowance_unexpected (WETH) | false | 2.47e15 < 1e24 |
| **stop_tick_moved_outside_planned_range_before_entry** | **true** | drift 219 > 200 |
| stop_pool_liquidity_drop | false | 6.17e17 > 1e15 |
| stop_gas_estimate_too_high | false | null (reverted) |
| stop_quoter_v2_failure | false | skipped_or_revert_inherited |
| stop_quote_slippage_above_threshold | false | None% (not > 5%) |
| stop_rpc_instability | false | no instability |
| stop_unknown_error | false | no unknown error |

## 5. Preflight 是否能提供足够信息给未来执行阶段？

**是。** 未来执行 stage 可以从 preflight_result.json 拿到：

- 当前 `block_number`（用于 staleness check）
- 余额（USDC, WETH, ETH native）
- allowance（USDC → NPM = 5 USDC，需要 ApproveExact 5+）
- 当前 `current_tick`（**WARNING**: 已漂出 frozen range 200 ticks）
- `current_liquidity`（远高于 1e15 阈值）
- 13 个 stop 的 triggered/handling 状态
- 整体 `preflight_status` = WARN（不再是 PASS）

**未提供**（需要 future stage 自取）：

- tokenId 捕获（mint 之后才有）
- actual fee accrual（hold 之后才有）
- 退出余额（decrease + collect 之后才有）

## 6. 安全

```text
no_signer_constructed = true
no_tx_sent             = true
no_approve             = true
no_mint                = true
no_send                = true
```

虽然 preflight_status 是 WARN（不是 FAIL），但**本轮只 review，不执行**。不会因 WARN 触发任何执行。
