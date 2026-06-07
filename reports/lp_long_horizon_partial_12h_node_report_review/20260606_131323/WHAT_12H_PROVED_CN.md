# 12h 证明了什么 (What 12h Proved) — 12h Node Report Review

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`

## 0. 一句话

12h 跑通验证了 **collector pipeline 端到端稳定性** + **adapter wiring 稳定性** + **checkpoint/heartbeat/finalize scheduling 稳定性** + **data quality flag 正确性** + **safety invariants preserved**. 这是 r0 phase 全部目标, 已全部完成. **不** 验证 LP edge / actual fee / 真实 range-tick-bin coverage.

## 1. 12h 证明了什么 (8 项)

### 1.1 ✅ collector 可稳定运行 12h (720 min exact)

- 实际 runtime: **720 min** (12h × 60min, exact)
- gate valid: `actual_runtime_minutes=720 >= 660` (gate threshold)
- 12/12 checkpoint **完整** 写出 (1_1324 → 12_0025)
- 12h 内 stage runner **无** 异常退出
- nohup detached launch 干净, pid 3871101 跑 12h 后正常 exit (no crash)
- 12h end timestamp 精确到 2026-06-07T01:24:44Z (与 END_TS=1780795484 对齐)

### 1.2 ✅ checkpoint / heartbeat / finalize scheduling 可用

- 12 个 checkpoint 每个 7 个文件 (pool/quote/fee/liq/regime/fee_placeholder/smoke_summary) **完整** 写出
- 12 × 4 = 48 个 sub-heartbeat (12_1_of_4 到 12_4_of_4_postfinal × 12 ckpt) + 12_end heartbeat 全部 update
- finalize block auto-run (rc=0), .finalize_succeeded marker 写入, FINAL_VERDICT.json 写入
- git auto-commit + push 跑通 (`30b67c4`)
- trap exit 干净, **不** overwrite finalize marker
- wallclock fix sleeping 3578s until END_TS=1780795484 正确

### 1.3 ✅ real pool address universe 可进入 pipeline

- 53 个 real on-chain pool address (Solana 49 + BSC V3 4) 全部 loaded 进 collector
- placeholder_pool_count = **0** (no fake pool address)
- all_pools_are_real_on_chain = **true** (per smoke_summary.json ckpt 1-12)
- pool 跨 5 protocols (orca_whirlpool / raydium_clmm / raydium_cpmm / meteora_dlmm / pancakeswap_v3)
- pool 跨 2 chains (solana + bsc) — Base 不可达已 honest disclosed
- pool_snapshots.jsonl 每 ckpt 53 行 (= 53 unique pool, deterministic)

### 1.4 ✅ no wallet / tx / probe safety preserved

- wallet_or_tx_touched = **false** (LOCKED in FINAL_VERDICT)
- transaction_sent = **false** (LOCKED)
- send_hard_disable_still_active = **true**
- 12h 期间 **无** eth_sendRawTransaction / eth_sendTransaction / solana_sendTransaction 调用
- 12h 期间 **无** wallet / keypair / signer / seed 读取
- 12h 期间 **无** approve / mint / swap / bridge 触发
- 12h 期间 **无** production position 写入
- 12h 期间 **不** 覆盖 shadow 原始表
- 12h 期间 **不** 接 paid RPC / paid indexer

### 1.5 ✅ 12h data pipeline stability PASS

- error_rate_pct = **0.0%** (no error during 12h)
- consecutive_429_max = **0** (no rate-limit, RPC quota 充足)
- data_quality_status = **PASS**
- gate_pass = **true**
- per-ckpt 文件 size **完全一致** (35KB pool / 98KB quote / 88KB fee / 15KB liq / 1.5KB regime) → pipeline deterministic 重复 run, no mid-run crash
- 12 个 smoke_summary.json 全部 selected_real_pool_count=53 + placeholder_pool_count=0 + all_pools_are_real_on_chain=true

### 1.6 ✅ r0 phase smoke_placeholder data layer 透明

- pool_snapshots.jsonl: real on-chain address + tvl_proxy_usd + vol24h_proxy_usd 来自 prior stage CSV (orca/raydium/raydium_cpmm/meteora/pancakeswap_v3 connector), 但 reserve_a_raw=0, reserve_b_raw=0, liquidity=0
- quote_snapshots.jsonl: smoke_placeholder=true, amount_in_raw=0, amount_out_raw=0 (proxy mode disclosed)
- fee_velocity.jsonl: smoke_placeholder=true, sample_count=0 (proxy mode disclosed)
- liquidity_distribution.jsonl: smoke_placeholder=true, active_range_liquidity=0 (proxy mode disclosed)
- market_regime.jsonl: smoke_placeholder=true, price_change_pct=0, realized_vol_pct=0 (regime label 静态分类)
- actual_fee_accrual_placeholder.json: schema only, all null, r1 requires user-provided tokenId
- **所有** 数据层 honest 标记 smoke_placeholder, r0_phase_status 字段 disclosed

### 1.7 ✅ auto_advance LOCKED 验证

- auto_advance_started = **false** (12h 跑完后 **不** 自动 24h)
- longer_stage_started = **false** (24h/48h/72h/7d **不** 启)
- can_advance_to_next = **false** (FINAL_VERDICT explicit)
- finalize 写 recommended_next_stage = `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` 是 **suggestion**, **不** 等同 auto-advance (per next_node_decision)
- 12h 期间 stage runner **不** 启 24h collector / parallel collector / daemon

### 1.8 ✅ finalize block 透明 + git automation OK

- .finalize_succeeded marker 写入 (size 0, time 2026-06-07T03:24Z)
- FINAL_VERDICT.json 写入 (size 1296 bytes)
- aggregate_summary.json 写入 (12 ckpt, deduped row counts)
- git auto-commit 干净 (`30b67c4 research: finalize 12h long horizon readonly run 20260606_131323`)
- git push 干净 (c3932db..30b67c4 → origin/feat/supabase-postgres-deployment)
- supervisor.log 83KB 完整记录
- nohup.log 83KB 完整记录

## 2. 12h 证明的"价值"

12h 跑通给我们的是 **r0 → r1 readiness 基础**:
- pipeline 不会再 crash
- adapter 不会再 missing
- checkpoint 不会再 skip
- finalize 不会再失败
- safety invariant 不会再被破坏

这些是 **engineering stability**, **不** 是 **edge proven**.

## 3. 重要 disclaimer

12h 跑通**不**等于:
- ❌ 不等于 LP edge proven (`edge_proven` 仍 `"no"`)
- ❌ 不等于 12h 数据是 actual fee data (smoke_placeholder)
- ❌ 不等于可进入 probe (`can_run_probe_now` 仍 `false`)
- ❌ 不等于可进入 canary (`tiny_canary_allowed` 仍 `"no"`)
- ❌ 不等于可进入 live (live mode hard-disabled)
- ❌ 不等于可进入 paper (paper mode not in spec)
- ❌ 不等于 24h 跑通会有 actual fee (同样的 r0 proxy, 24h 不会变)
- ❌ 不等于 53 池都值得参与 (preflight_candidate_count=0)

## 4. 12h 锁定字段 (LOCKED, 12h 后维持)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | r0 phase + freeze active |
| `tiny_canary_allowed` | `"no"` | r0 phase + freeze active |
| `edge_proven` | `"no"` | r0 phase data (smoke_placeholder) |
| `wallet_or_tx_touched` | `false` | read-only collector |
| `transaction_sent` | `false` | no tx |
| `send_hard_disable_still_active` | `true` | hard disable intact |
| `auto_advance_started` | `false` | 24h **不** 自动 |
| `longer_stage_started` | `false` | 24h/48h/72h/7d **不** 启 |
