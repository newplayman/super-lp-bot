# Input Evidence Audit — Stage B

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`
- branch: `feat/supabase-postgres-deployment`
- head_before: `404ddd1`

## 0. 审计结论

```text
previous_stage             = LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1
previous_status            = WARN
previous_run_id            = 20260603_190910
previous_commit            = 404ddd1
recommended_next_stage_prev = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1
this_stage_target          = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1
scope_target               = 20-50 Meteora DLMM candidate pools
verify_target              = >= 10 verified (owner = Meteora DLMM program)
decode_target              = >= 10 SDK decode success
quote_target               = >= 5 quote-ready pools
can_run_probe_now          = false (LOCKED; per spec this stage is NOT probe)
tiny_canary_allowed        = "no" (LOCKED)
```

## 1. 上游文件审计 (8 files, all present)

| # | file | 用途 | 状态 |
|---|---|---|---|
| 1 | `reports/lp_meteora_dlmm_survival_ev_preview/20260603_190910/FINAL_VERDICT.json` | prior stage final verdict | OK |
| 2 | `reports/lp_meteora_dlmm_survival_ev_preview/20260603_190910/ONEPAGE_CN.md` | one-page summary | OK |
| 3 | `reports/lp_meteora_dlmm_survival_ev_preview/20260603_190910/METEORA_SURVIVAL_EV_PREVIEW_CN.md` | 168 EV cells | OK |
| 4 | `reports/lp_meteora_dlmm_survival_ev_preview/20260603_190910/meteora_survival_ev_preview.csv` | 168 EV rows | OK |
| 5 | `reports/lp_meteora_dlmm_quote_binarray_coverage_expand_v2/20260603_150331/FINAL_VERDICT.json` | V7 final | OK |
| 6 | `reports/lp_meteora_dlmm_known_pool_connector/20260603_134202/FINAL_VERDICT.json` | V4 final | OK |
| 7 | `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/FINAL_VERDICT.json` | V3 feasibility | OK |
| 8 | `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/FINAL_VERDICT.json` | Solana RPC registry | OK |

## 2. Key carry-over findings

### 2.1 From prior survival EV preview (20260603_190910, commit 404ddd1)

- 168 EV cells computed for X/USDC (partial scope).
- 0/168 cells positive (all scenarios).
- best_net_ev_proxy_usd = -0.154 (2000 notional + 15m + zero_il_lvr).
- recommended_next_stage = `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1`.
- structural finding: X/USDC at retail scale is unprofitable; need to find other pools.

### 2.2 From V7 coverage expand v2 (20260603_150331, commit 3c72d3f)

- spec hard cap of 15 arrays; pool 1 (SOL/USDC) still 0 bins with liquidity.
- per spec: "if 15 arrays 仍失败, 必须停止并推荐 paid RPC 或 pool2-only survival EV preview; 不得无限扩展".
- This stage accepts partial scope and **expands feed** instead of expanding single-pool coverage further.

### 2.3 From V4 known pool connector (20260603_134202)

- 2/2 known pools decode (SOL/USDC + X/USDC).
- SDK @meteora-ag/dlmm v1.9.10.
- pool/fee snapshot 2/2 success.

### 2.4 From V3 SDK feasibility (20260603_130532)

- SDK path identified.
- 0/4 quote at V3 (multi-account blocked); later fixed in V5–V7.

### 2.5 From Solana RPC registry (20260603_102657)

- public RPC registered; primary=publicnode, fallback=mainnet-beta.

## 3. This stage objectives

- collect 20–50 Meteora DLMM candidate pools (from official/SDK + DexScreener/GeckoTerminal)
- chain-verify each candidate (owner = Meteora DLMM program `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`)
- SDK decode verified pools (active bin, fee, reserves, token mints)
- bin array read/decode (5 / 9 / 15 arrays; single-account path)
- quote 10U/20U/100U per pool
- score quote-ready pools (fee / liquidity / risk)
- survival EV preview for quote-ready pools
- decide if any pool is worth 10/20U preflight design
- NOT probe; NOT wallet; NOT transaction

## 4. This stage does NOT (硬边界)

- read Solana private key / seed phrase / keypair
- instantiate signer / wallet adapter
- construct any transaction
- call sendTransaction / sendRawTransaction
- call swap transaction builder
- call open_lp / close_lp / collect_fee / addLiquidity / removeLiquidity
- call bridge
- start live / canary / paper
- write production positions
- overwrite shadow tables
- modify EVM executor v2
- release v2 hard-disable
- set can_run_probe_now = true
- set tiny_canary_allowed = yes
- hard-code any program id from model memory (program id is constant `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` from public Solana metadata, NOT from model memory)
- fabricate pool addresses / fee data / quote data

## 5. Safety locks intact

```text
can_run_probe_now                  = false
execution_allowed_now              = false
transaction_sent                   = false
wallet_or_tx_touched               = false
solana_wallet_or_keypair_touched   = false
tiny_canary_allowed                = "no"
edge_proven                        = "no"
manual_approval_required           = true
send_hard_disable_still_active     = true
v2_modified_by_this_task           = false
v2_line_count_unchanged            = true (992)
```

## 6. 下一阶段

进入 Stage C — overnight runner bootstrap (tmux session + smoke check).
