# Meteora Survival EV Next-Stage Decision — Stage I

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_153736`

## 0. 决策

```text
recommended_next_stage = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1
default_when_no_explicit_choice = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1
```

## 1. 5 选项评估

| next stage | 触发条件 | V8 状态 |
|---|---|---|
| `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1` | partial preview insufficient but connector works; 需要更多 known pools | **✅ 触发** (X/USDC partial EV all negative; expand feed 找 positive EV pools) |
| `LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1` | 10/20U realistic or near-break-even candidate exists | ❌ (10/20U all negative; -$0.247 best realistic) |
| `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | 必须全量 discovery / SOL/USDC 也要 quote | ❌ (X/USDC alone insufficient; SOL/USDC needs GPA 找 liquidity; deferrable) |
| `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_FIX_REPEAT` | model/input bugs | ❌ (model is not buggy; heuristic-marked; missing fields marked) |
| `STOP_LP_RESEARCH_NOW` | partial EV clearly negative and no connector value | ❌ (read-only connector works; 7/8 stages done; better to expand feed) |

## 2. 为什么选 LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1

### 2.1 V8 EV 实证 (168 cells; all negative)

| scenario | il_lvr_pct | positive cells | best net_ev_usd | best net_ev_pct |
|---|---|---|---|---|
| zero_il_lvr | 0% | 0/42 | -$0.154 (2000/15m) | -0.0077% |
| optimistic | 0.1% | 0/42 | -$2.154 (2000/15m) | -0.1077% |
| realistic | 0.5% | 0/42 | -$10.154 (2000/15m) | -0.5077% |
| conservative | 2.0% | 0/42 | -$40.154 (2000/15m) | -2.0077% |

→ **All 168 cells negative.** X/USDC at retail notionals (10-2000 USD) has **structurally negative EV**.

### 2.2 根因

- base_fee_bps = 1.5 (low)
- assumed_volume_pct = 0.5% (medium, pessimistic)
- fixed cost = ~$0.19 round-trip + setup
- IL/LVR even at 0.1% = $2 on $2000 notional

→ **Meteora DLMM X/USDC at retail scale is structurally unprofitable** for a single-position LP.

### 2.3 候选 next_stage

| candidate | 评估 |
|---|---|
| **Known pool feed expansion** | **YES** — find higher-fee Meteora pools OR other AMM (Raydium CLMM, Orca Whirlpools); some pools have max_fee 20-30% with active volume |
| 10/20U probe preflight | NO — EV is negative; no point designing |
| Paid RPC for SOL/USDC | NO — X/USDC alone insufficient; SOL/USDC needs GPA 找 liquidity; deferrable |
| Survival EV preview fix repeat | NO — model is correct; heuristic-marked; not buggy |
| STOP | NO — read-only path works; better to expand feed |

### 2.4 expected outcome of next fix_repeat (feed expansion)

- Extend known pool feed to 5-10 Meteora DLMM pools (human-curated from Meteora UI)
- Re-run survival EV preview per pool
- **Likely** find pools with positive EV (those with higher base_fee_bps OR higher assumed volume)
- **OR** extend to Raydium CLMM (CAMMCzo5...) which has different fee structure
- **OR** extend to Orca Whirlpools (whirLbMi...) which has different LP mechanics

→ 期望: find at least 1 pool with realistic positive EV.

## 3. 进步 (V7 → V8)

| metric | V7 | V8 | delta |
|---|---|---|---|
| coverage | 12/15 arrays (spec cap) | n/a (no new arrays) | — |
| EV preview | not done | **168 cells computed (X/USDC only)** | new artifact |
| honest reporting | partial readiness (3 ready / 3 partial) | **honest negative EV; heuristic marked** | new dimension |
| next stage decision | "partial EV possible if pool 2 ready" | **"pool 2 EV all negative; expand feed"** | refined |

## 4. 风险 (per spec 边界)

- next fix_repeat risk: 5-10 pools × 168 cells = up to 1680 cells; 仍 public RPC + single-account path; expect ~10s per pool
- 如果 no pool with positive EV found even at 5-10 pools: 候选 paid_rpc_setup for GPA-based volume discovery
- 不建议再 fix_repeat of V8 model (model is correct)
- 不建议 STOP (read-only path fully working)

## 5. 不在本阶段做

- ❌ 不实现 production connector
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不 paid RPC call
- ❌ 不 fake EV data
- ❌ 不修改 EVM executor v2

## 6. 安全断言

```text
this_stage_only_decision       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 7. 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1`（无需操作员声明）
- 关键 input 需求:
  1. (默认) **同意扩展 known pool feed** (next fix_repeat 第一步)
  2. (可选) **operator 提供 Meteora UI top pools 列表** (5-10 pools; human-curated)
  3. (可选) **是否同意扩展到 Raydium CLMM / Orca Whirlpools** (different AMM protocols; different fee structures)
  4. (可选) **是否提供 paid RPC key** (用于 10-20U 真正 probe preflight)
  5. (可选) **是否接受 STOP** (如果 5-10 pools 都 negative EV; 仍 read-only connector 可用于其他目的)
- 不建议 10/20U probe preflight (V8 evidence: 10/20U X/USDC all negative)
- 不建议 STOP 立即 (V8 EV 是 first quantitative signal; read-only path fully working)
- 即便选 feed expansion, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
