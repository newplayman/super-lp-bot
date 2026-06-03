# Input Evidence Audit — LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1`
- run_id: `20260603_140707`
- branch: `feat/supabase-postgres-deployment`
- head before: `1c3d8ea` (research: add meteora dlmm known pool connector 20260603_134202 — V4)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/FINAL_VERDICT.json` | status=WARN; known_pool_connector_built=true; pool_snapshot=2/2; fee=2/2; bin_liquidity=0/2; quote=0/4; connector_readonly_ready=true; quote_ready=false; needs_paid_rpc=true; recommended_next_stage=LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/ONEPAGE_CN.md` | 一页总览 | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/METEORA_KNOWN_POOL_UNIVERSE_CN.md` | 2 selected + 1 skipped | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/meteora_known_pool_universe.json` | structured feed; full addresses | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/METEORA_POOL_SNAPSHOT_CN.md` | 2/2 full LbPair decode | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/meteora_pool_snapshot.json` | structured per-pool snapshot | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/METEORA_FEE_SNAPSHOT_CN.md` | 2/2 base + max fee | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/meteora_fee_snapshot.json` | structured per-pool fee | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/METEORA_BIN_LIQUIDITY_SNAPSHOT_CN.md` | 0/2; 403 public RPC blocker | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/meteora_bin_liquidity_snapshot.json` | structured blocker results | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/METEORA_QUOTE_SNAPSHOT_CN.md` | 0/4 quote; depends on bin arrays | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/meteora_quote_snapshot.json` | structured quote results | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/METEORA_CONNECTOR_READINESS_MATRIX_CN.md` | 6 tables; 3 ready / 2 blocked / 1 blocked_missing | OK |
| `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/meteora_connector_readiness_matrix.json` | structured readiness | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/FINAL_VERDICT.json` | upstream V3 | OK |

## 2. 关键事实（继承 V4）

```text
previous_stage                       = LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1
previous_status                      = WARN
previous_run_id                      = 20260603_134202
previous_commit                      = 1c3d8ea
known_pool_connector_built           = true
known_pool_count                     = 2
known_pool_full_addresses_from_v4    = [5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF, 9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad]
pool_snapshot_success_count          = 2
fee_snapshot_success_count           = 2
bin_liquidity_snapshot_success_count = 0
quote_snapshot_success_count         = 0
connector_readonly_ready             = true
quote_ready                          = false
survival_ev_ready                    = false
needs_paid_rpc                       = true
needs_known_pool_feed_expansion      = false
can_run_probe_now                    = false
solana_wallet_or_keypair_touched     = false
tiny_canary_allowed                  = "no"
edge_proven                          = "no"
v2_line_count_unchanged              = true (992)
```

## 3. V4 阻断与 V5 必须解决

| 阻断 | V4 状态 | V5 目标 |
|---|---|---|
| SDK getBinArrayForSwap 403 public RPC | V4 0/2 (multi-account via chunked) | V5 试 single-account `getAccountInfo` on derived bin array pubkey |
| SDK getBinArrayForSwap 410 mainnet-beta | V4 0/2 (same root) | V5 试 single-account fallback on mainnet-beta |
| quote depends on bin arrays | V4 0/4 | V5 试 1-3 account `getMultipleAccounts` if Stage E partial |
| bin_liquidity decode | V4 blocked | V5 试 SDK bin array decode (G) if Stage E/F succeeds |
| quote smoke | V4 blocked | V5 试 swapQuote (H) if Stage G succeeds |
| paid RPC requirement | V4 yes (claimed) | V5 single-account path 试一次后再判 (I) |

## 4. V5 目标 (来自 operator prompt)

1. **Stage C** — 审计 SDK helpers for bin array derivation (binIdToBinArrayIndex, deriveBinArray, getBinArrayForSwap, getBinArrays, getBinsAroundActiveBin)
2. **Stage D** — 推导 active + neighbor -1 / +1 bin array PDA for 2 known pools (no GPA)
3. **Stage E** — single-account getAccountInfo on each derived pubkey; document blockers
4. **Stage F** — small-batch getMultipleAccounts (1-3 accounts) if Stage E partial
5. **Stage G** — bin array decode via SDK if Stage E/F succeeds
6. **Stage H** — quote smoke v2 if Stage G succeeds
7. **Stage I** — paid_rpc_required decision (yes/no/partial) based on E/F/G/H
8. **Stage J** — next-stage decision
9. **Stage K** — final verdict
10. **Stage L** — tests + safety scan
11. **Stage M** — git publish

## 5. Known pool feed (full addresses from V4 artifact)

| pool_address | source | active_bin_id | bin_step |
|---|---|---|---|
| `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | swap_quote.ts | -12248 | 2 |
| `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | fetch_lb_pair_lock_info.ts | -236 | 100 |

## 6. 严格只读不变式（继承 + 本轮）

```text
can_run_probe_now                    = false
execution_allowed_now                = false
transaction_sent                     = false
wallet_or_tx_touched                 = false
solana_wallet_or_keypair_touched     = false
tiny_canary_allowed                  = "no"
edge_proven                          = "no"
manual_approval_required             = true
send_hard_disable_still_active       = true
v2_modified_by_this_task             = false
v2_line_count_unchanged              = true
```

本轮**不**改任何上述值；不读 keypair；不签名；不发 tx；不开 LP；不 swap；不 bridge；不 probe；不启动 live/canary/paper；不写 production positions；不修改 EVM executor v2；不释放 v2 hard-disable；不在 repo root 安装任何 npm package。

## 7. 决定

进入 Stage C — SDK bin array helper audit (在 /tmp 隔离 SDK env 检查 helper 可用性).
