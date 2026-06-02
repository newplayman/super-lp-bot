# Dynamic Tick Range Final Review

- stage: `LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1`
- phase: D
- run_id: `20260602_182402`
- 审查源码: `scripts/lp_base_10u_probe_executor_v2.py` 函数 `dynamic_tick_range_recompute(url, dry_run)` (l.325-394)

## 静态审查矩阵

| 审查项 | 期望 | 源代码定位 | 实际 | 结果 |
|---|---|---|---|---|
| v2 强制 runtime 读取 slot0 | true | l.339 `rpc_call(url, "eth_call", [{to: POOL, data: SEL_SLOT0}, "latest"])` | true | **PASS** |
| 不再使用 legacy frozen range | true | l.375-394 返回 dict 中 legacy range 仅出现在审计字段；mint builder 使用 caller-passed range | true | **PASS** |
| 根据 current tick / tickSpacing 重算 | true | l.356-357 `proposed_lower = current_tick - 200`, `proposed_upper = current_tick + 200`；`TICK_SPACING = 1`（FEE_TIER=100 对应 spacing 1，无需 quantize） | true | **PASS** |
| 是否有 drift threshold | true | l.115-116 `TICK_DRIFT_ABORT_THRESHOLD = 200`, `TICK_DRIFT_FRESH_APPROVAL_THRESHOLD = 200` | true | **PASS** |
| drift > threshold 时 fresh_approval_required | true | l.363-364 `fresh_approval_required = abs_drift > TICK_DRIFT_FRESH_APPROVAL_THRESHOLD` | true | **PASS** |
| current tick outside range 时 abort | true | l.367-369 `abort_reason = f"current_tick {current_tick} outside proposed range ..."`；`self_check_implementation_no_send` 在 l.747 检查 `current_tick_inside_new_range` 否则 mint package 标记 `"skipped": True, "reason"` | true | **PASS** |
| range 覆盖当前 tick | true | `[current_tick-200, current_tick+200]` 数学上必然包含 current_tick；本轮验证 `-200947 ≤ -200747 ≤ -200547` | true | **PASS** |
| range 不会过窄 | true | 半宽固定 200 ticks（fee tier 100 对应 spacing 1，等效 400 ticks 宽度）；不允许更窄 | true | **PASS** |
| 不允许 30m/20U 复用 10U/15m 旧审批 | true | 通过 `parse_approval_phrase` 强行校验 `notional=10 hold=15m`（l.314-317）；任何不同值都拒绝 | true | **PASS** |
| current tick 再变化时重算 | true | 每次 mode invocation（preflight / print-unsigned / self-check / execute-guarded）都会 fresh call `dynamic_tick_range_recompute` | true | **PASS** |

## 本轮 runtime 观察 (read-only)

| 字段 | 值 |
|---|---|
| current_tick_now | **-200747** |
| previous_legacy_center_tick | -200443 |
| drift_ticks | **-304** |
| abs_drift_ticks | **304** |
| drift_threshold_ticks | 200 |
| drift_exceeds_threshold | **true** |
| proposed_tick_lower_now | **-200947** |
| proposed_tick_upper_now | **-200547** |
| proposed_safety_margin_each_side | 200 |
| current_tick_inside_range | **true** (`-200947 ≤ -200747 ≤ -200547`) |
| fresh_approval_required | **true** |
| abort_if_not_fresh_approval | **yes** — 即任何 execute-guarded 调用必须有重新签发的 approval 才允许（本 stage 仍 hard-disabled） |
| RPC source | `public_fallback:https://base-rpc.publicnode.com` |

## drift 历史

| run_id | current_tick | drift_from_frozen |
|---|---|---|
| 20260602_112400 (dry-run builder) | -200443 | 0 |
| 20260602_135824 (build) | -200501 | 58 |
| 20260602_144843 (review 596b411) | -200609 | 166 |
| 20260602_150957 (review 83b41b9) | -200662 | 219 |
| 20260602_163036 (implementation) | -200708 | 265 |
| **20260602_182402 (this final review)** | **-200747** | **304** |

drift 趋势仍单调向负方向漂移（39 ticks in ~78 min from prior implementation run）。**threshold 200 不再可以承诺一次性满足任何未来执行**——任何后续执行必须重新读 slot0 + 重新生成 approval。

## abort 行为枚举

| condition | triggered (this run) | 上层处理 |
|---|---|---|
| slot0 read failed | false | `dynamic_tick_range_recompute` 返回 `{"error": ..., "abort_reason": "slot0_read_failed", "fresh_approval_required": true}` (l.346-351) |
| current_tick outside proposed range | false (-200747 is inside) | abort_reason 被设；`self_check_implementation_no_send` 跳过 mint_tx 构造 (l.757-762) |
| drift > threshold (200) | **true** (304 > 200) | `fresh_approval_required = true`；abort_reason 解释 |

## 与执行授权包阶段的约束

未来 `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1` 阶段必须：

1. **重新读取 slot0** — 不能信赖本阶段 snapshot。
2. **重新计算 proposed range** — 不能信赖本阶段 `-200947 / -200547`。
3. **重新生成 approval phrase**（每次 session_id 独立） — 即使 phrase 同形，因为它绑定的是 wallet / pool / notional / hold，而 range 是 runtime 推导的，所以必须重 sign-off。
4. **若 abs_drift > 200，必须重新人工审批** — 这是脚本内置的硬性要求。
5. **若 current_tick outside [proposed_lower, proposed_upper]，必须 ABORT** — 不允许放宽 margin。

## verdict

| field | value |
|---|---|
| runtime_slot0_read | true |
| legacy_frozen_range_unused | true |
| dynamic_recompute_correct | true |
| drift_threshold_enforced | true |
| fresh_approval_required_when_drift_exceeds | true |
| abort_when_tick_outside_range | true |
| range_covers_current_tick | true |
| not_too_narrow | true |
| 30m_20U_cannot_reuse_old_approval | true |
| dynamic_tick_range_pass | **true** |

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
tiny_canary_allowed           = no
this_review_runs_dynamic_recompute_only_for_audit = true
no_send_attempted             = true
```
