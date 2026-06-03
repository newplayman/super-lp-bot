# Input Evidence Audit — LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_153736`
- branch: `feat/supabase-postgres-deployment`
- head before: `3c72d3f` (research: expand meteora dlmm quote coverage v2 20260603_150331 — V7)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/FINAL_VERDICT.json` | status=WARN; coverage_12=12/12; coverage_15=15/15; sol_usdc=0/4; x_usdc=6/6 stable; can_enter_partial_survival_ev_preview=true; paid_rpc_required=true; recommended=LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1 | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/ONEPAGE_CN.md` | 一页总览 | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/METEORA_COMBINED_QUOTE_READINESS_V2_CN.md` | 6 tables; 3 ready / 3 partial | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/meteora_combined_quote_readiness_v2.json` | structured combined readiness | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/METEORA_QUOTE_READINESS_UPDATE_CN.md` | V6 readiness (3 ready / 3 partial) | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/meteora_quote_readiness_update.json` | V6 readiness structured | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/METEORA_QUOTE_SMOKE_V3_BY_COVERAGE_CN.md` | 6/12 quote (pool 2 6/6 stable; pool 1 0/6) | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/meteora_quote_smoke_v3_by_coverage.json` | structured quote | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/METEORA_EXPANDED_BIN_LIQUIDITY_DECODE_CN.md` | 2310 bins decoded; 731 with liquidez | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/meteora_expanded_bin_liquidity_decode.json` | structured bin liquidez | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/METEORA_POOL_SNAPSHOT_CN.md` | 2/2 pool snapshot | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/meteora_pool_snapshot.json` | structured per-pool snapshot | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/METEORA_FEE_SNAPSHOT_CN.md` | 2/2 fee snapshot | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/meteora_fee_snapshot.json` | structured per-pool fee | OK |

## 2. 关键事实（继承 V7）

```text
previous_stage                                = LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2
previous_status                               = WARN
previous_run_id                               = 20260603_150331
previous_commit                               = 3c72d3f
coverage_12_attempted                          = true
coverage_12_success_count                     = 12 (SOL/USDC; 9 success in V6 partial also)
coverage_15_attempted                          = true
coverage_15_success_count                     = 15 (SOL/USDC)
bin_liquidity_decode_success_count             = 1540 (V7) + 2310 (V6) = 3850 cumulative
sol_usdc_10u_quote_success                     = false
sol_usdc_20u_quote_success                     = false
x_usdc_quote_still_success                     = true (V6 6/6 stable)
quote_success_count_total                      = 0/4 (SOL/USDC only)
minimum_coverage_required                      = ≥15_arrays (per spec hard cap)
can_enter_full_survival_ev_preview            = false
can_enter_partial_survival_ev_preview         = true
paid_rpc_required                              = true
recommended_next_stage                         = LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1
can_run_probe_now                             = false
solana_wallet_or_keypair_touched              = false
tiny_canary_allowed                           = "no"
edge_proven                                   = "no"
v2_line_count_unchanged                       = true (992)
```

## 3. V7 阻断与 V8 必须解决

| 阻断 | V7 状态 | V8 目标 |
|---|---|---|
| SOL/USDC quote 全 阻断 | 0/8 cumulative (V5+V6+V7) | 标记 no_quote_data; **不**为 partial EV 假装 |
| Pool 2 (X/USDC) V6 6/6 stable | 已成功 (10U=941005; 20U=1882010) | 维持; 用 V6 quote data 进 survival EV |
| survival EV preview 模型 还没 跑 | V7 hit spec cap; STOP expansion | 本轮 只算 pool 2 partial EV |
| 10/20U preflight 是否值得 | 未评估 | 评估 realistic scenario; 不能 fake success |
| cost model + fee capture | 未做 | scenario-based heuristic; 标记 heuristic |

## 4. V8 目标 (来自 operator prompt)

1. **Stage C** — partial scope freeze (included X/USDC; excluded SOL/USDC with no_quote_data reason)
2. **Stage D** — survival EV model input build (6 notionals × 7 hold_windows × 4 scenarios = 168 cells for X/USDC)
3. **Stage E** — fee capture proxy (scenario-based; heuristic marked)
4. **Stage F** — Solana cost model (tx fee + rent + position cost; 3 scenarios)
5. **Stage G** — survival EV preview (compute net_ev across cells; honest reporting)
6. **Stage H** — 10/20U preflight implication (answer operator questions; **no probe**)
7. **Stage I** — next-stage decision
8. **Stage J** — final verdict
9. **Stage K** — tests + safety scan
10. **Stage L** — git publish

## 5. Known pool feed (full addresses from V4 artifact)

| pool_address | source | V7 status | V8 inclusion |
|---|---|---|---|
| `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | swap_quote.ts | quote blocked; no_quote_data | **excluded** (no_quote_data) |
| `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | fetch_lb_pair_lock_info.ts | V6 6/6 stable; quote data available | **included** (partial scope) |

## 6. 严格只读不变式（继承 + 本轮）

```text
can_run_probe_now              = false
execution_allowed_now          = false
transaction_sent               = false
wallet_or_tx_touched           = false
solana_wallet_or_keypair_touched = false
tiny_canary_allowed            = "no"
edge_proven                    = "no"
manual_approval_required       = true
send_hard_disable_still_active = true
v2_modified_by_this_task       = false
v2_line_count_unchanged        = true
```

本轮**不**改任何上述值；不读 keypair；不签名；不发 tx；不开 LP；不 swap；不 bridge；不 probe；不启动 live/canary/paper；不写 production positions；不修改 EVM executor v2；不释放 v2 hard-disable；partial scope 不可作 full EV 解读。

## 7. 决定

进入 Stage C — partial scope freeze (X/USDC included; SOL/USDC excluded with no_quote_data reason).
