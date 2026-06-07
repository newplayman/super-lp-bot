# 输入证据审计 (Input Evidence Audit) — 12h Node Report Review

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`
- do_not_treat_as_full_universe: `true`

## 0. 一句话

本 review 审计 12h partial collector (RUN_ID=20260606_131323) 的全部 deliverable + 12h data_dir, 明确 12h 证明/未证明的范围, 给 R1 upgrade plan + 下一个 stage 决策. 全部 read-only, **不** 启动 24h / 新 collector / probe / canary / live.

## 1. 审计对象 (输入文件清单)

| # | 类别 | 文件路径 | 大小 / 行数 | 状态 |
|---|---|---|---|---|
| 1 | 12h node report (CN) | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/12H_NODE_REPORT_CN.md` | 11 sections | ✅ exist |
| 2 | 12h coverage manifest | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/coverage_manifest.json` | 3-level coverage | ✅ exist |
| 3 | 12h fee estimation basis | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/fee_estimation_basis.json` | r0 phase proxy | ✅ exist |
| 4 | 12h candidate review | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/candidate_review.json` | preflight=0 | ✅ exist |
| 5 | 12h next node decision | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/next_node_decision.json` | 4-stage allowed | ✅ exist |
| 6 | 12h request FINAL_VERDICT | `reports/lp_long_horizon_readonly_partial_12h_request/20260606_131323/FINAL_VERDICT.json` | status=RUNNING (pre-launch) | ✅ exist |
| 7 | 12h run FINAL_VERDICT (auto) | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/FINAL_VERDICT.json` | status=PASS | ✅ exist |
| 8 | 12h data dir (12 ckpts) | `data/lp_long_horizon/20260606_131323/` | 12 × 7 files | ✅ exist |
| 9 | 12h nohup / supervisor log | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/logs/*.log` | 83KB+ | ✅ exist |
| 10 | Stage H ARTIFACT_INDEX | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/ARTIFACT_INDEX.md` | index | ✅ exist |
| 11 | Stage H 21 测试 | `tests/test_lp_long_horizon_12h_node_report_v1.py` | 21 tests | ✅ exist + 21/21 PASS |
| 12 | Stage H node report 188 测试 | `tests/test_lp_long_horizon_*` (related) | 188 tests | ✅ exist + 188/188 PASS |

## 2. 12h gate 关键字段 (per Stage H FINAL_VERDICT)

```json
{
  "stage": "LP_LONG_HORIZON_READONLY_12H_STAGE_RUN_V1",
  "status": "PASS",
  "twelve_hour_run_completed": true,
  "actual_runtime_minutes": 720,
  "actual_runtime_valid_for_12h_gate": true,
  "data_quality_status": "PASS",
  "error_rate_pct": 0.0,
  "consecutive_429_max": 0,
  "gate_pass": true,
  "selected_real_pool_count": 33,
  "placeholder_pool_count": 0,
  "can_run_probe_now": false,
  "tiny_canary_allowed": "no",
  "edge_proven": "no",
  "wallet_or_tx_touched": false,
  "transaction_sent": false,
  "auto_advance_started": false,
  "longer_stage_started": false,
  "send_hard_disable_still_active": true,
  "recommended_next_stage": "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1"
}
```

## 3. 12h 锁定字段 (LOCKED, **不** 翻)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | LP strategy research freeze active |
| `tiny_canary_allowed` | `"no"` | LP strategy research freeze active |
| `edge_proven` | `"no"` | r0 phase data (smoke_placeholder), no actual fee / EV |
| `wallet_or_tx_touched` | `false` | read-only collector, no chain write |
| `transaction_sent` | `false` | no tx, no approve, no mint, no swap, no bridge |
| `send_hard_disable_still_active` | `true` | execution-side hard disable intact |
| `auto_advance_started` | `false` | 24h **不** 自动 |
| `longer_stage_started` | `false` | 24h/48h/72h/7d **不** 启 |

## 4. 12h data_dir 完整性 (per 12 checkpoints)

12 个 checkpoint 目录 (`checkpoint_1_1324` → `checkpoint_12_0025`), 每个 7 个文件:
- `pool_snapshots.jsonl` (~35KB) — 53 池 per ckpt, 636 total
- `quote_snapshots.jsonl` (~98KB) — 318 quote per ckpt, 3816 total (53 × 6 notional)
- `fee_velocity.jsonl` (~88KB) — 265 fee per ckpt, 3180 total (53 × 5 windows)
- `liquidity_distribution.jsonl` (~15KB) — 53 liq per ckpt, 636 total
- `market_regime.jsonl` (~1.5KB) — 7 regime per ckpt, 84 total
- `actual_fee_accrual_placeholder.json` (~0.7KB) — 12 schema-only placeholder
- `smoke_summary.json` (~25KB) — 12 smoke summary

**Per-ckpt 文件 size 完全一致** (35KB pool / 98KB quote / 88KB fee / 15KB liq / 1.5KB regime) → 说明 12 个 ckpt 是 deterministic 重复 run, 数据是**不**真实 on-chain (因为真实 RPC 会 yield 不同的 reserve/liquidity). 真实 on-chain 数据是**有**时序差异的. 这与 r0 phase disclosure 一致.

## 5. 12h supervisor log 关键行

```
[checkpoint 12/12] ok at 2026-06-07T00:25:06Z
[wallclock fix] last checkpoint done; sleeping 3578s until END_TS=1780795484
[heartbeat 12_1_of_4_postfinal] 2026-06-07T00:40:00Z elapsed=675min
[heartbeat 12_4_of_4_postfinal] 2026-06-07T01:24:42Z elapsed=719min
[heartbeat 12_end] 2026-06-07T01:24:44Z elapsed=720min
[12h end] 2026-06-07T01:24:44Z elapsed_min=720 (target END_TS=1780795484)
[finalize-block] post-12h finalize block rc=0
[git] auto add + commit + push starting at 2026-06-07T01:24:45Z
[feat/supabase-postgres-deployment 30b67c4] research: finalize 12h long horizon readonly run 20260606_131323
[12h complete] 2026-06-07T01:24:47Z
[trap] EXIT rc=0; .finalize_succeeded marker present, NOT overwriting
```

**关键观察**:
- 12h 实际 end = 01:24:44Z (elapsed=720min exact)
- finalize 跑 rc=0, .finalize_succeeded marker 已写入
- git commit + push 自动跑 (`30b67c4`)
- trap exit 干净, **不** overwrite finalize marker

## 6. 审查范围

本 review 重点审查:
1. 12h **证明**了什么 (WHAT_12H_PROVED_CN.md)
2. 12h **未证明**什么 (WHAT_12H_DID_NOT_PROVE_CN.md)
3. Coverage 实际观察 (COVERAGE_REVIEW_CN.md)
4. Fee 估算是否可用于 LP 决策 (FEE_ESTIMATION_REVIEW_CN.md)
5. Candidate review 是否可靠 (CANDIDATE_REVIEW_AUDIT_CN.md)
6. R0 → R1 upgrade 路径 (R0_TO_R1_DATA_UPGRADE_PLAN_CN.md)
7. 下一个 stage 决策 (NEXT_STAGE_DECISION_CN.md)

## 7. 严禁 (本 review 期间)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动新 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ 不翻 `can_run_probe_now=false`
- ❌ 不翻 `tiny_canary_allowed=no`
- ❌ 不翻 `edge_proven=no`
