# Base 10U Probe Execution Script Boundary (设计)

- stage: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`
- phase: G
- run_id: `20260602_133221`
- wrote_to_production_tables: **false**

> 本文件定义**未来** `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1` 构建的执行脚本的允许/禁止边界。**本轮不构造脚本**。本轮只是 design。

## 允许的动作（7 类）

| 动作 | 前置 | 后置 |
|---|---|---|
| **load wallet only after explicit approval** | 用户输入的审批短语匹配 regex；时间戳在过去 15 min 内；session_id 唯一；fabrication_blocked=true | wallet_or_tx_touched = true（之后进入执行模式） |
| **sign approve exact only after explicit approval** | wallet 已加载；USDC balance 足够；当前 allowance < amount | 记录 tx_hash / block / gas / post-allowance |
| **sign mint only after explicit approval** | approve 完成或跳过；Step 0 全 green；deadline=now+3600（不是 placeholder） | 记录 tokenId / liquidity / actual amounts / feeGrowth / tokensOwed |
| **sign decrease/collect only within same approved probe** | session_id 与 mint 一致；positions(tokenId).liquidity > 0 | liquidity_removed == entry.liquidity；positions 后为 0 |
| **record tokenId** | — | 写入 ledger |
| **record actual fee** | — | 写入 fee trace |
| **exit after configured hold** | — | Step 4 |

## 禁止的动作（11 类）

```text
× no automatic repeat          — 不自动 loop / 调度；下次 probe 需新审批
× no multi-pool                 — 只动 0x72ab388e..；其他池需新 spec + 新审批
× no notional > approved         — amount 不可超审批 notional
× no ApproveMax                  — 只 ApproveExact
× no swap-back unless separately approved — 不自动换币
× no bridge                      — 不跨链桥
× no live loop                   — 不启动 lpbot-live / canary / paper
× no background unattended trading — 不留后台进程；脚本必须退出
× no strategy auto-selection     — 不自动选其他 range/notional/pool
× no wallet reuse beyond this run — 钱包只用于本次 session_id
× no hidden retry                — 不静默重试；retry 需新审批
```

## 未来审批短语模板

```text
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x<40 hex> pool=0x<40 hex> notional=10 hold=15m
```

校验正则：

```text
^APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x[0-9a-fA-F]{40} pool=0x[0-9a-fA-F]{40} notional=10 hold=15m$
```

### 本轮 non-effective 声明

- **本轮不构造执行脚本**；本轮即使有人键入上述短语，**也不会执行**。
- 未来该短语只在 `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1` 构建的 executor 中被检查；该 executor 仍需要**再一道独立审批**才能真正发起交易。

## 必须拒绝的替代短语

```text
APPROVE_BASE_10U_LP_PROBE_EXECUTE
APPROVE_BASE_10U_LP_PROBE_NOW
APPROVE_BASE_10U_LP_PROBE_SIGN
APPROVE_BASE_10U_LP_PROBE_MINT
APPROVE_BASE_10U_LP_PROBE_LIVE
APPROVE_BASE_10U_LP_PROBE_PAPER
APPROVE_BASE_10U_LP_PROBE_CANARY
APPROVE_BASE_20U_LP_PROBE_EXECUTION_ONE_SHOT ...     (20U 不允许首轮)
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT ... notional=20 ...  (20U 不允许)
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT ... hold=30m  (30m 仅作为延期；首轮 = 15m)
GO / SHIP_IT / PROCEED
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xUSER_PROVIDED_WALLET pool=0xUSER_PROVIDED_POOL notional=10 hold=15m
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=USER_SELECTED notional=10 hold=15m
```

## 安全

```text
wallet_or_tx_touched              = false
can_run_probe_now                 = false
tiny_canary_allowed               = no
edge_proven                       = no
executor_built_this_round         = false
executor_will_run_this_round      = false
approval_phrase_effective_this_round = false
```
