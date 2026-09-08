# SPY 退出深度在 USDG 池重测（2026-09-08 15:0x UTC，主脑亲跑）

## 起因

上线溢价录制器时发现：今早 `EXIT_DEPTH_LIVE_20260908.md` 里 SPY 的退出深度是在
**WETH 计价池**（`0xddcb…ab5e`）上测的，而实盘按 USDG 计价。当时我把这条记为
「须在 Stage B 前重测」。本文即该重测。

## 结果：在本项目的仓位规模上，两池没有实质差别

卖出 SPY 方向，滑点上限 50 bps：

| 仓位 | USDG 池冲击 | WETH 池冲击 | 差异 |
|---:|---:|---:|---|
| $500 | 0.1608 bps | 0.1605 bps | 0.2% |
| $5,000 | 1.6076 bps | 1.6050 bps | 0.2% |
| $50,000 | 16.2915 bps | 16.2227 bps | 0.4% |
| $200,000 | 流动性耗尽 | 可退 $144,703（撞 50bps 上限） | WETH 池更深 |

**结论**：WETH 池确实更深，但差别只在 **$50,000 以上**才显现。本项目受
`POSITION_TVL_SHARE=0.0005` 约束（$50 仓位需 $100k TVL），实际仓位远在该量级之下。
**因此「SPY 深度测错了池」这个担心不成立——在我们的规模上换池不改变任何结论。**
今早那份报告的 SPY 数字不必作废。

## 我自己在这次重测里踩的三个坑（值得记下）

### 1. 又踩了自己今早记录的「池 token 顺序」陷阱

首轮我对两个池一律传 `zero_for_one=True`（卖 token0）。但

| 池 | token0 | token1 | 卖 SPY 的方向 |
|---|---|---|---|
| SPY/USDG | **SPY**(18) | USDG(6) | `zero_for_one=True` |
| SPY/WETH | **WETH**(18) | SPY(18) | `zero_for_one=False` |

于是在 WETH 池上「卖 SPY」被算成了「卖 WETH」，同时输入价却填的是 SPY 的 $768.19，
两个错误叠加得到 WETH 池冲击 5.07 bps（真值 1.61）——**是真值的 3.16 倍，
恰好约等于 WETH/SPY 的价格比 3.23**。数字量级正常、单调性正常，只是全错。

我据此一度写出「USDG 池反而比 WETH 池深」的结论。**这正是
`REFERENCE_PRICE_AND_PREMIUM_20260908.md` §4 我自己写下的那条警告的实例：
不假定 token 顺序，必须先读 `token0()`/`token1()` 判角色。写下规则不等于遵守规则。**

### 2. `**pool_state` 让拼错的参数名静默通过

`exit_depth_for_size(*, position_value_usd, max_impact_bps, **pool_state)` 内部要的是
`current_tick` / `fee_pips`，我传的是 `tick` / `fee`。由于收在 `**pool_state` 里，
**没有任何报错**；内部 `KeyError` 被 `except (KeyError, TypeError, ValueError, ArithmeticError)`
捕获，统一返回 `INPUTS_UNAVAILABLE: EXIT_QUOTE`。

调用方因此**无法区分「我拼错了键名」与「链上确实没有数据」**。我为此白跑三轮。
建议（记入后续修复）：对必需键做显式校验并抛出指明键名的异常，或在返回里带上
`missing_keys` 字段。

### 3. `liquidity_exhausted` 被归成 `INPUTS_UNAVAILABLE`，语义是错的

$200,000 在 USDG 池上耗尽流动性，函数返回 `INPUTS_UNAVAILABLE: EXIT_QUOTE`。
但「池子吃不下这个量」是一个**算出来的答案**（PRD 语义下属 `COMPUTED_FAIL`），
不是「输入缺失」。二者在 fail-closed 下的动作相同，所以**没有资金风险**，
但审计链上分不清「拿不到数据」和「拿到了数据、池子太浅」——
而这两件事对应完全不同的处置。同样记入后续修复。

## 边界

- 单一时点快照（区块约 57,776,xxx），非序列。
- tick 网格取现价上下各 60 个 spacing，更远处的流动性未计入，
  因此大额（>$50k）结果偏保守。
- 未考虑同一标的在多个池间路由拆单；实盘可跨池退出，实际深度优于单池数字。
