# Meteora DLMM Discovery Strategy Decision — Stage H

- stage: `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1`
- run_id: `20260603_102657` (wait, this is V3 run: 20260603_130532)

## 0. 决策

```text
selected_strategy              = known_pool_feed_sdk_decode
selected_phase                 = Phase 2A
recommended_near_term_path     = known_pool_feed_sdk_decode
next_stage_recommendation      = LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1
```

## 1. 3 路径评估 (V3 实测后)

### Path 1: paid_rpc_gpa

| 维度 | 评估 |
|---|---|
| full discovery 可行 | ✅ (paid RPC ~10MB cap 容纳 Meteora DLMM ~1.8MB GPA response) |
| needs operator action | **yes** (paid RPC URL + key) |
| v3 状态 | 未尝试 (无 paid RPC key); V1 已证 public RPC 0/4 GPA |
| cost | paid (Helius/Triton/QuickNode ~$50/mo) |
| complexity | low |
| 适合 phase | **Phase 2B** (after Phase 2A is fully validated) |

### Path 2: known_pool_feed_sdk_decode (selected)

| 维度 | 评估 |
|---|---|
| full discovery 可行 | ❌ (无 GPA; 用 frozen feed) |
| needs operator action | **no** (uses public RPC + frozen feed) |
| v3 状态 | **validated: 2/2 pools full decode** (Stage E) |
| cost | free |
| complexity | low (Stage E script reusable) |
| **works** | DLMM.create / getActiveBin / getFeeInfo / reserves / token mints / decimals |
| **blocked** | getBinArrayForSwap (403) / swapQuote (depends) / getLbPairLockInfo (410) |
| 适合 phase | **Phase 2A** (current V3 path) |

### Path 3: official_rest_api

| 维度 | 评估 |
|---|---|
| full discovery 可行 | unknown (V2 探测 dlmm-api.meteora.ag 全部 404) |
| needs operator action | no |
| v3 状态 | unchanged from V2: no public REST API |
| 适合 phase | deprecated for now; re-evaluate if Meteora publishes |

## 2. 为什么选 known_pool_feed_sdk_decode (Phase 2A)

### 2.1 V3 实证 works

| SDK method | V3 实证 |
|---|---|
| `DLMM.create` | 2/2 成功 (4099ms / 2059ms) |
| `getActiveBin` | 2/2 成功 (返回 binId + price + xAmount + yAmount) |
| `getFeeInfo` | 2/2 成功 (base_fee_bps + max_fee_bps) |
| reserve fields | 2/2 成功 (raw amounts) |
| token mints + decimals | 2/2 成功 (9 SOL / 6 USDC; 6 X / 6 USDC) |

→ **pool_snapshot + fee_snapshot 完整 V3 实测**.

### 2.2 V3 实证 blocked (但只 blocking quote / bin liquidity / lock info)

| SDK method | V3 实证 |
|---|---|
| `getBinArrayForSwap` | 2/2 阻断 (403 Forbidden / 410 Gone on public RPC) |
| `swapQuote` | **未调** (depends on bin arrays) |
| `getLbPairLockInfo` | 2/2 阻断 (410 Gone) |

→ quote / bin_liquidity / lock_info **公共 RPC 限制**; **不是** connector 设计问题; **不是** SDK 问题. paid RPC 一上即解.

### 2.3 二元状态 — schema 已完整

6 张表 (Stage G):
- **可立即写**: `known_pool_universe_v1`, `pool_snapshot_v1`, `fee_snapshot_v1`
- **待 paid RPC**: `bin_liquidity_snapshot_v1`, `quote_snapshot_v1`, `survival_ev_preview_v1`

→ Phase 2A 可立刻推进 (3/6 表可写), Phase 2B 补 3/6 表.

## 3. next stage

**LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1**:
- 实现 6 张表 (3 张活跃, 3 张 schema ready 但 blocked)
- wire SDK smoke pipeline 跑 known_pool_universe
- freeze 2 pools; 可扩展 (operator input)
- **不**做 quote / EV
- **不**开 LP
- **不**接 keypair

## 4. 备选决策 (operator input)

| 如果 operator 提供 | 决策 |
|---|---|
| paid RPC URL | 可在 connector V1 + quote + EV 一起做; 跳过 fix_repeat |
| paid RPC + Lifinity pid | 可同时跑 Raydium CPMM; 风险 stage 复杂 |
| 更大的 known pool feed (人工 curate) | 可扩展 feed to 10+ pools; 仍不需要 paid RPC |
| 都不提供 | 走 default: LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1 (Phase 2A) |

## 5. 不在本阶段做

- ❌ 不实现 6 张表 (still design-only)
- ❌ 不决定 paid RPC vendor (operator input)
- ❌ 不扩展 known pool feed (operator input)
- ❌ 不连 live database

## 6. 安全断言

```text
this_stage_only_decision       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 7. 下一阶段

进入 Stage I — next-stage decision V3. 选 LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1.
