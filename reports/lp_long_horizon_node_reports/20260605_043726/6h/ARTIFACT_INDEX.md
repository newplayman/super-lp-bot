# ARTIFACT INDEX — 6h Node Report

- stage: `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`
- node: `6h`
- source_run_id: `20260605_043726`
- node_report_dir: `reports/lp_long_horizon_node_reports/20260605_043726/6h/`
- generated_at_utc: `2026-06-05T13:10:51Z`

## 1. 11 个文件 (per `node_report_schema_v1`)

| # | 文件 | 描述 | 状态 |
|---|---|---|---|
| 1 | `NODE_REPORT_CN.md` | 完整 10-question CN 报告 (chains / DEX / pools / missing / ready counts / preflight / fee proxy / range sensitivity / 12h / probe forbidden) | ✅ |
| 2 | `NODE_REPORT.json` | 完整 JSON node report (31KB) | ✅ |
| 3 | `POOL_UNIVERSE_COVERAGE_MANIFEST.csv` | 3 层覆盖范围 (chain/dex/pool), 19 行 | ✅ |
| 4 | `POOL_UNIVERSE_COVERAGE_MANIFEST.json` | 同上 (JSON, 19KB) | ✅ |
| 5 | `FEE_ESTIMATION_BASIS.json` | 5 pool type fee proxy 公式 | ✅ |
| 6 | `FEE_ESTIMATION_BASIS_CN.md` | 同上 (CN markdown) | ✅ |
| 7 | `RANGE_LIQUIDITY_FEE_SENSITIVITY.csv` | 4 pool type × 3 range 表格 (本轮 0 行, 因无 candidate) | ✅ |
| 8 | `RANGE_LIQUIDITY_FEE_SENSITIVITY.json` | 同上 (JSON) | ✅ |
| 9 | `CANDIDATE_REVIEW.csv` | best + rejected candidates (本轮 0 best, 30 rejected) | ✅ |
| 10 | `CANDIDATE_REVIEW.json` | 同上 (JSON, 13KB) | ✅ |
| 11 | `FINAL_NODE_VERDICT.json` | 节点最终 verdict (PASS, data_quality_ok, full_sample=true) | ✅ |

## 2. 额外文件 (本轮 Stage A→G 输出)

| # | 文件 | 描述 | 状态 |
|---|---|---|---|
| 12 | `NEXT_NODE_DECISION_CN.md` | 5 候选 next_stage 评估 + 选中 + 严禁自动启动 12h | ✅ |
| 13 | `next_node_decision.json` | 同上 (JSON) | ✅ |
| 14 | `ARTIFACT_INDEX.md` | 本文件 | ✅ |

**Total: 14 个新文件** (in `reports/lp_long_horizon_node_reports/20260605_043726/6h/`)

## 3. 关键数字

| 维度 | 数量 |
|---|---|
| checkpoint_count_observed | 6 |
| checkpoint_count_expected | 6 |
| pool_snapshot_rows | 30 (5 protocols × 1 placeholder pool × 6 ckpts) |
| quote_snapshot_rows | 180 (30 × 6) |
| fee_velocity_rows | 150 (25 × 6) |
| liquidity_distribution_rows | 30 (5 × 6) |
| market_regime_rows | 42 (7 × 6) |
| actual_fee_accrual_placeholder_rows | 6 (1 per ckpt) |
| chain_coverage_count | 2 (base + solana observed=true) |
| dex_coverage_count | 6 observed + 4 unobserved = 10 total |
| pool_coverage_count | 30 pool_snapshots rows (= 5 unique placeholder pool addresses × 6 ckpts) |
| quote_ready_pool_count | 0 (smoke placeholder, tvl=0) |
| fee_ready_pool_count | 0 |
| ev_ready_pool_count | 0 |
| preflight_candidate_count | 0 |
| watchlist_count | 0 |
| data_insufficient_count | 30 |
| reject_count | 0 (与 data_insufficient 等价) |

## 4. 锁定字段 (5 项)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 5. Recommended Next Stage

**`LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1`**

(12h 延展请求, **不**自动启动, 需用户单独 approve 短语 `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true` + 单独 FINAL_VERDICT + freeze 状态决定)

## 6. 输入证据 (本轮**未**修改)

| 路径 | 状态 |
|---|---|
| `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/FINAL_VERDICT.json` | 读 (V2 supervisor FAIL 状态) |
| `data/lp_long_horizon/20260605_043726/` | 读 (6/6 ckpts, 42 文件) |
| `scripts/lp_long_horizon_node_report_generator_v1.py` | 读 + 跑 (read-only dry-run mode) |

## 7. V2 在轨 (本轮**未**触碰)

- V2 supervisor PID 3872268 已退出 (trap EXIT 后 kill supervisor, expected behavior)
- V2 data 6/6 ckpts 完整 (42 文件), 0 修改
- V2 FINAL_VERDICT.json 0 修改
- V2 supervisor 脚本 0 修改
- V2 collector 脚本 0 修改

## 8. 严禁 (本轮全部不触发)

- 不启动 12h / 24h / 48h / 72h / 7d
- 不启动新 tmux
- 不启动 daemon / cron / systemd
- 不 probe / canary / live / paper
- 不读 wallet / keypair / signer / 私钥
- 不创建 signer
- 不发送 transaction / approve / mint / swap / bridge
- 不写 production positions
- 不覆盖 shadow 原始表
- 不接 paid RPC / paid indexer
- can_run_probe_now=false (locked)
- tiny_canary_allowed="no" (locked)
- edge_proven="no" (locked)
