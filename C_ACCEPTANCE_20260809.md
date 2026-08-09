# TP-C-v1 收口验收（2026-08-09）

最终结论：**C1–C5 已完成；C6/C7 未执行。当前不具备合法晋级 C6 的条件。**

原因有两项且任一项都足以阻止实盘：本轮 C2 终端 `accepted=0`；任务包要求的 C6 独立指挥官放行尚未发生。C5 仅证明 Base 构建与模拟管路可用，不把校准池伪装成 live 候选。

## FIX-C1：回归收口与 INV-GATE-02

- panel 脆化测试已改为锚定 `### 2.1 nohup`，不再被 §2.0 的首个 `install` 文本劫持。
- INV-GATE-02 明确枚举 `vetted / netcover_pass / entry_eligible / position_cap_pass`，分别覆盖 `_score_row` 与 `_enforce_fifth_gate`。
- 四个逐位摘闸变异均被测试捕获；独立摘除 `entry_eligible` 的探针以 `AssertionError: omitted terminal gate: entry_eligible` 失败。
- 历史事实已纠正：M0F 两个真实批次均出现 `netcover_pass=True + entry_eligible=False`，只是 `stable=False` 独立挡住误放行，不是纯理论风险。
- `RISK_INVARIANTS.md` 已增加 INV-GATE-02。

最终全量：`2906 passed, 14 skipped in 253.87s`，2920 collected，0 failed，0 collection error；没有新增 skip。

## FIX-C2：M1 TVL 粗筛与运行时 PositionCap

- M1/M2/M3/M4 TVL 粗筛为 `150K / 200K / 500K / 1M`，默认 M1；`--min-tvl` 只能收紧。
- TierConfiguredMax 为 `60 / 75 / 200 / 500 U`。
- 运行时定额固定为 `min(TierConfiguredMax, TVL×0.05%, ActiveLiquidityNotional×2%)`，并独立验证 TVL 0.10% 硬上限。
- `position_cap_usd`、investable、ActiveL、TVL share、hard-share 与 pass/reason 全部进入 score evidence；缺证或低于 M1 50U 时 fail-closed。
- `position_cap_pass` 已进入终闸与菜单导出；未调整 NC、STABLE、FEE_COVER 或占比常量。

真实 `scanner --once`：`screened=730 → top=30 → resolved=30 → scored=30 → accepted=0`，RPC 为 `DEGRADED`，新开仓继续被挡。30 池中 15 池 PositionCap 完整并通过，15 池因多工厂歧义缺失运行时 cap 而 fail-closed。逐池证据见 `reports/lp_c2_m1_once/20260809_c_acceptance/`。

## FIX-C3：真实历史下破退出回放

- 使用 3000 条真实 decoded swaps；3 个 LOWER breach，含 1 个 gap-through。
- 两个可接受报价场景按 paper `REMOVE_TO_STABLE`，风险库存降至 25%。
- gap-through 场景报价为 76 bps，高于既有 75 bps 硬限，正确进入 `slippage_limit → staged/limit_exit + alert`，没有虚报完成 risk-off。
- 模型成本相对真实 replay fill 偏差为 `-20.881% / -1.237% / -0.268%`；第一项已明确保留为校准警告。
- 钱包、签名、approve、广播、阈值变更均为 0。

报告：`reports/lp_defensive_exit_lower_replay/20260809_c3_acceptance/`。

## FIX-C4：Base 单仓最小执行器

- 只支持 Base、Uniswap v3 / Aerodrome Slipstream NPM、单仓；NPM/池/Token/action 白名单。
- 已实现 mint、decrease、collect、burn、ApproveExact 与退出 approve(0)。ApproveMax 强制拒绝。
- encrypted keystore 由独立 executor 进程通过 `cast mktx` 使用；没有裸私钥/助记词环境入口。
- gas estimate、EIP-1559、重试、pending nonce、pre-submit idempotency reservation、回执/revert、3 confirmations/reorg、fsync ledger 均已实现。
- simulate / quote / basis / RPC health / wallet balance 五检逐项 fail-closed。
- kill switch 进入 `EXIT_ONLY`，只允许 decrease / collect / burn / revoke。
- `LIVE_TRADING=true` 与启动确认串必须同时存在；缺任一项在签名前及广播边界抛 `LiveTradingLocked`。

定向 TDD：C4 19 passed；C4+C5 21 passed。权限隔离验收步骤见 `execution/README_BASE_M1_CN.md`。本轮没有创建真实 keystore、没有签名、没有广播。

## FIX-C5：全链路零广播预飞

C2 没有终端 accepted 候选，因此 C5 明确使用官方 Uniswap v3 WETH/USDC 0.05% 池作为**校准 fallback**，`accepted_for_live=false`：

- Open：M1 PositionCap 60U，计划 50U；双 Token ApproveExact、mint 完整 calldata、75 bps min amount、gas 与 EIP-1559 成本均落盘；五检全过。
- Exit：对同池当前公开 position 做 `decreaseLiquidity → collect → burn` 原子 `eth_call`，随后双 Token `approve(0)`；完整逐步与 multicall calldata、返回值、gas 均落盘。
- 两份报告都满足 `signed=false`、`keystore_loaded=false`、`transaction_hashes=[]`、`broadcast_count=0`。

报告：`reports/lp_base_m1_c5_dry_run/20260809_c_acceptance/`。这些结果只证明模拟管路，不覆盖 C2 终闸，不授权 C6。

## C6 / C7 状态与参数

- C6：**未执行**。没有 tx hash 是预期安全结果；需要在出现 accepted 候选后，由指挥官另行明确放行 10–20 USDC smoke。
- C7：**未执行**。100U 参数模板已落 `configs/base_m1_micro_live_v1.example.json`，其中 live/C6/C7 均为 false，broadcast_count=0。
- 参数：总资金 100U；单仓 50–60U；Reserve 40U；最大活跃仓 1；日亏 -5U 停新仓；总回撤 -10U → EXIT_ONLY；滑点 75 bps；KILL 从首笔真实开仓起算。实际 -10U floor 可能滑至约 -11～12U。

## 安全与边界复核

- real chain broadcast: 0
- signed transaction: 0
- wallet/private key/bridge access: 0
- live daemon started: 0
- M1-A Solana work: 0
- Go、`scripts/lp_long_horizon`、封存 `/opt/lpbot/lp-bot-v3`：未修改
- 既有 paper runner PID 1349731 仍存活，cwd 为本仓；未停止、未替换
