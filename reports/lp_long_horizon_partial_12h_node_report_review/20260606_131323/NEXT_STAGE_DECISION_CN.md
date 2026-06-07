# Next Stage Decision (12h Node Report Review)

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`

## 0. 一句话

12h 跑通仍是 r0 phase (smoke_placeholder fee/proxy, no tokenId, no live RPC, 53 池**全部** data_insufficient, preflight=0, watchlist=0). **不** 满足"12h 已经有真实 quote / fee / EV"的 24h extension 条件. **不** 满足 Base RPC reachable 的 adapter fix 条件 (Base 仍 403). **不** 满足 actual fee data 的 freeze reopen 条件. 推荐 next stage: **`LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`** (real-time read-only data layer, **不** mint / **不** freeze reopen / **不** actual fee).

## 1. 判断规则 (per spec)

### 1.1 spec 规则

```
如果当前 12h 主要仍是 R0 proxy / smoke_placeholder：
推荐 LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1

如果 12h 已经有真实 quote / fee / EV：
才允许推荐 24h
```

### 1.2 12h 实际状态 (per review)

| Metric | 值 | 评估 |
|---|---|---|
| `actual_fee_data_available` | **false** | r0 placeholder |
| `fee_proxy_only` | **true** | r0 proxy only |
| `candidate_decision_reliable` | **false** | preflight=0, watchlist=0, data_insufficient=53 |
| `preflight_candidate_count` | **0** | r0 |
| `watchlist_count` | **0** | r0 |
| `data_insufficient_count` | **53** (100%) | r0 |
| `ev_ready_pool_count` | **0** | r0 |
| `quote_snapshots.amount_in_raw` | **0** (smoke_placeholder=true) | r0 |
| `fee_velocity.fee_capture_proxy_usd` | **0** (smoke_placeholder=true) | r0 |
| `actual_fee_accrual.token_id` | **null** (schema only) | r0 |

**结论**: 12h **主要**仍是 r0 proxy / smoke_placeholder. **不** 满足"已有真实 quote / fee / EV"的条件. **应**推荐 R1 升级.

## 2. 4 allowed next stages 评估

### 2.1 LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1 (推荐)

**任务**: r0 → r1 upgrade, real-time read-only data layer (RPC + quote + volume + regime).

**判断依据**:
- ✅ 12h 主要仍是 r0 proxy → spec 规则 "推荐 R1"
- ✅ 53 池 r0 data layer 不足 → R1 升级**是**必要 next step
- ✅ R1 范围 = read-only, **不** mint / **不** freeze reopen / **不** actual fee → 与 freeze 一致
- ✅ R1 完成后 6 dimensions non-zero → 重新评估 preflight / watchlist / data_insufficient

**推荐** (per spec 规则 + 12h 实际状态).

### 2.2 LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1 (不推荐)

**任务**: 12h → 24h extension, **新** stage, 需**新**审批 + **新**scope freeze + **新**MANUAL_APPROVAL + **新**PRE_RUN_SAFETY_CHECK + **新**data_dir.

**判断依据**:
- ❌ 12h 已有真实 quote / fee / EV (条件不满足)
- ❌ 24h 跑出来**仍**是 r0 proxy (因 r0 collector + r0 adapters **不**改)
- ❌ 24h **不**解决 r0 → r1 升级 (time 不解决 data layer)
- ❌ 24h 浪费 12h compute (smoke_placeholder × 24h = 2x smoke_placeholder)

**不推荐** (per spec 规则 "只有 12h 已有真实 quote / fee / EV 才允许 24h").

### 2.3 LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT (不推荐)

**任务**: 在 Base-reachable env 再 smoke (or paid RPC).

**判断依据**:
- ❌ Base public RPC 仍 403 (env unchanged)
- ❌ Paid RPC blocked by freeze
- ❌ env change **不** 在本 stage 范围 (需 user 主动换 env)
- ❌ 即便 Base 修好, 仍 r0 phase (real data layer 仍 0)

**不推荐** (Base 不可达 blocker 未变, 即便可达仍 r0).

### 2.4 PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA (备选)

**任务**: 暂停.

**判断依据**:
- ⚠️ 是 valid option, 但 R1 升级是**更** productive next step
- ⚠️ 暂停 = 等 freeze reopen 或等 Base RPC fix, 但**不**解决 r0 → r1 升级
- ⚠️ 暂停 = 浪费 12h 已验证的 pipeline stability

**备选** (若 user 选 freeze 持续 + 不愿 R1).

## 3. recommended_next_stage 决策

**`LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`**

**决策理由**:
1. 12h 仍 r0 proxy (per fee_estimation_review + candidate_review_audit)
2. spec 明确: "如果当前 12h 主要仍是 R0 proxy / smoke_placeholder: 推荐 LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1"
3. R1 范围 = read-only, 与 freeze 一致
4. R1 完成后 6 dimensions non-zero → 重新评估 preflight / watchlist / data_insufficient
5. R1 不**不** mint / **不** freeze reopen / **不** actual fee → **不** 触发 freeze

## 4. R1 启动前必经步骤

| Step | 必需 | 备注 |
|---|---|---|
| 1. 新审批 (新 MANUAL_APPROVAL_RECORDED) | ✅ required | phrase: `APPROVE_LP_LONG_HORIZON_R1_REAL_DATA_UPGRADE stage=r1 mode=readonly no_probe=true no_mint=true` |
| 2. 新 scope freeze | ✅ required | `coverage_scope=partial_solana_bsc_real_universe_r1` + `r1_objectives=[real_rpc, real_quote, real_volume, real_regime, real_liquidity_distribution, actual_fee_schema_unchanged]` |
| 3. 新 PRE_RUN_SAFETY_CHECK | ✅ required | 12 checks all passed |
| 4. 新 r1 collector / adapters 升级 | ✅ required | 见 R0_TO_R1_DATA_UPGRADE_PLAN_CN.md |
| 5. 新 r1 tests (red-green-refactor) | ✅ required | 至少 30 测试, 覆盖 6 dimensions + freeze invariants |
| 6. 新 r1 启动 via nohup (或下个 env 找 tmux) | ✅ required | pid 单独, 不与 12h pid 混 |
| 7. 新 r1 data_dir | ✅ required | `data/lp_long_horizon/20260607_XXXXXX_r1/` |
| 8. 12h data_dir (20260606_131323) 不动 | ✅ required | per spec: 不修改前 stage data |

## 5. R1 完成后 next stage

| After R1 12h | Recommended next stage |
|---|---|
| R1 12h PASS, data_insufficient ≤ 10, preflight > 0, watchlist > 0, fee_proxy_only=false | `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1` (需 freeze reopen, user mint, tokenId) |
| R1 12h PASS, data_insufficient > 10, RPC reachability blocker | `LP_LONG_HORIZON_RPC_REACHABILITY_FIX_V1` (env change or wait for paid RPC approval) |
| R1 12h FAIL | `LP_LONG_HORIZON_R1_FAILURE_AUDIT_V1` (debug) |
| R1 12h PASS, freeze 仍 active, no actual fee data | `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` |

## 6. 严禁 (本 review + 后续 R1 期间)

- ❌ 不启动 24h / 48h / 72h / 7d (per spec 规则 + 12h 仍 r0)
- ❌ 不启动并行 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 翻 `can_run_probe_now=false`
- ❌ **不** 翻 `tiny_canary_allowed=no`
- ❌ **不** 翻 `edge_proven=no`
- ❌ **不** mint 实际 LP NFT 仓位 (R1 仅升级 data layer, **不** mint)

## 7. 锁定字段 (LOCKED, 12h review 期间 + R1 期间)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | freeze active |
| `tiny_canary_allowed` | `"no"` | freeze active |
| `edge_proven` | `"no"` | actual fee 缺失 |
| `global_lp_rejected` | `false` | 12h r0 data insufficient, **不** = reject |
| `actual_fee_data_available` | `false` | r0 placeholder, freeze 仍 active |
| `fee_proxy_only` | `true` | r0 proxy only |
| `candidate_decision_reliable` | `false` | preflight=0, watchlist=0, data_insufficient=53 |
| `preflight_candidate_count` | 0 | r0 |
| `watchlist_count` | 0 | r0 |
| `data_insufficient_count` | 53 | r0 (100%) |
| `r1_upgrade_required` | `true` | R1 **是** 必要 next step |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |

## 8. 关键 takeaway

- 12h r0 phase 跑通 = pipeline stability PASS, **不** = edge proven
- 53 池**全部** data_insufficient (100%), preflight=0, watchlist=0
- 24h extension **不**推荐 (r0 → 24h = 2x r0, 浪费)
- Base RPC fix **不**推荐 (env unchanged, 即便可达仍 r0)
- **推荐** R1 升级 (real-time read-only data layer, **不** mint / **不** freeze reopen)
- 后续 R1 → R2 (需 freeze reopen) → 才有 actual fee data
- LP edge proven **仍**需 freeze reopen + R2 actual fee + 24h+ tokenId diff

## 9. 决策表

| 推荐 | 任务名 | 范围 | 何时启 |
|---|---|---|---|
| ✅ **推荐** | `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1` | real-time read-only data layer (RPC + quote + volume + regime + liquidity_distribution) | 需新审批 |
| ❌ 不推荐 | `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` | 12h → 24h (r0, 浪费) | 需新审批 |
| ❌ 不推荐 | `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` | Base-reachable env smoke | 需换 env (uncontrolled) |
| ⚠️ 备选 | `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` | 暂停 | 任何时候 |
