# 参考价源定位与真实溢价实测（2026-09-08 08:5x UTC，主脑亲跑）

## 1. 链上无 oracle，参考价只能来自 REST

- 股票代币实现合约（`0xb354…5ae2`，11,615 B）内嵌 22 个地址常量，**逐个查证均无合约代码**，不是 oracle 引用。
- 在股票代币上直调 Chainlink `AggregatorV3` 接口（`latestRoundData` / `latestAnswer` / `description` / `aggregator` / `priceFeed`）**全部无返回**。

**结论**：股票代币**不引用任何链上价格源**。参考价必须来自外部，当前唯一可用的是 REST。

## 2. 参考价源：`GET /rhj/prices` 与 `/rhj/prices/{SYMBOL}`

一次返回全部 **194 个标的**。实测字段比 PRD §9.3 假设的更完整：

```json
{"tokenSymbol": "SPY",
 "deployments": [{"contractAddress": "0x117c…4C0C", "chainId": 4663}],
 "bid": "766.86", "ask": "766.95", "currency": "USD",
 "dailyTradingVolume": "106484", "isTradingHalt": false,
 "generatedAt": "2026-09-08T08:53:41.707033470Z",
 "dailyHigh": "770.49", "dailyLow": "766.73",
 "mintBurnTokenVolume": "3042.256", "mintBurnUsdVolume": "2333121.33768"}
```

对 PRD 的三条补充：

| 字段 | 价值 |
|---|---|
| `generatedAt` | **服务端生成时间**，PRD §8.1 明令「拉取时间不能替代服务器 generatedAt」——此处有真值可用，报价龄实测 3–4 秒 |
| `isTradingHalt` | 直接给出停牌状态，无需从时段推断 |
| `mintBurnTokenVolume` / `mintBurnUsdVolume` | **一级申赎流量**。PRD §13 的 `SUPPLY_EVENT_REVIEW` 与 §10.2 的「AP 增发修复溢价」原本只能靠 `totalSupply` 差分推断，现在有直接观测量 |

`?symbols=` 查询参数不被支持（返回 400 并暴露内部 protobuf 类型名 `GetPricesRequest`）。只能全量拉或单标的拉。

## 3. 首次真实溢价测算

`reference_token_price_usd = underlying_mid × currentMultiplier`（PRD §9.2），与 DEX 池价比较：

| 标的 | REST mid | 乘数 | token 参考价 | DEX 价 | 溢价 | 停牌 | 报价龄 |
|---|---|---|---|---|---|---|---|
| SGOV | 100.48 | 1.005102 | 100.99 | 101.36 | **+37 bps** | OK | 3s |
| GLD | 402.75 | 1.000000 | 402.75 | 405.35 | **+65 bps** | OK | 3s |
| SPY | 766.98 | 1.000000 | 766.98 | 768.86 | **+24 bps** | OK | 3s |
| QQQ | 717.36 | 1.000000 | 717.36 | 718.78 | **+20 bps** | OK | 3s |
| NVDA | 230.43 | 1.000000 | 230.43 | 231.11 | **+30 bps** | OK | 4s |
| AMC | 2.64 | 1.000000 | 2.64 | 2.6142 | **−90 bps** | OK | 4s |

五个 ETF／大盘股溢价集中在 **20–65 bps**，全部落在 PRD §12 的 `NORMAL`（<100 bps）档内。AMC 折价 90 bps，同样在 NORMAL 内。**没有一个标的处于 PRD 的 `REDUCE_SIZE`（100–300 bps）或更高档位。**

## 4. 又一个会造成假绿的坑：**池的 token 顺序不固定**

首次计算 AMC 溢价得到 `1.45e27 bps`——荒谬值。根因：

| 池 | token0 | token1 |
|---|---|---|
| SGOV / NVDA / GLD / QQQ | **USDG**(6) | STOCK(18) |
| **AMC** | **STOCK**(18) | USDG(6) |

Uniswap V3 按地址大小排序 token，**不保证计价币恒在 token0**。若代码假定 token0 恒为 USDG：

- 对 USDG 在前的池 → 结果正确
- 对 STOCK 在前的池 → 价格取成倒数，再叠加 10¹² 的精度缩放错误 → 得到 1e27 量级

这与此前记录的「USDG 6 位小数」是**同一类失败模式的两个面**：都表现为「大部分池正确、少数池荒谬」。荒谬值容易发现，但若某个池恰好两边都是 18 位（如 SPY/WETH），顺序反了只会得到倒数——**量级正常、方向错误，极难察觉**。

**要求**：任何价格计算必须先读 `token0()` / `token1()` 判定角色，再按角色决定是取 `px` 还是 `1/px`，**禁止假定顺序**。

## 5. RH-05 证据缺口更新

| 证据 | 状态 |
|---|---|
| ① 身份验证 | ✅ 四个 ETF 池 + USDG/WETH 全部 ATTESTED_SAME_BLOCK |
| ② **参考价** | ✅ REST `/rhj/prices`，含 `generatedAt` 与 `isTradingHalt` |
| ③ 乘数／暂停 ABI | ✅ `0xa60bf13d` / `0x97a4064f` / `0x5c975abb`，15/15 与 12/12 交叉验证 |
| ④ 真实费率 | ✅ 量级已测（非收益证据） |
| ⑤ **退出深度** | ⏳ RH-05c 进行中（codex），真实 tick 数据已备 |
| ⑥ 头寸级 fee-growth 回放 | ❌ 未开工 |

②③已补齐意味着终闸的 `data_complete_and_fresh` 首次具备可满足的条件。
