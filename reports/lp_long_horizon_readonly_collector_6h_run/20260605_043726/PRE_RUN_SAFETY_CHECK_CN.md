# V2 启动前安全检查 (Pre-Run Safety Check)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT_V2`
- run_id: `20260605_043726`
- check_at_utc: `2026-06-05T04:48:00Z`
- author: Agent (Claude Opus 4.8)
- branch: `feat/supabase-postgres-deployment`

## 0. 总结

**所有 8 项 pre-run 安全检查全部通过**. V2 supervisor 启动条件已满足.

## 1. 检查项 (8 项)

| # | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 1 | 无已有 lp_long_horizon tmux session | ✅ | `tmux ls` 无匹配 |
| 2 | 无 canary / live / paper / wallet / keypair 进程 | ✅ | `ps -ef` 无匹配 |
| 3 | 数据目录可写 | ✅ | write test 通过 (`data/lp_long_horizon/20260605_043726/`) |
| 4 | 报告目录可写 | ✅ | write test 通过 (`reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/`) |
| 5 | supervisor 脚本可执行 + 语法 OK | ✅ | `bash -n` 通过, executable bit set |
| 6 | V2 pytest 全部通过 | ✅ | 25/25 passed in 0.45s |
| 7 | V1 已标记 FAIL, 不可作为 12h gate | ✅ | V1 salvage FINAL_VERDICT.json status=FAIL, gate_pass=false, can_advance_to_12h=false |
| 8 | V1 data 保留, 不可篡改 | ✅ | `data/lp_long_horizon/20260604_134918/` 6 ckpt × 7 文件 = 42 文件 完整 |

## 2. V2 supervisor 关键修复确认 (V1 双 bug 已修)

| Bug | V1 状态 | V2 状态 | pytest 验证 |
|---|---|---|---|
| bash loop 缺 1 次 sleep (5h 而非 6h) | FAIL (300.12 min) | **FIXED** (END_TS-based, sleep until 6h) | test_v1_loop_bug_fixed ✅ |
| Python heredoc `false` typo → NameError | FAIL (finalize 崩溃) | **FIXED** (false → False + fail-safe trap) | test_no_lowercase_false_in_python_heredoc ✅ |
| finalize 失败无任何记录 (V1 silent loss) | FAIL (no FINAL_VERDICT) | **FIXED** (trap EXIT/SIGTERM/SIGINT/SIGHUP writes FAIL verdict) | test_v2_fail_safe_trap_present ✅ |

## 3. V2 supervisor 关键硬保证

- `SLEEP_SECONDS=3600` (LOCKED, 拒绝 SLEEP_SECONDS<3600 → exit 8)
- `LOOP_COUNT=6` (LOCKED, 拒绝 LOOP_COUNT≠6 → exit 9)
- `set -euo pipefail` (脚本第 17 行, 启用严格模式)
- `END_TS = START_TS + 6 * 3600` (V2 wallclock 逻辑)
- trap EXIT / SIGTERM / SIGINT / SIGHUP 写 FAIL FINAL_VERDICT
- approval phrase 校验: `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=6h mode=readonly no_probe=true`
- 推荐 next_stage 限于 5 个 allowed 集合

## 4. V2 pytest 25/25 全部通过

```
============================= 25 passed in 0.45s ==============================
```

| 测试组 | 数量 | 覆盖 |
|---|---|---|
| V1 loop bug fix | 2 | V2 wallclock logic, END_TS-based |
| 5h runtime gate | 2 | gate threshold 330, FAIL verdict on 5h |
| short mode 拒绝 | 3 | SLEEP_SECONDS<3600, LOOP_COUNT≠6, short_mode_used=true cannot pass |
| Python heredoc | 2 | no lowercase false, finalize block runs |
| V2 fail-safe | 2 | trap present, set -euo pipefail |
| no auto-advance | 1 | auto_advance_started=False, no auto_launch_12h |
| banned tokens | 4 | no signer/tx/wallet/production/shadow |
| V1 salvage integrity | 3 | FINAL_VERDICT complete, audit acknowledged, can_run_probe_now=false |
| process safety | 2 | no canary/live/keypair, no extra tmux |
| V2 smoke | 3 | supervisor executable, V2 stage name, 5h audit |

## 5. V1 状态确认 (不可作为 12h gate)

V1 (`20260604_134918`) salvage FINAL_VERDICT 字段:

- `status`: **FAIL**
- `six_hour_run_completed`: **false**
- `actual_runtime_minutes`: **300.12** (5h 0m 7s, 期望 360)
- `actual_runtime_valid_for_6h_gate`: **false** (300 < 330)
- `short_mode_used`: **false** (SLEEP_SECONDS=3600)
- `gate_pass`: **false**
- `can_advance_to_12h`: **false**
- `recommended_next_stage`: **`LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT_V2`**

V1 数据保留 (`data/lp_long_horizon/20260604_134918/`, 42 文件), 不可篡改, 供 V2 复用 / 审计.

## 6. V2 启动前不变式 (per task spec)

- `can_run_probe_now = false` ✅
- `tiny_canary_allowed = "no"` ✅
- `auto_advance_started = false` ✅
- `longer_stage_started = false` ✅
- 无 canary / live / paper / wallet / keypair 进程 ✅
- 无 cron / systemd ✅
- 无 production write ✅
- 无 shadow overwrite ✅
- 无 daemon leak ✅

## 7. 结论

V2 启动前安全检查 8/8 全部通过. V2 supervisor (`scripts/run_lp_long_horizon_readonly_6h_once.sh`) V1 双 bug 已修 + fail-safe trap 已加. V2 pytest 25/25 全部通过. V1 已标记 FAIL, 不可作为 12h gate. **V2 启动就绪**.
