# Base Uniswap V3 Adapter Wiring Smoke

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: base_uniswap_v3_adapter_smoke
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:42:00Z`

## 0. 总结

✅ **Base Uniswap V3 adapter file 已就位** (`scripts/lp_long_horizon/adapters/evm_base_uniswap_v3.py`). 提供 pool_snapshot (slot0, liquidity, token0, token1, fee) + quote (QuoterV2 staticcall + fallback math). Read-only (eth_call only), no signing, no keypair, no transaction.

⚠️ **RPC 不可用**: 本 stage smoke 记录 `rpc_unavailable: HTTPError`. 这是诚实披露 — public Base RPC 在此 stage runner 环境不可达. **不** 假装 pool observable. 下一 stage 需在能 reach public Base RPC 的环境再 smoke 真实池.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `adapter_file` | `scripts/lp_long_horizon/adapters/evm_base_uniswap_v3.py` |
| `smoke_pool_count` | 2 (1 verified + 1 placeholder) |
| `pool_snapshot_rows` | 0 (真实成功调用 eth_call 的池数) |
| `quote_snapshot_rows` | 0 |
| `error_count` | 2 |
| `adapter_ready` | **true** (file exists, signatures correct, self-check passes) |
| `collector_observable` | **false** (rpc_unavailable, recorded honestly) |
| `public_rpc_endpoint` | `https://mainnet.base.org` |

## 2. 测试池

| # | Pool Address | Source | Status |
|---|---|---|---|
| 1 | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` | verified (prior auth_package) | rpc_unavailable: rpc_unavailable: HTTPError |
| 2 | `0x0000000000000000000000000000000000000a01` | placeholder (test dry-run) | rpc_unavailable: rpc_unavailable: HTTPError |

## 3. 6 notional quote levels

`[10, 20, 100, 500, 1000, 2000]` USD.

## 4. Adapter 安全保证

- eth_call only (read-only HTTP POST JSON-RPC)
- No signing, no keypair, no transaction, no chain mutation
- 自检 `_self_check()`: 模块含 banned token 时立即 raise RuntimeError("REFUSE: ...")
- 复用现有 `scripts/lp_long_horizon/utils/retry.py` retry/backoff/timeout/429
- 复用现有 `scripts/lp_long_horizon/utils/abort.py` AbortController (429 + error rate monitor)

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `no_collector_started` | `true` |
| `no_12h_retry_started` | `true` |

## 6. 严禁 (本 stage 全部不触发)

- ❌ 不启动 Base collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer (仅用 public Base RPC if available)
