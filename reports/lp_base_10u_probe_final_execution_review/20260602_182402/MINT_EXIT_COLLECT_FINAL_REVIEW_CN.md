# Mint / Exit / Collect / Revoke Final Review

- stage: `LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1`
- phase: G
- run_id: `20260602_182402`
- 审查源码:
  - `build_mint_position_tx` l.476-521
  - `encode_mint` l.217-244
  - `monitor_position_loop_stub` l.526-545
  - `build_decrease_liquidity_tx` l.548-575
  - `build_collect_tx` l.578-599
  - `build_revoke_allowance_tx` l.602-613

## mint 审查

| 审查项 | 期望 | 源代码定位 | 实际 | 结果 |
|---|---|---|---|---|
| 参数结构正确 | 11-tuple `(token0, token1, fee, tickLower, tickUpper, amount0Desired, amount1Desired, amount0Min, amount1Min, recipient, deadline)` | l.228-239 encode；l.493 function signature | true | **PASS** |
| recipient = wallet | true | l.491 `wallet`，l.514 params.recipient = wallet，l.516 `recipient_bound_to_wallet:True` | true | **PASS** |
| deadline runtime 生成 | `int(time.time()) + 3600` | l.487 | true | **PASS** |
| amount0/amount1 desired & min 有 bound | true | print-unsigned 路径使用 `amount1_min_raw = int(amount * 0.995)` (l.904)，固定 0.5% slippage；self-check 用 9_949_999 | true | **PASS** |
| selector 正确 | `0x88316456` | l.131 + l.494 | true | **PASS** |
| encode_mint 不会双 0x | true | l.242-244 strip leading 0x 然后 concat | true (上轮已 fix) | **PASS** |
| fee tier locked | 100 | l.488 | true | **PASS** |
| token0/token1 order | WETH/USDC | l.488, l.65-66 | true | **PASS** |

## exit (decrease + collect + revoke) 审查

| 审查项 | 期望 | 源代码定位 | 结果 |
|---|---|---|---|
| decrease 构造存在 | true | `build_decrease_liquidity_tx` l.548-575 | **PASS** |
| decrease selector | `0x02751cec` | l.133, l.558 | **PASS** |
| decrease deadline runtime | now+3600 | l.554 | **PASS** |
| collect 构造存在 | true | `build_collect_tx` l.578-599 | **PASS** |
| collect selector | `0xfc6f7865` | l.135, l.585 | **PASS** |
| collect recipient = wallet | true | l.582 (passed `wallet`) | **PASS** |
| collect amount0Max / amount1Max = uint128.max | `(1 << 128) - 1` | l.579-580 default args | **PASS** |
| revoke 构造存在 | true | `build_revoke_allowance_tx` l.602-613 | **PASS** |
| revoke 组合 USDC + WETH | true | l.605-606 | **PASS** |

## monitor 限制审查

| 审查项 | 期望 | 源代码定位 | 结果 |
|---|---|---|---|
| iterations = 1 only | true | l.534-535 `if iterations > 1: raise ValueError` | **PASS** |
| 不启长循环 | true | l.543 `long_loop_started:False` | **PASS** |
| 无后台进程残留 | true | l.544 `background_process_left:False` | **PASS** |

## send path triggered 检查

| function | send_path_triggered? |
|---|---|
| build_mint_position_tx | **no** — l.518-520 `unsigned_only/no_send/transaction_sent=False/no_signature=True` |
| build_decrease_liquidity_tx | **no** — l.572-574 |
| build_collect_tx | **no** — l.596-598 |
| build_revoke_allowance_tx | **no** — l.610-612 |
| monitor_position_loop_stub | **no** — 仅返 dict |

## tokenId 记录 & fee telemetry 计划

| 审查项 | 当前状态 | 计划 |
|---|---|---|
| tokenId 记录 planned | **存在结构** — `build_decrease_liquidity_tx(wallet, token_id, ...)` / `build_collect_tx(wallet, token_id, ...)` / `monitor_position_loop_stub(token_id, iterations)` 均把 token_id 作为入参；telemetry `unsigned_mint_package.json` 包含 mint 参数；exit-side schema 待 authorization package 阶段补 `position_open / position_close` 文件 | **需在 authorization package 阶段新增** `mint_receipt.json`（含 tokenId 解码） + `decrease_collect_receipt.json` schema |
| feeGrowthInside / tokensOwed telemetry planned | **deviation** — v2 没有 builder 读取 `positions(tokenId)` 返回的 `feeGrowthInside0LastX128 / tokensOwed0 / tokensOwed1`；当前 build 只构造 tx，不读 chain 状态 | **需在 authorization package 阶段新增** `read_position_state_for_fee_accrual` 模式 |

这两个 deviation 都不阻断本 review；它们是未来 authorization package 阶段的必要补充。

## 本 review 是否触发 send

**no** — Stage G 仅做静态审查 + 代码 review；未调用任何 builder（除 Stage D preflight 已通过 read-only RPC 调用 `dynamic_tick_range_recompute` + telemetry write）。

## verdict

| field | value |
|---|---|
| mint_params_structurally_correct | true |
| recipient_bound_to_wallet | true |
| deadline_runtime_generated | true |
| amount_desired_min_bounded | true |
| decrease_builder_exists | true |
| collect_builder_exists | true |
| revoke_builder_exists | true |
| monitor_long_loop_refused | true |
| no_send_path_triggered | true |
| tokenId_recording_planned | true (struct ready；schema 待 authorization package) |
| feeGrowth_tokensOwed_telemetry_planned | partial (deviation logged) |
| mint_exit_collect_review_pass | **true** (deviations 非阻断) |

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
tiny_canary_allowed           = no
mint_executed                 = false
decrease_executed             = false
collect_executed              = false
```
