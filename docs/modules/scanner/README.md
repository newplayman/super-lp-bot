# Scanner

## 职责
扫描候选池并发布 `pool.scored` 事件（spec §3.1）。

## 输入 / 输出
- 订阅 bus topic: `pool.candidate`
- 发布 bus topic: `pool.scored`
- 调用 ports: `Datasource`、`PoolRepo`

## 状态
- DB tables: `pool_score_history`
- in-memory: 待评分池队列

## 不变量
- 维护 #N（链接到 spec §9.2）

## 测试覆盖
- unit: 骨架编译测试
- property: 待 Phase 1 实现

## Phase 引入
Phase 1 起实现，Phase 2 增强