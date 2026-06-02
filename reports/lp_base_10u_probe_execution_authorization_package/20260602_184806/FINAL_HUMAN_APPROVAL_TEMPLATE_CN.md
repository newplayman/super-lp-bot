# Final Human Approval Template

- stage: `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1`
- phase: H
- run_id: `20260602_184806`

## 唯一未来执行审批短语（exact phrase only）

```text
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m
```

regex (来自 `scripts/lp_base_10u_probe_executor_v2.py:77`)：

```text
^APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x[0-9a-fA-F]{40} pool=0x[0-9a-fA-F]{40} notional=10 hold=15m$
```

可变部分仅 wallet 与 pool 的 40-hex；本 probe 已 frozen 为上述值，任何其它 wallet/pool 都会被 4 项 cross-check 拒绝。

## 短语何时**不**生效

| 场景 | 是否生效 | 原因 |
|---|---|---|
| 当前 `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1` 阶段 | **不生效** | 本阶段无执行 runner |
| 任何 `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1` 阶段及之前（已完成） | **不生效** | executor v2 中 `execute-guarded` 永远 raise hard-disable |
| 未来 `LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1` 阶段（人工授权请求） | **不生效** | 该阶段仍是请求；执行还需进入再下一阶段 |
| 未来 `LP_BASE_10U_PROBE_FIRST_EXECUTION_RUN_V1`（假设命名） | **可能生效** | 仍需 send hard-disable 显式解除（独立 commit + audit） |

短语 **只**在那个最终执行 runner 接收到并经过 3-gate + 2-default + 解除 hard-disable + 实时 chain re-read 全部通过后，才会真正驱动 send。

## 执行时还必须满足

| 必须 | 来源 |
|---|---|
| `--mode execute-guarded` | argparse choices 强制 (Gate 1) |
| approval phrase 精确匹配（如上） | parse_approval_phrase (Gate 2) |
| `--i-understand-this-sends-real-transactions` flag 必须显式传 | argparse store_true (Gate 3) |
| `--dry-run-only false` & `--no-send false` 必须显式覆盖默认 true | argparse 默认 true |
| 实时重读 tick；若 drift > 200，**必须重新输入** approval phrase | dynamic_tick_range_recompute |
| 实时检查 USDC.allowance；不足才 ApproveExact | runner skip_approve_if_allowance_sufficient |
| `send_hard_disabled = false` (executor v2 中需另一次 commit 解除) | 当前为 true，未来必须经 audit |

## 拒绝示例

| 短语 | 结果 | 原因 |
|---|---|---|
| `APPROVE_BASE_20U_LP_PROBE_EXECUTION_ONE_SHOT wallet=... pool=... notional=20 hold=15m` | **拒绝** | 危险词 `\b20U\b` + regex 不匹配 + notional 不等 10 |
| `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=... pool=... notional=10 hold=30m` | **拒绝** | 危险词 `\b30m\b` + regex 不匹配 + hold 不等 15m |
| `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xDEADBEEF... pool=... notional=10 hold=15m` | **拒绝** | wallet cross-check 不通过 |
| `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=... pool=0xCAFEBABE... notional=10 hold=15m` | **拒绝** | pool cross-check 不通过 |
| `EXECUTE NOW wallet=... pool=... notional=10 hold=15m` | **拒绝** | 危险词 `\bEXECUTE\b` + `\bNOW\b` + regex 不匹配 |
| `APPROVE BASE 10U LP PROBE EXECUTION ONE SHOT ...`（带空格） | **拒绝** | regex `APPROVE_BASE_10U_...` 要求下划线 |
| `LIVE BASE 10U ...` / `CANARY ...` / `PAPER ...` | **拒绝** | 危险词 |
| `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=... pool=... notional=10 hold=15m GO` | **拒绝** | 危险词 `\bGO\b` |

## 操作员输入流程（未来执行阶段）

1. 操作员手动 cat 出当前 `current_tick` 与 frozen center 比对（read-only `eth_call slot0`）
2. 若 drift > 200，必须知悉将 **重新** 输入审批短语（同一 phrase 可重输入；但每次都是新 session_id）
3. 操作员执行 dry-run pre-check：`python3 scripts/lp_base_10u_probe_executor_v2.py --mode preflight ...`
4. 操作员手动检查 `dynamic_tick_range.json` 与 `preflight.json` 的 23 项 gate
5. 操作员手动输入精确短语，确认无 typo
6. 操作员手动加 `--i-understand-this-sends-real-transactions`
7. 即使全部正确，executor v2 当前版本仍 hard-disable；要执行必须先有独立 commit 解除 hard-disable + 单独 audit 通过

## 当前阶段不接受、不验证、不缓存任何短语

```text
this_stage_accepts_approval_phrase   = false
this_stage_validates_approval_phrase = false  (Stage H 仅展示模板)
this_stage_caches_approval_phrase    = false
this_stage_triggers_execution        = false
```

## 安全（本阶段不变量）

```text
wallet_or_tx_touched                  = false
approval_phrase_effective_this_round  = false
execution_allowed_now                 = false
can_run_probe_now                     = false
```
