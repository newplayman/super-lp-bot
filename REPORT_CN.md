# PnL Ledger v1 说明

当前版本的目标不是一次性完成策略正期望证明，而是把 Base live/canary 的收益归因补成可继续审计的底座，并把 snapshot 风控从“观察面”推进到“真实阻断输入”。

## 新增数据面

- `pnl_ledger`
  - 继续作为动作级账本
  - 现已包含：
    - `open`
    - `collect`
    - `close`
    - `settle`
    - `gas`
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
    - IL v1 估值
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
  - Base receipt 路径已按 `gasUsed * effectiveGasPrice * ETH/USD` 写入
  - 若 receipt 缺失 `effectiveGasPrice`，或无法解析出可用 ETH/USD 上下文，仍可能为 `0`
- `il_usd`
  - Position mark 已接入 IL v1：
    - `current_lp_gross_value_usd - current_hold_value_usd`
  - 仍不是更严格的 LVR/退出后完整归因
- `lvr_usd`
  - 当前版本保留字段，默认 `0`
- `net_pnl_usd`
  - v1 含义分两类：
    - `position_marks` 中表示未实现净盈亏近似值
    - `pnl_ledger` 中：
      - `gas/open/collect/close` 表示动作级记账
      - `settle` 表示 position close 后的 realized PnL 汇总口径

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
- Base receipt 上游所用：
  - `receipt.gas_used`
  - `receipt.effective_gas_price`

### 当前仍为估算或占位

- `gas_usd`
  - Base receipt 路径已真实化
  - 仍依赖 ETH/USD 价格上下文；没有可用 pool/context 时可能退化为 `0`
- `il_usd`
  - 已接入 IL v1，但仍是 mark-to-market 估算，不是最终 settle 后的严格会计口径
- `lvr_usd`
  - 当前为保留字段，默认 `0`
- `portfolio_snapshots.unrealized_pnl_usd`
  - 当前来自 `position_marks` 的未实现近似值
- `portfolio_snapshots.realized_pnl_usd`
  - 当前仅汇总 `pnl_ledger.kind = settle` 的 realized PnL

## 当前可依赖的用途

- 阻断新 open：
  - `stuck_tx_count > 0`
  - `exit_failed_position_count > 0`
  - `unreconciled_opening_timeout_count > 0`
  - `pending_exposure_usd` 超过 `live_risk.max_pending_exposure_usd`
  - `submitted_private_exposure_usd` 超过 `live_risk.max_submitted_private_exposure_usd`
  - `open + pending + submitted_private + new order` 超过 `live_risk.max_total_exposure_usd`
  - native balance 低于 `live_risk.min_gas_reserve_wei`
- 对 open positions 做周期性 mark
- 在 dashboard / 报表 / 后续 shadow 回填里消费已实现与未实现 PnL 基础字段

## 当前未完成项

- `gas_usd` 对非 Base receipt 路径、缺上下文价格路径的覆盖仍不完整
- `il_usd` 仍是 v1 估算，不是最终完整会计归因
- `lvr_usd` 真实计算
- shadow outcome 回填和 edge 统计还未接上
- close settle 仍依赖 latest mark/entry metadata，尚未做到完全事件级精算

## 下一步建议

1. 继续补 `gas_usd` 在缺 pool 上下文、manual reconcile、非 Base 路径的覆盖
2. 把 `IL v1` 升级为 close 后更严格的 realized IL 归因
3. 实现 `lvr_usd` 和更细的 fee/principal 拆分
4. 用 `shadow_decision_trace + position_marks + pnl_ledger + portfolio_snapshots` 回填 1h/6h/24h 策略样本

## Shadow Outcome 新增说明

- 新增 `shadow_outcome_labels`
  - 用于按 `1h / 6h / 24h` 回填 shadow 决策结果
  - 字段包含：
    - `entry_value_usd`
    - `simulated_position_value_usd`
    - `simulated_fee_usd`
    - `simulated_gas_usd`
    - `simulated_il_usd`
    - `simulated_net_pnl_usd`
    - `max_drawdown_usd`
    - `label`
- 当前 `simulated_gas_usd`
  - 优先走 Base 当前 gas price 与池内 WETH/USD 估值做近似
  - 若缺少可用 RPC / pool 上下文，会退化为 `0`
- 当前 `label`
  - `win` / `loss` 基于 gas 后 `simulated_net_pnl_usd`
  - `skip` 用于未选中或未 intent open 的样本
  - `invalid` 用于缺少足够 mark 数据的样本
