# Coverage Review (12h Node Report Review)

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`

## 0. 一句话

12h 实际观察了 **2 chains (solana + bsc)** + **5 protocols** + **53 real on-chain pool** (49 Solana + 4 BSC V3). **不** 观察 Base (RPC 全部 403) + Ethereum/Arbitrum (not in this stage). **0 placeholder** pool. quote-ready=53, fee-ready=53, **EV-ready=0** (r0 phase). data_quality=PASS.

## 1. Chain-level coverage (3 levels)

### 1.1 Observed chains (2/3)

| Chain | Pool count | Protocols | RPC reachable | Note |
|---|---|---|---|---|
| **solana** | 49 | orca_whirlpool (13), raydium_clmm (10), raydium_cpmm (10), meteora_dlmm (16) | mainnet-beta.helius-rpc.com / publicnode | ✅ observed |
| **bsc** | 4 | pancakeswap_v3 (4) | bsc-dataseed.binance.org | ✅ observed |
| **base** | 0 | — | base.publicnode.com / mainnet.base.org / 1rpc.io/base 全部 403 | ❌ missing |

### 1.2 Missing chains (1/3 in this stage + 2/3 not in this stage)

| Chain | Reason |
|---|---|
| **base** | All 4 public RPC endpoints returned 403 in this env (per prior stage `lp_long_horizon_collector_rpc_reachability_and_adapter_smoke_fix_v1`) |
| **ethereum** | Not in this stage (LPBOT focus: Base + Solana + BSC) |
| **arbitrum** | Not in this stage (LPBOT focus: Base + Solana + BSC) |

### 1.3 Total observed coverage

- observed_count: 2 / 3 (66.7%)
- missing_count: 1 / 3 (33.3%) — 仅 Base 因 env 不可达
- full_coverage_ready: **false**
- do_not_treat_as_full_universe: **true**

## 2. DEX-level coverage (3 levels)

### 2.1 Observed DEXes (5/9)

| DEX | Chain | Pool count | TVL bucket | Status |
|---|---|---|---|---|
| **solana/orca_whirlpool** | solana | 13 | 最高 SOL/USDC 32M, 最低 3.6M | ✅ observed |
| **solana/raydium_clmm** | solana | 10 | 最高 SOL/USDC 9.5M, 含 5 low-tvl (USWR/UNOS/SAOS/WorldCup, ~$20) | ✅ observed |
| **solana/raydium_cpmm** | solana | 10 | 最高 BOME/SOL 18M, 最低 230K | ✅ observed |
| **solana/meteora_dlmm** | solana | 16 | TVL proxy 0 (LB pair not on dlmm-api in this env) | ✅ observed (但 data incomplete) |
| **bsc/pancakeswap_v3** | bsc | 4 | TVL proxy 0 (not in stage CSV yet) | ✅ observed (但 data incomplete) |

### 2.2 Missing DEXes (4/9)

| DEX | Chain | Reason |
|---|---|---|
| **base/aerodrome_slipstream** | base | Base chain unreachable (chain-level missing) |
| **base/aerodrome_classic** | base | Base chain unreachable |
| **base/uniswap_v3** | base | Base chain unreachable |
| **bsc/pancakeswap_v2** | bsc | factory.getPair returned zero for all V2 candidate pairs in BSC; smoke excluded V2 |

### 2.3 DEX coverage

- observed_count: 5 / 9 (55.6%)
- missing_count: 4 / 9 (44.4%) — 3 Base + 1 BSC V2

## 3. Pool-level coverage (3 levels)

### 3.1 Pool counts (per 12h smoke_summary per ckpt)

| Metric | Value | Note |
|---|---|---|
| **observed_pool_count** | 53 | 49 Solana + 4 BSC V3 |
| **real_on_chain_pool_count** | 53 | 100% real on-chain addresses (from prior stage CSVs) |
| **placeholder_pool_count** | 0 | no fake / smoke address |
| **smoke_placeholder_pool_count** | 53 | 全 53 池 data fields 是 smoke_placeholder (reserve/liquidity/quote/fee/regime=0) |

### 3.2 Pool distribution by protocol

| Protocol | Count | % of 53 |
|---|---|---|
| solana/orca_whirlpool | 13 | 24.5% |
| solana/raydium_clmm | 10 | 18.9% |
| solana/raydium_cpmm | 10 | 18.9% |
| solana/meteora_dlmm | 16 | 30.2% |
| bsc/pancakeswap_v3 | 4 | 7.5% |

### 3.3 Pool distribution by chain

| Chain | Count | % of 53 |
|---|---|---|
| solana | 49 | 92.5% |
| bsc | 4 | 7.5% |

### 3.4 Pool TVL distribution (from prior stage CSV, proxy)

| TVL bucket | Count | Note |
|---|---|---|
| > $10M | 8 | High TVL Solana pools (SOL/USDC, BOME/SOL, etc.) |
| $1M - $10M | 17 | Medium TVL |
| $100K - $1M | 1 | (SPACEX/SOL 230K) |
| < $100K | 5 | (USWR/UNOS/SAOS/WorldCup ~$20-23 + SpaceX/SOL 230K) |
| 0 / unknown | 22 | Meteora DLMM 16 (LB pair not on dlmm-api) + BSC V3 4 (not yet in CSV) + 2 raydium low-tvl |

## 4. Data-layer coverage (readiness)

| Readiness | Count | Note |
|---|---|---|
| **quote-ready** | 53 | All 53 pools have quote_snapshots.jsonl per ckpt (smoke_placeholder) |
| **fee-ready** | 53 | All 53 pools have fee_velocity.jsonl per ckpt (smoke_placeholder) |
| **EV-ready** | **0** | No pool has actual fee + IL + tokenId data; r0 phase |
| **preflight-candidate** | **0** | tier_classifier=DEFERRED_TO_R1; r0 phase |
| **watchlist** | **0** | r0 phase; no candidate watchlist |
| **data-insufficient** | **53** | 全 53 池 r0 data layer 不够 |

### 4.1 quote-ready 详细

- 53 池 × 6 notional levels (10/100/1k/10k/100k/1M USD) = 318 quote per ckpt
- 12 ckpt × 318 = **3816 quote_snapshots total**
- 但 `amount_in_raw=0, amount_out_raw=0, price_impact_pct=0, slippage_pct=0, fee_usd=0` → smoke_placeholder
- r0_phase_status: smoke_placeholder=true

### 4.2 fee-ready 详细

- 53 池 × 5 windows (15m/1h/4h/24h/7d) = 265 fee per ckpt
- 12 ckpt × 265 = **3180 fee_velocity total**
- 但 `volume_proxy_usd=0, fee_capture_proxy_usd=0, sample_count=0` → smoke_placeholder
- r0_phase_status: "proxy (quote derived); r1 will upgrade to actual via tokenId"

### 4.3 EV-ready 详细

- 0 池 (因 r0)
- EV = (fee_actual_usd_24h) - (il_realized_pct * position_value) - (gas + rebalance + opportunity cost)
- 4 个 component 全部 0 / null / placeholder
- preflight_candidate_count = 0
- tier_a/b/c_assigned = false
- tier_classifier_output = DEFERRED_TO_R1

## 5. Data quality status

| Quality metric | 值 | 评估 |
|---|---|---|
| error_rate_pct | **0.0%** | ✅ PASS |
| consecutive_429_max | **0** | ✅ PASS |
| data_quality_status | **PASS** | ✅ |
| per-ckpt file size 一致 | ✅ | pipeline deterministic |
| 12 ckpt smoke_summary 一致 | ✅ | all_pools_are_real_on_chain=true, placeholder=0 |

**重要**: data_quality_status=PASS 是 **r0 phase quality**, 验证 pipeline + data flag 正确性, **不** 验证 data 真实性 (r0 data 全部 smoke_placeholder).

## 6. Coverage scope summary table

| Level | Observed | Missing | Total | Coverage % | Status |
|---|---|---|---|---|---|
| **Chain** | 2 (solana, bsc) | 1 (base) | 3 | 66.7% | partial (Base env 不可达) |
| **DEX** | 5 (4 Solana + 1 BSC) | 4 (3 Base + 1 BSC V2) | 9 | 55.6% | partial |
| **Pool** | 53 (real on-chain) | 0 (no fake) | 53 | 100% | real addresses OK |
| **Data layer (smoke)** | 53 (all r0 smoke) | 0 | 53 | 100% | r0 phase |
| **Data layer (actual)** | **0** | 53 | 53 | 0% | **r0 phase blocker** |
| **EV-ready** | **0** | 53 | 53 | 0% | r0 phase blocker |
| **preflight candidate** | **0** | 53 | 53 | 0% | r0 phase blocker |
| **Full coverage ready** | ❌ false | — | — | — | — |

## 7. Coverage gap 评估 (r0 → r1 升级需要)

| Gap | 阻塞原因 | R1 修复需要 |
|---|---|---|
| Base 链 0 池 | public RPC 403 | env 换 / paid RPC (freeze blocks) |
| BSC V2 0 池 | factory.getPair=0 | 换候选 pair or 接受 V2 不参与 |
| Meteora DLMM 16 池 TVL proxy=0 | dlmm-api 在此 env 不可达 | dlmm-api 修复 or 第三方 indexer (DexScreener / GeckoTerminal) |
| BSC V3 4 池 TVL proxy=0 | not yet in stage CSV | 集成 bsc candidate CSV from prior stage |
| 全 53 池 reserve/liquidity/quote/fee/regime=0 | no live RPC | 同 Base — freeze blocks |
| 全 53 池 on-position tokenId=0 | no actual LP mint | freeze reopen + user mint (by design) |
| market regime static | no real-time price feed | Pyth/CoinGecko 集成 (not yet wired) |

## 8. 重要 disclaimer

- 12h coverage **是** partial (66.7% chain / 55.6% DEX / 100% pool addresses, 0% actual data)
- 12h coverage **不** 是 full coverage
- 12h coverage **不** 证明 LP edge / 实际 fee / EV
- 12h coverage **不** 是 LP 决策 input
- 12h coverage **是** r0 phase engineering stability 验证
- 12h coverage **是** r1 upgrade plan 的 baseline

## 9. 锁定字段 (LOCKED)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `global_lp_rejected` | `false` |
| `actual_fee_data_available` | `false` |
| `fee_proxy_only` | `true` |
| `candidate_decision_reliable` | `false` |
| `r1_upgrade_required` | `true` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
