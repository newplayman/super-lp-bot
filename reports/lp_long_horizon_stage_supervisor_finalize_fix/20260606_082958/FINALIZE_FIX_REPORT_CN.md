# LP Long Horizon Stage Supervisor Finalize Fix V1 — Finalize Fix Report

- stage: `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1`
- run_id: `20260606_082958`
- branch: `feat/supabase-postgres-deployment`
- status: **PASS**
- generated_at_utc: `2026-06-06T08:45:00Z`

## 0. 一句话

修复 `scripts/run_lp_long_horizon_readonly_stage_once.sh` 中 4 个 Python heredoc (trap / aggregate / finalize / fallback) 的 lowercase `true`/`false` 插值 bug, 使未来 6h/12h/24h/48h/72h/7d 任意阶段 supervisor 都能直接写出**正确**的 raw FINAL_VERDICT (pass/fail 取决于真实 gate, 不再 fixed-zeros), 不再需要 corrected verdict 补救. 12h checkpoint fixture dry-run 验证通过 (status=PASS, runtime=720, 12 ckpts, 5 pool rows).

## 1. Bug 根因

### 1.1 V3 bug 引入路径

| 版本 | 行为 |
|---|---|
| V1 (6h supervisor) | 用 `set -u` + 显式 string `"true"` / `"false"`, **不** 把 `${REAL_GATE_PASS}` 直接插 Python dict |
| V2 (12h supervisor, 修 V1 NameError silent loss) | 引入 fail-safe trap + CORRECTED_FINAL_VERDICT_FALLBACK.json |
| **V3 (generalized stage supervisor)** | **reuse V2 structure, 但在 4 个 Python heredoc 内引入 `${REAL_GATE_PASS}` 直接 interpolation** → regression |

### 1.2 V3 4 个 bug site

| Line | Block | Code (before fix) | Bug |
|---|---|---|---|
| 361 | aggregate | `"actual_runtime_valid_for_${STAGE_NAME}_gate": ${REAL_GATE_PASS}` | bash 把 `true`/`false` 写进 Python dict, NameError |
| 412/427 | finalize | `agg["actual_runtime_valid_for_${STAGE_NAME}_gate"]` (reads) | 间接失败, 因为 agg 在 line 361 已写坏 |
| 471 | fallback | `actual_runtime_valid_for_${STAGE_NAME}_gate: ${REAL_GATE_PASS}` | 同 line 361 |
| 494 | fallback | `if ${REAL_GATE_PASS}` (Python ternary) | literal `true`/`false` in Python → NameError |
| 168-216 | trap | (already not embedding boolean) | 安全, 但加固 |

**为什么是 lowercase**: bash 内 `${VAR}` 取值后**不会** 改成 Python `True/False`. 即便在 Python heredoc 里, bash 仍按字面值替换. Python 看到 lowercase `true` → NameError: name 'true' is not defined.

### 1.3 V3 bug 的下游影响

| 维度 | 修复前 |
|---|---|
| raw FINAL_VERDICT status | 永远 FAIL (因为 finalize block rc=1, trap 写 default-zeros) |
| raw FINAL_VERDICT pool_snapshot_rows | 永远 0 (default-zeros, 真实可能是 60 placeholder 或 5 real) |
| corrected verdict | 必须有, 才能得出可读结论 |
| 12h raw FINAL_VERDICT | `status=FAIL, finalize_error=trap EXIT rc=1, pool_snapshot_rows=0` (历史记录) |
| 12h corrected FINAL_VERDICT | `status=PASS, gate_pass=true, 15/15 checks pass` (从 12 ckpts 重新 aggregate) |

## 2. Fix 方案

### 2.1 4 个统一原则

1. **所有 Python heredoc 改为 quoted form** `<<'PYEOF_xxx'` — 阻止 bash 插值进入 Python 代码
2. **所有 bash 值通过 env vars 传递** — `export DATA_DIR LOG_DIR STAGE_NAME ...` before `python3 <<'PYEOF_xxx'`
3. **Python 端用 `os.environ` 读取** — 只接受 integer / string, **不** 接受 bash boolean
4. **Python 端做 boolean 运算** — `runtime_valid = elapsed_min >= (duration_hours * 60 - tolerance_min)` (类型正确, 写 JSON 时变 `true`/`false`)

### 2.2 aggregate block 修复详情 (line 325-415)

**修复前**:
```python
agg = {
    "actual_runtime_valid_for_${STAGE_NAME}_gate": ${REAL_GATE_PASS},  # ← lowercase 'true' literal
    ...
}
```

**修复后**:
```python
# All values come from env vars (integers + strings only — NO bash boolean literal here).
elapsed_min = int(os.environ["ELAPSED_MIN"])
duration_hours = int(os.environ["DURATION_HOURS"])
tolerance_min = int(os.environ["TOLERANCE_MIN"])
# Compute gate validity in Python — no bash boolean interpolation.
runtime_valid = elapsed_min >= (duration_hours * 60 - tolerance_min)
agg = {
    "actual_runtime_valid_for_" + stage_name + "_gate": runtime_valid,  # ← real Python bool
    ...
}
```

### 2.3 finalize block 修复详情 (line 421-497)

**修复前**: 读 `agg["actual_runtime_valid_for_${STAGE_NAME}_gate"]` (被 line 361 写坏) → NameError

**修复后**:
```python
agg = json.loads((LOG / "aggregate_summary.json").read_text())  # proper bool from JSON
gate_valid = bool(agg.get("actual_runtime_valid_for_" + stage_name + "_gate", False))
status = "PASS" if gate_decision == "PASS" else "FAIL"
...
recommended_next_stage = "..." if gate_valid else "..."
```

### 2.4 fallback block 修复详情 (line 495-569)

**修复前**: 同样用 `${REAL_GATE_PASS}` 直接插值 → NameError (line 471 + 494)

**修复后**:
```python
agg = json.loads(...) if agg_path.exists() else {}
runtime_valid = bool(agg.get(...)) if agg_path.exists() else (
    elapsed_min >= (duration_hours * 60 - tolerance_min)  # fallback recompute in Python
)
```

**关键设计**: fallback 不依赖**仅** aggregate_summary.json — 如果 aggregate 也失败 (写出残缺 JSON), fallback 从 env vars `ELAPSED_MIN` / `DURATION_HOURS` / `TOLERANCE_MIN` 重新计算 `runtime_valid`. 这样 fallback 永远不会因为 `if ${REAL_GATE_PASS}` NameError 失败.

### 2.5 trap block 加固 (line 167-232)

trap block 之前**已经**不嵌 bash boolean (只插 `${ELAPSED_MIN_TRAP}` / `${DURATION_HOURS}` / `${TOLERANCE_MIN}` integer, 安全). 仍改为 quoted heredoc + env vars, 加注释说明 "fail-safe, 不依赖 aggregate_summary.json". 即便 aggregate block 写出残缺 JSON, trap 仍能写出 default-zeros FINAL_VERDICT (with proper bool field).

## 3. Dry-run 验证 (12h checkpoint fixture)

### 3.1 dry-run script: `scripts/test_stage_supervisor_finalize_from_existing_checkpoints_v1.py`

**输入**:
- `--source-data data/lp_long_horizon/20260605_082120` (12 ckpts, 60 placeholder rows)
- `--source-report reports/lp_long_horizon_readonly_12h_run/20260605_082120`
- `--out data/lp_long_horizon_supervisor_finalize_dryrun/20260606_082958`

**输出**:
- `aggregate_summary.json` (real JSON bool, ckpt=12, pool=5, quote=360, fee=300, liq=60, regime=84, actual_fee=12, gate_valid=true, gate_decision=PASS, runtime=720)
- `FINAL_VERDICT.json` (status=PASS, runtime=720, pool_rows=5, gate_pass=true, no wallet/tx, recommended=LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1)

**关键**: source 12h data dir (84 文件) **0 修改** (verified by re-snapshot of file paths + sizes).

### 3.2 dry-run 关键数字

| 维度 | 修复前 (raw v2 12h) | 修复后 (本 dry-run) |
|---|---|---|
| `raw_FINAL_VERDICT.status` | "FAIL" (NameError → trap default-zeros) | **"PASS"** (real gate from 720min runtime) |
| `pool_snapshot_rows` | 0 (default-zeros) | **5** (real, deduped from 12 ckpts) |
| `quote_snapshot_rows` | 0 | **360** |
| `fee_velocity_rows` | 0 | **300** |
| `liquidity_distribution_rows` | 0 | **60** |
| `market_regime_rows` | 0 | **84** |
| `actual_fee_accrual_placeholder_rows` | 0 | **12** |
| `actual_runtime_minutes` | 720 (from trap fallback) | **720** (read from source corrected verdict) |
| `actual_runtime_valid_for_12h_gate` | true (hardcoded in trap fallback) | **true** (computed Python bool, written to JSON, re-read) |
| `gate_decision` | "FAIL" (because finalize failed) | **"PASS"** (real gate) |
| corrected verdict needed? | **YES** (raw useless) | **NO** (raw self-explanatory) |

## 4. 测试 (22/22 passed)

| Stage | 数量 | 内容 |
|---|---|---|
| A (input evidence) | 2 | input_evidence_audit.json 存在, root_cause + line_in_stage_runner 字段对 |
| B (supervisor fix) | 8 | 无 unquoted heredoc with bash interpolation; 无 `${REAL_GATE_PASS}` 嵌入 Python heredoc; aggregate / finalize / fallback 三个 block 都用 quoted heredoc; Python 端写 proper bool; bash syntax OK |
| C (dry-run script) | 4 | 脚本存在; Python compile OK; 跑 12h fixture 出 FINAL_VERDICT; source 12h data **0 修改** |
| D (locked fields + final verdict) | 7 | FINAL_VERDICT.json 有全部 spec-required 字段; can_run_probe_now=false, tiny_canary_allowed="no", wallet_or_tx_touched=false, transaction_sent=false, auto_next_stage_disabled=true, long_run_started=false; recommended_next_stage 在 4-stage allowed set; 4 bug_fix_* 字段全 true; 无 forbidden process; 无 secret value |

## 5. 修复覆盖范围

| 路径 | 修复 | 状态 |
|---|---|---|
| aggregate block (line 325-415) | quoted heredoc + env vars + Python bool | ✅ |
| finalize block (line 421-497) | quoted heredoc + 读 aggregate_summary.json | ✅ |
| fallback block (line 495-569) | quoted heredoc + 读 aggregate_summary.json or env vars | ✅ |
| trap block (line 167-232) | quoted heredoc + env vars + 加固注释 | ✅ |
| 12h raw FINAL_VERDICT (历史 FAIL) | **不** 改 (v2 12h FINAL_VERDICT 保持 FAIL 状态, 已被 corrected verdict 透明化) | 不改 |
| 12h corrected FINAL_VERDICT | **不** 改 (上一阶段成果) | 不改 |
| 12h data_dir (84 文件) | **0 修改** | 锁定 |
| 6h data_dir (42 文件) | **0 修改** | 锁定 |
| 12h node report (commit 90cb18a) | **不** 改 | 锁定 |
| 12h supervisor / collector invocation | **不** 改 (上一阶段已修 --pool-universe) | 不改 |

## 6. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |
| `auto_next_stage_disabled` | `true` |

## 7. 严禁 (本轮全部不触发)

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
- ❌ **不**修改 v2 12h FINAL_VERDICT
- ❌ **不**修改 v2 6h FINAL_VERDICT + corrected verdict
- ❌ **不**修改 v2 12h corrected verdict
- ❌ **不**修改 12h node report

## 8. 下一步建议

**推荐 next stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`**

理由: 本 stage 已修 finalize (不再需要 corrected verdict 补救). 下一步 **不** 急着 12h retry, 而是先做 5 协议 EVM/Meteora coverage fix:
- Meteora DLMM (solana/meteora_dlmm) — 已有 adapter, 需 collector coverage
- Base Uniswap V3 (base/uniswap_v3) — Go adapter 已有, EVM collector 未接通
- Base Aerodrome (base/aerodrome) — Go adapter 已有, EVM collector 未接通
- BSC PancakeSwap V3 (bsc/pancakeswap_v3) — bsc_chain_adapter 未实现
- BSC PancakeSwap V2 (bsc/pancakeswap_v2) — bsc_chain_adapter 未实现

完整 universe (45 pools, 7 chains, 10 dex) → 才能跑有意义的 12h/24h/48h/72h/7d 真实池观察.

## 9. 4-stage allowed next stages

- `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` (本 stage 推荐)
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` (12h retry, 仍需用户单独审批 + 5 协议 coverage fix)
- `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_REPEAT` (进一步加固, e.g. 抽公共 finalize 函数)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (用户决定暂停)
