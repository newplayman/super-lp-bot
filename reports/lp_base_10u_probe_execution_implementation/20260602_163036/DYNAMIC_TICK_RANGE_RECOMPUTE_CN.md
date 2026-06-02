# Dynamic Tick Range Recompute

- stage: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`
- phase: D
- run_id: `20260602_163036`

## 实现

`scripts/lp_base_10u_probe_executor_v2.py` 中 `dynamic_tick_range_recompute(url, dry_run)`：

```python
1. read slot0(POOL) → current_tick
2. drift = current_tick - LEGACY_FROZEN_TICK (-200443)
3. proposed_lower = current_tick - 200
4. proposed_upper = current_tick + 200
5. if current_tick outside [proposed_lower, proposed_upper] => ABORT
6. if |drift| > 200 => fresh_approval_required = true
7. return structured dict (no tx, no sign)
```

**不**直接用 frozen [-200643, -200243]；**不**硬编码 tick range 到 tx。

## 本轮观察

| 字段 | 值 |
|---|---|
| previous_legacy_center_tick | -200443 |
| **current_tick** | **-200708** |
| drift_ticks | -265 |
| abs_drift_ticks | 265 |
| drift_threshold_ticks | 200 |
| drift_exceeds_threshold | **true** |
| old_tick_lower_legacy | -200643 |
| old_tick_upper_legacy | -200243 |
| proposed_tick_lower | -200908 |
| proposed_tick_upper | -200508 |
| current_tick_inside_new_range | **true**（-200908 ≤ -200708 ≤ -200508） |
| fresh_approval_required | **true**（drift 265 > 200） |
| abort_reason | drift -265 from legacy center -200443 exceeds threshold 200; fresh approval required |
| dry_run | true |
| no_send_attempted | true |

## 与上一轮 review (83b41b9 at 46811930) 对比

| 维度 | 83b41b9 (46811930) | 本轮 (~46812500) | 差 |
|---|---|---|---|
| current_tick | -200662 | -200708 | -46 ticks |
| cumulative drift from frozen -200443 | 219 | 265 | +46 ticks |
| 触发 stop | manual_intervention_required (WARN) | fresh_approval_required (WARN) | 仍 WARN |
| current tick inside new range? | (frozen range) no | (proposed range -200908 to -200508) yes | ✓ |

**含义**：tick drift 继续累积（53 ticks in 13 min from prior; 46 ticks in 30 min since prior review），**drift 是加速的**。本轮 stop 没触发 ABORT 因为 current_tick 仍 inside 重新计算的新 range；**但** fresh_approval_required=true 意味着未来执行 stage 必须 re-approve。

## 5 个阶段 tick drift 趋势

| run_id | current_tick | drift_from_frozen |
|---|---|---|
| 20260602_112400 (dry-run builder) | -200443 | 0 |
| 20260602_135824 (build) | -200501 | 58 |
| 20260602_144843 (review 596b411) | -200609 | 166 |
| 20260602_150957 (review 83b41b9) | -200662 | 219 → STOP WARN |
| **20260602_163036 (this implementation)** | **-200708** | **265 → fresh_approval_required WARN** |

## abort 条件

| id | triggered | condition | action |
|---|---|---|---|
| abort_current_tick_outside_proposed_range | false | proposed_lower ≤ current_tick ≤ proposed_upper | n/a (current tick -200708 IS inside [-200908, -200508]) |
| abort_drift_exceeds_threshold_requires_fresh_approval | **true** | abs(drift) > 200 | future executor must re-approve |

## 未来 implementation 期望

- 持续重读 current_tick
- 当 drift > 200：必须 re-approve (新 session_id + 新 tick range)
- 当 current_tick outside new range：ABORT，不继续
- 短期持有（15m）能容忍大约 200-300 ticks 漂移；**超过必须 abort**

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
dry_run               = true
no_send_attempted     = true
```
