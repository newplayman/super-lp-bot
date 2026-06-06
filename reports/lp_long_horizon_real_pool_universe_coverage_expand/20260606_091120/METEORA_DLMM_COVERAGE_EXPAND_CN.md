# Meteora DLMM Coverage Expand

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- section: Meteora DLMM
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:14:00Z`

## 0. 总结

✅ **Meteora DLMM coverage 已扩**. 16 个真实 Solana DLMM 池全部 verified on-chain (owner=LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo, data_len=904, dlmm_sized=true), 全部 selected for 12h retry. 与原 33 个 Solana real pools 合并后, Solana total = 49 池, 满足 45 pool target. 但**全** 49 池仅在 Solana, 因为 Base/BSC 5 协议仍未接通, 所以 `collector_full_coverage_ready` 仍 `false`.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `chain` | solana |
| `protocol` | meteora_dlmm |
| `pool_type` | dlmm |
| `verification_method` | on-chain getAccountInfo + decode |
| `verification_artifact` | `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_pool_chain_verification.json` |
| `candidate_count` | 16 |
| `verified_count` | **16** (100% verified) |
| `selected_for_12h_retry_count` | **16** |
| `placeholder_pool_count` | **0** |
| `all_pool_addresses_real` | **true** (no `<smoke_pool_`) |
| `owner_program` | LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo (Meteora DLMM program) |
| `data_len` | 904 (DLMM-sized) |
| `adapter_ready` | **true** (Meteora DLMM Go adapter exists; SDK + bin array decode) |
| `collector_observable` | **true** (Meteora DLMM 已在 long-horizon collector 中) |
| `tvl_hint` | None (R0 不量化) |
| `volume_hint` | None (R0 不量化) |

## 2. 16 selected_for_12h_retry pools

| # | Pool Address | Token Pair | Base Fee (bps) | Bin Step | Active Price | SDK Decode |
|---|---|---|---|---|---|---|
| 1 | `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | wSOL/USDC | 0.02 | None | 0.086349 | ✅ |
| 2 | `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | JTO/USDC | 1.5 | None | 0.093651 | ✅ |
| 3 | `6eR5rRdexbht8aiiQmYq7yKb7EhdD3af22B4mHDmCp8x` | PUMP-HfAF/wSOL | 2.0 | None | 0.016746 | ✅ |
| 4 | `H9b4sPAeiyN8DEcWa6MG2kvxqmCqBEpxmexwCh84jg4H` | MINT-Axhc/USDC | 2.5 | None | 0.042099 | ✅ |
| 5 | `6qz7THwQvcjF3HyDGLuKaLBUk6EyJKeZXZMWLAeiwfjd` | MINT-BPxx/USDC | 0.25 | None | 0.000265 | ✅ |
| 6 | `CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa` | PUMP-FeMb/wSOL | 1.0 | None | 0.079986 | ✅ |
| 7 | `9bL8Pptpb8M2jEAb63EoarA6Po6Akarpha3JPzQfXGS3` | MINT-Dnnm/wSOL | 1.0 | None | 0.067438 | ✅ |
| 8 | `8ztFxjFPfVUtEf4SLSapcFj8GW2dxyUA9no2bLPq7H7V` | MINT-Dz9m/wSOL | 0.2 | None | 1.412914 | ✅ |
| 9 | `2G7fxAhBo1sE4SmS9fXQ3BFPEpga3kLf4UyAVyCcp9uf` | PUMP-CPV5/wSOL | 2.0 | None | 0.005775 | ✅ |
| 10 | `Cgnuirsk5dQ9Ka1Grnru7J8YW1sYncYUjiXvYxT7G4iZ` | MINT-5UUH/wSOL | 0.2 | None | 1.010040 | ✅ |
| 11 | `FhdW3Y6Ea6hXKbkGkt5YSAVtDNd5qJ8USevMaPyEr45S` | MINT-3ZLe/USDC | 0.2 | None | 0.002862 | ✅ |
| 12 | `6oFWm7KPLfxnwMb3z5xwBoXNSPP3JJyirAPqPSiVcnsp` | BONK/wSOL | 0.05 | None | 0.000701 | ✅ |
| 13 | `BCv5Ggg5563AYfkrErdXok2hKfjgUNtQ1A4yKuNbTjQ9` | MINT-SKRb/wSOL | 0.1 | None | 0.172886 | ✅ |
| 14 | `6VxKTxaV4yY18rpzNLJwKMt3kyyiv4hjFixCbhs7j5gp` | MINT-9gnq/wSOL | 2.0 | None | 0.008262 | ✅ |
| 15 | `DJ8qzBm3ZoRi4YiVmpiLBBuc67cq737vqaTNbMRJGcvZ` | MINT-6SjV/wSOL | 1.0 | None | 0.000024 | ✅ |
| 16 | `8UYCgRrxZc3XKY8PBJDSKubAUP4mpbxoj1EZJ7A5G9wy` | PUMP-33eu/wSOL | 1.0 | None | 0.073026 | ✅ |

(全部 pool_addresses 来自 `meteora_pool_chain_verification.json` 第 i 行; 16 unique real Solana addresses; no placeholder; no smoke)

## 3. Token Pair Mapping (mint → symbol)

| Mint | Symbol |
|---|---|
| So11111111111111111111111111111111111111112 | wSOL |
| EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v | USDC |
| FUAfBo2jgks6gB4Z4LfZkqSZgzNucisEHqnNebaRxM1P | JTO |
| DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 | BONK |
| 其他 | `MINT-XXXX` (未知 mint, 仅用前 4 字符) |

## 4. 验证标准

每个 pool 都**通过**以下 4 项:
1. `account_exists = true` (getAccountInfo 返回非空)
2. `owner = LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` (Meteora DLMM program)
3. `owner_is_meteora_dlmm = true`
4. `data_len = 904` (DLMM-sized, Meteora DLMM LbPair struct size)
5. `dlmm_sized = true`
6. (可选) `sdk_decode_success = true` (lbPair bin array decode)

## 5. 与 V2 12h universe 关系

- V2 12h universe = 33 pools (5 协议: orca_whirlpool_clmm: 8, orca_whirlpool_stable: 5, raydium_clmm: 10, raydium_cpmm: 10)
- 本 stage 新增 16 Meteora DLMM pools → Solana total = 33 + 16 = **49 pools**
- **49 ≥ 45 (target_min_pool_count) → pool count target met**
- **但** collector_full_coverage_ready 仍 false 因为 Base/BSC 5 协议未接通

## 6. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 7. 严禁 (本节全部不触发)

- ❌ 不启动 Meteora collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不写 production positions
- ❌ 不接 paid RPC / paid indexer (使用 public Solana RPC)

## 8. 下游

进入 Stage C (Base Uniswap V3) + Stage D (Base Aerodrome) + Stage E (BSC PancakeSwap) → 合并到 expanded universe (Stage F) → coverage gap decision (Stage G).
