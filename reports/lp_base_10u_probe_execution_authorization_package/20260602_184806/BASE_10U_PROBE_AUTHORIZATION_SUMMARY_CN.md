# Base 10U LP Probe — Authorization Summary

- stage: `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1`
- phase: C
- run_id: `20260602_184806`

## 候选参数（frozen — 任何偏离即拒绝）

| 维度 | 值 |
|---|---|
| candidate_chain | **Base** (chain_id 8453) |
| candidate_protocol | **Uniswap V3** (Base) |
| pool | **0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38** |
| pair | **WETH / USDC** |
| fee_tier | **100** (0.01%) |
| tick_spacing | 1 |
| NonfungiblePositionManager (NPM) | **0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1** |
| QuoterV2 | 0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a |
| WETH | 0x4200000000000000000000000000000000000006 |
| USDC | 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913 |
| wallet | **0xb05b2872ace4564ff247555b6f7b097d31f3d835** |
| notional | **10 USD** (10_000_000 USDC raw = 10 * 1e6) |
| hold_window | **15m** |
| **max manual extension** | **NONE for first execution** — 第一轮必须严格 15m，不允许临时延长；任何 hold 调整必须重新生成 approval + 重审 |

## 期望操作序列（仅当未来阶段重新解封 send 后执行）

| # | 步骤 | 类型 | 备注 |
|---|---|---|---|
| 1 | **preflight** | read-only | 重读 chain_id / slot0 / NPM 代码 / pool 代码；recompute dynamic tick range；检查 gas/USDC/WETH balance；检查 allowance |
| 2 | **approve exact USDC** _(conditional)_ | tx | 仅在 USDC allowance(NPM) < 10_000_000 时执行；amount = 10_000_000 raw（exact）；**禁 ApproveMax** |
| 3 | **mint LP position** | tx | NPM.mint(WETH, USDC, fee=100, tickLower=dynamic, tickUpper=dynamic, amount0Desired=0, amount1Desired=10_000_000, amount0Min=0, amount1Min=9_950_000, recipient=wallet, deadline=now+3600)；deadline runtime |
| 4 | **record tokenId** | read-only | 从 mint receipt 解析 ERC721 `Transfer(0x0, wallet, tokenId)` log；若解析失败 ⇒ **manual intervention**，停 |
| 5 | **hold monitor** | read-only | 15 分钟内每 1-3 分钟 read-only 读取 slot0 + NFPM.positions(tokenId)；记录 actual fee state；不动 chain |
| 6 | **decreaseLiquidity** | tx | NPM.decreaseLiquidity(tokenId=记录值, liquidity=本 position 全部, amount0Min, amount1Min, deadline=now+3600) |
| 7 | **collect** | tx | NPM.collect(tokenId, recipient=wallet, amount0Max=uint128.max, amount1Max=uint128.max) |
| 8 | **revoke allowance** _(conditional)_ | tx | 若 step 2 执行过，则 approve(USDC, NPM, 0) 撤销授权 |
| 9 | **final PnL report** | read-only | 计算 entry/exit value、fee earned、gas cost、actual PnL；写 telemetry artifact |

每个 tx 步骤 (#2/#3/#6/#7/#8) 都必须：

- runtime-generated deadline = now + 3600
- 单笔 gas 估算 < `MAX_GAS_LIMIT_PER_TX`（建议 600_000）
- gas_price < `MAX_GAS_PRICE_GWEI`（建议 2 gwei）
- 收到 receipt 后立刻 telemetry 落盘；若 receipt timeout（≥ 120s），manual intervention

## 这不是什么

> **关键警告**：本 probe **不是**正 EV 策略证明，**不是**已通过 edge proven。

| 真相 | 含义 |
|---|---|
| **高风险小额通道探针** | 目的是验证执行通道是否通畅、获取真实的 fee accrual 数据点 |
| **不是正 EV 策略证明** | edge_proven = no；本 probe 后续也不会自动转为正 EV 证明 |
| **真实结果可能亏损** | 10U + gas 全损是可能的情景之一 |
| **目标 = 数据，不是利润** | 成功标准是拿到 tokenId、actual fee data、actual PnL 数字 — 不是赚钱 |

## 成功标准（执行后判定）

| 必须达到 | 期望 |
|---|---|
| tokenId 提取成功 | 来自 mint receipt ERC721 Transfer event |
| entry fee state 记录 | NFPM.positions(tokenId) 完整字段 |
| hold fee state 记录 | 至少 1 次中间读取 |
| pre-exit fee state 记录 | decreaseLiquidity 之前 |
| post-collect fee state 记录 | collect 之后 |
| actual PnL 计算 | (exit_USDC + exit_WETH_USD) - (entry_USDC + entry_WETH_USD) - 总 gas_USD |
| telemetry 全 7+4 artifact 落盘 | preflight / dynamic_range / approval_check / unsigned_approve / unsigned_mint / stop_conditions / execution_gates + entry/hold/pre-exit/post-collect fee state |

## 失败但仍可接受场景

- mint reverted 但 USDC 未损失（仅 gas 损失） — 仍记录 telemetry，标记 status=mint_failed
- decreaseLiquidity reverted — 进 manual intervention；不允许自动重试
- collect 返回 0 fee — 仍记录 actual fee state

## 失败且必须升级 manual intervention 场景

- tokenId 解析失败
- positions(tokenId) 与 expected params 不匹配
- decreaseLiquidity 后 collect 失败导致 token 留在 NPM
- 任意 hold 中 tick 漂出 range 且 IL > 1.0%

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
tiny_canary_allowed           = no
edge_proven                   = no
execution_allowed_now         = false
this_phase_only_assembles_doc = true
```
