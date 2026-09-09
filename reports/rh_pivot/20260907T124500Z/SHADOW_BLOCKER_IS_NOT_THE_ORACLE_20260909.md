# Shadow 打不开，不是因为链上没有 oracle，是因为表里少两列

日期：2026-09-09 主脑实测（真实样本复算，非推理）

## 交接的核心判断需要推翻

`HANDOFF_20260909_CN.md` §4.1 与 `DECISIONS_PENDING_CN.md` 决策一都写着：
「无链上 oracle 时能否用 REST `generatedAt`——**这是 Shadow 闭环唯一剩下的阻塞项**。」

**不成立。** 用真实样本复算 `evaluate_health`：

```
真实样本算出的 flags: ['API_STALE', 'ORACLE_UNAVAILABLE']

只消掉 ORACLE_UNAVAILABLE（即 RH-02L 接线后）
  剩余 flags: ['API_STALE']
  allows_new_position('RTH', 剩余) = False        <== 仍然打不开

两个都消掉
  allows_new_position('RTH', []) = True
```

`allows_new_position` 是 `session == "RTH" and not flags`——**任何一个 flag 都足以拦死**。
所以决策一即使完全落地，shadow 也不会解锁。

## 两个 flag 的真实成因：缺列，不是缺数据

`rh_market_states` 的 14 列里**没有** `oracle_updated_at`，也**没有** `source_event_time`。
`shadow_runner` 用 `sample.get("oracle_updated_at")` 与
`sample.get("source_event_time")` 取值，`dict.get` 对不存在的键返回 `None` 而不报错。

`evaluate_health` 的两个分支于是无条件命中：
```
if oracle_dt is None:  flags.add("ORACLE_UNAVAILABLE")   # 结构性，非陈旧
if api_dt   is None:   flags.add("API_STALE")
```

**关键**：`api_stale_secs` 传进去的 `reference_age_secs` 实测只有 **3 秒**，
数据非常新鲜；但 `api_dt is None` 的分支先触发，**根本没走到年龄比较**。
新鲜度信息一直存在，只是没有以 `evaluate_health` 期望的时间戳形式提供。

## 而且监控的池根本不是股票代币池

shadow daemon 跑的是 `--pool 0x52e65b17…`，即 `POOL_USDG_WETH`
（`dec0=18` / `dec1=6`，`input_price_usd=2484`）——**CORE 桶**。

CORE 桶的价格来自链上 `sqrtPriceX96`，**本来就不需要股票 oracle**。
对它报 `ORACLE_UNAVAILABLE`，是拿股票代币的闸去卡一个 WETH/USDG 池。

决策一（REST `generatedAt`）针对的是 **STOCK 桶**；当前 shadow 跑的是 CORE 桶。
两者被混为一谈了。

## 正确的修法（分桶，且有顺序约束）

| 桶 | 价格来源 | 新鲜度依据 | 状态 |
|---|---|---|---|
| CORE（WETH/USDG） | 链上 `sqrtPriceX96` | **`good_block` 的区块时间戳** | 数据在手边，未写入 |
| STOCK | REST 参考价 | REST `generatedAt` | RH-02L 已建能力，待接线 |

区块时间戳就在 `collect_round` 的局部变量里（`blk_age` 已取过 `timestamp`
用来算 `reference_age_secs`），与溯源列是同一类问题：**数据在手边，没写进去**。

## ★顺序约束：先修 gas，再解锁 shadow★

`pool_meta.json` 的 `gas_usd_estimate` 仍是被证伪的 `0.02`（真值 $0.4614）。
一旦这两列补上，shadow 会开始真正放行并做经济计算——
**用错的 gas 算出的 shadow 结论，比不放行更糟，因为它看起来是有结论的。**

因此必须：**RH-03d（gas 刷新）落地 → 刷新 pool_meta → 重启 shadow daemon
→ 再补新鲜度两列**。反过来做会污染整段 shadow 数据。

## 一个需要用户知情的判断

用区块时间戳作为 CORE 桶的新鲜度依据，主脑判定为**修正数据管道缺陷**
（缺列导致「数据缺失」被误报成「数据陈旧」），**不是放宽闸门**：
区块时间戳是链上价格的权威时间源，对 DEX 池价而言正是正确的新鲜度依据。
用户已授权更宽松的 REST 单点数据源，此项严于彼项。

**若用户不同意这个判定，此项应回退，shadow 将继续无法在任何时段放行。**
