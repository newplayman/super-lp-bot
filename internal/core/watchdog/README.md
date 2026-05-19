# Watchdog Module

## 职责

守护循环 + 全局不变量 runtime 断言（spec §5.1）：多档循环巡检系统级风险，触发 kill-switch 或降级。

## 输入 / 输出

- 订阅 bus topic:
  - `*.position.opened` - 跟踪活跃仓位
  - `*.position.closed` - 更新仓位状态
  - `*.execution.stuck` - execution 卡死信号
  - `*.risk.kill_triggered` - 其他模块触发的 kill
  - `*.recon.mismatch` - 对账不匹配信号
- 发布 bus topic:
  - `*.risk.watchdog_warn` - Watchdog 自身发 warn
  - `*.risk.watchdog_kill` - Watchdog 触发的系统 kill

## 循环档位

| 档位 | 间隔 | 检查项 |
|------|------|--------|
| fast | 10s | execution 卡死、RPC 连通性 |
| normal | 30s | 仓位状态一致、pending tx 超时 |
| slow | 1min | 全局敞口不变量 (#1)、stop-loss 时限 (#6) |
| health | 5min | 综合健康检查、审计日志完整性 |

## 不变量关联

- #1 总敞口 ≤ 配置上限（slow 档）
- #6 stop-loss 触发 ≤ N 秒内必有撤出 tx（normal 档）

## 状态

- in-memory: 上次各档执行时间、心跳时间戳
- DB: 无持久化（watchdog 是瞬时判断）

## 测试覆盖

- unit: Watchdog 接口、循环调度、状态迁移
- property: 不变量 #1 #6
- fork: 不适用（无链交互）

## Phase 引入

Phase 1 起实现基础循环，Phase 2 增强 VaR 触发，Phase 3 全量监控