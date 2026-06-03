# Input Evidence Audit — LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2`
- run_id: `20260603_150331`
- branch: `feat/supabase-postgres-deployment`
- head before: `0729ea8` (research: expand meteora dlmm binarray quote coverage 20260603_143729 — V6)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/FINAL_VERDICT.json` | status=WARN; expanded_pda_success=42/42; single_account=33/42; bin_liquidity=2310; quote=6/12; sol_usdc=0/6; x_usdc=6/6; min_coverage=≥9_arrays; paid_rpc_required=partial; recommended_next_stage=LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/ONEPAGE_CN.md` | 一页总览 | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/METEORA_QUOTE_SMOKE_V3_BY_COVERAGE_CN.md` | 6/12 quote; pool 1 blocked | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/meteora_quote_smoke_v3_by_coverage.json` | structured quote results | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/METEORA_EXPANDED_BIN_LIQUIDITY_DECODE_CN.md` | 2310 bins decoded | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/meteora_expanded_bin_liquidity_decode.json` | structured bin liquidity | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/METEORA_QUOTE_READINESS_UPDATE_CN.md` | 6 tables judged | OK |
| `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/20260603_143729/meteora_quote_readiness_update.json` | structured readiness | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/FINAL_VERDICT.json` | upstream V5 | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/FINAL_VERDICT.json` | upstream V4 | OK |

## 2. 关键事实（继承 V6）

```text
previous_stage                                = LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1
previous_status                               = WARN
previous_run_id                               = 20260603_143729
previous_commit                               = 0729ea8
expanded_pda_derivation_ran                   = true
expanded_pda_success_count                    = 42 (2 pools × (5+7+9))
single_account_read_ran                      = true
single_account_read_success_count            = 33 (V5 6/6; V6 33/42 = 78.6%)
bin_liquidity_decode_success_count            = 2310
quote_smoke_ran                               = true
quote_smoke_attempted_count                   = 12
quote_smoke_success_count                     = 6
sol_usdc_quote_success                        = false  (0/6 at 5/7/9 arrays)
x_usdc_quote_success                          = true   (6/6 at 5/7/9 arrays)
minimum_coverage_required                     = ≥9_arrays (still insufficient for pool 1)
paid_rpc_required                             = partial  (single-account path works; pool 1 needs >9 arrays OR paid RPC GPA)
recommended_next_stage                        = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
can_run_probe_now                             = false
solana_wallet_or_keypair_touched             = false
tiny_canary_allowed                          = "no"
edge_proven                                  = "no"
v2_line_count_unchanged                      = true (992)
```

## 3. V6 阻断与 V7 必须解决

| 阻断 | V6 状态 | V7 目标 |
|---|---|---|
| SOL/USDC quote blocked | 9 arrays × 70 bins = 630 bins ≈ 12% range; 0/6 attempts | 扩 9 → 12 → 15 arrays; target 4/4 quote success on public RPC; if 15 still blocked, STOP |
| Pool 2 (X/USDC) 2/2 success | already works at 3-9 arrays | 维持 (sanity check, no expansion) |
| 15 arrays RPC risk | public RPC may rate-limit after 5+ req/s sustained | single-account getAccountInfo, retry+backoff via withFallback |
| 12 arrays success shortcut | 12 may be enough (per spec "12-15 may work") | auto-checkpoint: if 12 succeeds, skip 15 |

## 4. V7 目标 (来自 operator prompt)

1. **Stage C** — 设计 12/15 arrays coverage plan; max 15 hard rule
2. **Stage D** — 推导 12/15 arrays PDA for SOL/USDC (priority) + X/USDC (sanity)
3. **Stage E** — getAccountInfo on 12/15 arrays; document blockers
4. **Stage F** — decode all fetched bin arrays; find nearest/farthest liquidity
5. **Stage G** — SOL/USDC quote smoke v4 at 12 (auto-checkpoint) then 15 if needed
6. **Stage H** — combined quote readiness V2 (pool 2 sanity + combined)
7. **Stage I** — next-stage decision
8. **Stage J** — final verdict
9. **Stage K** — tests + safety scan
10. **Stage L** — git publish

## 5. 硬性边界 (per spec "不得无限扩展")

- max coverage = 15 arrays
- if 15 arrays still blocked, STOP and recommend paid_rpc_setup OR partial survival EV preview with pool 2 only
- auto-checkpoint: if 12 arrays achieves 2/2 SOL/USDC quote, skip 15

## 6. Known pool feed (full addresses from V6 artifact)

| pool_address | source | active_bin_id | bin_step | V6 status |
|---|---|---|---|---|
| `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | swap_quote.ts | -12248 | 2 | quote blocked (0/6) at 5/7/9 |
| `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | fetch_lb_pair_lock_info.ts | -236 | 100 | quote success (6/6) at 5/7/9 |

## 7. 严格只读不变式（继承 + 本轮）

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

本轮**不**改任何上述值；不读 keypair；不签名；不发 tx；不开 LP；不 swap；不 bridge；不 probe；不启动 live/canary/paper；不写 production positions；不修改 EVM executor v2；不释放 v2 hard-disable；不在 repo root 安装任何 npm package。

## 8. 决定

进入 Stage C — 12/15 arrays coverage plan (per spec "max 15; 不得无限扩展").
