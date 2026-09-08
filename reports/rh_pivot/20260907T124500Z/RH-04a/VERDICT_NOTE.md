# RH-04a 主脑裁决：ACCEPT

17 个测试全绿，脚本 250 行，`float(` 零命中，全量 3307 passed / 14 skipped。

## 主脑独立复核（不依赖 worker 自报）

| 用例 | 验证 | 结果 |
|---|---|---|
| **T38** | collect、价不变、gas=0 | NAV `102 → 102`，**Decimal 精确相等**，不是容差内近似 |
| **T39** | collect、gas=0.10 | NAV `102 → 101.90`，delta 精确 `-0.10`；gas 只扣一次（RH-INV-12） |
| **T40** | 外部入金 10、无交易 | NAV +10 但 `net_pnl == 0` |
| **内部/外部流** | 六种类型 | `collect` / `remove_liquidity` / `bucket_transfer` / `swap` 全为内部；`deposit` / `withdrawal` 为外部；未知类型抛 `UNKNOWN_FLOW_KIND`（RH-INV-13） |
| **缺输入** | `wallet=None` | 抛 `NAV_INPUT_MISSING: wallet`，**不返回 0** |
| **D04** | HODL 基准 | `1 WETH + 1000 USDG = 3500`，`3 WETH + 1000 USDG = 8500`——随实际初始两腿数量变化，非 50/50 假设 |
| **§12.4** | 无价资产 | 进 `unvalued` 并从 NAV 扣除（`100 → 70`），**不按最后成交价估值** |

## 一处自我更正

主脑首次验证 D04 时构造的两组输入总值恰好都等于 7500（1×2500+5000 与 2×2500+2500），得出"两者相同"的错误观察。换用总值不同的输入后确认实现正确。**记录此事以防后续误读该次输出。**

**裁决：ACCEPT。**
