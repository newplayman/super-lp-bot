# BSC Adapter Smoke Retry

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: bsc_adapter_smoke_retry
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:44:00Z`

## 0. 总结

✅ **BSC RPC reachable** (https://bsc-dataseed.binance.org). Smoke ran with selected endpoint.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `bsc_rpc_reachable` | **true** |
| `bsc_rpc_selected` | `https://bsc-dataseed.binance.org` |
| `pancakeswap_v3_smoke_success_count` | 4 / 4 |
| `pancakeswap_v2_factory_getpair_success_count` | 0 / 3 |
| `pancakeswap_v2_getreserves_success_count` | 0 / 3 |
| `pool_snapshot_rows` | 4 |
| `quote_snapshot_rows` | 24 |
| `error_count` | 3 |

## 2. BSC V3 smoke (4 pools)

| # | Pool | Status |
|---|---|---|
| 1 | `0x172fcD41E0913e95784454622d1c3724f546f849` | OK |
| 2 | `0x36696169C63e42cd08ce11f5deeBbCeBae652050` | OK |
| 3 | `0xf2688Fb5B81049DFB7703aDa5e770543770612C4` | OK |
| 4 | `0x81A9b5F18179cE2bf8f001b8a634Db80771F1824` | OK |


## 3. BSC V2 smoke (3 candidate pairs via factory.getPair)

| # | Pair | factory.getPair | discovered address | getReserves |
|---|---|---|---|---|
| 1 | WBNB/USDT | pair_not_found | `0x0000000000000000000000000000000000000000` | skipped_no_pair |
| 2 | WBNB/USDC | pair_not_found | `0x0000000000000000000000000000000000000000` | skipped_no_pair |
| 3 | USDT/USDC | pair_not_found | `0x0000000000000000000000000000000000000000` | skipped_no_pair |


## 4. CPMM formula test (independent of RPC)

`cpmm_amount_out(1000 * 10^18, 1_000_000 * 10^18, 1_000_000 * 10^18, 20)` = `997004989020957084829`

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |

## 6. 严禁

- ❌ 不启动 BSC collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
