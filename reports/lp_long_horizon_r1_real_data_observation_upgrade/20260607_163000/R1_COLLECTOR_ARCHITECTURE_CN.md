# R1 Collector Architecture

- stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`
- run_id: `20260607_163000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:55:00Z`

## 0. 一句话

R1 collector = 复用 R0 collector 的 universe loader + per-pool iteration, **不**改 R0, **不**改 adapters dir, **不**改 RPC registry. R1 collector = 新文件 `scripts/lp_long_horizon_r1_real_data_collector_v1.py`, 复用 `scripts/lp_long_horizon/adapters/` 已有 8 个 adapter (solana_rpc_readonly / public_api_coingecko / local_artifact_replay + 5 EVM/BSC). R1 smoke 短跑 (max_pools=20, max_snapshots=1, no-daemon), 真实 on-chain data + confidence + honest failure reasons, **不** fallback to 0 placeholder, **不** long-run.

## 1. 整体架构

```
                    R1_collector.py (new, scripts/lp_long_horizon_r1_real_data_collector_v1.py)
                                |
                                | 1. 读 --pool-universe (expanded_universe_for_12h_retry.json, 72 pools)
                                |    filter chain reachable, limit to --max-pools=20
                                |
                                | 2. per pool × per protocol → 调 adapter
                                |    ├─ solana_clmm / cpmm / dlmm → solana_rpc_readonly
                                |    ├─ bsc_v3 / v2 / base → evm_bsc_pancakeswap_v3 / v2 / evm_base_*
                                |    └─ price feed → public_api_coingecko
                                |
                                | 3. 6 dimensions per pool × per notional × per window
                                |    ├─ r1_pool_snapshot (live reserve/liquidity/tick)
                                |    ├─ r1_quote_snapshot (QuoterV2 staticcall)
                                |    ├─ r1_fee_velocity (DexScreener / on-chain)
                                |    ├─ r1_liquidity_distribution (bitmap / bin_array)
                                |    ├─ r1_market_regime (Pyth/CoinGecko)
                                |    └─ r1_candidate_review (4-dim confidence aggregation)
                                |
                                | 4. 写 r1_*.csv / r1_*.json + r1_smoke_summary.json
                                |    → data/lp_long_horizon_r1_smoke/<RUN_ID>/
                                v
                R1 smoke output (短跑, 2-3 min, NO long-run)
```

## 2. R1 collector 关键设计

### 2.1 复用 R0 资产 (NO modification)

- ✅ 复用 `scripts/lp_long_horizon/adapters/solana_rpc_readonly.py` (Solana RPC)
- ✅ 复用 `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v3.py` (BSC V3)
- ✅ 复用 `scripts/lp_long_horizon/adapters/evm_bsc_pancakeswap_v2.py` (BSC V2)
- ✅ 复用 `scripts/lp_long_horizon/adapters/evm_base_aerodrome.py` (Base Aerodrome)
- ✅ 复用 `scripts/lp_long_horizon/adapters/evm_base_uniswap_v3.py` (Base UniV3)
- ✅ 复用 `scripts/lp_long_horizon/adapters/solana_meteora_dlmm_check.py` (Meteora verify)
- ✅ 复用 `scripts/lp_long_horizon/adapters/public_api_coingecko.py` (price feed)
- ✅ 复用 `scripts/lp_long_horizon/adapters/local_artifact_replay.py` (CSV replay)
- ❌ **不**修改 R0 collector (`scripts/lp_long_horizon_readonly_collector_v1.py`)
- ❌ **不**修改任何 adapter

### 2.2 R1 collector 内部模块

```
lp_long_horizon_r1_real_data_collector_v1.py
├─ main() — CLI entry, --pool-universe --output-dir --run-id --max-pools --max-snapshots --no-daemon
├─ load_pool_universe(path) → list[Pool] (reuse R0 universe format)
├─ per_chain_protocol_router(pool) → adapter_callable
├─ fetch_r1_pool_snapshot(pool, adapter) → R1PoolSnapshot (with confidence + invalid_reason)
├─ fetch_r1_quote_snapshot(pool, adapter, notional_usd) → R1QuoteSnapshot × 6 notional
├─ fetch_r1_fee_velocity(pool, adapter, window) → R1FeeVelocity × 5 windows
├─ fetch_r1_liquidity_distribution(pool, adapter) → R1LiquidityDistribution
├─ fetch_r1_market_regime(pool, chain) → R1MarketRegime
├─ aggregate_r1_candidate_review(pool, 5 dimensions) → R1CandidateReview
├─ write_r1_outputs(dim_data, output_dir) → r1_*.csv + r1_*.json
└─ write_r1_smoke_summary(dim_data, output_dir) → r1_smoke_summary.json
```

### 2.3 R1 collector 关键行为

#### a) per chain 路由

```
chain=base:
  protocol=aerodrome_slipstream → evm_base_aerodrome.fetch_slipstream_state(pool)
  protocol=aerodrome_classic → evm_base_aerodrome.fetch_classic_reserves(pool)
  protocol=uniswap_v3 → evm_base_uniswap_v3.fetch_slot0_liquidity(pool)
  confidence handling: Base RPC 不可达 → 全部 confidence=unavailable, invalid_reason=rpc_unreachable

chain=bsc:
  protocol=pancakeswap_v3 → evm_bsc_pancakeswap_v3.fetch_slot0_liquidity_quoter(pool)
  protocol=pancakeswap_v2 → evm_bsc_pancakeswap_v2.fetch_getReserves_factory_getPair(pool)
  confidence handling: BSC V2 factory.getPair=0 → confidence=unavailable, invalid_reason=pool_address_invalid

chain=solana:
  protocol=orca_whirlpool → solana_rpc_readonly.fetch_whirlpool_state(pool)
  protocol=raydium_clmm → solana_rpc_readonly.fetch_raydium_clmm_state(pool)
  protocol=raydium_cpmm → solana_rpc_readonly.fetch_raydium_cpmm_state(pool)
  protocol=meteora_dlmm → solana_meteora_dlmm_check.fetch_meteora_dlmm_state(pool)
  confidence handling: Meteora dlmm-api 不可达 → confidence=unavailable, invalid_reason=indexer_unreachable
```

#### b) 如何处理 Base RPC 不可达

- R1 collector 在 main() 探测 1 次 base.publicnode.com (或 mainnet.base.org)
- 如 403 / timeout → 标 `base_unreachable=true`, **不** 重试, **不** raise
- per-pool 处理: 跳过所有 base 池, 写 r1_pool_snapshot 行 with `confidence=unavailable, invalid_reason=rpc_unreachable`
- summary 写 `chains_skipped=["base"]`

#### c) 如何处理 Solana/Meteora RPC empty

- Meteora DLMM 池 (`solana/meteora_dlmm`) 在 R1 仍可能 dlmm-api 不可达
- 处理: per-pool 调 solana_meteora_dlmm_check.fetch → 如返回 None / raise → 标 `confidence=unavailable, invalid_reason=indexer_unreachable`
- **不** fallback to 0, **不** fallback to placeholder
- 其它 Solana 协议 (Orca/Raydium) 走 `getMultipleAccountsInfo`, **不** 走 dlmm-api, 应能拿到

#### d) 如何处理 BSC V2 getPair zero

- evm_bsc_pancakeswap_v2.fetch 调 `factory.getPair(tokenA, tokenB)`
- 如返回 0x0...0 → 标 `confidence=unavailable, invalid_reason=pool_address_invalid`
- **不** raise, **不** fallback
- summary 写 `bsc_v2_pools_excluded=N`

#### e) 如何避免 fallback placeholder

- R1 collector **不** 用 smoke_placeholder flag (R0 用, R1 **不** 用)
- R1 collector 用 `confidence=unavailable` + `invalid_reason="..."` 表达失败
- **不** 用 0 / null / "" 作为 fallback; 如拿不到, 直接 unavailable + reason
- 这与 R0 关键区别: R0 = 0 fallback, R1 = unavailable + reason

#### f) 如何标记 actual_fee_data_available=false

- R1 collector 写 r1_smoke_summary.json:
  - `actual_fee_data_available: false` (硬编码, R1 不 actual fee)
  - `fee_proxy_only: true` (硬编码, R1 不 = actual fee)
  - `actual_fee_schema_unchanged: true` (r1 actual_fee_accrual **不** 改, schema 维持 placeholder)

#### g) 如何保持 read-only

- R1 collector 内部**不**调任何写 chain state 的 RPC (sendTransaction / write API)
- 全部 RPC 调仅 read-only: getMultipleAccountsInfo, getAccountInfo, eth_call, getLogs (read-only logs)
- **不** 调 approve / mint / addLiquidity / removeLiquidity / collect / swap / bridge
- **不** 读 wallet / seed / keypair / signer (R1 内部**不** 调 wallet 相关 module)
- write-only 操作 = 写本地 data dir + reports (R1 smoke output), **不** 写 production

## 3. R1 short smoke 流程

### 3.1 CLI

```bash
python3 scripts/lp_long_horizon_r1_real_data_collector_v1.py \
  --run-id 20260607_163000 \
  --pool-universe reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/expanded_real_pool_universe_for_12h_retry.json \
  --output-dir data/lp_long_horizon_r1_smoke/20260607_163000 \
  --max-pools 20 \
  --max-snapshots 1 \
  --no-daemon
```

### 3.2 步骤

1. 加载 universe (72 pools), 按 chain × protocol 排序
2. 探测 RPC reachability (per chain × per endpoint, 1 quick check)
3. 限 --max-pools=20 池 (优先级: solana_orca > solana_raydium > bsc_v3 > base_* > bsc_v2 > solana_meteora_dlmm_last)
4. per pool × per dimension 调 adapter, **不** retry (1 attempt per call, fail fast)
5. 6 dimensions 写 r1_*.csv + r1_*.json
6. r1_candidate_review per pool 聚合
7. r1_smoke_summary.json 写顶层 summary
8. 退出 (无 daemon, no long-run)

### 3.3 timeout / rate limit 处理

- per RPC call timeout = 5s (5 sec)
- per pool × per dimension total time ≤ 30s
- total R1 smoke 期望 2-3 min (20 pools × 6 dimensions × 1 attempt)
- 遇 429 → **不** retry, 直接 confidence=unavailable, invalid_reason=rpc_rate_limited
- 遇 403 → **不** retry, 直接 confidence=unavailable, invalid_reason=rpc_unreachable

## 4. R1 expected output (per spec required fields)

```
r1_smoke_summary.json:
  selected_pool_count: 20
  pool_snapshot_rows: 20
  quote_snapshot_rows: 120 (20 × 6 notional)
  fee_velocity_rows: 100 (20 × 5 windows)
  liquidity_distribution_rows: 20
  market_regime_rows: 2 (solana + bsc; base skipped if unreachable)
  candidate_review_rows: 20
  quote_ready_pool_count: 0-N (depends on RPC success)
  fee_ready_pool_count: 0-N
  liquidity_ready_pool_count: 0-N
  ev_ready_pool_count: 0-N
  preflight_candidate_count: 0-N
  watchlist_count: 0-N
  data_insufficient_count: 0-N
  actual_fee_data_available: false (HARD CODED)
  fee_proxy_only: true (HARD CODED, R1 ≠ actual)
  no_wallet_tx_probe: true
  chain_distribution: {solana: N, bsc: M, base: 0 (if unreachable)}
  protocol_distribution: {...}
  confidence_distribution: {high: X, medium: Y, low: Z, unavailable: W}
```

## 5. R1 不做什么 (per spec hard prohibition)

- ❌ **不**启动 24h / 48h / 72h / 7d
- ❌ **不**启动 long-running collector
- ❌ **不**启动 tmux / cron / systemd / daemon (--no-daemon 必填)
- ❌ **不** probe / canary / live / paper
- ❌ **不**读 wallet / seed / keypair / signer
- ❌ **不**发送 transaction
- ❌ **不** approve / mint / add-liquidity / remove-liquidity / collect / swap / bridge
- ❌ **不**写 production positions
- ❌ **不**覆盖 shadow 原始表
- ❌ **不**接 paid RPC / paid indexer
- ❌ **不**写真实 secret
- ❌ can_run_probe_now 维持 false
- ❌ tiny_canary_allowed 维持 "no"
- ❌ edge_proven 维持 "no"
- ❌ actual_fee_data_available 维持 false
- ❌ **不**修改 R0 collector / adapters / RPC registry
- ❌ **不**修改 12h data dir
- ❌ **不**修改 12h review reports
- ❌ **不** mint LP NFT (R1 严格 read-only)
- ❌ **不** actual position fee accrual
- ❌ **不** collect fee

## 6. R1 锁定字段 (R1 smoke 期间)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `r1_schema_ready` | `true` (after Stage B) | 6 dimensions schema defined |
| `r1_collector_built` | `true` (after Stage D) | scripts/lp_long_horizon_r1_real_data_collector_v1.py exists |
| `r1_short_smoke_ran` | `true` (after Stage E) | smoke command executed, output files written |
| `actual_fee_data_available` | `false` | R1 **不** actual fee |
| `fee_proxy_only` | `true` (R0) → R1=depends on R1 smoke | R1 ≠ actual, but quote/fee/liquidity/regime may be real |
| `can_run_probe_now` | `false` | freeze active |
| `tiny_canary_allowed` | `"no"` | freeze active |
| `edge_proven` | `"no"` | R1 不 = edge proven |
| `wallet_or_tx_touched` | `false` | read-only R1 |
| `transaction_sent` | `false` | no tx |
