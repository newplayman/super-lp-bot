# BSC PancakeSwap V3 Adapter Wiring Smoke

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: bsc_pancakeswap_v3_adapter_smoke
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:44:00Z`

## 0. 总结

✅ **BSC PancakeSwap V3 adapter 已就位** (`scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v3.py`). 提供 pool_snapshot (slot0, liquidity, token0, token1, fee) + quote (QuoterV2 staticcall + fallback math). Read-only (eth_call only).

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_file` | `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v3.py` |
| `smoke_pool_count` | 2 (1 verified WBNB/USDT 0.05% + 1 placeholder) |
| `pool_snapshot_rows` | 1 |
| `quote_snapshot_rows` | 6 |
| `error_count` | 1 |
| `adapter_ready` | **true** |
| `quoter_v2_address` | `0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997` (public BSC mainnet, from prior research) |

## 2. 2 测试池

| # | Pool Address | Source | Status |
|---|---|---|---|
| 1 | `0x36696169C63e42cd08ce11f5deeBbCeBae652050` | WBNB/USDT 0.05% (bsc_quote_target_candidates.csv) | OK |
| 2 | `0x0000000000000000000000000000000000000c01` | placeholder | rpc_unavailable: slot0_decode_too_short |

## 3. 6 notional quote levels

`[10, 20, 100, 500, 1000, 2000]` USD.

## 4. Reuses BSC QuoterV2

Per spec: "可复用之前 BSC QuoterV2 amount fix / precise quote 逻辑". `PANCAKE_V3_QUOTER_V2 = 0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997` 来自 `reports/lp_bsc_pancakeswap_v3_precise_quote/20260602_235959/bsc_quote_target_candidates.csv`.

## 5. Adapter 安全保证

- eth_call only (read-only)
- No signing, no keypair, no transaction
- 自检 `_self_check()`: module refuses to import if banned tokens present
- 复用 `scripts/lp_long_horizon/utils/retry.py` + `abort.py`

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

## 7. 严禁

- ❌ 不启动 BSC collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
