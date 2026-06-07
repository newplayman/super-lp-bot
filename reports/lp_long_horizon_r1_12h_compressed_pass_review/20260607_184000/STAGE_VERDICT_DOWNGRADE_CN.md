# R1 12h Compressed Pass Review — Stage Verdict Downgrade

- prior_commit: `7aba170`
- prior_run_id: `20260607_171000`
- prior_stage: `LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1`
- review_run_id: `20260607_184000`
- review_stage: `LP_LONG_HORIZON_R1_12H_COMPRESSED_PASS_REVIEW_V1`
- review_audited_at_utc: `2026-06-07T18:40:00Z`
- branch: `feat/supabase-postgres-deployment`
- new_stage_verdict: **`R1_12H_SHORT_COMPRESSED_PASS_NOT_FULL_WALLCLOCK`**

## 0. 一句话

按 user 验收, 上一轮 commit `7aba170` 的 "R1 12h PASS" verdict **不** 接受为真实 12h wallclock 毕业. 原因: 实际 runtime 仅 263s / 4.38 min (12 ckpt × 10s sleep = 120s + 12 × 11s collector = 132s), 是 **compressed runner smoke**, **不** 是 真实 12h wallclock observation. Stage verdict 降级为 `R1_12H_SHORT_COMPRESSED_PASS_NOT_FULL_WALLCLOCK`, 并启动 真正 12h wallclock repeat (`LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V1`).

## 1. 上一轮 (7aba170) 实际状态 (诚实重述)

| 字段 | 7aba170 实际值 | 含义 |
|---|---|---|
| `r1_12h_completed` | `true` | 12/12 ckpt 跑完 |
| `wallclock_compressed` | **`true`** (诚实披露) | sleep=10s/ckpt, **不** 3600s |
| `actual_runtime_minutes` | **4.38** | 263s |
| `actual_runtime_seconds` | **263** | < 43200s (12h) |
| `short_sleep_seconds_per_iteration` | 10 | = compressed |
| `gate_decision` | DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE | 保留 |
| 12 ckpt 间隔 | ~10s (compressed) | **不** ~3600s |
| 数据层 | 6 dim 全 row, watchlist 7→7 | OK |
| forbidden actions | 0 | OK |
| 真实 12h wallclock stability | **未** 验证 | FAIL 12h gate |
| 实际可代表 12h observation | **否** (compressed) | 降级 |

## 2. Stage Verdict 降级 (per user acceptance)

**之前 (7aba170)**: `status=PASS, gate_decision=DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE`
**降级后**: `status=COMPRESSED_PASS, stage_verdict=R1_12H_SHORT_COMPRESSED_PASS_NOT_FULL_WALLCLOCK, gate_decision=DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE (still)`

**重要**: gate_decision 保留 = 数据层 / forbidden actions 仍 OK, 但**不** = 12h wallclock 毕业. **不**允许:
- ❌ 称为 R1 12h 毕业
- ❌ 进入 R2
- ❌ 翻 freeze / actual_fee / can_run_probe_now / tiny_canary_allowed / edge_proven
- ❌ 翻 fee_proxy_only (仍是 true)
- ❌ 翻 auto_advance_to_24h (仍 false)

## 3. 关键发现 (7aba170 报告的事后诚实)

### 3.1 7aba170 **没** 证明

- ❌ **没** 证明 12h real wallclock 数据稳定性
- ❌ **没** 证明 12 ckpt × 3600s 间隔的稳定性
- ❌ **没** 证明 12h 内任何 source health 变化
- ❌ **没** 证明 12h 内 watchlist drift / extension / shrink (短跑无 evolution)
- ❌ **没** 证明 market regime 12h 趋势 (仅 1 个 snapshot × 2 chain × 5min data)
- ❌ **没** 证明 fee/liquidity/ev source 跨 12h 变化 (短跑无 evolution)

### 3.2 7aba170 **证明**了

- ✅ R1 12h runner script 可跑 (supervisor + heartbeat + aggregate)
- ✅ R1 schema 6 dimensions 可在 12 ckpt 持续产出 row
- ✅ R1 collector whitelist fix 后可写 12 ckpt 数据
- ✅ Aggregate function 可聚合 watchlist + ready + source health 跨 ckpt
- ✅ Report deliverable pipeline (8 files) 可生成
- ✅ forbidden actions 全部 0
- ✅ source health 诚实记录 (无 fake data)

## 4. 修正 7aba170 结论

| 维度 | 7aba170 (before patch) | 修正后 (after patch) |
|---|---|---|
| 标题 | "R1 12h 12/12 ckpt 跑通, gate=PASS" | "R1 12h **compressed runner smoke pass**, **不** = full 12h wallclock pass" |
| `status` | `PASS` | `COMPRESSED_PASS` |
| `stage_verdict` | (n/a) | `R1_12H_SHORT_COMPRESSED_PASS_NOT_FULL_WALLCLOCK` |
| `gate_decision` | DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE | (保留, 数据层 PASS) |
| `can_run_probe_now` | `false` (LOCKED) | `false` (LOCKED, **不** 翻) |
| `tiny_canary_allowed` | `"no"` (LOCKED) | `"no"` (LOCKED, **不** 翻) |
| `edge_proven` | `"no"` (LOCKED) | `"no"` (LOCKED, **不** 翻) |
| `actual_fee_data_available` | `false` (LOCKED) | `false` (LOCKED, **不** 翻) |
| `fee_proxy_only` | `true` | `true` (R1 ≠ actual fee) |
| `wallet_or_tx_touched` | `false` | `false` (✅ 保持) |
| `transaction_sent` | `false` | `false` (✅ 保持) |
| `auto_advance_to_24h` | `false` | `false` (✅ 保持) |

## 5. 修正 commit (7aba170 → 7aba170 + patch)

**本 patch 提交**: `research: downgrade 7aba170 verdict to R1_12H_SHORT_COMPRESSED_PASS_NOT_FULL_WALLCLOCK`

**内容**:
- 修改 `reports/lp_long_horizon_r1_12h_real_data_observation/20260607_171000/FINAL_VERDICT.json`:
  - `status: PASS` → `status: COMPRESSED_PASS`
  - 新增 `stage_verdict: R1_12H_SHORT_COMPRESSED_PASS_NOT_FULL_WALLCLOCK`
  - 新增 `compressed_disclosure: { wallclock_compressed: true, short_sleep: 10, actual_runtime_seconds: 263, <_12h_threshold: 43200, NOT_full_wallclock: true }`
  - 保留所有 LOCKED fields (can_run_probe_now, tiny_canary_allowed, edge_proven, actual_fee_data_available, fee_proxy_only, wallet_or_tx_touched, transaction_sent, auto_advance_to_24h, longer_stage_started)
- 修改 `reports/lp_long_horizon_r1_12h_real_data_observation/20260607_171000/R1_12H_OBSERVATION_REPORT_CN.md`:
  - 标题 + 总结改为诚实 compressed runner smoke pass
  - 标注 **不** = 12h wallclock observation 毕业
- 修改 `reports/lp_long_horizon_r1_12h_real_data_observation/20260607_171000/ONEPAGE_CN.md`: 同上
- **不** 修改 data/, **不** 修改 scripts/, **不** 修改 tests/ (旧 test 仍 7aba170 pass, 因 FINAL_VERDICT.json 仍存在 LOCKED fields)

## 6. 后续: 真正 12h wallclock repeat

**下一 stage**: `LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V1`
- 使用 `scripts/run_lp_long_horizon_r1_12h_stage_once.sh` (full wallclock supervisor, **不** short)
- 硬性参数: duration_wallclock_seconds >= 43200, checkpoint_count = 12, checkpoint_interval_seconds = 3600
- coverage_scope: `partial_solana_bsc_real_universe_r1_12h_full_wallclock`
- new_data_dir: `data/lp_long_horizon_r1_12h_full_wallclock/<RUN_ID>/`
- new_report_dir: `reports/lp_long_horizon_r1_12h_full_wallclock_observation/<RUN_ID>/`
- 严禁 short supervisor / compressed sleep / fast-forward

## 7. 锁定字段 (本 patch 期间仍不翻)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | freeze |
| `tiny_canary_allowed` | `"no"` | freeze |
| `edge_proven` | `"no"` | R1 12h compressed ≠ edge |
| `actual_fee_data_available` | `false` | R1 ≠ actual fee |
| `fee_proxy_only` | `true` | R1 ≠ actual fee |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |
| `auto_advance_to_24h` | `false` | **不** 自动 |
| `longer_stage_started` | `false` | **不** 自动 |
| `auto_advance_to_r2` | `false` | **不** 自动 |

## 8. 严禁 (本 patch 期间)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动 full wallclock repeat (本 patch 仅修正 verdict, **不** 启 12h)
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / add/remove liquidity / collect / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 R0 collector / adapters
- ❌ 不覆盖 7aba170 data dir (data/lp_long_horizon_r1_12h/20260607_171000/) — 这是 compressed run, **不** 抹除
- ❌ **不** 翻 actual_fee_data_available / can_run_probe_now / tiny_canary_allowed / edge_proven
- ❌ **不** 翻 fee_proxy_only
- ❌ **不** mint 实际 LP NFT 仓位
- ❌ **不** 进入 R2 (本 patch **不** 触发 R2)
