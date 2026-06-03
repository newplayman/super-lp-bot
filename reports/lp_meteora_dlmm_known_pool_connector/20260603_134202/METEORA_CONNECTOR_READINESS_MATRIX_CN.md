# Meteora Connector Readiness Matrix — Stage I

- stage: `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`
- run_id: `20260603_134202`

## 0. 关键判定

```text
connector_readonly_ready       = yes (3/6 tables ready; 2/2 pools decoded)
quote_ready                   = no  (0/4 quote; bin_arrays blocked on public RPC)
survival_ev_ready             = no  (depends on quote)
needs_paid_rpc                = yes (to unblock bin_liquidity + quote + EV)
needs_known_pool_feed_expansion = no  (2 pools sufficient for V4 validation)
```

## 1. 6 表状态

| # | table | status | reason | fix path |
|---|---|---|---|---|
| 1 | `meteora_dlmm_known_pool_universe_v1` | **ready** | 2/2 pools from official SDK examples, full addresses from V3 artifact, all on mainnet | none needed |
| 2 | `meteora_dlmm_pool_snapshot_v1` | **ready** | 2/2 pools full LbPair decode succeeded (DLMM.create + getActiveBin + token mints + reserves) | none needed |
| 3 | `meteora_dlmm_fee_snapshot_v1` | **ready** | 2/2 pools base_fee_bps + max_fee_bps extracted (sync, no RPC) | none needed |
| 4 | `meteora_dlmm_bin_liquidity_snapshot_v1` | **blocked_public_rpc** | getBinArrayForSwap 403 on public RPC; 0/2 success | paid RPC or known bin array index |
| 5 | `meteora_dlmm_quote_snapshot_v1` | **blocked_public_rpc** | swapQuote needs binArrays; 0/4 success | paid RPC or known bin array index |
| 6 | `meteora_dlmm_survival_ev_preview_v1` | **blocked_missing_quote** | no quote data → no EV | fix quote first |

**summary**:
- 3 tables **ready** (universe, pool_snapshot, fee_snapshot)
- 2 tables **blocked_public_rpc** (bin_liquidity, quote)
- 1 table **blocked_missing_quote** (survival_ev, derived blocker)
- 0 tables **invalid** / **not_attempted**

## 2. 详细判定

### 2.1 `connector_readonly_ready` = yes

3/6 tables ready with 2/2 pools each:
- known_pool_universe: 2 pools from official SDK examples (full addresses, all on mainnet)
- pool_snapshot: 2/2 full LbPair decode via `DLMM.create` + `getActiveBin`
- fee_snapshot: 2/2 fee via `dlmmPool.getFeeInfo()`

Connector V1 **可以** 实装这 3 张表, 用 SDK read-only, **不**需要 paid RPC.

### 2.2 `quote_ready` = no

0/4 quote success. **根因**: `swapQuote` requires pre-fetched `BinArrayAccount[]`, 只能通过 `dlmmPool.getBinArrayForSwap(swapYtoX, count)` 拉, 这被 public RPC 403 阻断 (per Stage G + H).

→ Connector V1 **不能** 实装 quote_snapshot (除非 paid RPC 或 known bin array index).

### 2.3 `survival_ev_ready` = no

依赖 quote. quote blocked → EV cannot be computed. **派生 blocker**.

### 2.4 `needs_paid_rpc` = yes

Phase 2B 必经:
- provider options: Helius / Triton / QuickNode
- 必需: operator 提供 paid RPC URL
- 预期: 一旦 paid RPC 上, 6/6 tables ready (3/6 already ready; 3/6 to unblock)

### 2.5 `needs_known_pool_feed_expansion` = no

2/2 pools verified + decoded. feed size 对 connector V1 验证**足够**; 扩展 (10+ pools) 可在 Phase 2B paid RPC 之后.

## 3. Phase 2A vs Phase 2B 边界

| 项 | Phase 2A (V4 完成) | Phase 2B (待) |
|---|---|---|
| pool_snapshot | ✅ ready | ready |
| fee_snapshot | ✅ ready | ready |
| known_pool_universe | ✅ ready | ready |
| bin_liquidity | ❌ blocked | needs paid RPC |
| quote | ❌ blocked | needs paid RPC |
| survival_ev | ❌ blocked_missing_quote | needs paid RPC + EV computation |
| feed size | 2 pools | can expand to 10+ (paid RPC GPA) |

## 4. 关键诚实发现 (per spec "状态可选")

- 表 4 + 5: blocked_public_rpc (**真** blocker, **不**是 connector 设计问题)
- 表 6: blocked_missing_quote (**派生** blocker)
- 表 1 + 2 + 3: **真** ready

## 5. 不在本阶段做

- ❌ 不实装任何表
- ❌ 不连 live database
- ❌ 不写 production positions
- ❌ 不 paid RPC (无 key)
- ❌ 不 fake quote / bin_liquidity success
- ❌ 不修改 EVM executor v2

## 6. 安全断言

```text
this_stage_only_decision       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 7. 下一阶段

进入 Stage J — next-stage decision: 选 `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` (bin/quote blocker 需要 fix; connector 实现无 bug).
