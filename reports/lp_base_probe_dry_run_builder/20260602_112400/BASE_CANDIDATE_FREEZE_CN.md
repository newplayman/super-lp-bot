# Base 候选池冻结

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: C
- run_id: `20260602_112400`
- wallet_address_masked: `0xb05b...d835`

## 冻结的候选

| 字段 | 值 |
|---|---|
| chain | **base** |
| chain_id | **8453** |
| pool | **`0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38`** |
| pair | **WETH/USDC** |
| protocol | Uniswap V3 (Base) |
| fee_tier | **100** (0.01%) |
| tick_spacing | 1 |
| token0 | `0x4200...0006` (WETH, decimals=18) |
| token1 | `0x8335...2913` (USDC, decimals=6) |
| NPM | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` |
| QuoterV2 | `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a` |

## Notional & horizon

| | 值 |
|---|---|
| preferred_notional_usd | **10** |
| max_notional_usd | **20** |
| horizons | 15m (first), 30m (promote only if 15m clean) |

## 钱包 token 命中

| token | balance (human) | |
|---|---|---|
| WETH | 0.002470 | ≈ $4.89 |
| USDC | 21.775 | ≈ $21.77 |
| ETH native | 0.0000905 | ≈ $0.18 (gas) |

**双 token 命中** — WETH 端 amount0 与 USDC 端 amount1 都可由钱包直接出。

## 上游 evidence（primary pool 4 层 self-consistent）

| 数据层 | 关键事实 |
|---|---|
| precise_quote | 20U capacity_pass, row 存在 |
| v3_tick_liquidity | slot0 成功, current_tick=-200503, liquidity=4.55e17 |
| real_cost_model | total_cost_usd_20u=$0.0380, quote_gas=203739 |
| real_fee_accrual | new_net_ev_proxy=-$0.0600, fee_source=pool_level_proxy_only |

## 被否的 alternates

| pool | pair | 否决理由 |
|---|---|---|
| `0x9c087eb7...` | VIRTUAL/WETH | 钱包不持 VIRTUAL；获取 VIRTUAL 需 swap，本轮禁止 |
| `0xd0b53d92...` | USDC/WETH | upstream EV proxy 对高价位 token 异常大负数（known pipeline bug） |
| `0xb94b2233...` | cbBTC/USDC | 钱包无 cbBTC + 同样 EV 异常 |
| `0xc211e1f8...` | cbBTC/WETH | 钱包无 cbBTC + 同样 EV 异常 |

## BSC 替代路径拒绝

| 字段 | 值 |
|---|---|
| candidate_pool | `0x172fcd41e0913e95784454622d1c3724f546f849` (USDT/WBNB 0.01%) |
| 拒绝理由 | upstream router Phase F: `bsc_can_dry_run_10u=false, bsc_can_dry_run_20u=false`；钱包 BSC 资金 = $0.00；本轮不桥不 swap |

## 校验

```text
frozen_count = 1
expected     = 1
match        = true
```

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
```
