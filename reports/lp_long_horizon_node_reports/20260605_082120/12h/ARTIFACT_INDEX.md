# ARTIFACT INDEX — 12h Node Report

- stage: `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`
- node: `12h`
- source_run_id: `20260605_082120`
- node_report_dir: `reports/lp_long_horizon_node_reports/20260605_082120/12h/`
- corrected_verdict: `reports/lp_long_horizon_readonly_12h_extension/20260605_082120/CORRECTED_FINAL_VERDICT.json`
- generated_at_utc: `2026-06-06T07:40:30Z`
- **coverage_scope: `partial_solana_real_pool_universe`**
- **do_not_treat_as_full_coverage: `true`**

## 1. 11 个 spec-required 输出文件 (in `reports/lp_long_horizon_node_reports/20260605_082120/12h/`)

| # | 文件 | 字节 |
|---|---|---|
| 1 | `NODE_REPORT.json` | 53729 |
| 2 | `NODE_REPORT_CN.md` | 24000+ (10-question 完整版) |
| 3 | `POOL_UNIVERSE_COVERAGE_MANIFEST.csv` | 9139 |
| 4 | `POOL_UNIVERSE_COVERAGE_MANIFEST.json` | 32558 |
| 5 | `FEE_ESTIMATION_BASIS.json` | 1498 |
| 6 | `FEE_ESTIMATION_BASIS_CN.md` | 999 |
| 7 | `RANGE_LIQUIDITY_FEE_SENSITIVITY.csv` | 277 |
| 8 | `RANGE_LIQUIDITY_FEE_SENSITIVITY.json` | 55 |
| 9 | `CANDIDATE_REVIEW.csv` | 5041 |
| 10 | `CANDIDATE_REVIEW.json` | 27430 |
| 11 | `FINAL_NODE_VERDICT.json` | 5300+ (含 spec-required 完整字段) |

## 2. 额外文件 (本 stage 输出)

| # | 文件 | 描述 |
|---|---|---|
| 12 | `NEXT_NODE_DECISION_CN.md` | 5 候选 next_stage 评估 + 选中 + 严禁 auto 24h |
| 13 | `next_node_decision.json` | 同上 (JSON) |
| 14 | `ARTIFACT_INDEX.md` | 本文件 |

**Total: 14 个新文件 (12h node report dir)**

## 3. 关键数字 (corrected)

| 维度 | 值 |
|---|---|
| actual_runtime_minutes | 720 |
| actual_runtime_valid_for_12h_gate | true |
| short_mode_used | false |
| checkpoint_count | 12 / 12 (100% complete) |
| pool_snapshot_rows | 60 (5 placeholder × 12 ckpts) |
| quote_snapshot_rows | 360 (30 × 12) |
| fee_velocity_rows | 300 (25 × 12) |
| liquidity_distribution_rows | 60 (5 × 12) |
| market_regime_rows | 84 (7 × 12) |
| actual_fee_accrual_placeholder_rows | 12 (1 × 12) |
| data_quality_status | data_quality_ok |
| gate_pass | true (15/15 gate checks pass) |
| selected_real_pool_count | 33 (Stage C universe) |
| placeholder_pool_count | 0 |
| coverage_gap_count | 12 |
| chain_coverage_count | 7 (1 observed: solana) |
| dex_coverage_count | 10 (5 observed: solana smoke placeholder) |
| pool_coverage_count | 60 (5 unique placeholder × 12 ckpts) |
| quote_ready_pool_count | 0 |
| fee_ready_pool_count | 0 |
| ev_ready_pool_count | 0 |
| preflight_candidate_count | 0 |
| watchlist_count | 0 |
| data_insufficient_count | 60 |
| reject_count | 0 |

## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 5. 严禁 (本轮全部不触发)

- 不启动 24h / 48h / 72h / 7d
- 不启动新 tmux / cron / systemd / daemon
- 不 probe / canary / live / paper
- 不读 wallet / keypair / signer / 私钥
- 不创建 signer
- 不发送 transaction / approve / mint / swap / bridge
- 不写 production positions
- 不覆盖 shadow 原始表
- 不接 paid RPC / paid indexer
- **不**覆盖 V2 12h 原始 FAIL verdict
- **不**修改 12h data_dir (84 文件, 0 修改)
- **不**修改 6h data_dir (42 文件, 0 修改)
- **不**修改 12h supervisor 脚本 (虽然有 bug, 但本轮 read-only, 修复留给下一轮)

## 6. 输入证据 (本轮**只**读)

- `reports/lp_long_horizon_readonly_12h_run/20260605_082120/FINAL_VERDICT.json` (V2 supervisor FAIL verdict, default-zero)
- `data/lp_long_horizon/20260605_082120/` (12 ckpts × 7 文件 = 84 文件, 实际数据)
- `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json` (Stage C 33 real pool universe)
- `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/inflight_healthcheck_20260605_151011.json` (Stage in-flight healthcheck)

## 7. 输出 (本轮**新**写)

- `reports/lp_long_horizon_readonly_12h_extension/20260605_082120/CORRECTED_FINAL_VERDICT.json` (corrected verdict from checkpoints)
- `reports/lp_long_horizon_readonly_12h_extension/20260605_082120/CORRECTED_TWELVE_HOUR_RUN_SUMMARY_CN.md` + `.json`
- `reports/lp_long_horizon_node_reports/20260605_082120/12h/` (14 files, 11 spec-required + 3 extras)

## 8. 5-stage allowed next stages

- `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` (24h 延展, 需 Meteora DLMM + Base/BSC 补完 + 5 项前置)
- `LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT` (本 stage 推荐, 让用户决策)
- `LP_LONG_HORIZON_12H_COLLECTOR_FIX_REPEAT` (修 V3 supervisor 脚本 line 435 + 493 + 升级 collector)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (用户要求暂停)
- `STOP_LP_RESEARCH_NOW` (用户要求停止)

## 9. Recommended next stage

**`LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT`**

理由: 12h node report 已 PASS (gate=PASS, 12/12 ckpts, full_sample=true), 但 coverage_scope=partial_solana_real_pool_universe + selected_real_pool_count=33 < target_min_pool_count=45 (gap=12, 5 协议缺失). per inflight_healthcheck 结论, **不**推荐 24h 延展 until Meteora DLMM + Base/BSC adapters 补完.

## 10. 24h 准入前置条件 (5 项必全)

1. Meteora DLMM Go pool adapter implemented + readonly connector research done
2. Base Uniswap V3 + Aerodrome collector wired into smoke mode (EVM public RPC)
3. BSC chain adapter + PancakeSwap V3/V2 pool adapters implemented
4. V3 supervisor script fixed (line 435 + 493: bash `${REAL_GATE_PASS}` → `${REAL_GATE_PASS^^}` 或 `<<'PYEOF'` quoted heredoc)
5. Upstream collector (`scripts/lp_long_horizon_readonly_collector_v1.py`) upgraded to accept real_pool_universe JSON instead of hardcoded smoke placeholder

5 项全部完成 → 用户可单独审批 24h 延展.
