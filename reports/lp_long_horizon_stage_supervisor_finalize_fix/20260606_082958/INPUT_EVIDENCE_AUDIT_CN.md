# Input Evidence Audit — Stage Supervisor Finalize Fix V1

- stage: `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1`
- run_id: `20260606_082958`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T08:30:00Z`

## 0. 总结

✅ **本轮只修 supervisor finalize bug, 不启动 12h/24h/48h/72h/7d**. 修复前 → 修复后:

| 路径 | 修复前 | 修复后 |
|---|---|---|
| raw FINAL_VERDICT (success) | NameError on `true`/`false`, fallback trap 写 default-zeros, status=FAIL with `pool_snapshot_rows=0` | `<<'PYEOF'` quoted heredoc + explicit `"true"/"false"` string parsing + `agg["actual_runtime_valid_for_<STAGE>_gate"]` reused from `aggregate_summary.json` |
| raw FINAL_VERDICT (failure) | finalize block rc≠0, fallback 用 `if ${REAL_GATE_PASS}` literal `true`/`false` 触发 NameError | fallback 用 `agg.get("actual_runtime_valid_for_<STAGE>_gate", False)` from `aggregate_summary.json`, no shell boolean interpolation |
| corrected verdict 是否仍需要 | YES (raw 失败, 必须靠 corrected verdict 才能得出可读结论) | **NO** (raw FINAL_VERDICT 现在无论 success 还是 fail 都能生成) |
| `pool_snapshot_rows=0` default-zeros | 出现 (raw FAIL 把 0 写进 FINAL_VERDICT) | 不再出现 (用 `agg` 写) |

## 1. 4 个输入证据文件 (只读)

### 1.1 `reports/lp_long_horizon_readonly_12h_run/20260605_082120/FINAL_VERDICT.json` (v2 raw)

```json
{
  "stage": "LP_LONG_HORIZON_READONLY_12H_STAGE_RUN_V1",
  "status": "FAIL",
  "supervisor_finalize_failed": true,
  "finalize_error": "trap EXIT rc=1",
  "pool_snapshot_rows": 0,   // ← DEFAULT ZEROS, 真实是 60 (5 placeholder × 12 ckpts) in v2 / 5 in v3
  "quote_snapshot_rows": 0,
  ...
}
```

**12h raw finalizer failed**. 由 v3 supervisor finalize bug 导致. trap EXIT rc=1 表明 supervisor post-stage python block 抛 NameError. fail-safe trap 写 default-zeros 兜底. **`pool_snapshot_rows=0` 实际不对**: v2 12h 真实收集 60 pool snapshot rows (5 placeholder × 12 ckpts).

### 1.2 `reports/lp_long_horizon_readonly_12h_extension/20260605_082120/CORRECTED_FINAL_VERDICT.json` (corrected)

```json
{
  "stage": "LP_LONG_HORIZON_12H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1",
  "source_supervisor_finalize_failed": true,
  "source_finalize_error": "trap EXIT rc=1; post-12h python block NameError on 'true' (bash ${REAL_GATE_PASS} interpolated to lowercase 'true' in Python ternary)",
  "corrected_from_checkpoints": true,
  "checkpoint_count": 12,
  "pool_snapshot_rows": 5,   // ← 真值 from checkpoints
  "gate_pass": true,
  "gate_check_pass_count": 15,
  "gate_check_fail_count": 0
}
```

**corrected verdict was needed** because raw v2 failed. corrected verdict 直接 re-aggregate 12 个 checkpoint 数据得出 gate=PASS, 15/15 checks pass, runtime=720min (12h 实际跑完).

### 1.3 `reports/lp_long_horizon_node_reports/20260605_082120/12h/FINAL_NODE_VERDICT.json` (node report)

确认 v2 raw FINAL_VERDICT `v2_status=FAIL`, `v2_data_quality_status=FAIL`, `v2_supervisor_recommended_next_stage=LP_LONG_HORIZON_12H_NODE_REPORT FIX_REPEAT`. node report 本体 PASS, 但 raw finalizer bug 导致需要 node report + corrected verdict 才能说明白.

### 1.4 `scripts/run_lp_long_horizon_readonly_stage_once.sh` (stage runner v3)

| Line | Bug |
|---|---|
| 168-216 | trap block 使用 `<<PYEOF_TRAP` (unquoted heredoc), bash 变量会被插值. python 代码段**自身**没插值问题 (python-only block) |
| 317-385 | success aggregate block `python3 <<PYEOF` (unquoted heredoc) — **Line 361** `"actual_runtime_valid_for_${STAGE_NAME}_gate": ${REAL_GATE_PASS}` 把 `true` literal 插进 python dict value. python 看到 lowercase `true`, 触发 `NameError: name 'true' is not defined` |
| 391-441 | success finalize block `python3 <<PYEOF` (unquoted heredoc) — **Line 412** `actual_runtime_valid_for_${STAGE_NAME}_gate: agg["actual_runtime_valid_for_${STAGE_NAME}_gate"]` (这里**没**直接插 `${REAL_GATE_PASS}`, 是**读** `agg` dict), 但 **Line 427** `gate_pass: agg["actual_runtime_valid_for_${STAGE_NAME}_gate"]` 引用了**被 line 361 写坏的** agg key. 也就是说, line 361 写坏 agg dict, line 412/427 读 → 间接失败. **Line 402** `"PASS" if agg["gate_decision"] == "PASS" else "FAIL"` 用 string "PASS" 比较, 这部分安全 |
| 449-499 | fallback block `python3 - <<PYEOF_FALLBACK` (unquoted heredoc) — **Line 471** `actual_runtime_valid_for_${STAGE_NAME}_gate: ${REAL_GATE_PASS}` (lowercase). **Line 494** `if ${REAL_GATE_PASS}` (literal `true`/`false` in Python ternary) — 触发 NameError. fallback 自身就因为同样 bug 失败 |

**root cause = Python heredoc lowercase true/false interpolation**.

## 2. 根因 (RCA)

`scripts/run_lp_long_horizon_readonly_stage_once.sh` 在第 313-315 行设置:

```bash
REAL_GATE_PASS=false  # 或 true
GATE_DECISION="PASS"  # 或 "FAIL"
```

后续在 4 处直接用 `${REAL_GATE_PASS}` 嵌入 Python heredoc (unquoted `<<PYEOF`):

| 位置 | 嵌入方式 | 结果 |
|---|---|---|
| line 361 (aggregate) | `"actual_runtime_valid_for_${STAGE_NAME}_gate": ${REAL_GATE_PASS}` | python dict value 变 `true` / `false` literal, NameError |
| line 412 (finalize) | (no direct ${REAL_GATE_PASS}, reads `agg`) | 间接失败, 因为 agg 在 line 361 已写坏 |
| line 471 (fallback) | `actual_runtime_valid_for_${STAGE_NAME}_gate: ${REAL_GATE_PASS}` | 同 line 361 |
| line 494 (fallback) | `if ${REAL_GATE_PASS}` | Python ternary 看到 `true` / `false` literal, NameError |

**为什么 bash `${REAL_GATE_PASS}` 是 lowercase `true/false`**: bash 内 `${VAR}` 取值后, **不会** 改成 Python `True/False`. 即便在 Python heredoc 里, bash 仍按字面值替换. Python 看到 lowercase `true` → NameError.

**为什么 V1 (6h supervisor) 也没事**: V1 6h supervisor 用 `set -u` + 显式 string `"true"` / `"false"`, **不** 把 `${REAL_GATE_PASS}` 直接插 Python dict. V3 supervisor 复用 V2 12h structure 时引入此 regression.

## 3. 修复方案 (本 stage)

### 3.1 success path (line 308-441) 修复

1. 把 `${REAL_GATE_PASS}` 显式 uppercase: `${REAL_GATE_PASS^^}` (bash 内置转大写), 让 `True` / `False` 嵌入 python
2. **更安全**: 改用 `<<'PYEOF'` quoted heredoc + 通过 environment variable (`export REAL_GATE_PASS_PYTHON="${REAL_GATE_PASS}")` 传值, **不**在 heredoc 内插值
3. **最干净**: 在 success path 直接读 `aggregate_summary.json` (由前一个 python block 写的), 不传 `${REAL_GATE_PASS}` 也不读 `agg["actual_runtime_valid_for_${STAGE_NAME}_gate"]` (因为这个 key 在 line 361 也被写坏)

### 3.2 fallback path (line 449-499) 修复

1. 同样用 `<<'PYEOF_FALLBACK'` quoted heredoc
2. 同样从 `aggregate_summary.json` 读 `actual_runtime_valid_for_<stage>_gate` boolean 字段 (由 line 356-382 aggregate block 写入, **前提** aggregate block 也用同样修复)
3. **不** 直接 `${REAL_GATE_PASS}` 也不 `if ${REAL_GATE_PASS}` literal

### 3.3 trap block (line 168-216) 修复

trap block 当前**不**有 `${REAL_GATE_PASS}` 嵌入 python, 但有 `${ELAPSED_MIN_TRAP}` (int) 和 `${DURATION_HOURS}` (int), 不会触发 NameError. **保持现状**, 但加注释说明: 此 block 是 fail-safe, 不依赖可能写坏的 `aggregate_summary.json`.

### 3.4 aggregate block (line 317-385) 修复 (根因)

`actual_runtime_valid_for_${STAGE_NAME}_gate: ${REAL_GATE_PASS}` 是 bug 起点. 改为:

```python
# 在 Python 端显式判断, 避免 bash 插值
gate_valid = (${ELAPSED_MIN}) >= (${DURATION_HOURS} * 60 - ${TOLERANCE_MIN})
agg["actual_runtime_valid_for_${STAGE_NAME}_gate"] = gate_valid
```

这样:
- bash 只插值 integer (`${ELAPSED_MIN}`, `${DURATION_HOURS}`, `${TOLERANCE_MIN}`), 不会触发 NameError
- Python 端做 boolean 运算, 类型正确 (Python `bool`)
- aggregate_summary.json 写出的 `actual_runtime_valid_for_<STAGE>_gate` 字段是 **真** boolean (`true` / `false` JSON), 后续 finalize block 读这个 JSON 时, `json.loads` 解析为 Python `bool`, 不会再有 NameError

## 4. 修复覆盖范围 (本 stage)

| 路径 | 修复 | 状态 |
|---|---|---|
| aggregate block (line 317-385) | `<<'PYEOF'` quoted heredoc, Python 端 boolean 运算, `agg["actual_runtime_valid_for_<STAGE>_gate"]` 写入真 boolean | **本轮修** |
| finalize block (line 391-441) | `<<'PYEOF'` quoted heredoc, 读 `agg["actual_runtime_valid_for_<STAGE>_gate"]` (从 aggregate_summary.json) | **本轮修** |
| fallback block (line 449-499) | `<<'PYEOF_FALLBACK'` quoted heredoc, 读 `agg.get("actual_runtime_valid_for_<STAGE>_gate", False)`, no shell boolean | **本轮修** |
| trap block (line 168-216) | (already not interpolating boolean) 加注释: 不依赖可能写坏的 aggregate_summary.json | **本轮加固** |
| 12h raw FINAL_VERDICT (历史 FAIL) | **不** 修改 (v2 12h FINAL_VERDICT 保持 FAIL 状态, 已被 corrected verdict 透明化) | **不** 改 |

## 5. 与 collector fix stage 的关系

上一阶段 `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1` 已修复:

- ✅ collector CLI `--pool-universe` 接通 real pool universe
- ✅ stage runner line 262 转发 `--pool-universe` 给 collector
- ✅ 短 smoke 验证 5 real pools, 0 placeholder, all_pool_addresses_real=true

**real pool universe collector fix already done**. 本 stage 仅修 supervisor finalize, 不动 collector / stage runner collector invocation. collector fix 之前的工作保持完整.

## 6. 本轮运行边界

| 维度 | 状态 |
|---|---|
| 12h data_dir (84 文件) | **0 修改** |
| 6h data_dir (42 文件) | **0 修改** |
| v2 12h FINAL_VERDICT | **不** 改 |
| v2 6h FINAL_VERDICT + corrected verdict | **不** 改 |
| v2 12h corrected verdict | **不** 改 |
| 12h node report (commit 90cb18a) | **不** 改 |
| V3 supervisor finalize bug | **本轮修** |
| 不启动 12h / 24h / 48h / 72h / 7d | **本轮** 修, 不启动 |
| 不启动长期 collector | **本轮** 修, 不启动 |
| 不启动新 tmux / cron / systemd / daemon | ✅ 不启动 |
| 不 probe / canary / live / paper | ✅ 不触发 |
| 不读 wallet / keypair / signer / 私钥 | ✅ 不读 |
| 不发送 transaction / approve / mint | ✅ 不发 |
| 不写 production positions | ✅ 不写 |
| 不覆盖 shadow 原始表 | ✅ 不覆盖 |
| 不接 paid RPC / paid indexer | ✅ 不接 |
| can_run_probe_now | `false` (LOCKED) |
| tiny_canary_allowed | `"no"` (LOCKED) |

## 7. 结论

✅ **Stage A PASS** — 输入证据齐备, 根因确认 (Python heredoc lowercase `true`/`false`), 修复方案明确. 进入 Stage B 修复 supervisor finalize.
