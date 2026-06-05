# Corrected Next Stage Decision

- stage: `LP_LONG_HORIZON_6H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1`
- source_run_id: `20260605_043726`
- corrected_from_checkpoints: **true**
- gate_pass: **true**
- data_quality_status: **PASS**

## 0. 推荐 next_stage

**LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1**

## 1. 理由

rebuilt 6h gate PASS (data_quality_status=PASS, 13/13 gate checks pass). data 完整 (6/6 ckpts, 5 pool_snapshots, 180 quote_snapshots, 150 fee_velocity, 42 market_regime rows). 但**仍需用户单独审批** 12h 延展 (`APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true`).

## 2. 严禁

- `can_advance_to_12h`: **false** (LOCKED, 不自动 12h)
- `auto_advance_started`: **false**
- `longer_stage_started`: **false**
- `do_not_auto_start_12h`: **true**
- `manual_approval_required_for_12h`: **true**

如用户决定 12h 延展, 需重新审批:
```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true
```

## 3. 5-stage allowed next stages

- `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1` (本 stage 推荐, 因 gate PASS)
- `LP_LONG_HORIZON_NODE_REPORT_FIX_REPEAT` (node report 生成失败时)
- `LP_LONG_HORIZON_COLLECTOR_6H_FIX_REPEAT` (gate FAIL, 修 supervisor)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (用户要求暂停)
- `STOP_LP_RESEARCH_NOW` (用户要求停止)
