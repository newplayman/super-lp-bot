# 股票池经济可行性实测（2026-09-08 06:5x UTC，主脑亲跑）

数据：`STOCK_POOLS_TVL.json`（192 个有流动性的池，逐池链上余额实测）。TVL 为**计价腿余额 × 2 的粗估**，非精确 CLMM TVL；WETH 计价按实测池价 2477 USDG/WETH 换算。**这是规模判据，不是收益证据。**

## 1. 规模分布

| 门槛 | 池数 |
|---|---|
| TVL ≥ $1,000 | 149 |
| TVL ≥ $10,000 | 123 |
| TVL ≥ $100,000 | **73** |
| TVL ≥ $1,000,000 | 18 |
| 中位数 | **$44,493** |
| 最大 | NVDA/USDG 0.05%，**$9.74M** |

## 2. 用旧引擎真实仓位闸算出的硬结论

调用 `lp_netcover_engine_v1_readonly.position_cap_usd`（未改一行，`POSITION_TVL_SHARE=0.0005`）：

```
q_max <= min(tier_max, TVL x 0.0005, active x 0.02, TVL x 0.001)
```

- **192 个池全部能算出正的仓位上限**，中位数仅 **$22.43**。
- 仓位上限达到旧单仓下限 50U 的池：**73 个**。
- 反解得到的门槛非常干净：**要让单仓 ≥ 50U，池 TVL 必须 ≥ $100,000**（因为 `50 / 0.0005 = 100,000`）。

这条与 B1 §9.3 的旧结论形成鲜明对比：在旧链上，A 档股票×稳定币「M1 尺度不成立」的根因是 33 个池里最高 NetCover 只有 0.106、仓位被 TVL 占比闸压到 5–60U。**在 RH 链上，规模不再是瓶颈**——73 个池可以容纳 50U 单仓，18 个池 TVL 超百万。

## 3. 这**不**构成任何经济结论

规模只解开了 `position_cap_pass` 这一道闸。终闸十项里另外九项一项都还没证据：

| 闸 | 现状 |
|---|---|
| `identity_verified` | 仅 USDG/WETH 一个池做过 factory 回指验证；73 个股票池**一个都没做** |
| `data_complete_and_fresh` | 无 Chainlink 参考价、无 `oraclePaused()`、无 source age |
| `netcover_pass` | **无 fee APR、无真实成交量**，NetCover 根本算不出来 |
| `market_and_chain_risk_pass` | 时段分类器已就绪但尚未接入这些标的 |
| `position_and_exit_depth_pass` | **无退出报价**，只知道池里有多少钱，不知道能撤出多少 |
| `capital_policy_pass` | 100U 下 CORE 上限 42.5U < 旧单仓 50U，`CAPITAL_POLICY_CONFLICT` 未解 |

## 4. 对 RH-05 的排序建议

按「规模够 + 数据完整度高 + PRD §10.2 偏好 ETF」交集，首批研究标的：

| 标的 | 池 | TVL | 理由 |
|---|---|---|---|
| **SGOV/USDG 0.30%** | `0xfab5…1bfe` | $5.35M | 短期国债 ETF，波动最低，最适合先跑通管线 |
| **GLD/USDG 0.30%** | `0x7a6a…97ec` | $4.94M | 黄金 ETF，无财报无拆股风险 |
| **SPY/WETH 0.05%** | `0xddcb…ab5e` | $1.68M | 宽基 ETF，费档最低 |
| **QQQ/USDG 0.05%** | `0xd60a…597d` | $1.43M | 宽基 ETF |

**AMC 不进首批**：虽有 $2.31M 池，PRD D09 明令首版仅事件观察。**CRWD 单列**为乘数口径实测对照（`currentMultiplier=4.0`，全链唯一整数倍拆股）。

## 5. 下一步必须补的证据

1. 对上述 4 个 ETF 池做 factory 回指身份验证（同 USDG/WETH 的做法）。
2. 接 Chainlink 股票 feed，取 token-equivalent 参考价与 `updatedAt`。
3. 读 token 合约的 `uiMultiplier()` / `oraclePaused()` ABI。
4. 用 `eth_getLogs` 采 Swap 事件算真实费率收入（**不是网页 APR**）。
5. 测实际 size 的退出报价深度。

在 1–5 全部补齐前，任何「股票 LP 可行」的说法都是无依据的。
