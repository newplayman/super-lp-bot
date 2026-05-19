# PnL (Profit and Loss)

## 职责
实时仓位估值与盈亏计算。追踪 mark-to-market（盯市）价值、已实现盈亏（realized PnL）、无常损失（IL），为风控和策略提供决策依据。

## 输入 / 输出

### Bus 订阅
- `<env>.position.opened` — 新仓启动，初始化跟踪
- `<env>.position.closed` — 仓平，计算已实现 PnL，写 ledger
- `<env>.tx.confirmed` — 手续费收集触发
- `<env>.tx.reorged` — 回滚盯市估值

### Bus 发布
- `<env>.position.priced` — 周期性仓位估值发布
- `<env>.position.range_breach` — 仓位超出预设范围
- `<env>.risk.var_updated` — VaR 更新（Phase 2+）

### Ports 调用
- `ports.LedgerRepo` — 追加 PnL 分项记录（fee/IL/swap/gas/slippage/rug）
- `ports.PositionRepo` — 读写仓位状态
- `ports.PoolRepo` — 读取池当前状态（价格、流动性）
- `ports.Bus` — 发布估值事件
- `ports.Alerter` — 告警（P0/P1）
- `ports.Chain` — 读取链上实时价格

### 依赖 pkg
- `pkg/il` — IL 计算（V2/V3）
- `pkg/decimal` — 高精度算术

## 状态

### DB Tables
- `pnl_ledger` — append-only 分项记录

### In-memory
- 当前仓位盯市价值缓存
- 每仓位累计 fee/IL 快照

## 不变量
- #5: daily realized_pnl_ledger == Σ closed_position_pnl
- #6: stop-loss 触发 ≤ N 秒内有撤出 tx 或 ALERT

## 测试覆盖
- unit: MarkMarket, CalcRealizedPnL, IL 计算
- property: PnL 非负性边界、VaR 单调性（Phase 2+）
- fork: N/A（PnL 是计算模块）

## Phase 引入
Phase 0 部分实现（仅计算子集）；Phase 1 实时盯市；Phase 2 VaR