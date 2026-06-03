# Base 10U Probe GO/NO-GO Review — Stage F

- stage: `LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1`
- run_id: `20260603_040018`
- candidate: Base / Uniswap V3 / WETH-USDC 0.01% / pool 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 / wallet 0xb05b...d835 / notional 10 USD / hold 15m

## 1. 决策结果

```text
go_nogo                              = NO_GO
primary_reason                       = "0/47 market_safe checkpoints; tick drift -722 ticks (>200 threshold by 522 ticks); fresh_approval_required continuously; market data shows monotonic worsening"
blocking_conditions                  = 3
next_required_action                 = LP_BASE_10U_PROBE_REFRESH_DRY_RUN_V1
```

## 2. GO 条件逐条评估（必须 12 条全过）

| # | 条件 | 评估 | 证据 |
|---|---|---|---|
| 1 | `market_safe_count / total >= 80%` | **FAIL** | 0/47 = 0% |
| 2 | latest ckpt 无 hard stop | **FAIL** | `any_stop_condition_active: true`（`fresh_approval_required: true`）|
| 3 | latest current_tick inside dynamic range | **PASS** | `current_tick_inside_new_range: true`（动态 ±200 范围）|
| 4 | drift ≤ 阈值 OR fresh approval satisfiable | **PARTIAL** | drift -722 远超 200; fresh approval 5→10 USDC **技术上 satisfiable**, 但 fix 不解决 drift 问题 |
| 5 | quote valid | **N/A** | v1 monitor 未收集 quote; 不可 GO 基于缺失字段 |
| 6 | exit quote valid | **N/A** | 同上 |
| 7 | gas estimate sane | **PASS** | 0.006–0.014 gwei（极低）|
| 8 | ETH gas balance sufficient | **PASS** | 0.0905 ETH ≈ $300+ 足够无数次 10U probe |
| 9 | USDC balance sufficient | **PASS** | 21.77 USDC 足够 |
| 10 | USDC allowance plan clear | **PASS** | plan = `ApproveExact(USDC, NPM, 10 USDC)`; 但需要 fresh approval |
| 11 | no RPC instability | **PASS** | 0/47 failures |
| 12 | no signer / wallet / tx touched | **PASS** | `wallet_or_tx_touched: false` |
| 13 | hard-disable still active | **PASS** | `send_hard_disable_still_active: true` |

**GO fail count: 3/13**（条件 1, 2, 4）→ 必 NO_GO

## 3. NO-GO 条件逐条触发情况（任一触发即 NO_GO）

| 条件 | 触发？ | 证据 |
|---|---|---|
| market_safe=false in latest checkpoint | **YES** | iter=47 `market_safe_for_execution_candidate: false` |
| tick drift exceeds threshold | **YES** | iter=47 drift_ticks=-722 (> 200) |
| current tick outside proposed range | NO | in range |
| quote stale or unavailable | N/A | v1 未收集 |
| exit quote unavailable | N/A | v1 未收集 |
| gas too high | NO | 极低 |
| wallet balance insufficient | NO | 充裕 |
| allowance ambiguity | NO | plan clear |
| RPC unstable | NO | 0 failure |
| data incomplete | MINOR | v1 不收集 quote_drift |
| any stop condition unresolved | **YES** | `fresh_approval_required: true` 持续 |

**NO-GO triggers: 3** — 不可 GO。

## 4. 漂移趋势（决定 NO_GO 而非 REFRESH 的关键）

```text
iter 1   drift = -385  (启动)
iter 10  drift = -363
iter 18  drift = -414
iter 20  drift = -573  (开始恶化)
iter 30  drift = -548
iter 40  drift = -631
iter 47  drift = -722  (终点)
```

漂移从 -385 恶化到 -722（+337 ticks = ~0.3 USDC 单边）。**单边持续恶化**说明 WETH/USDC 价格持续走弱（USDC 相对 WETH 升值）。这**不是** tick 围绕 frozen center 振荡的常规市场情况，**是**结构性偏移。

**含义**：单次 ApproveExact 不会让 `market_safe=true` — 实际市场状态不允许 10U probe 在当前 frozen range 周围 ±200 ticks 内执行。

## 5. 决定依据

### 5.1 为什么不 GO

- 0/47 market_safe；
- latest ckpt 仍 `any_stop_condition_active=true`；
- latest drift -722 >> 200 阈值；
- 漂移趋势单调恶化；
- 当前任何"GO"会需要操作员在 armed runner 真正 unseal 后用 ApproveExact 把 5 USDC allowance 提到 10 USDC + 接受 fresh approval 路径 + 接受 -722 drift 风险。这违反 armed runner spec 中的"drift > 阈值需要 fresh approval 且 drift 仍 > 200 时操作员必须明确接受"要求。

### 5.2 为什么不选 REFRESH_REQUIRED

REFRESH_REQUIRED 适用于"市场状态良好但需要重新跑一次 dry-run / 重新收集 quote"的情况。当前情况是"市场结构偏移"（tick -722，离 frozen center 远，且趋势恶化），不是简单的 "quote 不新鲜"。**REFRESH 不会让 tick 回到 -200443 附近**。

### 5.3 为什么选 NO_GO（不是 REFRESH_REQUIRED）

`LP_BASE_10U_PROBE_REFRESH_DRY_RUN_V1` 适用于：
- tick drift 暂时超阈值但市场在均值回归
- quote 数据不全需要重跑
- allowance 刚被消耗需要重新 approve

当前情况：
- 漂移**持续恶化**（-385 → -722），无均值回归迹象
- allowance 仍 5 USDC（一直未变）
- 没有任何字段因为时间过时而失效

所以 NO_GO 比 REFRESH_REQUIRED 更准确。

## 6. 风险评估

如果操作员**绕过本 NO_GO 决策**硬要走 `LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1`：

1. **市场侧风险**：进入 armed runner 后必须先 ApproveExact 10 USDC USDC；mint 落点会在 dynamic range [-201365, -200965]，但当前 tick -201165 离 frozen center -200443 已 ~7 美元价值距离的 USDC 侧；
2. **LP 几何风险**：range 上沿 -200965 离 frozen center -200443 远 ~5 美元，下沿 -201365 离 frozen center 远 ~9 美元；进入后任何 1 美元 USDC 升值都会立刻出 range 上沿 → IL；
3. **基础数据风险**：v1 monitor 不收 quote_drift，**任何 armed runner 走真 dry-run 时都缺 quote freshness 校验**（v2 monitor 候选 schema）；
4. **操作员负担**：fresh approval 路径必须主动接受 `-722 drift` 风险。

## 7. next_required_action

**`LP_BASE_10U_PROBE_REFRESH_DRY_RUN_V1`** 是"次坏"选择（如市场回归 frozen 附近）；

**`LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1`** 也是合法选项，但 operator prompt 只给了 4 个 allowed next stages 里的"REFRESH_DRY_RUN"或"MARKET_UNSAFE_WAIT"或"FINAL_OPERATOR_AUTHORIZATION_REVIEW"或"STOP"。

**`STOP_LP_RESEARCH_NOW`** 在市场已持续 8h 不利情况下也是合理选项。

本阶段推荐 `LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1`（因为 REFRESH 也不解决问题）；但 `REFRESH_DRY_RUN` 在 stage G 决策表上更具体。**两者在合法集合内**。详见 stage G 决策文件。

## 8. 安全断言（守住）

```text
can_run_probe_now                = false
execution_allowed_now            = false
tiny_canary_allowed              = "no"
send_hard_disable_still_active   = true
wallet_or_tx_touched             = false
private_key_loaded               = false
eth_sendTransaction_called       = false
eth_sendRawTransaction_called    = false
approve_executed                 = false
mint_executed                    = false
decrease_executed                = false
collect_executed                 = false
burn_executed                    = false
swap_executed                    = false
live_started                     = false
canary_started                   = false
paper_started                    = false
any_funds_spent                  = false
```
