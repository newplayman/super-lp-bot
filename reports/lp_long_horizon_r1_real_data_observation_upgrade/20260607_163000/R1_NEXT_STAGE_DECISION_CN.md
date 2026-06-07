# R1 Next-Stage Decision

- stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`
- run_id: `20260607_163000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T17:10:00Z`
- r1_smoke_ran: true
- r1_smoke_status: PASS

## 0. 一句话

R1 smoke 跑通, 6 dimensions **全部**有非零 row count (20/120/100/20/2/20), market regime 真实 CoinGecko data, 7 BSC V3 池 watchlist (medium confidence), data_insufficient 0. Per spec 规则 ("如果 R1 smoke 生成了非零真实数据 → 推荐 LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1"), **推荐** next stage = **`LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1`** (R1 12h 扩展, 12h 跑通验证 R1 stability + watchlist evolution + data quality).

## 1. spec 决策规则

### 1.1 spec 规则

```
如果 R1 smoke 生成了非零真实数据：
  pool_snapshot_rows > 0
  quote_snapshot_rows > 0
  fee_velocity_rows > 0
  liquidity_distribution_rows > 0
  candidate_review_rows > 0
则推荐 LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1

如果 R1 smoke 仍全是 0 或 placeholder：
推荐 fix repeat。

不得选择 probe/live/canary。
```

### 1.2 R1 smoke 实际状态 (rules match)

| Metric | 值 | Rule match |
|---|---|---|
| `pool_snapshot_rows` | **20** | ✅ > 0 |
| `quote_snapshot_rows` | **120** | ✅ > 0 |
| `fee_velocity_rows` | **100** | ✅ > 0 |
| `liquidity_distribution_rows` | **20** | ✅ > 0 |
| `market_regime_rows` | **2** | (not in spec rule, but real data) |
| `candidate_review_rows` | **20** | ✅ > 0 |

**5/5 spec rules match** → 推荐 `LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1`.

## 2. 4 allowed next stages 评估

### 2.1 LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1 (推荐)

**任务**: R1 12h 扩展, 跑 12h × 1h ckpt, 验证 R1 stability + watchlist evolution + data quality + new dim (e.g. 6h regime trend, 24h fee trend).

**判断依据**:
- ✅ 5/5 spec rules match
- ✅ R1 smoke 6 dim 全部有非零 row count
- ✅ R1 7 watchlist (首次>0)
- ✅ R1 data layer 比 R0 强 5 项
- ✅ R1 12h 是合理 next step (从 0 池 0 watchlist → 7 watchlist; 12h 验 stability + data quality + watchlist evolution)

**推荐** (per spec 规则).

### 2.2 LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT (不推荐)

**任务**: R1 collector / adapters fix + re-smoke.

**判断依据**:
- ❌ R1 smoke 已跑通, 6 dim 全部有 row count
- ❌ R1 7 watchlist, 0 data_insufficient
- ❌ fix repeat 仅在 "R1 smoke 仍 0 / placeholder" 时适用 (per spec)
- ⚠️ **不** 排除后续 fix (e.g. R1 12h 跑出 fee 或 liquidity 问题时再 fix)

**不推荐** (R1 smoke 已满足 spec rule).

### 2.3 LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT (不推荐)

**任务**: Base RPC 修复 + re-smoke (在 Base-reachable env).

**判断依据**:
- ❌ Base 仍 403 (env unchanged)
- ❌ Paid RPC blocked by freeze
- ❌ env change **不** 在 stage 范围
- ❌ 即便 Base 修好, R1 仍有 13 Solana + 7 BSC V3 已 smoke, **不** blocker R1 12h

**不推荐** (Base 不可达 blocker 未变, R1 已 solana + bsc 跑通).

### 2.4 PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA (备选)

**任务**: 暂停.

**判断依据**:
- ⚠️ valid option, 但 R1 12h 是**更** productive next step
- ⚠️ 暂停 = 浪费 R1 已验证的 data layer + 7 watchlist
- ⚠️ 暂停 = 等 freeze reopen or Base fix, 但**不**解决 R1 12h 验证需求

**备选** (若 user 选 freeze 持续 + 不愿 R1 12h).

## 3. recommended_next_stage 决策

**`LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1`**

**决策理由**:
1. R1 smoke 5/5 spec rules match (全部 row count > 0)
2. R1 7 watchlist, data_insufficient 0, market regime 真实 CoinGecko
3. R1 12h 是合理 next step (验 stability + watchlist evolution)
4. R1 12h **不** 触发 probe/canary/live (维持 freeze)
5. R1 12h **不** 翻 can_run_probe_now / tiny_canary_allowed / edge_proven

## 4. R1 12h 启动前必经步骤

| Step | 必需 | 备注 |
|---|---|---|
| 1. 新审批 (新 MANUAL_APPROVAL_RECORDED) | ✅ required | phrase: `APPROVE_LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION stage=r1_12h mode=readonly no_probe=true no_mint=true` |
| 2. 新 scope freeze | ✅ required | `coverage_scope=partial_solana_bsc_real_universe_r1_12h` |
| 3. 新 PRE_RUN_SAFETY_CHECK | ✅ required | 12 checks all passed (incl. r1_smoke_pass, no_wallet_tx_probe, no_paid_rpc, no_modify_12h_data) |
| 4. 新 r1 12h data dir | ✅ required | `data/lp_long_horizon_r1_12h/<RUN_ID>/` (与 R1 smoke 区分) |
| 5. R1 collector 12h 适配 | ✅ required | scripts/lp_long_horizon_r1_real_data_collector_v1.py 加 --duration-hours --checkpoint-interval-minutes (or 新文件 scripts/lp_long_horizon_r1_12h_wallclock_v1.py) |
| 6. R1 12h tests | ✅ required | 至少 10 测试, 覆盖 6 dim 跨 12 ckpt + freeze invariants + R1 schema |
| 7. R1 12h 启动 via nohup (或下个 env 找 tmux) | ✅ required | pid 单独, 不与 R1 smoke pid 混 |
| 8. R1 smoke data dir (20260607_163000) 不动 | ✅ required | per spec: 不修改前 stage data |
| 9. 12h data dir (20260606_131323) 不动 | ✅ required | per spec: 不修改 12h stage data |

## 5. R1 12h 完成后 next stage

| After R1 12h | Recommended next stage |
|---|---|
| R1 12h PASS, watchlist 0→N (N≥7), fee/liquidity 仍 unavailable | `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1` (需 freeze reopen) |
| R1 12h PASS, watchlist 0→N, fee/liquidity 改善 | `LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1` (review 12h node report) |
| R1 12h FAIL | `LP_LONG_HORIZON_R1_FAILURE_AUDIT_V1` (debug) |
| R1 12h PASS, freeze 仍 active, no actual fee | `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` |

## 6. 严禁 (R1 12h 期间仍不触发)

- ❌ 不启动 24h / 48h / 72h / 7d (R1 12h 是 12h, **不** 升级)
- ❌ 不启动并行 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / add/remove liquidity / collect / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 翻 `can_run_probe_now=false`
- ❌ **不** 翻 `tiny_canary_allowed=no`
- ❌ **不** 翻 `edge_proven=no`
- ❌ **不** 翻 `actual_fee_data_available=false`
- ❌ **不** mint 实际 LP NFT 仓位 (R1 12h 仍 read-only data layer)

## 7. 锁定字段 (R1 12h 期间仍 LOCKED)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | freeze active |
| `tiny_canary_allowed` | `"no"` | freeze active |
| `edge_proven` | `"no"` | R1 ≠ actual fee |
| `global_lp_rejected` | `false` | R1 0 preflight 是 data insufficient, **不** = reject |
| `actual_fee_data_available` | `false` | R1 ≠ actual fee |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |

## 8. 决策表

| 推荐 | 任务名 | 范围 | 何时启 |
|---|---|---|---|
| ✅ **推荐** | `LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1` | R1 12h 扩展, 12h × 1h ckpt, 验证 stability + watchlist evolution | 需新审批 + 新 scope freeze |
| ❌ 不推荐 | `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT` | R1 collector fix + re-smoke | R1 12h 跑出 fee/liquidity 问题时再考虑 |
| ❌ 不推荐 | `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` | Base-reachable env smoke | 需换 env (uncontrolled) |
| ⚠️ 备选 | `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` | 暂停 | 任何时候 |
