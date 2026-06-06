# ARTIFACT INDEX — Real Pool Universe Collector Fix V1

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1`
- run_id: `20260605_083000`
- branch: `feat/supabase-postgres-deployment`
- status: **PASS**
- generated_at_utc: `2026-06-06T08:14:30Z`

## 1. 7 个输出文件 (in `reports/lp_long_horizon_real_pool_universe_collector_fix/20260605_083000/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `INPUT_EVIDENCE_AUDIT_CN.md` | 输入证据审计 (CN) |
| 2 | `input_evidence_audit.json` | 输入证据审计 (JSON) |
| 3 | `REAL_POOL_UNIVERSE_SMOKE_RESULT_CN.md` | 短 smoke 验证结果 (CN) |
| 4 | `real_pool_universe_smoke_result.json` | 短 smoke 验证结果 (JSON) |
| 5 | `FINAL_VERDICT.json` | Final verdict (含 spec-required 完整字段) |
| 6 | `ONEPAGE_CN.md` | One-pager 总结 (CN) |
| 7 | `ARTIFACT_INDEX.md` | 本文件 |

## 2. 修改的脚本

| 文件 | 描述 |
|---|---|
| `scripts/lp_long_horizon_readonly_collector_v1.py` | 新增 `--pool-universe` / `--max-pools` / `--max-snapshots` / `--run-id` / `--no-daemon` CLI args; 新增 `_load_pool_universe` / `_select_universe_pools` / `_build_real_pool_snapshot` / `_real_universe_smoke_mode` 函数; 拒绝任何 placeholder (`<smoke_pool_` / `<smoke_mint_`) in real universe; 真实池写真实 pool_address / TVL / volume / source_artifact |
| `scripts/run_lp_long_horizon_readonly_stage_once.sh` (line 262) | stage runner 转发 `--pool-universe "${POOL_UNIVERSE_PATH}" --max-snapshots 1 --run-id "${RUN_ID}"` 给 collector (替代 `--pools-per-protocol 5`) |
| `tests/test_lp_long_horizon_real_pool_universe_collector_fix_v1.py` | 27 tests 验证: --pool-universe parses, placeholder rejected, parse fail no fallback, selected_real_pool_count>0, real_pool_universe_used=true, stage runner forwards, no wallet/tx, final verdict 4-stage allowed |

## 3. 短 smoke 输出 (in `data/lp_long_horizon_real_pool_smoke/20260605_083000/`)

| 文件 | 字节 | 描述 |
|---|---|---|
| `pool_snapshots.jsonl` | 3600 | 5 real pool snapshots (5 unique real on-chain Solana addresses) |
| `quote_snapshots.jsonl` | 9270 | 30 rows (5 × 6 notional) |
| `fee_velocity.jsonl` | 8310 | 25 rows (5 × 5 windows) |
| `liquidity_distribution.jsonl` | 1465 | 5 rows |
| `market_regime.jsonl` | 1516 | 7 regime classifications |
| `actual_fee_accrual_placeholder.json` | 729 | R0 schema only |
| `smoke_summary.json` | 4055 | 完整 summary (real_pool_universe_used=true, placeholder_pool_count=0, all_pools_are_real_on_chain=true) |

## 4. 关键数字

| 维度 | 修复前 (12h actual) | 修复后 (本短 smoke) |
|---|---|---|
| `real_pool_universe_used` | false (collector 没接通) | **true** |
| `placeholder_pool_count` | 0 in request, 5 in actual | **0** (both) |
| `pool_snapshot_rows` | 60 (5 placeholder × 12 ckpts) | **5** (5 real pools × 1 snapshot) |
| `all_pools_are_real_on_chain` | false (smoke_placeholder=true) | **true** |
| `unique_pool_addresses` | 5 placeholder | **5 real** (Hp53XEtt4S8..., G2FiE1yn..., 9tXiuRRw..., 68soqftZ..., 5xfKkFmh...) |
| `real_tvl_total` | 0 (placeholder) | **52M USD** (31M+6.7M+5.4M+5.3M+3.7M) |
| `real_24h_vol_total` | 0 (placeholder) | **30M USD** (20M+2M+4M+2.9M+1.3M) |
| `source_artifact` | "smoke placeholder" | "reports/lp_orca_whirlpool_readonly_connector/20260604_025414/orca_candidate_source_collection.csv" |
| `selection_reason` | "smoke placeholder" | "real_on_chain_orca_pool_stable_pair_classified" |

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 6. 严禁 (本轮全部不触发)

- ❌ 不启动 12h retry (本轮仅短 smoke 验证 fix, **不** 启动 12h)
- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动长期 collector
- ❌ 不启动新 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 V2 12h FINAL_VERDICT
- ❌ **不**修改 V2 6h FINAL_VERDICT + V2 6h corrected verdict
- ❌ **不**修改 V2 12h corrected verdict
- ❌ **不**修改 12h node report
- ❌ **不**修复 V3 supervisor finalize bug

## 7. 输入证据 (本轮**只**读)

- `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json` (33 real pools, 0 placeholder)
- `reports/lp_long_horizon_node_reports/20260605_082120/12h/FINAL_NODE_VERDICT.json` (12h node report)
- `reports/lp_long_horizon_readonly_12h_extension/20260605_082120/CORRECTED_FINAL_VERDICT.json` (12h corrected verdict)
- `scripts/lp_long_horizon_readonly_collector_v1.py` (collector v1 source)
- `scripts/run_lp_long_horizon_readonly_stage_once.sh` (stage runner source)

## 8. 4-stage allowed next stages

- `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` (本 stage 推荐)
- `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR FIX_REPEAT` (进一步扩展 fix)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (用户要求暂停)
- `STOP_LP_RESEARCH_NOW` (用户要求停止)

## 9. Recommended next stage

**`LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1`**

理由: 本 stage 已修复 collector CLI (--pool-universe) + stage runner (forward --pool-universe), 短 smoke 验证 collector 写真实池 (5 real pools, 0 placeholder, all_pool_addresses_real=true, no wallet/tx/probe). 满足 LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1 的 5 项前置. 但 12h retry 仍需 3 项额外阻塞清除: 修 V3 supervisor finalize bug (line 435 + 493); EVM (Base/BSC) coverage fix to make 12h full-universe; 用户单独审批 12h retry 短语.

## 10. 12h retry 仍需的 3 项阻塞清除

1. **V3 supervisor finalize bug** (`scripts/run_lp_long_horizon_readonly_stage_once.sh` line 435 + 493): bash `${REAL_GATE_PASS}` interpolated to lowercase `true` in Python ternary, 触发 NameError, fail-safe trap 写 default-zeros. 修复: `${REAL_GATE_PASS^^}` 大写, 或 `<<'PYEOF'` quoted heredoc, 或在 Python 端用 `agg["actual_runtime_valid_for_12h_gate"]` 替代
2. **EVM coverage** (Meteora DLMM + Base Uniswap V3 + Base Aerodrome + BSC PancakeSwap V3 + BSC PancakeSwap V2): 当前 12h 是 `partial_solana_real_pool_universe`. 12h retry 需先做 5 个缺失协议的 coverage fix, 才能算 full-universe
3. **用户单独审批**: 新 approval 短语 `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true` (sha256 重新计算), 单独 stage FINAL_VERDICT
