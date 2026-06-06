# LP Long Horizon Stage Supervisor Finalize Fix V1 — One Pager

- stage: `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1`
- run_id: `20260606_082958`
- branch: `feat/supabase-postgres-deployment`
- status: **PASS**

## 0. 一句话

修复 `scripts/run_lp_long_horizon_readonly_stage_once.sh` 中 4 个 Python heredoc 的 lowercase `true`/`false` 插值 bug, 使 supervisor finalize 不再因为 bash boolean 嵌入 Python 触发 NameError. 未来 6h/12h/24h/48h/72h/7d raw FINAL_VERDICT 都能**直接**得出可读结论, 不再需要 corrected verdict 补救. 12h checkpoint fixture dry-run 验证 status=PASS, runtime=720, pool_rows=5, 12 ckpts. **严禁**自动启动 12h / 24h / 等长跑. 12h retry 仍需用户单独审批 + 5 协议 EVM coverage fix.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `raw_finalize_bug_fixed` | **true** |
| `fallback_finalize_bug_fixed` | **true** |
| `lowercase_python_boolean_removed` | **true** |
| `existing_12h_checkpoint_finalize_dryrun_pass` | **true** |
| `final_verdict_always_generated` | **true** |
| `auto_next_stage_disabled` | **true** |
| `long_run_started` | **false` |
| `can_run_probe_now` | **false** (LOCKED) |
| `tiny_canary_allowed` | **"no"** (LOCKED) |
| `wallet_or_tx_touched` | **false** (LOCKED) |
| `transaction_sent` | **false** (LOCKED) |
| `recommended_next_stage` | **`LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`** |

## 2. Bug 根因 (4 sites)

| Line | Block | Before | After |
|---|---|---|---|
| 361 | aggregate | `"actual_runtime_valid_for_${STAGE_NAME}_gate": ${REAL_GATE_PASS}` (lowercase true literal) | `runtime_valid = elapsed_min >= (duration_hours * 60 - tolerance_min)` (Python bool) |
| 412/427 | finalize | reads `agg[...]` (corrupted) | reads `aggregate_summary.json` via `json.loads` (proper bool) |
| 471 | fallback | `actual_runtime_valid_for_${STAGE_NAME}_gate: ${REAL_GATE_PASS}` (lowercase) | reads `aggregate_summary.json` (or env vars fallback) → Python bool |
| 494 | fallback | `if ${REAL_GATE_PASS}` (Python ternary literal) | `if runtime_valid:` (Python bool) |

**关键设计**: aggregate block 写 `aggregate_summary.json` (real JSON bool for `actual_runtime_valid_for_<STAGE>_gate`). finalize + fallback 都**读**这个 JSON file via `json.loads` — 不会再有 NameError. 即使 aggregate 写出残缺 JSON, fallback 还有 env var 兜底 (recompute runtime_valid in Python).

## 3. 修复前后对比 (dry-run with 12h checkpoint fixture)

| 维度 | 修复前 (raw v2 12h) | 修复后 (本 dry-run) |
|---|---|---|
| `FINAL_VERDICT.status` | FAIL (NameError → trap default-zeros) | **PASS** (real gate) |
| `pool_snapshot_rows` | 0 (default-zeros) | **5** (deduped from 12 ckpts) |
| `quote_snapshot_rows` | 0 | **360** |
| `fee_velocity_rows` | 0 | **300** |
| `liquidity_distribution_rows` | 0 | **60** |
| `market_regime_rows` | 0 | **84** |
| `actual_fee_accrual_placeholder_rows` | 0 | **12** |
| `actual_runtime_minutes` | 720 (from trap fallback) | **720** (real, read from source corrected verdict) |
| `actual_runtime_valid_for_12h_gate` | true (hardcoded in trap fallback) | **true** (Python bool, written to JSON, re-read) |
| `gate_decision` | FAIL (because finalize failed) | **PASS** (real gate) |
| corrected verdict needed? | **YES** (raw useless) | **NO** (raw self-explanatory) |

## 4. 修改的文件

| 文件 | 改动 |
|---|---|
| `scripts/run_lp_long_horizon_readonly_stage_once.sh` | 4 个 Python heredoc (trap / aggregate / finalize / fallback) 全部改为 quoted form + env vars. 引入 env var exports (DATA_DIR, LOG_DIR, STAGE_NAME, RUN_ID, LOOP_COUNT, SLEEP_SECONDS, ELAPSED_MIN, DURATION_HOURS, TOLERANCE_MIN, GATE_DECISION, REPORT_DIR, SESSION + TRAP_*). aggregate 写 real JSON bool, finalize / fallback 读 JSON, 永不嵌 bash boolean |
| `scripts/test_stage_supervisor_finalize_from_existing_checkpoints_v1.py` | **新文件** — dry-run 测试脚本, 用 12h checkpoint fixture 验证 fix, 不修改 source 12h data |
| `tests/test_lp_long_horizon_stage_supervisor_finalize_fix_v1.py` | **新文件** — 22 pytest tests |

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 6. 测试结果

| 阶段 | 数量 | 内容 |
|---|---|---|
| A (input evidence) | 2 | input_evidence_audit.json 结构 + 字段对 |
| B (supervisor fix) | 8 | 无 unquoted heredoc; 无 bash boolean 嵌入 Python; aggregate/finalize/fallback 三个 block 都用 quoted heredoc + env vars; Python 端写 proper bool; bash syntax OK |
| C (dry-run script) | 4 | 脚本存在; Python compile OK; 跑 12h fixture 出 FINAL_VERDICT (status=PASS, runtime=720, pool_rows=5); source 12h data **0 修改** |
| D (locked + final verdict) | 7 | FINAL_VERDICT 全部 spec-required 字段; locked 字段全 false/no; 4 bug_fix_* 字段全 true; recommended 在 4-stage allowed set; 无 forbidden process; 无 secret value |

**22/22 passed**.

## 7. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_6H_FINALIZER_REBUILD_V1` | 上一 stage | 6h corrected verdict 从 checkpoints 重建 (gate=PASS) |
| `LP_LONG_HORIZON_12H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1` | 上一 stage | 12h corrected verdict (gate=PASS, 15/15 checks) |
| `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1` | 上一 stage | 12h 节点报告 (transparency on coverage gap) |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1` | 上一 stage | collector CLI `--pool-universe` + stage runner forward; 5 real pool smoke verified |
| **`LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1`** | **本 stage** | **supervisor finalize 4 个 Python heredoc 的 lowercase bool bug; 4 个 block 全部 quoted + env vars; dry-run 12h fixture status=PASS** |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` | **推荐 next** | 5 协议 EVM/Meteora coverage fix (45 pool target) |

## 8. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d (本轮**只**修 finalize, **不** 启动)
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
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report

## 9. 下一轮建议 (用户决策)

| 选项 | 含义 |
|---|---|
| **`LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`** (本 stage 推荐) | 5 协议 EVM/Meteora coverage fix, 完整 universe (45 pool target) → 12h retry 才有意义 |
| `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` | 12h retry (仍需用户单独审批 + 5 协议 coverage fix + finalize fix 已 ok) |
| `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_REPEAT` | 进一步加固, e.g. 抽公共 finalize 函数, 加 dry-run 进 preflight |
| `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` | 用户决定暂停 |

## 10. 关键数据点

- **12h raw FINAL_VERDICT (历史 FAIL)** 显示 `status=FAIL, finalize_error=trap EXIT rc=1, pool_snapshot_rows=0`. 这是**当前** 12h raw 数据, **不**是本 stage dry-run.
- **本 stage dry-run** 显示 `status=PASS, runtime=720, pool_rows=5, 12 ckpts, no wallet/tx/probe`. 是 fix 验证.
- 12h raw FINAL_VERDICT **不**应被本 stage 修复覆盖. 12h raw FINAL_VERDICT FAIL + default-zeros 仍正确 (因为 v3 supervisor 跑的是 commit 23fed9d **之前**的 stage runner). 修复是**前瞻**的, 未来 stage 才生效.

## 11. 后续

本 stage 完成, 22/22 pytest + 0 forbidden process + 0 wallet/tx. 修复确认 supervisor finalize 不再因 lowercase Python boolean 失败. 已 commit + push 到 `feat/supabase-postgres-deployment`. 用户可在下一轮决定:
1. 触发 `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` (推荐): 5 协议 EVM/Meteora coverage fix
2. 触发 `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` (需手动审批): 12h retry, finalize fix 已 ok, 但 EVM coverage 仍 partial
3. 暂停或停止

严禁 (per LP strategy research freeze): probe / canary / live / paper / wallet / tx / auto-12h.
