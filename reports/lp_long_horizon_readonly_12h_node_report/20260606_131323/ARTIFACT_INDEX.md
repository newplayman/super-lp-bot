# ARTIFACT INDEX — 12h Readonly Continuous Observation Node Report V1

- stage: `LP_LONG_HORIZON_READONLY_12H_STAGE_RUN_V1` (Stage H auto-finalize)
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- 12h status: **PASS** (gate PASS, 12/12 checkpoints ok, error_rate=0.0%)
- coverage_scope: `partial_solana_bsc_real_universe`
- generated_at_utc: `2026-06-07T16:20:00Z`

## 1. Output files (in `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `12H_NODE_REPORT_CN.md` | 12h node report (中文) — 时间线 / 池分布 / 数据质量 / locked fields / 4-stage allowed next stages |
| 2 | `coverage_manifest.json` | 3-level coverage manifest (chain/dex/pool) + smoke_placeholder data fields + r0_phase_disclosure |
| 3 | `fee_estimation_basis.json` | r0 phase fee estimation basis (proxy mode, all 0) + r1_blockers list + honest_caveat |
| 4 | `candidate_review.json` | r0 phase candidate review (preflight_candidate_count=0, tier_classifier=DEFERRED_TO_R1) |
| 5 | `next_node_decision.json` | 4-stage allowed next stages with rationale + user_decision_required_for_24h + key_questions |
| 6 | `ARTIFACT_INDEX.md` | 本文件 |

## 2. Auto-finalize 12h outputs (in `reports/lp_long_horizon_readonly_12h_run/20260606_131323/`)

| File | 描述 |
|---|---|
| `.finalize_succeeded` | finalize 成功 marker (0 bytes) |
| `FINAL_VERDICT.json` | 12h gate verdict (status=PASS, runtime=720, gate_pass=true) |
| `logs/aggregate_summary.json` | 12h aggregate (12 ckpt, 53 pool, 3816 quote, 3180 fee, 636 liq, 84 regime) |
| `logs/supervisor.log` | 12h supervisor log (12 checkpoint 记录 + 12h end + finalize block) |
| `logs/nohup.log` | nohup detached log |
| `logs/heartbeat/` | per-ckpt heartbeat (12 ckpt × 4 sub-heartbeat + 12_end) |
| `logs/checkpoint/` | per-ckpt log |

## 3. 12h raw data (in `data/lp_long_horizon/20260606_131323/`)

| Dir | 描述 |
|---|---|
| `checkpoint_1_1324/` | ckpt 1 (smoke): pool_snapshots.jsonl, quote_snapshots.jsonl (318), fee_velocity.jsonl (265), liquidity_distribution.jsonl (53), market_regime.jsonl (7), actual_fee_accrual_placeholder.json, smoke_summary.json |
| `checkpoint_2_1424/` | ckpt 2 |
| ... | ... |
| `checkpoint_12_0025/` | ckpt 12 (final): same structure as ckpt 1 |
| `logs/supervisor.log` | 12h supervisor log (per-ckpt heartbeat + checkpoint ok) |

## 4. Stage H deliverables checklist

| Deliverable | Path | Status |
|---|---|---|
| FINAL_VERDICT.json (12h finalize) | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/FINAL_VERDICT.json` | ✅ done (auto by stage runner) |
| 12h node report (中文) | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/12H_NODE_REPORT_CN.md` | ✅ done (this stage) |
| coverage_manifest.json | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/coverage_manifest.json` | ✅ done |
| fee_estimation_basis.json | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/fee_estimation_basis.json` | ✅ done |
| candidate_review.json | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/candidate_review.json` | ✅ done |
| next_node_decision.json | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/next_node_decision.json` | ✅ done |
| ARTIFACT_INDEX.md | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/ARTIFACT_INDEX.md` | ✅ done |

## 5. Locked fields (12h finalize + node report 期间)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `send_hard_disable_still_active` | `true` |
| `auto_advance_to_next` | `false` |
| `longer_stage_started` | `false` |
| `auto_advance_started` | `false` |
| `can_advance_to_next` | `false` (FINAL_VERDICT explicit) |
| `data_quality_status` | `PASS` |
| `gate_pass` | `true` |

## 6. 12h 时间表 (Stage H finalize 详情)

| 阶段 | 时间 (UTC) | 状态 |
|---|---|---|
| launched (nohup, pid 3871101) | 2026-06-06T13:24:00Z | ✅ done |
| checkpoint 1/12 | 2026-06-06T13:24:45Z | ✅ done |
| checkpoint 12/12 (final) | 2026-06-07T00:25:06Z | ✅ done |
| 12h end (elapsed=720min) | 2026-06-07T01:24:44Z | ✅ done |
| finalize-block (auto) | 2026-06-07T03:24:xxZ | ✅ done (rc=0) |
| git commit + push | 2026-06-07T01:24:45Z | ✅ done (`30b67c4`) |
| Stage H deliverables (this stage) | 2026-06-07T16:20:00Z | ✅ done |

## 7. 4-stage allowed next stages (per finalize + next_node_decision)

1. `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` (24h extension, 需 user 重新审批)
2. `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1` (review 12h node report, read-only)
3. `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` (Base RPC fix, 需换 env)
4. `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (暂停)

**绝对禁止** (per LP strategy research freeze): probe / canary / live / paper / wallet / tx / auto-24h / 24h-without-new-approval.

## 8. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1` | done | supervisor finalize 4 Python heredoc lowercase bool bug |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` | done | universe 33 → 72 (8 protocols, 3 chains); 23 池 not observable |
| `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` | done | 4 EVM/BSC adapter + 1 Meteora verify |
| `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1` | done | rpc_registry.py + 13 → 49 observable; Base 不可达 |
| `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1` | done | 启动 12h partial (53 池) via nohup; checkpoint 1/12 ok |
| `LP_LONG_HORIZON_READONLY_12H_STAGE_RUN_V1` (Stage H auto) | done | 12h 跑通, 12/12 ok, gate PASS, finalize PASS |
| **`LP_LONG_HORIZON_READONLY_12H_NODE_REPORT_REVIEW_V1`** (this stage, 写 node report + 4 deliverable) | **done** | **12h node report + coverage_manifest + fee_estimation_basis + candidate_review + next_node_decision 全部写完** |
| 下一 stage (user decide) | pending | 4 allowed next stages (per §7) |
