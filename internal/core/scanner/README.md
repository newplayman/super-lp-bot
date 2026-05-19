# Scanner

## 职责
扫描候选池并发布 `pool.scored` 事件（spec §3.1）。

## 输入 / 输出
- 订阅 bus topic: `pool.candidate`（候选池列表）
- 发布 bus topic: `pool.scored`（评分后的池）
- 调用 ports: `Datasource`（历史价格/量）、`PoolRepo`（存储评分结果）

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

## 实现路径
1. T-070: 骨架 stub（Phase 0）
2. T-301: Run() 实现（Phase 1）
3. T-302: Score() 实现（Phase 1）
4. T-303: AssignTier() 实现（Phase 1）