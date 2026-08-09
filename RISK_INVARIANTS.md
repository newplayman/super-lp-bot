# RISK_INVARIANTS — Tactical LP Bot v2.1 系统不变量
**日期：2026-08-08。地位：高于任何策略参数与 Tier 软策略；违反任一不变量 = 阻断动作 + 告警，不是降分。**
**每条含：声明 / 强制点（哪个模块在何时校验）/ 测试。全部测试须在 M0 结束前绿。**

---

## INV-IL-01 — fee/reward 不得进入 LP_NAV_EX_FEE

- **声明**：`LP_NAV_EX_FEE` 只含按当前 tick/range/liquidity 推算的 position 本体两腿价值；任何已收/未收 fee、reward 不得混入。
- **强制点**：`il_inventory_engine` 的 NAV 计算函数（单一入口，禁止旁路计算）。
- **测试**：给定固定 position，注入任意 fee/reward 增量 → `LP_NAV_EX_FEE` 不变；`IL_vs_HODL` 不变。

## INV-IL-02 — 每个 active position 必须有不可变 entry HODL 基线

- **声明**：`(q0_entry, q1_entry)` 在 mint 时刻写入（entry-ratio swap 完成后、mint 前的实际两腿数量），此后只读；entry swap 成本单独入交易成本账。
- **强制点**：开仓流程写入 ledger `positions` 表（NOT NULL、无 UPDATE 路径）；rebalance 产生**新 position 新基线**，旧仓按退出结算。
- **测试**：尝试更新基线字段 → 拒绝；同一价格比下 `IL≈0`（tick rounding 容差）；价格比偏离越大 |IL| 单调不减；**out-of-range 后继续移动价格，IL_vs_HODL 仍变化**（不冻结）。

## INV-EXIT-01 — Risk-off 完成 = 库存回到目标风险，不是 liquidity removed

- **声明**：任何止损/风控退出流程的终态判定是"账户 risky inventory ≤ profile 目标"，`removeLiquidity` 成功不等于退出完成。
- **强制点**：`exit_policy` 状态机——EXITING 态只有在 post-trade inventory 校验通过后才转 COOLDOWN。
- **测试**：§12.2 Defensive Exit Replay：下破后 80%+ risky 库存场景，仅 remove 不 swap → 系统不得标记 risk-off 完成。

## INV-EXIT-02 — REMOVE_TO_STABLE / PANIC_EXIT 必须过 quote + 最大滑点闸

- **声明**：任何换回稳定币的动作先 quote；超过滑点硬线不得盲 swap，转入可解释的分阶段/限价退出状态并告警。
- **强制点**：`exit_policy` → 执行 sidecar 契约（slippage 硬上限是 sidecar 侧参数，Python 侧无法绕过）。
- **测试**：quote failure 与滑点超限两个 replay 场景 → 断言不发 swap、状态机进入分阶段退出、告警发出。

## INV-COST-01 — 预期净利不足成本安全倍数禁止开仓

- **声明**：`ExpectedNetProfit_H < max(MinProfitUSD, SafetyMultiple × RoundTripCost)` → 禁止开仓（SKIP），无论显示 APR 多高。Tiny 默认 SafetyMultiple=5、MinProfitUSD=$1。
- **强制点**：`netcover_engine` 出仓前最后一闸；allocator 不得输出违反此式的仓位。
- **测试**：构造"年化 80% 但 30U/12h 预期 $0.08"的池 → SKIP；§12.3 Cost Sensitivity 输出各仓位档 break-even。

## INV-RPC-01 — DEGRADED 禁新增；EXIT_ONLY 只允许减风险动作

- **声明**：DEGRADED：禁 open/add，存量继续监控；EXIT_ONLY：仅 remove/collect/swap→USDC，禁 add、rebalance、新 token approve。
- **强制点**：`rpc_health` 状态注入 risk gate；执行 sidecar 按状态过滤 action allowlist（双层）。
- **测试**：模拟 429 风暴/双源失效 → 断言各态动作过滤正确（含 sidecar 层拒绝）。

## INV-RPC-02 — 付费服务开通必须指挥官人工确认（v2.1 新增，非审计原文）

- **声明**：`RPC_UPGRADE_GATE` 触发后系统只产出升级建议报告；任何付费 RPC/API 的开通需指挥官确认 + 预算上限 + 用量告警。bot 无权自主产生计费。
- **强制点**：系统内不存在任何写入付费凭据/开通计费的自动路径（代码审查项）。
- **测试**：触发升级闸 → 只有报告与告警产物，无任何配置变更。

## INV-RWA-01 — instrument 未归一化禁止直接算 basis

- **声明**：不同 issuer / multiplier / timestamp / price_semantics / session 的报价，未归一化前不得进入 basis 计算；缺字段的报价按 stale 处理。
- **强制点**：`rwa_reference` 模块类型层（basis 函数只接受 normalized instrument 对）。
- **测试**：喂入 semantics 不同的两个报价 → 拒绝并标记；multiplier 变更（split）场景 → 归一化后 basis 连续。

## INV-V4-01 — v4 hook / 费率必须来自当前链上状态

- **声明**：Uniswap v4 池的 hook 地址、LP fee、protocol fee 一律运行时读链；`hooks != address(0)` 硬拒；禁止静态配置/新闻日期作为费率依据。
- **强制点**：scanner 的 v4 pool snapshot 采集器 + risk gate 硬拒条款。
- **测试**：mock 一个带 hook 的池 → 硬拒；协议费 config 变更 → snapshot 字段随链上变化。

## INV-TVLSHARE-01 — 仓位上限运行时计算

- **声明**：`PositionCapUSD = min(TierConfiguredMax, PoolTVL×0.0005, ActiveLiquidityNotional×ActiveShareLimit)`，硬上限 0.10% TVL；静态档位表只是粗筛，不得作为最终依据。
- **强制点**：allocator 出仓与执行前双校验。
- **测试**：TVL 缩水场景 → cap 随动收缩；active liquidity 稀薄的大 TVL 池 → 被第三项约束。

## INV-GATE-01 — 阈值只能被证据收紧或校准，不能为频率放松（v2.1 新增，非审计原文）

- **声明**：NetCover/绝对利润/升档 gate 等阈值的调整只允许来自 Shadow 校准报告（附误差数据），禁止以"交易机会太少"为由调低。
- **强制点**：config 变更走 `config_version` + 变更理由记录（§10.3 可复算决策链）。
- **测试**：审计脚本核对 config 变更记录均附校准报告引用。

## INV-GATE-02 — 终态 accepted 必须合取全部终闸位

- **声明**：终态 `accepted` 必须显式合取每一个终闸布尔位。当前边界包括 `vetted`、`netcover_pass`、`entry_eligible`、`position_cap_pass`；未来新增终闸位时，必须同时加入终闸合取式与本不变量的枚举注册表。任何单一闸位为 false，最终 `vetted/accepted` 都必须为 false；不得依赖另一个无关闸“碰巧”挡住。
- **强制点**：scanner 的 `_enforce_fifth_gate` 先以 pre-NetCover `entry_eligible` 为权威生成最终 `vetted`；`_score_row` 在持久化 `accepted` 前再次合取全部终闸位，形成两层保护。
- **测试**：`tests/test_inv_gate_02_terminal_conjunction.py` 枚举两个终态函数消费的全部 gate 字段，逐位置 false；同时校验合取式 AST 结构，并用逐闸摘除变异体证明元测试会失败。

---

## 与测试套件的映射

| 不变量 | 主测试载体 |
|---|---|
| INV-IL-01/02 | §12.1 IL Math Replay + 附录 C P0-1 验收 5 条 |
| INV-EXIT-01/02 | §12.2 Defensive Exit Replay |
| INV-COST-01 | §12.3 Cost Sensitivity |
| INV-RPC-01/02 | RPC 降级 replay + 升级闸演练 |
| INV-RWA-01 | §12.5 RWA Session Replay 前置校验 |
| INV-V4-01 | v4 snapshot 采集器单测 + 硬拒用例 |
| INV-TVLSHARE-01 | allocator 单测（TVL/active-liquidity 边界） |
| INV-GATE-01 | config 变更审计脚本 |
| INV-GATE-02 | `test_inv_gate_02_terminal_conjunction.py` 终闸枚举 + 摘闸变异测试 |
