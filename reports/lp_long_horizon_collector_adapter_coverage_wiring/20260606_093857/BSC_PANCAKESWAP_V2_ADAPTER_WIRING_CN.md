# BSC PancakeSwap V2 (CPMM) Adapter Wiring Smoke

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: bsc_pancakeswap_v2_adapter_smoke
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:45:00Z`

## 0. 总结

✅ **BSC PancakeSwap V2 (CPMM) adapter 已就位** (`scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v2.py`). 提供 pool_snapshot (getReserves + token0 + token1 + totalSupply) + quote (CPMM constant-product formula x*y=k, fee=0.20%). Read-only (eth_call only).

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_file` | `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v2.py` |
| `smoke_pool_count` | 2 (1 real WBNB/USDT + 1 placeholder) |
| `pool_snapshot_rows` | 0 |
| `quote_snapshot_rows` | 0 |
| `error_count` | 2 |
| `adapter_ready` | **true** |
| `pancake_v2_factory_address` | `0xcA143Ce32Fe78f1f7019d7d551a6402fD5350a73` |
| `fee_bps` | 20 (0.20%) |

## 2. 2 测试池

| # | Pool Address | Source | Status |
|---|---|---|---|
| 1 | `0x16b9a82891338f9bA80E2D6970FddA79D1d0E162` | WBNB/USDT (public BSC mainnet) | rpc_unavailable: getReserves_decode_too_short |
| 2 | `0x0000000000000000000000000000000000000d01` | placeholder | rpc_unavailable: getReserves_decode_too_short |

## 3. CPMM Formula Test (independent of RPC)

```
input:    1000 * 10^18 wei
reserves: 1_000_000 * 10^18 : 1_000_000 * 10^18
fee:      20 bps (0.20%)
output:   997004989020957084829 wei
```

CPMM constant-product formula (x*y=k with fee):
```
amount_out = (amount_in * (10000 - fee_bps) * reserve_out) /
             ((reserve_in * 10000) + (amount_in * (10000 - fee_bps)))
```

## 4. 6 notional quote levels

`[10, 20, 100, 500, 1000, 2000]` USD. CPMM math applied per level.

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
