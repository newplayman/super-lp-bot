# Partial Observable Real Pool Universe for 12h

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`
- section: partial_observable_universe
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T13:16:00Z`

## 0. 总结

✅ **Partial observable universe 已就位**: 53 pools (solana 49 + bsc 4). 0 placeholder. 0 Base. 0 BSC V2. 全部真实 on-chain, 全部 `collector_observable=true`.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `coverage_scope` | `partial_solana_bsc_real_universe` |
| `do_not_treat_as_full_universe` | **true** |
| `expanded_pool_count` | 72 |
| `selected_pool_count` | **53** |
| `excluded_pool_count` | 19 (10 Base + 9 BSC V2/placeholder + 0 Solana misc) |
| `placeholder_pool_count` | **0** |
| `all_pools_are_real_on_chain` | **true** |
| `all_collector_observable` | **true** |

## 2. Chain / Protocol distribution (selected)

| Chain | Pools | Protocols |
|---|---|---|
| solana | 49 | orca_whirlpool, raydium_clmm, raydium_cpmm, meteora_dlmm |
| bsc | 4 | pancakeswap_v3 |


## 3. Excluded pools (with reason)

| Chain | Protocol | Pool Address | Reason |
|---|---|---|---|
| base | uniswap_v3 | `0x72ab388e2e2f6facef59e3c3fa2c...` | base_chain_rpc_unreachable |
| base | uniswap_v3 | `PENDING_BASE_UNIV3_RPC_VALIDAT...` | base_chain_rpc_unreachable |
| base | uniswap_v3 | `PENDING_BASE_UNIV3_RPC_VALIDAT...` | base_chain_rpc_unreachable |
| base | uniswap_v3 | `PENDING_BASE_UNIV3_RPC_VALIDAT...` | base_chain_rpc_unreachable |
| base | uniswap_v3 | `PENDING_BASE_UNIV3_RPC_VALIDAT...` | base_chain_rpc_unreachable |
| base | aerodrome | `PENDING_AERODROME_RPC_VALIDATI...` | base_chain_rpc_unreachable |
| base | aerodrome | `PENDING_AERODROME_RPC_VALIDATI...` | base_chain_rpc_unreachable |
| base | aerodrome | `PENDING_AERODROME_RPC_VALIDATI...` | base_chain_rpc_unreachable |
| base | aerodrome | `PENDING_AERODROME_RPC_VALIDATI...` | base_chain_rpc_unreachable |
| base | aerodrome | `PENDING_AERODROME_RPC_VALIDATI...` | base_chain_rpc_unreachable |
| bsc | pancakeswap_v3 | `0x1401ff943D08a7E098328C1d3a9d...` | not_observable |
| bsc | pancakeswap_v3 | `0x6805E0E5333c5c3acCF2930Be473...` | not_observable |
| bsc | pancakeswap_v3 | `0xc721dECCD986D54B39e8c29428A1...` | not_observable |
| bsc | pancakeswap_v3 | `0x18C5aFFA481e7EDbF37405AdE553...` | not_observable |
| bsc | pancakeswap_v2 | `0x16b9a82891338f9bA80E2D6970Fd...` | bsc_v2_factory_getpair_returned_zero_address |
| bsc | pancakeswap_v2 | `0x58F876857a02D6762E0101bb5C46...` | bsc_v2_factory_getpair_returned_zero_address |
| bsc | pancakeswap_v2 | `PENDING_BSC_PANCAKE_V2_RPC_VAL...` | bsc_v2_factory_getpair_returned_zero_address |
| bsc | pancakeswap_v2 | `PENDING_BSC_PANCAKE_V2_RPC_VAL...` | bsc_v2_factory_getpair_returned_zero_address |
| bsc | pancakeswap_v2 | `0xA39Af17CE4a8eb807E076805Da1e...` | bsc_v2_factory_getpair_returned_zero_address |




## 4. Filter rules (honest)

1. **Base 链全部 excluded** (`base_rpc_unreachable_in_current_env`)
2. **BSC V2 全部 excluded** (`bsc_v2_factory_getpair_returned_zero_address`)
3. **Placeholder/PENDING 全部 excluded** (`pending_or_placeholder`)
4. **不可观测池全部 excluded** (`not_observable`)

**不** 用 placeholder 替补. **不** 假装 Base 池 observable.

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` (启动时变 true) |

## 6. 严禁

- ❌ 不启动 12h / 24h retry (本 stage 仅**构建** universe, **不** 启动)
- ❌ 不启动 long-running collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不写真实 secret
