# 10/20U Probe 风控边界（仅设计，不执行）

- stage: `LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`
- phase: D

## 资金限制

```text
max_total_funds_usd                = 20
preferred_probe_funds_usd          = 10
max_single_pool_count              = 1
max_concurrent_positions           = 1
max_total_positions_per_day        = 1
no_auto_repeat                     = true
no_multi_pool                      = true
no_compounding                     = true
no_hidden_approval                 = true
no_automatic_retry_if_mint_fails   = true
no_automatic_swap_back_if_quote_unsafe = true
```

## 持有时间

```text
initial_hold_window                  = 15m
max_extension_hold_window            = 30m  (仅 health_ok 时人工手动延长)
extension_decision_is_manual         = true
default_action_at_initial_hold_expiry = exit
```

`health_ok` 的要求：

- tick 仍在选定 `[tickLower, tickUpper]` 范围内
- mid-price drift 未超 stop 阈值
- fee velocity 最近 5m bucket 非零
- 最近 10 个 RPC 调用全部成功
- 无 pending approval / decrease / collect

## 10 个 stop conditions

| # | 触发 | 阈值 | 动作 |
|---|---|---|---|
| S1 | quote drift | mid-price 移动 >40 bps | exit_immediately |
| S2 | gas spike | exit 时 gas_price > mint 时 5× | exit_immediately 或 5min 内等正常化 |
| S3 | tick out-of-range | 任何超过 `[tickLower, tickUpper]` 的 tick | exit_immediately |
| S4 | pool liquidity collapse | active-tick liquidity < mint 时 50% | exit_immediately |
| S5 | fee velocity stale | candidate pool 5min 内无新 Swap | exit_immediately |
| S6 | RPC unstable | 最近 5 个调用中 ≥2 个失败 | exit_immediately |
| S7 | token approval unexpected | 已存在 allowance 且 ≠ planned ApproveExact 数量 | abort_before_mint |
| S8 | tokenId 未识别 | mint 后 30s 内未观察到 PositionManager NFT Transfer | alert_and_freeze（不自动 exit，等人工） |
| S9 | exit quote unavailable | QuoterV2 staticcall 失败 / 返回 0 | 等 60s + 重试一次，然后 freeze（不强行 swap） |
| S10 | mark-to-market loss | M2M 损失 > $0.50 | exit_immediately |

## Approval 政策

```text
approve_strategy                      = ApproveExact
approve_max_forbidden                 = true
post_exit_revoke_required             = true
approval_recipient_allowlist          = [PancakeSwap V3 NonfungiblePositionManager (BSC)]
approval_amount_capped_at_probe_notional = true
```

绝对禁止 `ApproveMax` / `Approve(uint256.MAX)` 类调用。Exit 后必须执行 revoke。

## Pre-mint 必须全部 true 的硬门禁

```text
1. rpc_capability_matrix_passed
2. candidate_pool_tickLiquidity_present_in_active_range
3. real_cost_model_present_for_this_notional
4. fee_velocity_present_for_this_window
5. human_operator_typed_explicit_approval_phrase
6. dry_run_builder_produced_calldata_simulated_with_eth_call_only_no_signing
7. wallet_address_confirmed_in_allowlist
8. BSC_RPC_PRIMARY_env_var_set_to_paid_endpoint
9. gas_price_below_per_session_ceiling
10. no_active_lpbot_live_or_canary_or_paper_process_on_host
```

任何一条 false → 不准 mint。本设计不允许自动解锁 — 必须人工依据上述清单一项项打勾。

## 安全标记

```text
wallet_or_tx_touched         = false
can_run_probe_now            = false
tiny_canary_allowed          = no
edge_proven                  = no
```
