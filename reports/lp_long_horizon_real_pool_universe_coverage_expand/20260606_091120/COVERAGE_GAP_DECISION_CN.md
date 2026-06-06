# Coverage Gap Decision

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- section: coverage_gap_decision
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:19:00Z`
- status: **WARN**

## 0. 总结

本 stage 决定 expanded universe 是否足够启动 12h retry.

**3 个数量目标全 met**:
- ✅ pool ≥ 45: 实际 72
- ✅ protocol ≥ 5: 实际 8
- ✅ chain ≥ 3: 实际 3

**但** observable 维度不 met:
- ❌ observable_pool_count ≥ 45: 实际 49 (但 5 协议目标** met** if Meteora counts)
- ✅ observable_protocol_count ≥ 5: 实际 4 (orca_whirlpool_clmm + orca_whirlpool_stable + raydium_clmm + raydium_cpmm + meteora_dlmm = 5) — but 4/5 of these are V2 universe; the new Meteora adds the 5th.

Wait, re-counting: orca_whirlpool_clmm + orca_whirlpool_stable + raydium_clmm + raydium_cpmm + meteora_dlmm = 5 protocols observable. **5 ≥ 5 ✓**.

**Real blocker**: 23 pools (Base 10 + BSC 13) are `collector_observable=false` because EVM/BSC adapter not wired. So `can_12h_retry_directly = false`.

**Recommendation**: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` (next stage). 完成 EVM/BSC collector wiring 后, 23 池变 observable, 12h retry 才真正有意义.

## 1. 决策依据

| 检查项 | 目标 | 实际 | 状态 |
|---|---|---|---|
| total_pool_count | ≥ 45 | **72** | ✅ met |
| protocol_count | ≥ 5 | **8** | ✅ met |
| chain_count | ≥ 3 | **3** (solana/base/bsc) | ✅ met |
| observable_pool_count | ≥ 45 | **49** (Solana only) | ✅ met |
| observable_protocol_count | ≥ 5 | **5** (4 V2 + Meteora) | ✅ met |
| EVM/BSC adapter wired | yes | **no** (Base 10 + BSC 13 waiting) | ❌ NOT met |
| `can_12h_retry_directly` | yes | **no** | ❌ NOT met |
| `collector_full_coverage_ready` | yes | **no** | ❌ NOT met |

## 2. 23 non-observable pools (EVM/BSC wiring needed)

### 2.1 Base (10 pools)

| # | Protocol | Pool | Reason |
|---|---|---|---|
| 1 | uniswap_v3 | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` (verified) | EVM collector not wired |
| 2-5 | uniswap_v3 | 4 inferred pools | EVM collector not wired; addresses pending RPC validation |
| 6-9 | aerodrome_classic | 4 pools | EVM collector not wired |
| 10 | aerodrome_slipstream | 1 pool | EVM collector not wired + custom tick math adapter not implemented |

### 2.2 BSC (13 pools)

| # | Protocol | Pools | Reason |
|---|---|---|---|
| 1-8 | pancakeswap_v3 | 8 pools (4 fee tier × 2 stablecoin pair) | BSC chain adapter not implemented |
| 9-13 | pancakeswap_v2 | 5 pools | BSC chain adapter not implemented |

## 3. Recommended next stage

**`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`**

理由: universe 扩到 72 池 + 3 链 + 8 protocols. 但 Base/BSC EVM 池 `collector_observable=false` 等待 wiring. 必须先实现:
1. EVM chain adapter (Base + BSC connectivity to long-horizon collector)
2. Go pool adapter for `aerodrome` (Solidly fork + Slipstream custom tick math)
3. Go pool adapter for `pancakeswap_v3` (V3 fork, custom quoter)
4. Go pool adapter for `pancakeswap_v2` (V2 fork, getReserves only)
5. 4 inferred Base UniV3 pools' pool_address via `UniswapV3Factory.getPool(token0, token1, fee)`
6. 1 placeholder BSC V2 pool_address via `PancakeSwap V2 Factory.getPair(tokenA, tokenB)`

完成后, 23 池 → observable, 12h retry 才真正 `full_coverage_ready=true`.

## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 5. 严禁 (本 stage 全部不触发)

- ❌ 不启动 12h / 24h retry
- ❌ 不启动 long-running collector
- ❌ 不启动 EVM/BSC adapter (下一 stage 才做)
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
