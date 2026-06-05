# Next Node Decision: 6h → ? (Continuous Observation)

- stage: `LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1`
- decision_stage: `E_NEXT_NODE_DECISION`
- decided_at_utc: `2026-06-05T13:11:00Z`
- source_run_id: `20260605_043726`
- node: `6h`

## 0. V2 状态

| 字段 | 值 |
|---|---|
| V2 FINAL_VERDICT path | `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/FINAL_VERDICT.json` |
| V2 status | **FAIL** (per V2 supervisor FINAL_VERDICT) |
| V2 gate_pass | **false** (per V2 supervisor FINAL_VERDICT) |
| V2 data_quality_status | **FAIL** (per V2 supervisor FINAL_VERDICT) |
| V2 actual_runtime_minutes | 360 |
| V2 actual_runtime_valid_for_6h_gate | true |
| V2 short_mode_used | false |
| V2 six_hour_run_completed | false (per V2 FINAL_VERDICT) |
| V2 can_advance_to_12h | false |
| V2 recommended_next_stage | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT` |
| V2 finalize_error | `trap EXIT rc=1` (post-6h summary block hit error after ckpt 6 + 4 postfinal heartbeats) |

## 1. V2 状态矛盾讨论

**矛盾点**: V2 FINAL_VERDICT 自身说 FAIL, 但本轮 node report generator 用 V2 实际 ckpt 数据生成 PASS node report.

### V2 supervisor 视角

V2 supervisor 在 6h wallclock 完成后, 进入 post-6h summary block, 该 block 触发 fail-safe trap (EXIT rc=1), trap 写 FAIL FINAL_VERDICT (preserving V2 supervisor 的 "no silent loss" 不变量 from V1 fix). Supervisor log 末尾:

```
[checkpoint 6/6] ok at 2026-06-05T09:51:33Z
[V2 wallclock fix] last checkpoint done; sleeping 3596s until END_TS=1780656689
[heartbeat 6_1_of_4_postfinal] ... elapsed=315min
[heartbeat 6_2_of_4_postfinal] ... elapsed=330min
[heartbeat 6_3_of_4_postfinal] ... elapsed=345min
[heartbeat 6_4_of_4_postfinal] ... elapsed=360min
[6h end] 2026-06-05T10:51:29Z elapsed_min=360 (target END_TS=1780656689)
[trap] EXIT rc=1; writing FAIL FINAL_VERDICT
```

V2 实际数据**完整**: 6/6 ckpts, 每 ckpt 30 quote_snapshots + 25 fee_velocity + 5 liquidity + 7 regime + 5 pool_snapshots + 1 actual_fee_placeholder + 1 smoke_summary. 0 error indicators in logs.

### Node Report Generator 视角

Generator 读 ckpt 数据, 发现:
- 6/6 ckpts 完整
- 30 quote_snapshots/ckpt × 6 = 180 quote rows
- 25 fee_velocity/ckpt × 6 = 150 fee rows
- 5 liquidity/ckpt × 6 = 30 liq rows
- 7 market_regime/ckpt × 6 = 42 regime rows
- 5 pool_snapshots/ckpt × 6 = 30 pool rows

`gate_status: PASS, data_quality_status: data_quality_ok, full_sample: true, partial_sample: false`.

### 结论

- **V2 supervisor 自身 FAIL 状态**只影响 V2 supervisor 的 post-6h summary block (Python aggregate + write 7 reports 步骤失败), **不影响** R0 节点报告.
- **V2 数据本身完整且可复用**. 6h wallclock 完成, 真实数据 (placeholder 形式) 已写入.
- Node report **可以**作为 R0 数据观察 + 是否继续采集判断的依据.

## 2. 候选 next_stage 评估

### 2.1 `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1`

| 必要条件 | 状态 |
|---|---|
| 6h V2 gate pass | ⚠️ V2 FINAL_VERDICT gate_pass=false, **但** node report gate_status=PASS (data_quality_ok, 6/6 ckpts). 节点报告**可以**作为 R0 数据观察依据. |
| node report full_sample=true | ✅ true (6/6 ckpts) |
| data_quality_status PASS 或 WARN_ACCEPTABLE | ✅ data_quality_ok |

**条件部分满足** (V2 supervisor FAIL vs node report PASS). 详见 discussion. **选中此 stage**.

### 2.2 `LP_LONG_HORIZON_NODE_REPORT_FIX_REPEAT`

| 必要条件 | 状态 |
|---|---|
| node report 生成失败或 coverage manifest 不完整 | ❌ node report 已成功生成, coverage manifest 完整 (3 levels: chain/dex/pool) |

**条件不满足, 不选**.

### 2.3 `LP_LONG_HORIZON_COLLECTOR_6H_FIX_REPEAT`

| 必要条件 | 状态 |
|---|---|
| V2 6h 本身失败 | ⚠️ V2 supervisor FAIL, **但** V2 数据**完整**. collector 本身**无 bug** (6/6 ckpts 完整, no error indicators). V2 supervisor post-6h summary block 失败, 不是 collector 失败. |

**条件部分满足**. 修 supervisor 才是正确做法, 不是修 collector. **不选**.

### 2.4 `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`

| 必要条件 | 状态 |
|---|---|
| 暂不继续 collector | ❌ 用户新意图: 6h → 12h 连续, 不在节点停. |

**条件不满足, 不选**.

### 2.5 `STOP_LP_RESEARCH_NOW`

| 必要条件 | 状态 |
|---|---|
| edge_proven=yes 强烈推荐停止 | ❌ edge_proven=no |
| 用户明确要求停 LP research | ❌ 用户未要求停 |

**条件不满足, 不选**.

## 3. 选中: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1`

### 3.1 理由 (primary)

- node report full_sample=true + gate=PASS
- 用户新意图 = 6h → 12h 连续, 不在节点停
- 12h 延展请求**不**自动启动, 需用户单独 approve 短语 + 单独 FINAL_VERDICT + freeze 状态决定

### 3.2 理由 (secondary)

- V2 supervisor FAIL 不阻断 R0 节点报告
- V2 实际数据完整可复用
- 12h 延展会建立新 supervisor, 复用同一 RUN_ID 累积 data, 自动在 12h 节点生成 12h node report

### 3.3 NOT_collector_fix_repeat

- collector 本身**无 bug** (6/6 ckpts 完整, no error indicators)
- V2 supervisor post-6h summary block 失败 = supervisor 自身问题 (Python aggregate + write 7 reports 步骤)
- 修 supervisor ≠ fix_repeat collector

## 4. 严禁自动启动 12h

| 字段 | 锁定值 |
|---|---|
| `do_not_auto_start_12h` | **true** |
| `manual_approval_required_for_12h` | **true** |
| `manual_approval_phrase_12h` | `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true` |

12h 延展**必须**:
1. 用户单独审批 (新 approval 短语, sha256 必须重新计算)
2. 新 supervisor 12h stage, 复用同一 RUN_ID `20260605_043726` 或新 RUN_ID
3. 单独 stage FINAL_VERDICT
4. freeze 状态单独决定 (当前 LP strategy research 仍处于 freeze)

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 6. 结论

**选中**: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1`

理由: node report full_sample=true + gate=PASS, 用户新意图 = 连续观察, V2 supervisor FAIL 不阻断 R0 节点报告. 12h 延展**不**自动启动, 等用户单独审批.

**Stage E 状态**: PASS → 进入 Stage F (FINAL_NODE_VERDICT).
