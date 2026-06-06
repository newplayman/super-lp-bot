# Adapter Registry Design

- stage: `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`
- section: adapter_registry
- run_id: `20260606_093857`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T09:40:00Z`

## 0. 总结

✅ **8 个 read-only adapter 全覆盖**: 3 existing + 4 new + 1 verify. 所有 adapter 都 `read_only_only=true, wallet_required=false, transaction_required=false`. 4 new adapter (Base UniV3 / Base Aerodrome / BSC V3 / BSC V2) 全部 eth_call only.

## 1. Adapter Inventory

| # | Adapter Name | Chain | Protocol | Type | Status | File |
|---|---|---|---|---|---|---|
| 1 | solana_rpc_readonly | solana | * | * | existing | `scripts/lp_long_horizon/adapters/solana_rpc_readonly.py` |
| 2 | public_api_coingecko | * | * | * | existing | `scripts/lp_long_horizon/adapters/public_api_coingecko.py` |
| 3 | local_artifact_replay | * | * | * | existing | `scripts/lp_long_horizon/adapters/local_artifact_replay.py` |
| 4 | evm_base_uniswap_v3 | base | uniswap_v3 | v3 | **new** | `scripts/lp_long_horizon/adapters/evm_base_uniswap_v3.py` |
| 5 | evm_base_aerodrome | base | aerodrome | classic+slipstream | **new** | `scripts/lp_long_horizon/adapters/evm_base_aerodrome.py` |
| 6 | evm_bsc_pancakeswap_v3 | bsc | pancakeswap_v3 | v3 | **new** | `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v3.py` |
| 7 | evm_bsc_pancakeswap_v2 | bsc | pancakeswap_v2 | v2 | **new** | `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v2.py` |
| 8 | solana_meteora_dlmm_check | solana | meteora_dlmm | dlmm | **verify** | `scripts/lp_long_horizon/adapters/solana_meteora_dlmm_check.py` |

## 2. Capabilities per Adapter

### 2.1 existing: solana_rpc_readonly (Solana generic)

- `supports_pool_snapshot: true` (via getMultipleAccountsInfo)
- `supports_quote_snapshot: fallback_only` (no quoter, only reserves-based proxy)
- `supports_fee_velocity_proxy: false`
- `supports_liquidity_distribution: false`
- `supports_market_regime: false`
- **read-only**: HTTP POST JSON-RPC, no signing, no keypair

### 2.2 existing: public_api_coingecko (any chain)

- `supports_pool_snapshot: false`
- `supports_quote_snapshot: false`
- `supports_fee_velocity_proxy: true` (OHLC)
- `supports_liquidity_distribution: false`
- `supports_market_regime: true` (OHLC-based)
- **read-only**: HTTP GET, no auth

### 2.3 existing: local_artifact_replay (any chain)

- Replays prior research artifacts (e.g. `meteora_pool_chain_verification.json`, `bsc_quote_target_candidates.csv`)
- `supports_pool_snapshot: true` (from artifact)
- `supports_quote_snapshot: from_artifact`
- `supports_fee_velocity_proxy: from_artifact`
- **read-only**: file read only

### 2.4 new: evm_base_uniswap_v3

- eth_call only (no signing, no keypair, no RPC mutation)
- `pool_snapshot`: UniswapV3Pool.slot0() + liquidity() + token0() + token1() + fee()
- `quote_snapshot`: QuoterV2.quoteExactInputSingle staticcall at 6 notional levels (10/20/100/500/1000/2000U); fallback math if QuoterV2 unavailable
- `fee_velocity_proxy`: heuristic from volume_hint (no real volume)
- `liquidity_distribution`: partial (tick liquidity via tick spacing if available)
- `market_regime: NORMAL` (no real-time signal in R0)

### 2.5 new: evm_base_aerodrome

- eth_call only
- **classic** (Solidly fork): Pool.getReserves() + reserve0 + reserve1 + stable flag + CPMM/stable-like quote proxy
- **slipstream** (V3 fork custom tick math): `adapter_ready=false` honestly. **不** 假装 V3 standard layout.
- per spec: 不得伪造 V3 layout

### 2.6 new: evm_bsc_pancakeswap_v3

- eth_call only
- Pool.slot0() + liquidity() + token0() + token1() + fee()
- Quote: QuoterV2.quoteExactInputSingle staticcall + fallback math
- Reuses BSC QuoterV2 amount fix from prior research (3-batch fallback for out-of-liquidity)

### 2.7 new: evm_bsc_pancakeswap_v2

- eth_call only
- Pool.getReserves() + reserve0 + reserve1 (CPMM)
- Quote: CPMM formula x*y=k with fee=0.2% (no quoter)
- TVL proxy: reserve0 * price0 + reserve1 * price1 (if price available)

### 2.8 verify: solana_meteora_dlmm_check

- Re-uses `solana_rpc_readonly` to read Meteora DLMM 16 verified pool accounts
- Decode LbPair struct (904 bytes) per existing connector
- NOT a new wire; verify existing connector works in long-horizon pipeline
- 1-2 pool short smoke

## 3. Common Safety Guarantees (all 8 adapters)

| Property | Value |
|---|---|
| `read_only_only` | **true** |
| `wallet_required` | **false** |
| `transaction_required` | **false** |
| Allowed operations | eth_call (read-only), getMultipleAccountsInfo, getReserves, slot0, file read |
| Forbidden operations | sendTransaction, signTransaction, eth_sendRawTransaction, eth_sendTransaction, approve, mint, addLiquidity, removeLiquidity, collect, swap, bridge |
| Forbidden resource reads | private_key, mnemonic, seed, keystore, keypair |
| Forbidden processes | canary, lpbot-live, live, paper, sendTransaction, keypair |
| Error handling | retry/backoff/timeout/429 (reuses `scripts/lp_long_horizon/utils/retry.py`) |
| Abort mechanism | reuses `scripts/lp_long_horizon/utils/abort.py` (AbortController, ErrorRateMonitor) |

## 4. Registry vs. Auto-Discovery

**Registry is read-only metadata, not auto-discovery.** Rationale:
- Spec: "如果当前项目不适合拆目录，也可以在 collector 内部实现，但必须保持清晰 adapter registry"
- The long-horizon collector (`scripts/lp_long_horizon_readonly_collector_v1.py`) already has hardcoded protocol samples in `PROTOCOL_SAMPLES`. This stage's registry is metadata-only; future stages can wire auto-dispatch.
- Per spec, registry must be **清晰** (clear). 8-adapter explicit list is more auditable than auto-discovery.

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

- ❌ 不启动 12h / 24h / 48h / 72h / 7d retry
- ❌ 不启动 long-running collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不写 production positions
- ❌ 不接 paid RPC / paid indexer (用 public RPC if available)

## 7. 下游

进入 Stage C (Base UniV3 wire) + D (Aerodrome) + E (BSC V3) + F (BSC V2) + G (Meteora verify) → 4 个新 Python adapter file. 完成后 integrated smoke (Stage H) 跑 12 池 (per chain) + coverage readiness decision (Stage I).
