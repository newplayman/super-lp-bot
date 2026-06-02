# Exit / Collect / Revoke Builder 实现

- stage: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`
- phase: G
- run_id: `20260602_163036`

## 实现

`scripts/lp_base_10u_probe_executor_v2.py` 中 4 个函数：

| 函数 | 描述 |
|---|---|
| `monitor_position_loop_stub` | 单次 stub；iterations>1 直接 raise |
| `build_decrease_liquidity_tx` | NPM.decreaseLiquidity(tokenId, liquidez, amount0Min, amount1Min, deadline) |
| `build_collect_tx` | NPM.collect(tokenId, recipient=wallet, amount0Max=uint128.max, amount1Max=uint128.max) |
| `build_revoke_allowance_tx` | 合并 revoke-USDC + revoke-WETH |

## 限制

- monitor **只能** iterations=1；iterations>1 raise ValueError
- decrease / collect / revoke 只输出结构化 dict；**不发送**；**不签名**；**不调用任何 transact()**
- deadline 在每个 builder 中实时计算（now+3600；不是 legacy 2099-01-01 placeholder）

## 5 项测试 全部 PASS

| # | test | result |
|---|---|---|
| 1 | monitor_position_loop_stub(iterations=1) | **PASS** (token_id=42, ran_in_dry_run=True, long_loop_started=False) |
| 2 | monitor_position_loop_stub(iterations=5) | **PASS rejected** (ValueError) |
| 3 | build_decrease_liquidity_tx(token_id=42, liquidity=1e18) | **PASS** (selector 0x02751cec correct, deadline now+3600, unsigned_only/no_send/transaction_sent=False) |
| 4 | build_collect_tx(token_id=42) | **PASS** (recipient=wallet, amount0Max=uint128.max, amount1Max=uint128.max) |
| 5 | build_revoke_allowance_tx | **PASS** (revoke_usdc=0, revoke_weth=0, approvemax_forbidden=True) |

## 安全

```text
no_tx_sent                  = true
no_sign                     = true
no_signer_constructed      = true
no_wallet_client_constructed = true
no_long_loop_started        = true
no_background_process_left  = true
unsigned_only               = true
no_send                     = true
transaction_sent            = false
wallet_or_tx_touched        = false
can_run_probe_now           = false
tiny_canary_allowed         = no
```
