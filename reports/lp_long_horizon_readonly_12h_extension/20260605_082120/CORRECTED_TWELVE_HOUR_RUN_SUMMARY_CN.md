# Corrected 12h Run Summary (重建自 checkpoint)

- stage: `LP_LONG_HORIZON_12H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1`
- source_run_id: `20260605_082120`
- source_verdict_path: `reports/lp_long_horizon_readonly_12h_run/20260605_082120/FINAL_VERDICT.json`
- source_verdict_status: **FAIL** (supervisor_finalize_failed=true; trap EXIT rc=1; post-12h python block NameError on lowercase 'true' from bash ${REAL_GATE_PASS} interpolated into Python ternary)
- corrected_at_utc: `2026-06-06T07:32:00Z`
- corrected_from_checkpoints: **true**

## 0. 一句话

12h supervisor 跑满了 12h wallclock (T0=2026-06-05T14:57:39Z, T_end=2026-06-06T02:57:39Z, 实际 720 min), 12 个 checkpoint 全部生成 (84 文件). 但 post-12h python block 因 `bash ${REAL_GATE_PASS} 变量被插值成 lowercase 'true' (而非 Python 'True')` 触发 NameError, 最终 FINAL_VERDICT 由 fail-safe trap 写 default-zeros (覆盖真实数据). 本 rebuild 脚本从 12 个 checkpoint dir 重建正确 verdict, 写到 CORRECTED_FINAL_VERDICT.json, **不**覆盖 V2 12h 原始 FAIL verdict.

## 1. 实际运行时间

- actual_runtime_minutes: **720**
- expected_min_runtime_minutes: 660 (12h - 1h tolerance)
- actual_runtime_valid_for_12h_gate: **true**
- short_mode_used: **false** (LOCKED)

## 2. row counts (rebuilt from data_dir)

| 类别 | count |
|---|---|
| selected_pool_count | 5 (smoke placeholder deduped) |
| pool_snapshot_rows | 5 |
| quote_snapshot_rows | **360** (30 × 12 ckpts) |
| fee_velocity_rows | **300** (25 × 12 ckpts) |
| liquidity_distribution_rows | **60** (5 × 12 ckpts) |
| market_regime_rows | **84** (7 × 12 ckpts) |
| actual_fee_accrual_placeholder_rows | **12** (1 × 12 ckpts) |

## 3. safety 字段 (LOCKED)

- wallet_or_tx_touched: **false**
- transaction_sent: **false**
- no_production_write: **true**
- no_shadow_overwrite: **true**
- can_run_probe_now: **false**
- tiny_canary_allowed: **"no"**
- send_hard_disable_still_active: **true**
- auto_advance_started: **false**
- longer_stage_started: **false**

## 4. checkpoint 状态

12 个 checkpoint 全部存在, 全部含 7 文件 (pool/quote/fee/liq/regime/actual_fee/summary). T0=14:57:39Z, ckpt_12 完成 at 01:57:51Z, supervisor log 显示 `[12h end] 2026-06-06T02:57:39Z elapsed_min=720 (target END_TS=1780714659)`.

## 5. 重建方法

读 `data/lp_long_horizon/20260605_082120/` 12 个 checkpoint dir, dedup 聚合 row counts (per pool_address, per (pool_address, notional, quote_at)). 与 V3 supervisor Stage 3 aggregate logic 相同, 但 V3 supervisor 自身 Stage 3-4 触发 NameError, 故需要 rebuild.

## 6. 与 V2 12h FINAL_VERDICT 差异

| 字段 | V2 12h FINAL_VERDICT | CORRECTED |
|---|---|---|
| status | FAIL | **PASS** |
| selected_pool_count | 0 | 5 |
| pool_snapshot_rows | 0 | 5 |
| quote_snapshot_rows | 0 | **360** |
| fee_velocity_rows | 0 | **300** |
| liquidity_distribution_rows | 0 | **60** |
| market_regime_rows | 0 | **84** |
| actual_fee_accrual_placeholder_rows | (n/a) | **12** |
| gate_pass | false | **true** |
| data_quality_status | FAIL | **data_quality_ok** |
| coverage_scope | (n/a) | **partial_solana_real_pool_universe** |
| do_not_treat_as_full_coverage | (n/a) | **true** |
| selected_real_pool_count | 33 | **33** |
| placeholder_pool_count | 0 | **0** |

## 7. coverage_scope + 缺失协议 (honest disclosure)

`coverage_scope = partial_solana_real_pool_universe` (not full multi-chain coverage). 缺失:

- Meteora DLMM (solana/meteora_dlmm) — no Go pool adapter
- Base Uniswap V3 (base/uniswap_v3) — Go adapter exists, EVM collector not wired
- Base Aerodrome (base/aerodrome) — same
- BSC PancakeSwap V3 (bsc/pancakeswap_v3) — BSC chain adapter not implemented
- BSC PancakeSwap V2 (bsc/pancakeswap_v2) — same

`selected_real_pool_count = 33` < `target_min_pool_count = 45` (gap=12). Meteora DLMM 至少 10 池缺失 + 4 EVM 池.

## 8. 12h supervisor finalize bug root cause

`scripts/run_lp_long_horizon_readonly_stage_once.sh` Stage 4 (FINAL_VERDICT 写) + V3 fix (CORRECTED_FINAL_VERDICT_FALLBACK.json) **两个 python heredoc 都用了 bash `${REAL_GATE_PASS}` 变量在 Python ternary 中**:
```python
"recommended_next_stage": "X" if ${REAL_GATE_PASS} else "Y"
```
bash interpolation 把 `${REAL_GATE_PASS}` 替换为 lowercase `true` (或 `false`), Python 看到 `if true else` 触发 NameError. 两次都 crash. trap EXIT 写 default-zeros.

**修复路径** (下一轮):
- Stage 4 line 435 + V3 fix line 493: 把 `${REAL_GATE_PASS}` 替换为 `${REAL_GATE_PASS^^}` (bash 变量大写) **或** 用 Python 字符串 `"X" if agg["actual_runtime_valid_for_12h_gate"] else "Y"` (引用 aggregate 的 Python boolean, 而不是 bash 变量)
- V3 fix 的 CORRECTED_FINAL_VERDICT_FALLBACK.json 也没有真正生效 (fallback heredoc 同样有 `${REAL_GATE_PASS}` bug)
- 建议下一轮改用 `<<'PYEOF'` (quoted heredoc, 不让 bash 插值), 让 Python 看到 `$REAL_GATE_PASS` 字符串, 然后用 `os.environ.get('REAL_GATE_PASS')` 读取

## 9. next_stage 推荐

`recommended_next_stage = LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT` — 先生成 12h 节点报告透明化覆盖范围, 然后用户单独审批是否做 Meteora DLMM / Base/BSC adapter coverage fix, **不**是直接 24h.

**严禁 auto 24h**. 即便 gate=PASS, coverage_scope=partial_solana_real_pool_universe 不允许推进 24h.
