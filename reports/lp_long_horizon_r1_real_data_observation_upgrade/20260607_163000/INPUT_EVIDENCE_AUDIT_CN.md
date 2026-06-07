# 输入证据审计 (Input Evidence Audit) — R1 Real-Data Observation Upgrade V1

- stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`
- run_id: `20260607_163000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:55:00Z`
- coverage_scope: `partial_solana_bsc_real_universe` (12h 实际观察范围)
- do_not_treat_as_full_universe: `true`
- r1_scope: real-time read-only data layer (6 dimensions non-zero, **不** mint / **不** freeze reopen / **不** actual fee)

## 0. 一句话

本 stage 把 long-horizon collector 从 R0 (proxy/placeholder, all zeros) 升级到 R1 (real-time read-only data layer, 6 dimensions 真实数据或诚实标记失败原因). R1 仅做 short smoke, **不** 启动 24h/48h/72h/7d, **不** mint/wallet/tx/probe, **不** 翻 freeze.

## 1. 审计对象 (输入文件清单)

| # | 类别 | 文件路径 | 状态 |
|---|---|---|---|
| 1 | 12h review FINAL_VERDICT | `reports/lp_long_horizon_partial_12h_node_report_review/20260606_131323/FINAL_VERDICT.json` | ✅ exist, status=PASS, recommended=R1 |
| 2 | R0 → R1 upgrade plan | `reports/lp_long_horizon_partial_12h_node_report_review/20260606_131323/R0_TO_R1_DATA_UPGRADE_PLAN_CN.md` | ✅ exist, 5+1+1 R1 objectives |
| 3 | 12h fee estimation review | `reports/lp_long_horizon_partial_12h_node_report_review/20260606_131323/FEE_ESTIMATION_REVIEW_CN.md` | ✅ exist, 5 missing field groups |
| 4 | 12h candidate review audit | `reports/lp_long_horizon_partial_12h_node_report_review/20260606_131323/CANDIDATE_REVIEW_AUDIT_CN.md` | ✅ exist, 53/53 data_insufficient |
| 5 | 12h coverage manifest | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/coverage_manifest.json` | ✅ exist, 2/3 chain |
| 6 | 12h fee estimation basis | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/fee_estimation_basis.json` | ✅ exist, r0 phase |
| 7 | 12h candidate review | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/candidate_review.json` | ✅ exist, preflight=0 |
| 8 | RPC reachability + adapter smoke | `reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/FINAL_VERDICT.json` | ✅ exist, rpc_registry_ready=true |
| 9 | 72-pool expanded universe | `reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/expanded_real_pool_universe_for_12h_retry.json` | ✅ exist, 72 pools |
| 10 | R0 collector (35KB) | `scripts/lp_long_horizon_readonly_collector_v1.py` | ✅ exist, 801 lines |
| 11 | Adapters dir (8 files) | `scripts/lp_long_horizon/adapters/` | ✅ exist |

## 2. 12h gate 关键字段 (per prior FINAL_VERDICT)

```json
{
  "twelve_hour_pipeline_passed": true,
  "actual_runtime_minutes": 720,
  "data_quality_status": "PASS",
  "error_rate_pct": 0.0,
  "checkpoint_count": 12,
  "selected_pool_count": 53,
  "placeholder_pool_count": 0,
  "coverage_scope": "partial_solana_bsc_real_universe",
  "full_coverage_ready": false,
  "lp_edge_proven": false,
  "global_lp_rejected": false,
  "actual_fee_data_available": false,
  "fee_proxy_only": true,
  "candidate_decision_reliable": false,
  "preflight_candidate_count": 0,
  "watchlist_count": 0,
  "data_insufficient_count": 53,
  "ev_ready_pool_count": 0,
  "r1_upgrade_required": true,
  "can_run_probe_now": false,
  "tiny_canary_allowed": "no",
  "edge_proven": "no",
  "wallet_or_tx_touched": false,
  "transaction_sent": false
}
```

## 3. R0 → R1 关键判断 (per prior R0_TO_R1_DATA_UPGRADE_PLAN)

| R0 短板 | R1 升级 |
|---|---|
| pool_snapshots reserve_a/b/liquidity/active_tick = 0/null | R1 走 live RPC 拿真实 on-chain reserve/liquidity/tick/bin |
| quote_snapshots amount_in/out/price_impact/slippage/fee = 0 | R1 走 QuoterV2 staticcall / Whirlpool quote_swap |
| fee_velocity volume_proxy/fee_capture/sample_count = 0 | R1 用 DexScreener / on-chain swap event |
| liquidity_distribution active_range/near_active = 0 | R1 跨 tickLower/tickUpper 累积 liquidity 分布 |
| market_regime price_change/realized_vol = 0 | R1 集成 Pyth/CoinGecko 7d sliding window |
| actual_fee_accrual token_id / fee_growth / tokens_owed = null | R1 **不** mint / **不** actual tokenId, schema 维持 placeholder |

## 4. R1 必须确认 (per spec)

- ✅ R0 12h pipeline passed (720 min, error 0%, data_quality PASS)
- ✅ R0 actual_fee_data_available = false
- ✅ R0 fee_proxy_only = true
- ✅ R0 data_insufficient_count = 53 (100%)
- ✅ R1 required (per recommended_next_stage)
- ✅ 本轮**只**做 R1 data layer (6 dimensions), **不** 启动 long-run

## 5. R1 不做 (per spec hard prohibition)

- ❌ 不 mint LP NFT
- ❌ 不产生 tokenId
- ❌ 不 actual position fee accrual
- ❌ 不 collect fee
- ❌ 不 live / canary / paper / probe
- ❌ 不 freeze reopen
- ❌ 不翻 can_run_probe_now (维持 false)
- ❌ 不翻 tiny_canary_allowed (维持 "no")
- ❌ 不翻 edge_proven (维持 "no")

## 6. R1 6 dimensions (per spec)

1. **real pool snapshot** (live RPC reserve/liquidity/tick/bin)
2. **real quote snapshot** (QuoterV2 staticcall / Whirlpool quote_swap)
3. **real fee velocity proxy** (DexScreener / on-chain swap event)
4. **real volume source** (5 windows: 15m/1h/4h/24h/7d)
5. **real range / tick / bin / liquidity distribution** (ticks(net) bitmap / bin_array)
6. **market regime classification** (Pyth/CoinGecko 7d sliding window)

## 7. R1 启动范围

- **R1 collector**: 新文件 `scripts/lp_long_horizon_r1_real_data_collector_v1.py`
- **R1 data layer**: r1_pool_snapshot / r1_quote_snapshot / r1_fee_velocity / r1_liquidity_distribution / r1_market_regime / r1_candidate_review
- **R1 smoke**: max_pools=20, max_snapshots=1, no-daemon, 短跑 (~2-3min), **不** 24h
- **R1 data dir**: `data/lp_long_horizon_r1_smoke/20260607_163000/`
- **R1 reports**: `reports/lp_long_horizon_r1_real_data_observation_upgrade/20260607_163000/`

## 8. 严禁 (本 R1 stage 期间)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不启动 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction
- ❌ 不 approve / mint / add-liquidity / remove-liquidity / collect / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ 不写真实 secret
- ❌ can_run_probe_now 维持 false
- ❌ tiny_canary_allowed 维持 "no"
- ❌ edge_proven 维持 "no"
- ❌ 不**修改** 12h data dir (20260606_131323)
- ❌ 不**修改** 12h review reports (20260606_131323/...)
- ❌ 不**修改** R0 collector (lp_long_horizon_readonly_collector_v1.py)

## 9. input_evidence_audit_decision

**decision: PROCEED_TO_R1_BUILD**

R0 evidence 全部 audit pass, R1 upgrade required, R1 scope 明确, hard prohibition 全部 clear, R1 启动条件满足. 进入 R1 schema + architecture + collector + smoke 阶段.
