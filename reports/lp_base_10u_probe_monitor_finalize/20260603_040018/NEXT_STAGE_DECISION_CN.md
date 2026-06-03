# Next Stage Decision — Stage G

- stage: `LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1`
- run_id: `20260603_040018`
- go_nogo: **NO_GO**

## 1. 决策

```text
recommended_next_stage  = LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1
allowed_next_stages     = [
  "LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1",   # 不选 (NO_GO)
  "LP_BASE_10U_PROBE_REFRESH_DRY_RUN_V1",                       # 不选 (REFRESH 不解决 monotonic drift)
  "LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1",                    # 选
  "STOP_LP_RESEARCH_NOW"                                        # 不选 (operator 还没说停)
]
default_when_no_explicit_choice = LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1
```

## 2. 为什么选 MARKET_UNSAFE_WAIT 而非其他 3 个

### 2.1 不选 FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1

- 该阶段需要 GO 条件全部满足（上游 spec）
- 当前 NO_GO 触发 3 项（market_safe=false、drift 超阈值、stop condition unresolved）
- 选它等于越过 GO/NO-GO 评审

### 2.2 不选 REFRESH_DRY_RUN_V1

- REFRESH 适用于：市场在 frozen center 附近震荡 / quote 数据过期 / allowance 刚被消耗 / 想重新算 dynamic range
- 当前情况：tick drift 从 -385 单调恶化至 -722，**不是震荡**；allowance 一直是 5 USDC（未消耗）；quote_drift 字段 v1 缺失但当前任务不是关于 quote freshness
- REFRESH 不会让 tick 回到 frozen center；这超出 REFRESH 的修复域

### 2.3 选 MARKET_UNSAFE_WAIT_V1

- 该阶段假定"市场状态结构性不安全，但**不是**永久坏；等一段时间可能回归"
- 当前数据：8h 内 tick 单边偏移 337 ticks；只要 WETH 价格回到 ~$2700（与 frozen 当时相比），tick 应回 -200443 附近
- 这是当前 4 个合法 next stage 中**唯一**正确处理"市场结构性偏移，等待自然回归"的情况

### 2.4 不选 STOP_LP_RESEARCH_NOW

- 操作员已明确表态"继续推进 lp-bot"
- 当前只是 1 次 NO_GO（受 8h 内单边市场影响）
- 不应该把 1 次不利当成永久停止的信号

## 3. MARKET_UNSAFE_WAIT 阶段的预期动作

下一阶段 **`LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1`** 应包括（spec 留给下个 stage 定义）：

1. 启动另一个 read-only monitor（短一些，例如 4–6h），看 tick 是否回归 frozen center 附近
2. **不**修改 armed runner v1；v2 也不动
3. **不** unseal hard-disable
4. **不** ApproveExact
5. 若新 monitor 报告 tick drift ≤ 200，回到 `LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1`
6. 若新 monitor 仍 ≥ 200，再决定 GO 一次 / 改 candidate / STOP

具体 spec 由下一个 stage 的 prompt 提供；本阶段只决定**下一步往哪走**，不预先写 spec。

## 4. 行为约束

```text
next_stage_must_not:
  - 执行 probe
  - 发送任何交易
  - 构造任何 signer
  - 加载任何私钥
  - 解除 v2 hard-disable
  - 接受 one-shot execution phrase
  - 写 production positions
  - 覆盖 shadow 原始表
  - 修改策略执行路径

can_run_probe_now                = false (next stage 仍为 false)
execution_allowed_now            = false
tiny_canary_allowed              = "no"
send_hard_disable_still_active   = true
```

## 5. 4 个合法 next stage 的触发条件表

| next stage | 触发条件 | 当前是否触发 |
|---|---|---|
| `LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1` | GO 条件全过 | **否** (3 项 GO fail) |
| `LP_BASE_10U_PROBE_REFRESH_DRY_RUN_V1` | drift/市场状态变化需重新 dry-run | **否** (变化是 structural 不是 stale) |
| `LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1` | 市场 unsafe 但可等 | **是** (本次选择) |
| `STOP_LP_RESEARCH_NOW` | 市场持续不适合 或 operator 不想继续 | **否** (operator 未表态停) |

## 6. 阶段决策签名

```text
operator_choice_recorded_in_this_run = false
operator_choice_is_execution_authorization = false
this_stage_did_not_execute           = true
this_stage_did_not_send_any_tx       = true
this_stage_did_not_construct_signer  = true
this_stage_did_not_load_private_key  = true
this_stage_did_not_call_subprocess   = true
recommended_next_stage               = LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1
```
