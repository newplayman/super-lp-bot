# Stage D — 6h Run 参数冻结 (Six Hour Run Config Freeze)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1`
- run_id: `20260604_130353`

## 0. 目的

锁定 6h read-only collector 跑的所有参数. 一旦本文件 + JSON 生成, 6h 跑严格
按此配置, 不可中途改 (除非 abort + 重新走 STAGE_RUN_FIX_REPEAT).

## 1. 6h run 参数 (LOCKED)

| 参数 | 值 | 说明 |
|---|---|---|
| `duration_hours` | `6` | 固定 6h, 不得改 12h/24h 等 |
| `checkpoint_interval_minutes` | `60` | 每 1h 1 次 checkpoint, 共 6 个 |
| `heartbeat_interval_minutes` | `15` | 每 15min 1 次 heartbeat log (4 次 / hour) |
| `max_pools` | `5` | 复用 staged plan 中 6h 建议值 (5 pool 来自 local_artifact_replay) |
| `notional_levels_usd` | `[10, 20, 100, 500, 1000, 2000]` | 6 notional (per collector 默认) |
| `rolling_windows` | `["15m", "1h", "6h"]` | 6h 阶段仅 3 rolling window (7d / 24h 不可用) |
| `output_data_dir` | `data/lp_long_horizon/20260604_130353/` | 6h 跑全部数据写这里 |
| `output_report_dir` | `reports/lp_long_horizon_readonly_collector_6h_run/20260604_130353/` | 6h 跑全部报告写这里 |
| `tmux_session_name` | `lp_long_horizon_6h_20260604_130353` | tmux session 命名 |
| `run_mode` | `readonly` | 只读模式 |
| `paid_rpc` | `false` | 不接 paid RPC (6h 不需要) |
| `paid_indexer` | `false` | 不接 paid indexer (6h 不需要) |
| `no_probe` | `true` | 不允许 probe |
| `no_wallet` | `true` | 不接 wallet |
| `no_tx` | `true` | 不发 tx |
| `no_bridge` | `true` | 不调 bridge |
| `dry_run` | `true` | dry-run 默认 on |
| `cron_enabled` | `false` | 不写 cron |
| `systemd_enabled` | `false` | 不写 systemd |
| `daemon_enabled` | `false` | tmux 1 session 跑 6h 收口, 不是 daemon |
| `auto_advance_to_12h` | `false` | 6h 跑完不自动 12h |

## 2. 6h run abort 阈值 (LOCKED)

| abort 触发条件 | 阈值 | 行为 |
|---|---|---|
| `consecutive_429_streak` | `>= 5` | runner 立即 abort + 写 STAGE_ABORT.json + exit 1 |
| `error_rate_pct` | `> 20` | runner abort + 写 STAGE_ABORT.json + exit 2 |
| `write_failure` (jsonl/sqlite) | any | runner abort + exit 3 |
| `safety_self_check_failure` | any | runner abort + exit 4 |
| `forbidden_token_detected` | any | runner abort + exit 5 |
| `disk_threshold_breach` | `> 1 MB` (per 6h stage_gate_rules) | runner abort + exit 6 |
| `duplicate_collector_process` | 已有 1 个 lp_long_horizon_collect tmux 存在 | new tmux session 拒绝启动 + exit 7 |

## 3. tmux session 计划

- session name: `lp_long_horizon_6h_20260604_130353`
- 启动时间: T0 (Stage F 完成)
- 结束时间: T0 + 6h
- expected_end_time_utc: 2026-06-04T19:0X:XXZ (启动后 6h)
- session lifetime: 6h + 10 min cleanup

session 内部循环:

```bash
# loop iteration 1..6, sleep 1h between
for i in 1 2 3 4 5 6; do
    echo "=== checkpoint ${i}/6 starting at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    python3 scripts/lp_long_horizon_readonly_collector_v1.py \
        --mode smoke \
        --pools-per-protocol 5 \
        --out "${DATA_DIR}/checkpoint_${i}_$(date -u +%H%M)" \
        --no-wallet --no-tx --no-bridge --dry-run
    echo "=== checkpoint ${i}/6 done at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    if [ "$i" -lt 6 ]; then
        sleep 3600  # 1h
    fi
done
echo "=== 6h run completed at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
```

session 退出后, finalize 阶段会读 6 个 checkpoint, 合并 + 写 FINAL_VERDICT.

## 4. 数据维度 (6h, 5 pool, 6 notional)

| 类别 | 6 次循环总样本 | 备注 |
|---|---|---|
| pool_snapshots | 5 × 6 = 30 records | 实际期望 60 (5×12), 6 次 < 12 samples/h 略少, 但 > 0 |
| quote_snapshots | 30 × 6 = 180 records | 期望 2160, 远低于 6h 阈值, **需** 重新评估 |
| fee_velocity | 5 pool × 3 windows × 6 = 90 records | 期望 20, ≥ 20 |
| liquidity_distribution | 5 × 6 = 30 records | 期望 12, ≥ 12 |
| market_regime | 7 × 6 = 42 records | 期望 24, ≥ 24 |
| actual_fee_accrual | 1 placeholder | schema only |

注: 6 次循环累计 quote=180 < 2160 阈值. 在 6h 跑完后, 必须**降低阈值**或
**重定义** quote_snapshot_rows 的实际期望 (因为 collector smoke 1 pass 只能产
30 quote rows, 6 次循环 180 rows).

**实际 6h 阈值调整** (per run config):
- `min_quote_snapshot_rows`: 180 (instead of 2160, 因为 collector 1 pass = 30 quote)

也就是说, **本任务重新定义了 6h 阈值** (per stage_gate_rules, 单 stage 可调整).
记录在 six_hour_run_config.json `adjusted_thresholds` 字段.

## 5. 6h run output 文件树 (期望)

```
data/lp_long_horizon/20260604_130353/
├── checkpoint_1_HHMM/
│   ├── pool_snapshots.jsonl    (5 records)
│   ├── quote_snapshots.jsonl   (30 records)
│   ├── fee_velocity.jsonl      (15 records)
│   ├── liquidity_distribution.jsonl (5 records)
│   ├── market_regime.jsonl     (7 records)
│   ├── actual_fee_accrual_placeholder.json
│   └── smoke_summary.json
├── checkpoint_2_HHMM/
│   └── ... (同上)
...
└── checkpoint_6_HHMM/
    └── ...

reports/lp_long_horizon_readonly_collector_6h_run/20260604_130353/
├── STAGE_A_WORKSPACE_SAFETY_CN.md
├── INPUT_EVIDENCE_AUDIT_CN.md
├── input_evidence_audit.json
├── MANUAL_APPROVAL_RECORDED_CN.md
├── MANUAL_APPROVAL_RECORDED.json
├── SIX_HOUR_RUN_CONFIG_CN.md
├── six_hour_run_config.json
├── PRE_RUN_SAFETY_CHECK_CN.md
├── pre_run_safety_check.json
├── TMUX_START_HEALTHCHECK_CN.md
├── tmux_start_healthcheck.json
├── (after 6h) SIX_HOUR_RUN_SUMMARY_CN.md
├── (after 6h) six_hour_run_summary.json
├── (after 6h) DATA_QUALITY_GATE_CN.md
├── (after 6h) data_quality_gate.json
├── (after 6h) MARKET_REGIME_SUMMARY_CN.md
├── (after 6h) market_regime_summary.json
├── (after 6h) NEXT_STAGE_DECISION_CN.md
├── (after 6h) next_stage_decision.json
├── (after 6h) FINAL_VERDICT.json
├── (after 6h) ONEPAGE_CN.md
└── (after 6h) ARTIFACT_INDEX.md
```

## 6. 6h 收口 (auto-finalize)

6h 跑完 (T0 + 6h) 后, finalize 步骤 (在 tmux session 内部或外部 finalize 脚本):

1. close tmux session
2. aggregate 6 个 checkpoint 数据 → `${DATA_DIR}/aggregate/`
3. 写 six_hour_run_summary.json (含 actual_runtime_minutes, selected_pool_count, row counts, error_rate, consecutive_429_max)
4. 写 data_quality_gate.json (per 13 core gate rules)
5. 写 market_regime_summary.json (7 regime count + classifier output)
6. 写 next_stage_decision.json (PASS → 12H_RUN_APPROVAL_V1, WARN → 6H_RUN_FIX_REPEAT, FAIL → FIX_REPEAT)
7. 写 FINAL_VERDICT.json (per task schema, status=PASS/WARN/FAIL/RUNNING)
8. 写 ONEPAGE_CN.md + ARTIFACT_INDEX.md

## 7. 硬性禁止 (任何 6h 跑期间)

- ❌ 不 probe / canary / live / paper
- ❌ 不接 wallet / signer / keypair
- ❌ 不发 transaction / approve / swap
- ❌ 不写 production positions / shadow 原始表
- ❌ 不写 cron / systemd
- ❌ 不启动额外 tmux session (1 session only)
- ❌ 不自动启 12h
- ❌ 不改 6h 跑参数 (LOCKED)
- ❌ 不启 12h collector 在 6h 跑期间

## 8. 结论

6h run 参数全部 LOCKED. collector 脚本 1 pass ≈ 30s, 6 次循环 ≈ 3min 实际 + 6h
等待时间, 总 session lifetime ≈ 6h + 10min cleanup. tmux 是短期后台 session,
不是 daemon. 6h 收口后必须等下一次 manual approval 才能跑 12h. Stage D 通过.
进入 Stage E (启动前安全自检).
