# Orca Whirlpool Pool Snapshot — Stage G

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`

## 0. 关键结果

```text
attempted_count           = 75
sdk_decode_success_count  = 75    (100% via @orca-so/whirlpools 8.0.0)
sdk_decode_failure_count  = 0
high_fee_pool_count       = 40    (fee_rate_bps >= 30)
stable_pair_count         = 24    (USDC/USDT in tokenA or tokenB)
sol_pair_count            = 42    (SOL in tokenA or tokenB)
quote_candidate_count     = 0     (filled in stage I)
```

## 1. Fee tier 分布 (实际链上, 不是 metadata)

| fee_bps | count | Orca tier |
|---|---|---|
| 1 | 13 | Splash / ultra-low |
| 2 | 3 | low |
| 4 | 4 | standard stable |
| 5 | 9 | standard |
| 16 | 6 | mid |
| 30 | 31 | high |
| 65 | 1 | high (custom) |
| 100 | 6 | very high |
| 200 | 2 | extreme |

**Orca fee model**: per-pool `feeRate` is on-chain (u16); SDK reads live.

## 2. Top 10 池 by liquidity (Q64.64 raw)

| pool | tick_spacing | fee_bps | liquidity | current_tick | tokenA | tokenB |
|---|---|---|---|---|---|---|
| `Hp53XEtt4S8S` | 1 | 1 | 5.86e16 | -2485 | SOL | J1toso1u (jitoSOL) |
| `9tXiuRRw7kbe` | 1 | 1 | 1.51e16 | 0 | 2b1kV6Dk | USDC |
| `9RqDTfwCx2Sg` | 1 | 1 | 1.31e16 | 5 | 2u1tszSe | USDC |
| `4fuUiYxTQ6QC` | 1 | 1 | 1.71e15 | 8 | USDC | USDT |
| `45zpzzpZquaV` | 64 | 30 | 1.47e15 | 43106 | hntyVP6Y | mb1eu7Tz |
| `KLkoFSdCpC52` | 64 | 30 | 5.99e14 | 61029 | SOL | 3dQTr7ro |
| `DtYKbQELgMZ3` | 1 | 1 | 4.88e14 | -1720 | SOL | jupSoLaH |
| `Czfq3xZZDmsd` | 4 | 4 | 2.86e14 | -26485 | SOL | USDC |
| `AxqAWNZqozhT` | 1 | 1 | 2.41e14 | 0 | USDSwr9A | USDC |
| `5xfKkFmhzNhH` | 1 | 1 | 2.41e14 | -1356 | WFRGSWja | J1toso1u |

## 3. Orca fee 模式

Orca Whirlpools 用 V3-like 集中流动性:
- tick_spacing = 1 (tightest, 1bps fee) — stable / low-vol
- tick_spacing = 4 / 8 (4-5bps fee) — standard SOL/USDC
- tick_spacing = 64 (30bps fee) — mid vol / memecoin
- tick_spacing = 128 (100bps fee) — high vol / exotic
- max fee in our sample: 200bps (2%) — extreme

## 4. SDK 路径走通验证

- `fetchConcentratedLiquidityPool(rpc, mintA, mintB, tickSpacing)` → 100% success
- on-chain liquidity / sqrt_price / tick_current_index / fee_rate 全部读出
- 无 keypair / 无 signer / 无 transaction

## 5. 安全断言

```text
no_keypair_loaded                = true
no_signer_constructed            = true
no_transaction_sent               = true
solana_wallet_or_keypair_touched = false
SDK @orca-so/whirlpools 8.0.0   = used for decode only
repo_node_modules                = NOT created (SDK in /tmp isolated)
```

## 6. 下一阶段

进入 Stage H — tick array read/decode (bounded coverage, hard cap 5 arrays, single-account getAccountInfo path)。
