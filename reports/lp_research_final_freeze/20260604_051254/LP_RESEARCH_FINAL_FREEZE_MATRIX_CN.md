# LP Research Final Freeze Matrix — Stage C

- stage: `LP_RESEARCH_FINAL_FREEZE_AND_HANDOFF_V1`
- run_id: `20260604_051254`
- matrix_version: `v1`
- freeze_date_utc: `2026-06-04T05:14:00Z`
- overall_recommendation: **`STOP_LP_RESEARCH_NOW`**

## 0. 矩阵覆盖范围 (7 research lines)

| # | research_line | chain | connector_status |
|---|---|---|---|
| 1 | EVM V3 scale economics | EVM (multi-chain) | not_run_in_phase |
| 2 | BSC PancakeSwap V3 | BSC | not_run_in_phase |
| 3 | Solana Meteora DLMM | Solana | **complete** |
| 4 | Solana Orca Whirlpools | Solana | **complete** |
| 5 | Solana Raydium CLMM | Solana | **complete** |
| 6 | Solana Raydium CPMM (AMM v4) | Solana | **complete** |
| 7 | Solana stable / LST-stable pools | Solana | **complete** |

## 1. 累计矩阵 (5 run protocols)

| research_line | pool_count | quote_ready | row_count | pos_zero_il | pos_opt | pos_real | pos_cons | best_ev | verdict |
|---|---|---|---|---|---|---|---|---|---|
| Meteora DLMM V8 | 56 | 27 | 4536 | 15 | 0 | 0 | 0 | +$0.544 | REJECT |
| Orca Whirlpools V1 | 75 | 10 | 1680 | 29 | 0 | 0 | 0 | +$0.106 | REJECT |
| Raydium CLMM V1 | 65 | 50 | 8400 | 480 | 0 | 0 | 0 | +$0.167 | REJECT |
| Raydium CPMM V1 (AMM v4) | 81 | 73 | 12264 | 1344 | 0 | 0 | 0 | +$0.172 | REJECT |
| **Solana stable V1** | 25 | 10 | 1680 | 30 | 0 | 0 | 0 | +$0.204 | **REJECT** |
| **summary** | | | **28560** | **1898** | **0** | **0** | **0** | all < $0.55 in zero_il_lvr | **5/5 reject** |

## 2. 详细 (per protocol)

### 2.1 Meteora DLMM V8 (20260604_021913)
- protocol: Meteora DLMM, Solana
- program_id: `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`
- pool_type: DLMM (V3-class, dynamic fee, IL binary)
- pool_count: 56 (SDK decode 100%, quote-ready 27)
- row_count: 4536 (56 × 6 × 7 × 4)
- best_pool: `CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa` (three/SOL)
- best_net_ev_proxy_usd: **+$0.544** (only in zero_il_lvr, 2000 USD, 7d)
- stop_reason: best cell $0.544 only in zero_il_lvr; realistic EV negative; 25-100bps dynamic fee not enough for retail

### 2.2 Orca Whirlpools V1 (20260604_025414)
- protocol: Orca Whirlpools, Solana
- program_id: `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`
- pool_type: V3 CL (gradual IL, lazy tick array)
- pool_count: 75 (SDK decode 100%, quote-ready 10, 14983 candidates from Orca official API)
- row_count: 1680
- best_pool: `C9U2Ksk6KKWvLEeo5yUQ7Xu46X7NzeBJtd9PBfuXaUSM` (SOL/Fartcoin)
- best_net_ev_proxy_usd: **+$0.106** (only in zero_il_lvr, 2000 USD, 7d)
- stop_reason: best cell $0.106 only in zero_il_lvr; tick array LAZY init makes quote collection difficult; 16bps fee not enough

### 2.3 Raydium CLMM V1 (20260604_034503)
- protocol: Raydium CLMM, Solana
- program_id: `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`
- pool_type: V3 CL (gradual IL, lazy tick array)
- pool_count: 65 (SDK decode 100%, quote-ready 50)
- row_count: 8400
- best_pool: `3nMFwZXwY1s1M5s8vYAHqd4wGs4iSxXE4LRoUMMYqEgF` (SOL/USDT)
- best_net_ev_proxy_usd: **+$0.167** (only in zero_il_lvr, 2000 USD, 7d)
- stop_reason: best cell $0.167 only in zero_il_lvr; V3 CL 25bps default not enough; tick arrays lazy init

### 2.4 Raydium CPMM V1 / AMM v4 (20260604_040952)
- protocol: Raydium AMM v4 (constant product), Solana
- program_id: `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` (the only deployed constant-product Raydium on mainnet; new "CPMM" cp-swap pid NOT on mainnet)
- pool_type: constant product (x*y=k, 100% IL on price change)
- pool_count: 81 (SDK decode 100%, quote-ready 73)
- row_count: 12264
- best_pool: `vs6XUbGcVWG75Gv81qvDMBxkQ67Kr2eLrFNDTrCxxwk` (YZai/SOL)
- best_net_ev_proxy_usd: **+$0.172** (only in zero_il_lvr, 2000 USD, 7d)
- stop_reason: best cell $0.172 only in zero_il_lvr; AMM v4 CPMM 100% IL on price change

### 2.5 Solana stable / LST-stable V1 (20260604_044118) — **FINAL STOP stage**
- protocols: Meteora Stable Swap (ex-Saber) + Orca Whirlpool stable LST
- program_ids: `SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ` (Meteora Stable Swap) + `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` (Meteora DAMM v2) + `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` (Orca)
- pool_type: Curve-style stable-stable + LST-stable
- pool_count: 25 (SDK decode 100%, quote-ready 10)
- row_count: 1680
- best_pool: `AiMZS5U3JMvpdvsr1KeaMiS354Z1DeSg5XjA4yYRxtFf` (mSOL/USDC)
- best_net_ev_proxy_usd: **+$0.204** (only in zero_il_lvr, 2000 USD, 7d)
- stop_reason: best cell $0.204 only in zero_il_lvr; Meteora DAMM v2 API mislabels Orca pools; no active stable-stable on mainnet

## 3. 2 protocols NOT in phase (out_of_scope)

### 3.1 EVM V3 scale economics
- chain: EVM (multi-chain)
- scope: V3 EVM scale economics connector (Uniswap V3 etc.) — not run in this LP research phase
- existing artifacts: scale_economics scripts/research notes in prior commits (e.g. `scripts/lp_*.py` history)

### 3.2 BSC PancakeSwap V3
- chain: BSC
- scope: PancakeSwap V3 QuoterV2 connector — not run in this LP research phase
- existing artifacts: BSC QuoterV2 fix documentation; not exercised in this phase

## 4. 累计总览

| 维度 | 值 |
|---|---|
| research_lines in matrix | 7 |
| research_lines run (5/5 reject) | 5 |
| research_lines not run in phase | 2 (EVM V3, BSC PancakeSwap) |
| total positive cells (any scenario, any protocol) | 0 |
| total best_ev (any protocol) | all < $0.55 in zero_il_lvr |
| all can_run_probe_now | false |
| all tiny_canary_allowed | no |
| all wallet_or_tx_touched | false |
| **overall_recommendation** | **`STOP_LP_RESEARCH_NOW`** |

## 5. frozen state (per spec)

```text
research_freeze_complete = true
edge_proven = no
can_run_probe_now = false
tiny_canary_allowed = no
positive_realistic_any_protocol = false
positive_optimistic_any_protocol = false
positive_conservative_any_protocol = false
zero_il_lvr_positive_only = true
reopen_conditions_documented = true (see Stage F)
docs_updated = true (see Stage H)
wallet_or_tx_touched = false
solana_wallet_or_keypair_touched = false
transaction_sent = false
recommended_next_stage = STOP_LP_RESEARCH_NOW
```

## 6. 下一阶段

进入 Stage D — WHY_STOP_LP_RESEARCH_NOW_CN.md (大白话解释 9 reasons)。
