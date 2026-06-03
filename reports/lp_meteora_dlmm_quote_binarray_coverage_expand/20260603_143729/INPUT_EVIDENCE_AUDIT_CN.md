# Input Evidence Audit — LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1`
- run_id: `20260603_143729`
- branch: `feat/supabase-postgres-deployment`
- head before: `202de5b` (research: fix meteora dlmm quote binarray path 20260603_140707 — V5)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/FINAL_VERDICT.json` | status=WARN; binarray_pda_success=6/6; single_account_smoke_success=6/6; bin_liquidity_decode=420; quote_smoke=2/4; paid_rpc_required=partial; recommended_next_stage=LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/ONEPAGE_CN.md` | 一页总览 | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/METEORA_BINARRAY_PDA_DERIVATION_CN.md` | 6 PDA pubkeys derived | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/meteora_binarray_pda_derivation.json` | structured PDA results | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/METEORA_BINARRAY_SINGLE_ACCOUNT_SMOKE_CN.md` | 6/6 single-account success | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/meteora_binarray_single_account_smoke.json` | structured smoke results | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/METEORA_BIN_LIQUIDITY_DECODE_CN.md` | 420 bins decoded | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/meteora_bin_liquidity_decode.json` | structured bin liquidity | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/METEORA_QUOTE_SMOKE_V2_CN.md` | 2/4 quote (pool 2 success, pool 1 blocked) | OK |
| `reports/lp_meteora_dlmm_quote_binarray_fix/20260603_140707/meteora_quote_smoke_v2.json` | structured quote results | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/FINAL_VERDICT.json` | upstream V4 final | OK |

## 2. 关键事实（继承 V5）

```text
previous_stage                                = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1
previous_status                               = WARN
previous_run_id                               = 20260603_140707
previous_commit                               = 202de5b
binarray_helper_audit_ran                     = true
binarray_pda_derivation_ran                   = true
binarray_pda_success_count                    = 6  (2 pools × 3 offsets)
single_account_smoke_ran                      = true
single_account_smoke_success_count            = 6  (V4 multi-account blocker BYPASSED)
single_account_smoke_403_count                = 0
single_account_smoke_410_count                = 0
bin_liquidity_decode_success_count            = 420  (6 bin arrays × 70 bins)
quote_smoke_ran                               = true
quote_smoke_success_count                     = 2  (V1-V4 all 0; V5 first real quote)
quote_smoke_attempt_count                     = 4
sol_usdc_quote_success                        = false  (V5 pool 1 blocked; tight bin_step=2)
x_usdc_quote_success                          = true   (V5 pool 2 success; wide bin_step=100)
paid_rpc_required                             = partial  (NOT true; single-account path works)
recommended_next_stage                        = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
can_run_probe_now                             = false
solana_wallet_or_keypair_touched             = false
tiny_canary_allowed                          = "no"
edge_proven                                  = "no"
v2_line_count_unchanged                      = true (992)
```

## 3. V5 阻断与 V6 必须解决

| 阻断 | V5 状态 | V6 目标 |
|---|---|---|
| SOL/USDC quote blocked | 3 arrays × 70 bins = 210 bins ≈ 4% price range; 10U-20U USDC swap needs more | 扩 coverage 3 → 5 → 7 → 9 arrays; target 4/4 quote success on public RPC |
| Pool 2 (X/USDC) 2/2 success | already works | 维持 (re-verify) |
| bin liquidity depth | 420 bins decoded but per-bin xAmount=0 in many far bins | 扩 coverage 找 liquidity 区间 |
| EV preview | 2/4 quote partial | 需要 4/4 才能进 survival EV preview |

## 4. V6 目标 (来自 operator prompt)

1. **Stage C** — 设计 3/5/7/9 arrays coverage plan; 估计 cost + risk
2. **Stage D** — 推导 5/7/9 arrays PDA for 2 known pools (no RPC; pure math)
3. **Stage E** — getAccountInfo on 5/7/9 arrays; document blockers
4. **Stage F** — decode 成功读取的 bin arrays; count bins with liquidity
5. **Stage G** — quote smoke v3 by coverage; target SOL/USDC 4/4 success
6. **Stage H** — quote readiness update
7. **Stage I** — next-stage decision
8. **Stage J** — final verdict
9. **Stage K** — tests + safety scan
10. **Stage L** — git publish

## 5. Known pool feed (full addresses from V5 artifact)

| pool_address | source | active_bin_id | bin_step | V5 status |
|---|---|---|---|---|
| `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | swap_quote.ts | -12248 | 2 | quote blocked (tight bin_step) |
| `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | fetch_lb_pair_lock_info.ts | -236 | 100 | quote success (wide bin_step) |

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

本轮**不**改任何上述值；不读 keypair；不签名；不发 tx；不开 LP；不 swap；不 bridge；不 probe；不启动 live/canary/paper；不写 production positions；不修改 EVM executor v2；不释放 v2 hard-disable；不在 repo root 安装任何 npm package。

## 7. 决定

进入 Stage C — coverage expansion plan (3/5/7/9 arrays design + estimate cost + risk).
