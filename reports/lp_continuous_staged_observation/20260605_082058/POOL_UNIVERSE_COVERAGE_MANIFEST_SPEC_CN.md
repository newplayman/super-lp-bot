# Stage E: 池宇宙覆盖范围 Manifest Spec

- spec: `pool_universe_coverage_manifest_spec_v1`
- spec_version: `1.0`
- designed_at_utc: `2026-06-05T08:22:30Z`

## 0. 目的

为每个节点 (6h/12h/24h/48h/72h/7d) 定义链 / DEX / 池三层覆盖范围 manifest, 透明化"collector 实际观察到了什么 / 哪些链/DEX 尚未实现 connector / 哪些池尚未 selected_for_candidate_review".

**严格不假装覆盖**: 如果某链/DEX/池当前 collector 尚未实现, manifest 必须写 `observed=false` + 原因.

## 1. 当前实现状态 (2026-06-05)

### 1.1 Go chain adapter

| 路径 | 状态 |
|---|---|
| `internal/adapters/chain/base` | ✅ implemented (Base mainnet public RPC + ABI) |
| `internal/adapters/chain/solana` | ✅ implemented (Solana mainnet public RPC) |

### 1.2 Go pool adapter

| 路径 | chain | protocol | pool_type | 状态 |
|---|---|---|---|---|
| `internal/adapters/pool/uniswap_v3` | base | uniswap_v3 | v3 | ✅ implemented |
| `internal/adapters/pool/aerodrome` | base | aerodrome | v2_cpmm | ✅ implemented |
| `internal/adapters/pool/raydium_clmm` | solana | raydium_clmm | clmm | ✅ implemented |
| `internal/adapters/pool/whirlpool` | solana | orca_whirlpool | clmm | ✅ implemented |
| `internal/adapters/pool/pancakeswap_v3_solana` | solana | pancakeswap_v3_solana | v3 | ✅ implemented |
| (missing) | solana | meteora_dlmm | dlmm | ❌ not_implemented_yet |
| (missing) | solana | raydium_cpmm | v2_cpmm | ❌ not_implemented_yet |
| (missing) | solana | raydium_amm_v4 | v2_cpmm | ❌ not_implemented_yet (legacy AMM) |
| (missing) | bsc | pancakeswap_v3 | v3 | ❌ bsc_chain_adapter_not_implemented_yet |
| (missing) | bsc | pancakeswap_v2 | v2_cpmm | ❌ bsc_chain_adapter_not_implemented_yet |

### 1.3 Python readonly scripts

- Base: `lp_base_*_readonly.py` ✅
- BSC: `lp_bsc_*_readonly.py` (placeholder only, BSC chain adapter missing) ⚠️
- Solana: `lp_solana_*_readonly.py` ✅
- Long horizon collector: `scripts/lp_long_horizon_readonly_collector_v1.py` (design + smoke modes)

## 2. Manifest 三层结构

### 2.1 Level 1: Chain Coverage

| 字段 | 类型 | 必填 |
|---|---|---|
| `chain` | string enum [base, bsc, solana, ethereum, arbitrum, optimism, polygon] | ✅ |
| `observed` | boolean | ✅ |
| `pool_count` | integer | ✅ |
| `quote_ready_count` | integer | ✅ |
| `fee_ready_count` | integer | ✅ |
| `ev_ready_count` | integer | ✅ |
| `invalid_reason` | string | (if observed=false) |

**规则**:
- chain adapter 已实现 → `observed=true`
- chain adapter 缺失 → `observed=false` + `invalid_reason='chain_adapter_not_implemented_yet'`
- RPC rate limited → `observed=true` + `invalid_reason='rpc_rate_limited'`
- 安全跳过 → `observed=false` + `invalid_reason='chain_skipped_for_safety'`

**当前 V2 观察**: ✅ base + solana; ❌ bsc + ethereum + arbitrum + optimism + polygon.

### 2.2 Level 2: DEX/Protocol Coverage

| 字段 | 类型 | 必填 |
|---|---|---|
| `chain` | string | ✅ |
| `protocol` | string enum | ✅ |
| `pool_type` | string enum [v3, clmm, v2_cpmm, dlmm, stable] | ✅ |
| `observed_pool_count` | integer | ✅ |
| `quote_ready_count` | integer | ✅ |
| `fee_ready_count` | integer | ✅ |
| `ev_ready_count` | integer | ✅ |
| `connector_used` | string | ✅ (e.g. `internal/adapters/pool/raydium_clmm` 或 `null`) |
| `data_source` | string enum [public_rpc, public_indexer, design_placeholder, smoke_placeholder] | ✅ |
| `invalid_reason` | string | (if observed=false) |

**规则**:
- protocol pool adapter 已实现 → `observed=true` + `connector_used` 写文件路径
- 缺失 → `observed=false` + `connector_used='null'` + `invalid_reason='not_implemented_yet'`
- `data_source` 默认 `public_rpc` (R0), B 线可选 `paid_indexer` (需用户单独批准)

### 2.3 Level 3: Pool Coverage

| 字段 | 类型 | 必填 |
|---|---|---|
| `chain` / `protocol` / `pool_address` / `token_pair` / `pool_type` / `fee_tier_or_fee_bps` | various | ✅ |
| `tvl_proxy` | number (USD) | ✅ |
| `volume_proxy` | number (USD/window) | ✅ |
| `liquidity_near_active` | number | (v3/clmm/dlmm) |
| `quote_ready` / `fee_ready` / `ev_ready` | boolean | ✅ |
| `selected_for_candidate_review` | boolean | ✅ |
| `reject_reason` | string | (if not selected) |

**`selected_for_candidate_review` 规则**:
```
selected = quote_ready AND fee_ready AND ev_ready
       AND tvl_proxy >= min_tvl
       AND volume_proxy >= min_volume
       AND regime_diversity NOT 严重偏向 regime_5/6/7
```

**Stable / LST-stable 池特殊字段** (因 IL 低但 depeg/LST risk 仍要计入):
- `depeg_risk_score` (0-1)
- `lst_depeg_history_30d` (事件数)
- `stable_curve_steepness` (curve 斜率)
- 额外 `reject_reason`: `depeg_risk_too_high` / `lst_depeg_within_30d`

## 3. observed=false 透明化 (关键)

| Chain | Protocol | observed | invalid_reason |
|---|---|---|---|
| base | uniswap_v3 | true | (无) |
| base | aerodrome | true | (无) |
| solana | meteora_dlmm | **false** | `not_implemented_yet` |
| solana | orca_whirlpool | true | (无) |
| solana | raydium_clmm | true | (无) |
| solana | raydium_amm_v4 | **false** | `not_implemented_yet` |
| solana | raydium_cpmm | **false** | `not_implemented_yet` |
| solana | pancakeswap_v3_solana | true | (无) |
| bsc | pancakeswap_v3 | **false** | `bsc_chain_adapter_not_implemented_yet` |
| bsc | pancakeswap_v2 | **false** | `bsc_chain_adapter_not_implemented_yet` |
| ethereum | (any) | **false** | `chain_skipped_for_safety_mainnet_only_design_target` |
| arbitrum | (any) | **false** | `chain_skipped_for_safety_mainnet_only_design_target` |
| optimism | (any) | **false** | `chain_skipped_for_safety_mainnet_only_design_target` |
| polygon | (any) | **false** | `chain_skipped_for_safety_mainnet_only_design_target` |

**任何 observed=false 都不是"暂时不观察", 都不是"不重要", 而是 honest disclosure: collector 当前未实现对应 connector / chain adapter**.

## 4. Manifest 输出格式

### CSV

- 编码: utf-8
- 分隔符: `,`
- header: `level,chain,protocol,pool_address,token_pair,pool_type,fee_tier_or_fee_bps,observed,tvl_proxy,volume_proxy,liquidity_near_active,quote_ready,fee_ready,ev_ready,selected_for_candidate_review,reject_reason,connector_used,data_source,invalid_reason`
- `level` ∈ {`chain`, `dex`, `pool`}

### JSON

- 3 top-level keys: `chain_coverage` / `dex_coverage` / `pool_coverage`
- 每个 key 是 array of objects (per `node_report_schema.json` coverage_block)

## 5. Manifest Validation

- 所有 7 chains 必须有 chain_coverage 行 (即使 observed=false)
- 所有 10 protocols 必须有 dex_coverage 行 (即使 observed=false)
- observed=false 必须有 invalid_reason
- selected_for_candidate_review=false 必须有 reject_reason
- stable / LST-stable 池必须有 depeg 字段

## 6. 硬性不动作 (本轮)

| ID | 约束 |
|---|---|
| M1 | 不修改任何 V2 connector |
| M2 | **不**新增 connector (缺失的协议在 manifest 写 observed=false) |
| M3 | 不修改现有 pool adapter |
| M4 | 不读 wallet / keypair / signer |
| M5 | 不写 chain state |

## 7. 结论

覆盖范围 manifest spec 设计完成. 关键:

- 3 层结构 (chain / dex / pool)
- 7 chains × 10 protocols 全部列出
- observed=false 必须有 invalid_reason (honest disclosure)
- stable / LST-stable 池额外 depeg 字段
- 不新增 connector, 不假装覆盖

**Stage E PASS** → 进入 Stage F (无探针资金时手续费估算依据说明).
