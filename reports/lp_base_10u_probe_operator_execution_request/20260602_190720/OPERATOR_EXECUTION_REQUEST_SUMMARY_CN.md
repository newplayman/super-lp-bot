# Operator Execution Request Summary

- stage: `LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1`
- phase: C
- run_id: `20260602_190720`

## 一句话

请操作员审视 10U Base WETH/USDC LP probe 的最终授权包，在 A / B / C 三个选项中作出选择。**当前阶段不会执行任何链上动作；任何选择都通向下一阶段（A → armed runner build；B → 包修复；C → 停止研究），仍非 send 时刻**。

## 这不是什么

> **这不是正 EV 押注**

| 维度 | 状态 | 来源 |
|---|---|---|
| `edge_proven` | **no** | 所有上游 FINAL_VERDICT.json |
| `tiny_canary_allowed` | **no** | 上述 |
| 历史 backtest / paper 证明正 EV | **没有** | `reports/final_freeze/20260531_124000/` 与 `CLAUDE.md` |
| 当前 LP strategy research 状态 | **FROZEN** | `docs/LPBOT_RESEARCH_STATUS_CN.md` |

任何对"赚钱"的期待都不应作为操作员选 A 的理由。

## 这是什么

> **10U 小额通道探针，目的是买数据**

### 目的

| 目的 | 期望产出 |
|---|---|
| 获取真实 tokenId | mint receipt 解析的 ERC721 Transfer event → tokenId 入 telemetry |
| 验证 mint / decrease / collect / revoke 通道 | 4 笔（或最多 5 笔含 approve）tx 全部 receipt 落盘；任意失败进 manual intervention |
| 记录 actual fee accrual | NFPM.positions 的 `feeGrowthInsideLastX128 + tokensOwed` 在 entry/hold/pre_exit/post_collect 4 个时间点 |
| 记录 actual PnL | `(exit_USDC + exit_WETH_USD) - (entry_USDC + entry_WETH_USD) - 总 gas_USD` |
| 校准未来 100 / 500 / 1000 / 2000 USD 规模的 EV 模型 | 用本轮 actual fee + actual gas + actual slippage 与 backtest/paper 期望对比，建立 reality gap 模型 |

## 候选对象（frozen — 不可更改；任何偏离 ⇒ 拒绝）

| 字段 | 值 |
|---|---|
| chain | Base (chain_id 8453) |
| protocol | Uniswap V3 (Base) |
| pool | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` |
| pair | WETH / USDC |
| fee_tier | 100 (0.01%) |
| NPM | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` |
| wallet | `0xb05b2872ace4564ff247555b6f7b097d31f3d835` |
| notional | **10** USD (10_000_000 USDC raw) |
| hold_window | **15m** |
| max_manual_extension | **none for first execution** |

## 当前已知风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| realistic EV **未证明** 为正 | 高 | 接受 — 本 probe 是数据采集，不是 EV 验证 |
| 最坏可能损失 **接近 10U + ~10U gas ≈ 20 USD** | 中 | 资金量级 sandbox；操作员心理 + 财务接受 |
| tick 漂移可能在执行时触发 abort | 中 | 27 项 pre-execution gate；fresh approval 要求 |
| approve / mint / exit 任一笔可能 revert | 中 | manual intervention 路径就位 |
| actual fee 可能 **不足以** 覆盖 gas / slippage / IL | 中 | 接受 — 这是数据采集的代价 |
| pool 极端事件（hack / depeg / 大单） | 低-中 | 单池 sandbox；不重复 |
| RPC 故障 / nonce 撞 / replacement tx | 低 | rpc_call 5 次 retry；receipt timeout 120s ⇒ manual intervention |
| 操作员误操作（typo / 错 wallet / 错 pool） | 低 | 4 项 cross-check + 27 危险词；27-gate checklist |

## 当前仍不能执行

| 障碍 | 状态 |
|---|---|
| executor v2 `execute-guarded` 永远 raise hard-disable | **active** (line 974) |
| 当前 stage 没有 execution runner | n/a |
| 上一阶段 `next_execution_command_draft` 已标记 hard-disable 未解除 | confirmed |
| 解除 hard-disable 必须独立 commit + 二审 | spec 已写明 |

## 用户下一步

请去 `OPERATOR_DECISION_MENU_CN.md` 选 A / B / C。

**A** = 进 armed runner 构建（仍不发 tx）；
**B** = 回 authorization package 修复；
**C** = 停 LP 研究。

**禁止** 在本阶段选 "直接执行"。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
execution_allowed_now         = false
hard_disable_still_active     = true
tiny_canary_allowed           = no
edge_proven                   = no
this_stage_only_assembles_request = true
```
