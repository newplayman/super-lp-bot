# Stage E — 6h Supervisor 脚本实现 (6h Supervisor Script Implementation)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1`
- run_id: `20260604_134918`

## 0. 实现文件

- `scripts/run_lp_long_horizon_readonly_6h_once.sh` (executable, 27KB, 305 lines)

## 1. 脚本职责

1. **preflight 校验**:
   - hard reject `SLEEP_SECONDS < 3600` (short mode forbidden, exit 8)
   - hard reject `LOOP_COUNT != 6` (override forbidden, exit 9)
   - hard reject approval phrase mismatch (exit 11)
   - hard reject existing tmux session (exit 13)
   - hard reject forbidden process (canary / live / paper / sendTransaction / keypair)
   - hard reject unwritable data dir / report dir

2. **real 6h loop**:
   - `LOOP_COUNT=6` (LOCKED)
   - `SLEEP_SECONDS=3600` (1h per iteration, LOCKED)
   - 6 checkpoint × 1h sleep = 6h wallclock
   - 1 checkpoint ≈ 30s collector work, 59m30s sleep
   - heartbeat every 15 min (4 per hour) = 24 heartbeats over 6h

3. **gate validation at finalize**:
   - `actual_runtime_minutes = (END_TS - START_TS) / 60`
   - if < 330 → gate FAIL, status=FAIL (硬 fail, 不允许 short mode 冒充)
   - else → gate PASS, status=PASS

4. **row aggregation**:
   - dedup 6 checkpoint records (按 pool_address / (pool_address, notional, quote_at) 去重)
   - 写 aggregate_summary.json

5. **report writing** (8 份):
   - `SIX_HOUR_RUN_SUMMARY_CN.md` + `.json`
   - `DATA_QUALITY_GATE_CN.md` + `.json`
   - `MARKET_REGIME_SUMMARY_CN.md` + `.json`
   - `NEXT_STAGE_DECISION_CN.md` + `.json`
   - `FINAL_VERDICT.json`
   - `ONEPAGE_CN.md`
   - `ARTIFACT_INDEX.md`

6. **auto commit + push**:
   - `git add reports/.../6h_fix/${RUN_ID} reports/.../6h_run/${RUN_ID} data/lp_long_horizon/${RUN_ID} scripts tests`
   - `git commit -m "research: finalize real 6h long horizon readonly collector ${RUN_ID}"`
   - `git push origin feat/supabase-postgres-deployment`

7. **tmux cleanup**:
   - `tmux kill-session -t lp_long_horizon_6h_${RUN_ID}` at exit
   - 防止 session leak

## 2. short mode / override hard reject

```bash
# HARD GUARD: short mode forbidden
if [ "${SLEEP_SECONDS}" -lt 3600 ]; then
    echo "REFUSED: SLEEP_SECONDS=${SLEEP_SECONDS} < 3600 (short mode forbidden)" >&2
    exit 8
fi

# HARD GUARD: loop count forbidden
if [ "${LOOP_COUNT}" -ne 6 ]; then
    echo "REFUSED: LOOP_COUNT=${LOOP_COUNT} != 6 (override forbidden)" >&2
    exit 9
fi
```

任务规范硬性要求: "禁止使用 LOOP_COUNT=6 SLEEP_SECONDS=10 这类短模式冒充".
脚本 exit 8 + 8 类 abort condition 之一 (short_mode_detected) 保证 hard reject.

## 3. supervisor 与 tmux session 关系

| 阶段 | 实体 | 生命周期 |
|---|---|---|
| tmux session | lp_long_horizon_6h_${RUN_ID} | 6h + 10 min cleanup |
| supervisor script | bash run_lp_long_horizon_readonly_6h_once.sh | 同 tmux session |
| collector 子进程 | python3 lp_long_horizon_readonly_collector_v1.py --mode smoke | per checkpoint (≈30s) |
| sleep 子进程 | bash sleep $((3600/4)) | per heartbeat (15min) |

Agent **不需要**前台等 6h. Agent 启动 tmux session 后立即**早回报** (Stage G),
tmux session 6h 内在 VPS 跑完, supervisor 自动 finalize + auto commit + auto push,
然后**晚回报** (Stage H) 通过 git log / git status 看到 auto push 痕迹.

## 4. safety 21 字段继承 (per task spec + previous 6h best practice)

- `touched_trading_path = false` (LOCKED)
- `touched_wallet_tx_bridge_live_paper = false` (LOCKED)
- `wallet_or_tx_touched = false` (LOCKED)
- `transaction_sent = false` (LOCKED)
- `send_hard_disable_still_active = true` (LOCKED)
- `no_paid_rpc_integration = true` (LOCKED)
- `no_paid_indexer_integration = true` (LOCKED)
- `no_protocol_re_run = true` (LOCKED)
- `no_heuristic_modification = true` (LOCKED)
- `no_long_running_daemon = true` (tmux is short-lived session, not persistent)
- `no_signer_creation = true` (LOCKED)
- `no_12h_24h_48h_72h_7d_run = true` (LOCKED, no auto advance)
- `no_auto_advance = true` (LOCKED)
- `no_cron_enabled = true` (LOCKED)
- `no_systemd_enabled = true` (LOCKED)
- `no_extra_tmux_session = true` (max 1 session)
- `no_actual_daemon = true` (tmux is short-lived)
- `no_approval_recorded_for_other_stages = true` (only 6h approved)
- `secret_leak_count = 0` (LOCKED)
- `production_write_count = 0` (LOCKED)
- `shadow_overwrite_count = 0` (LOCKED)

## 5. 与 collector 脚本集成

supervisor 调用 `scripts/lp_long_horizon_readonly_collector_v1.py --mode smoke`,
per checkpoint:
```bash
python3 scripts/lp_long_horizon_readonly_collector_v1.py \
    --mode smoke \
    --pools-per-protocol 5 \
    --out "${CKPT_DIR}" \
    --no-wallet --no-tx --no-bridge --dry-run
```

`--mode smoke` 是 collector 1-pass 模式 (per smoke_v1 fix_repeat_v1),
不依赖 paid RPC, 不写 production 路径, 写 research-only 数据.

## 6. 异常处理

| 异常 | 处理 |
|---|---|
| short mode detected | exit 8, 写 supervisor.log 标注 |
| override LOOP_COUNT | exit 9, 写 supervisor.log 标注 |
| approval phrase missing | exit 11, 写 supervisor.log 标注 |
| existing tmux session | exit 13, 写 supervisor.log 标注 |
| forbidden process | exit 14, 写 supervisor.log 标注 |
| unwritable data dir | exit 15, 写 supervisor.log 标注 |
| unwritable report dir | exit 16, 写 supervisor.log 标注 |
| collector checkpoint failed | exit 1, 写 supervisor.log 标注 |
| actual_runtime < 330 at finalize | gate FAIL, 仍写 FINAL_VERDICT status=FAIL, exit 0 (auto-push) |

**关键**: 任何 exit 都先写 supervisor.log + 写 FINAL_VERDICT, **不**让 supervisor 默默退出.
auto commit + push 用 `|| { echo "skipped" }` 防 git error 阻塞.

## 7. supervisor 与 auto commit/push 集成

任务规范 H 明确: "完成后自动 commit + push".

supervisor 末尾包含:
```bash
git add "reports/lp_long_horizon_readonly_collector_6h_fix/${RUN_ID}" \
        "reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID}" \
        "data/lp_long_horizon/${RUN_ID}" \
        scripts tests
git commit -m "research: finalize real 6h long horizon readonly collector ${RUN_ID}"
git push origin feat/supabase-postgres-deployment
```

`git commit` 失败 (无变化) 用 `|| { echo "skipped"; }` 容错.
`git push` 失败 仍写 supervisor.log, manual review needed (但**不**让 tmux session 卡死).

## 8. 结论

6h supervisor 脚本 (`scripts/run_lp_long_horizon_readonly_6h_once.sh`) 完整实装.
- 默认 LOOP_COUNT=6 SLEEP_SECONDS=3600 (real 6h wallclock)
- hard reject short mode / override
- 6 个 checkpoint 全部生成 + aggregate
- 8 份报告自动写
- auto commit + push
- auto kill tmux

Agent 启动 tmux session 后**早回报**, 不需要前台等 6h. supervisor 在后台 6h 跑完 + finalize.
Stage E 通过. 进入 Stage F (启动前安全自检).
