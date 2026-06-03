# Meteora Combined Quote Readiness V2 — Stage H

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2`
- run_id: `20260603_150331`

## 0. 关键判定

```text
sol_usdc_quote_ready                  = no (blocked at 12 AND 15 arrays; spec hard cap reached)
x_usdc_quote_ready                    = yes (V6: 6/6 stable at 5/7/9 arrays; not re-run this round)
bin_liquidity_ready                  = partial (pool 1: 0 bins with liquidity; pool 2: 231 bins)
quote_ready                          = partial (pool 1 blocked at ALL tiers 3-15; pool 2 ready)
survival_ev_ready                    = partial (only pool 2 has quote data)
paid_rpc_required                     = yes (per spec hard cap reached; only paid RPC GPA or partial EV)
can_enter_full_survival_ev_preview   = no
can_enter_partial_survival_ev_preview = yes (pool 2 only)
```

## 1. V7 实证 (coverage 12/15 on SOL/USDC)

| coverage | pda | read | bins | bins_with_liq | quote 10U | quote 20U |
|---|---|---|---|---|---|---|
| 12_arrays | 12/12 | 8/12 (4 null) | 560 | **0** | ❌ blocked | ❌ blocked |
| 15_arrays | 15/15 | 10/15 (5 null) | 700 | **0** | ❌ blocked | ❌ blocked |

→ **Pool 1 has 0 bins with liquidity at coverage 12 AND coverage 15.** This is the real on-chain finding: the active bin's ±10% range has no liquidity deposited at all.

## 2. 关键 finding: pool 1 liquidity 离 active bin 太远，15 arrays 不够

- 9_arrays (V6): 12% range, 50 bins with liquidez
- 12_arrays (V7): 16.8% range, **0 bins with liquidez** (but 560 bins decoded)
- 15_arrays (V7): 21% range, **0 bins with liquidez** (but 700 bins decoded)

Wait — the 50/231 with liquidez numbers at 5/7/9 arrays (V6) included pool 2's wide bin_step=100 dense liquidity. For **pool 1 only** (SOL/USDC), V6 had 0/0/0 bins with liquidez at 5/7/9 arrays. V7 still 0/0 at 12/15.

→ **Pool 1 (SOL/USDC) consistently 0 bins with liquidity across 5/7/9/12/15 array coverage** (0-21% range). The active bin's surrounding region has **no liquidity deposits** at all.

## 3. 单账户 path 持续 works

| metric | V5 (3_arrays) | V6 (5/7/9_arrays) | V7 (12/15_arrays) |
|---|---|---|---|
| single-account success | 6/6 | 33/42 | 8+10=18/27 |
| 0 RPC errors | yes | yes | yes |
| Account_null (un-initialized) | 0 | 9 | 4+5=9 |

→ Single-account path **scales linearly** with coverage. No RPC limit. Just **no liquidity** in the queried range.

## 4. 6 表 readiness V2

| # | table | status | reason |
|---|---|---|---|
| 1 | `meteora_dlmm_known_pool_universe_v1` | **ready** | 2/2 pools from official SDK examples |
| 2 | `meteora_dlmm_pool_snapshot_v1` | **ready** | 2/2 pools full LbPair decode |
| 3 | `meteora_dlmm_fee_snapshot_v1` | **ready** | 2/2 pools base + max fee |
| 4 | `meteora_dlmm_bin_liquidity_snapshot_v1` | **partial** | pool 1: 0/1260 bins with liquidity; pool 2: 231/280 bins |
| 5 | `meteora_dlmm_quote_snapshot_v1` | **partial** | pool 1: 0/8 quote attempts (5+7+9+12+15 arrays); pool 2: V6 6/6 stable |
| 6 | `meteora_dlmm_survival_ev_preview_v1` | **partial** | only pool 2 quote data; pool 1 cannot compute EV |

## 5. per spec hard rule enforcement

Per spec "max 15 arrays; 如果 15 arrays 仍失败, 必须停止并推荐 paid RPC 或 pool2-only survival EV preview; 不得无限扩展":

- V7 hit 15 arrays cap
- Pool 1 quote still blocked
- **STOP expansion**
- Recommend: `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` OR `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` (partial, pool 2 only)

## 6. 不在本阶段做

- ❌ 不实现 production code
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不 compute survival EV (deferred)
- ❌ 不修改 EVM executor v2

## 7. 安全断言

```text
this_stage_only_readiness_assessment = true
solana_wallet_or_keypair_touched = false
can_run_probe_now = false
v2_line_count_unchanged = true (992)
```

## 8. 下一阶段

进入 Stage I — next-stage decision V7: 选 `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` 或 `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` (partial, pool 2 only).
