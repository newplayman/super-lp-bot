# PnL Ledger v1 说明

本轮新增的目标不是一次性完成策略正期望证明，而是把 live/canary 的收益归因数据流补成可继续审计的底座。

## 新增数据面

- `pnl_ledger`
  - 继续作为动作级账本
  - 新增字段：
    - `source`
    - `position_value_usd`
    - `fee_collected_usd`
    - `fee_uncollected_usd`
    - `gas_usd`
    - `il_usd`
    - `lvr_usd`
    - `net_pnl_usd`
- `position_marks`
  - 新增 open position 的周期性估值表
  - 记录每次 mark 时的：
    - 当前头寸价值
    - 未收手续费估值
    - 已实现手续费累计
    - gas 成本累计
    - 未实现净盈亏
- `portfolio_snapshots`
  - 新增健康字段：
    - `stuck_tx_count`
    - `exit_failed_position_count`
    - `unreconciled_opening_count`
    - `unreconciled_opening_timeout_count`

## 字段含义

- `position_value_usd`
  - 当前头寸主仓价值的 USD 估值
- `fee_collected_usd`
  - 已通过 collect/close 动作落地的手续费 USD
- `fee_uncollected_usd`
  - 基于链上 fee growth / tokens owed 估算的未收手续费 USD
- `gas_usd`
  - 当前版本数据流已预留；部分路径仍可能为 `0`
- `il_usd`
  - 当前版本保留字段，默认 `0`
- `lvr_usd`
  - 当前版本保留字段，默认 `0`
- `net_pnl_usd`
  - v1 含义分两类：
    - `position_marks` 中表示未实现净盈亏近似值
    - `pnl_ledger` 动作行中表示该动作确认时记入的已实现净盈亏

## 真实链上值 vs 估算值

### 已直接来自链上事实

- `positions.token_id`
- `positions.metadata.actual_amount0`
- `positions.metadata.actual_amount1`
- `positions.metadata.liquidity`
- `positions.metadata.receipt_block`
- `execution_intents.status`
- `transactions.status`
- `position_marks` 的 `position_value_usd` 上游所用：
  - `positions(tokenId)` 读取到的 `liquidity`
  - pool `slot0()`
  - fee growth / tokens owed

### 当前仍为估算或占位

- `gas_usd`
  - 字段与写入路径已存在，但并非所有动作都能稳定得到真实 USD 成本
- `il_usd`
  - 当前为保留字段，默认 `0`
- `lvr_usd`
  - 当前为保留字段，默认 `0`
- `portfolio_snapshots.unrealized_pnl_usd`
  - 目前来自 `position_marks` 的未实现近似值
- `portfolio_snapshots.realized_pnl_usd`
  - 目前来自 `pnl_ledger` 的动作累计值

## 当前可依赖的用途

- 阻断新 open：
  - `stuck_tx_count > 0`
  - `exit_failed_position_count > 0`
  - `unreconciled_opening_timeout_count > 0`
  - `submitted_private_exposure_usd > 0`
  - `open + pending + submitted_private + new order` 超过当前临时 cap
- 对 open positions 做周期性 mark
- 在 dashboard / 报表 / 后续 shadow 回填里消费已实现与未实现 PnL 基础字段

## 当前未完成项

- `gas_usd` 全路径真实化
- `il_usd` 真实计算
- `lvr_usd` 真实计算
- close 时更严格的 realized/unrealized 切换归集
- 把 `PortfolioSnapshot` 风控 cap 从当前临时口径升级为真正的账户级预算口径

## 下一步建议

1. 把 `gas_usd` 在 mint / collect / close / RBF 路径补成真实值
2. 做 `calculateILFromPosition()` 的真实实现
3. 给 `position_marks` 增加 close 前最后一笔 settle 逻辑
4. 用 `shadow_decision_trace + position_marks + pnl_ledger` 回填 1h/6h/24h 策略样本
