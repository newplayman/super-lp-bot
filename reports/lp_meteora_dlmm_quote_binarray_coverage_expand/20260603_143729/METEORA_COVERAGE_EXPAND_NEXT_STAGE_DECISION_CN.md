# Meteora Coverage Expand Next-Stage Decision — Stage I

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1`
- run_id: `20260603_143729`

## 0. 决策

```text
recommended_next_stage = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
default_when_no_explicit_choice = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
```

## 1. 5 选项评估

| next stage | 触发条件 | V6 状态 |
|---|---|---|
| `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` | quote success enough + bin liquidity + fee | ⚠️ (6/12 quote; only pool 2; partial EV possible) |
| `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` | coverage expansion improved but still partial | **✅ 触发** (V6 9 arrays; pool 1 still blocked; try 12-15 OR different strategy) |
| `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | public RPC cannot read enough bin arrays | ❌ (single-account path works for 33/42 reads; not a hard RPC blocker) |
| `LP_METEORA_DLMM_KNOWN_POOL_CONNECTOR_FIX_REPEAT` | connector bug | ❌ (connector V1 + expand V1 work; no bug) |
| `STOP_LP_RESEARCH_NOW` | no safe read-only path | ❌ (read-only path fully working) |

## 2. 为什么选 LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT

### 2.1 V6 实证 (5/7/9 arrays all 2/4 quote)

V6 expanded coverage 3 → 5 → 7 → 9 arrays, but:
- **Pool 1 (SOL/USDC) quote 0/6** across all tiers (even 9 arrays × 70 bins = 630 bins ≈ 12% price range)
- **Pool 2 (X/USDC) quote 6/6** stable across all tiers

→ Pool 1 quote blocked **not** by RPC limit (single-account path works 33/42), but by:
- 9_arrays still insufficient for pool 1's liquidity distribution
- OR pool 1 has very wide price gap between active bin and existing liquidity

### 2.2 next fix_repeat 候选 strategies

| strategy | description | expected |
|---|---|---|
| 12-15 arrays | extend coverage slightly beyond spec's 9 max | medium (15 arrays = 18% range; may suffice) |
| 21 arrays | extend more (3x spec max) | high but violates spec "不得无限扩展" |
| `maxExtraBinArrays=10` | let SDK fetch more on demand | medium (may hit multi-account 403) |
| Different active bin pick | e.g. shift active bin to -12200 (closer to liquidity) | depends on data |
| Skip pool 1 EV | use only pool 2 for EV | immediate (partial EV) |
| Paid RPC GPA | enumerate all bin arrays | high (but operator key required) |

## 3. 进步 (V5 → V6)

| metric | V5 | V6 | delta |
|---|---|---|---|
| coverage | 3 arrays | 5/7/9 arrays | 3x more |
| single-account read success | 6/6 (V5) | 33/42 (V6) | more attempts, 0 RPC errors |
| bins decoded | 420 | 2310 (5_arrays: 630; 7: 770; 9: 910) | **5.5x more** |
| quote attempts | 4 | 12 | 3x more |
| quote success | 2/4 | 6/12 (all pool 2) | pool 2 stable; pool 1 unchanged |
| pool 2 quote | 2/2 | 6/6 (V5+V6 combined) | 100% stable |
| pool 1 quote | 0/2 | 0/6 (V5+V6) | 0% (real blocker) |

## 4. 风险 (per spec 边界)

- next fix_repeat risk: extending to 12-15 arrays is **slightly beyond spec's 9 max** (spec says "不得无限扩展"; 12-15 is bounded, not infinite)
- 池 1 may still block even at 15 arrays if liquidity is far from active
- fallback to paid_rpc_setup if 12-15 also fails

## 5. 不在本阶段做

- ❌ 不实现 production connector
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不调 swap tx builder
- ❌ 不 paid RPC call
- ❌ 不 fake quote success
- ❌ 不修改 EVM executor v2

## 6. 安全断言

```text
this_stage_only_decision       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 7. 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT`（无需操作员声明）
- 关键 input 需求（建议下个 prompt 提供）:
  1. (默认) **同意扩 coverage 9 → 12-15 arrays** (next fix_repeat 第一步, 仍 public RPC)
  2. (若 12-15 仍 blocked) **paid RPC 决策** (Phase 2B; Helius / Triton / QuickNode)
  3. (可选) **skip pool 1 EV**, 用 only pool 2 (immediate partial EV)
  4. (可选) **swapQuote maxExtraBinArrays=10** (let SDK try harder; but may hit multi-account)
- 不建议直接进 EV preview (6/12 quote; partial EV; not full evaluation)
- 不建议 STOP (33/42 single-account success + 2310 bins + 6/12 quote = 显著进步)
- 即便选 fix_repeat, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
