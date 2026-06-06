# ARTIFACT INDEX — Stage Supervisor Finalize Fix V1

- stage: `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1`
- run_id: `20260606_082958`
- branch: `feat/supabase-postgres-deployment`
- status: **PASS**
- generated_at_utc: `2026-06-06T08:45:00Z`

## 1. 7 个输出文件 (in `reports/lp_long_horizon_stage_supervisor_finalize_fix/20260606_082958/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `INPUT_EVIDENCE_AUDIT_CN.md` | 输入证据审计 (CN) — v2 12h raw FAIL + corrected PASS + node report + stage runner 源码 |
| 2 | `input_evidence_audit.json` | 输入证据审计 (JSON) — root_cause + line_in_stage_runner (361/471/494) |
| 3 | `FINALIZE_FIX_REPORT_CN.md` | 修复报告 (CN) — 4 个 block 修复详情 + dry-run 验证 + 测试结果 |
| 4 | `finalize_fix_report.json` | 修复报告 (JSON) — fix_summary, lines_modified, dry_run_results, fix_verification_checklist |
| 5 | `FINAL_VERDICT.json` | Final verdict (含 spec-required 完整字段, 4 bug_fix_* 全 true) |
| 6 | `ONEPAGE_CN.md` | One-pager 总结 (CN) |
| 7 | `ARTIFACT_INDEX.md` | 本文件 |

## 2. 修改的脚本

| 文件 | 描述 |
|---|---|---|
| `scripts/run_lp_long_horizon_readonly_stage_once.sh` | 4 个 Python heredoc (trap / aggregate / finalize / fallback) 全部改为 `<<'PYEOF_xxx'` quoted form + env vars. 引入 `export DATA_DIR LOG_DIR STAGE_NAME RUN_ID LOOP_COUNT SLEEP_SECONDS ELAPSED_MIN DURATION_HOURS TOLERANCE_MIN GATE_DECISION REPORT_DIR SESSION` for aggregate/finalize/fallback, plus `export TRAP_*` for trap. Python reads `os.environ` and computes runtime_valid in Python with proper bool type. aggregate writes real JSON bool to `aggregate_summary.json`. finalize / fallback read that JSON via `json.loads` — no bash boolean interpolation. |
| `scripts/test_stage_supervisor_finalize_from_existing_checkpoints_v1.py` | **新文件** — dry-run test script, re-runs supervisor finalize logic against existing 12h checkpoint fixture, writes to separate `--out` dir, does NOT modify source. |
| `tests/test_lp_long_horizon_stage_supervisor_finalize_fix_v1.py` | **新文件** — 22 pytest tests covering input evidence audit, supervisor fix verification, dry-run script correctness, locked fields, allowed next stages. |

## 3. Dry-run 输出 (in `data/lp_long_horizon_supervisor_finalize_dryrun/20260606_082958/`)

| 文件 | 字节 | 描述 |
|---|---|---|
| `aggregate_summary.json` | 2231 | real JSON bool for `actual_runtime_valid_for_12h_gate`, ckpt=12, pool=5, quote=360, fee=300, liq=60, regime=84, actual_fee=12, runtime=720, gate_decision=PASS |
| `FINAL_VERDICT.json` | 1408 | status=PASS, runtime=720, pool_rows=5, gate_pass=true, no wallet/tx, recommended=LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1 |

**Source 12h data dir (84 文件) — 0 修改**. Source 12h report dir (FINAL_VERDICT.json) — 0 修改.

## 4. 关键数字 (修复前 vs 修复后, 12h fixture)

| 维度 | 修复前 (raw v2 12h) | 修复后 (本 dry-run) |
|---|---|---|
| `FINAL_VERDICT.status` | FAIL (NameError → trap default-zeros) | **PASS** (real gate) |
| `pool_snapshot_rows` | 0 (default-zeros) | **5** (deduped from 12 ckpts) |
| `quote_snapshot_rows` | 0 | **360** |
| `fee_velocity_rows` | 0 | **300** |
| `liquidity_distribution_rows` | 0 | **60** |
| `market_regime_rows` | 0 | **84** |
| `actual_fee_accrual_placeholder_rows` | 0 | **12** |
| `actual_runtime_minutes` | 720 (trap fallback) | **720** (real) |
| `actual_runtime_valid_for_12h_gate` | true (trap fallback hardcoded) | **true** (Python bool) |
| `gate_decision` | FAIL (because finalize failed) | **PASS** (real gate) |
| corrected verdict needed? | YES (raw useless) | **NO** (raw self-explanatory) |

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |
| `auto_next_stage_disabled` | `true` |

## 6. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d
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
- ❌ **不**修改 v2 12h FINAL_VERDICT
- ❌ **不**修改 v2 6h FINAL_VERDICT + corrected verdict
- ❌ **不**修改 v2 12h corrected verdict
- ❌ **不**修改 12h node report (commit 90cb18a)

## 7. 输入证据 (本轮**只**读)

- `reports/lp_long_horizon_readonly_12h_run/20260605_082120/FINAL_VERDICT.json` (v2 raw FAIL, default-zeros)
- `reports/lp_long_horizon_readonly_12h_extension/20260605_082120/CORRECTED_FINAL_VERDICT.json` (corrected PASS, gate_check_pass_count=15, runtime=720, pool_snapshot_rows=5)
- `reports/lp_long_horizon_node_reports/20260605_082120/12h/FINAL_NODE_VERDICT.json` (node report PASS, v2_status=FAIL, finalize_error=trap EXIT rc=1)
- `scripts/run_lp_long_horizon_readonly_stage_once.sh` (V3 stage runner source — 4 bug sites identified at line 361, 471, 494)
- `data/lp_long_horizon/20260605_082120/` (12 checkpoint dirs, 60 placeholder pool rows, 360 quote rows, 300 fee rows, 60 liq rows, 84 regime rows, 12 actual_fee placeholder)

## 8. 4-stage allowed next stages

- `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` (本 stage 推荐)
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` (12h retry, 仍需用户单独审批)
- `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_REPEAT` (进一步加固, e.g. 抽公共 finalize 函数)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (用户决定暂停)

## 9. Recommended next stage

**`LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`**

理由: 本 stage 已修 supervisor finalize bug (4 个 Python heredoc lowercase true/false NameError). 12h checkpoint fixture dry-run 验证通过 (status=PASS, runtime=720, pool_rows=5, 12 ckpts). 下一步 **不** 急着 12h retry, 而是先做 5 协议 EVM/Meteora coverage fix:
- Meteora DLMM (solana/meteora_dlmm) — 已有 adapter, 需 collector coverage
- Base Uniswap V3 (base/uniswap_v3) — Go adapter 已有, EVM collector 未接通
- Base Aerodrome (base/aerodrome) — Go adapter 已有, EVM collector 未接通
- BSC PancakeSwap V3 (bsc/pancakeswap_v3) — bsc_chain_adapter 未实现
- BSC PancakeSwap V2 (bsc/pancakeswap_v2) — bsc_chain_adapter 未实现

完整 universe (45 pool target) → 才能跑有意义的 12h/24h/48h/72h/7d 真实池观察.

## 10. 12h retry 仍需的 2 项阻塞清除 (本 stage 修完 finalize, 不再是 blocker)

1. **5 协议 EVM/Meteora coverage fix**: 当前 12h 是 `partial_solana_real_pool_universe`. 12h retry 需先做 coverage fix, 才能算 full-universe
2. **用户单独审批**: 新 approval 短语 `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true` (sha256 重新计算), 单独 stage FINAL_VERDICT, 单独 freeze 状态决定
