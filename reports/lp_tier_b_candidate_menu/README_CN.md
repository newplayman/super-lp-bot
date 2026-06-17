# Tier-B 候选池甄选菜单（vetted menu）— 2026-06-17

**目的**：扩大 Tier-B 候选池（此前只有 USDC-SAPIEN 过闸）。这是**研究输出/菜单**，
不是仓位决定。Tier-B 都是方向性下注，方向性敞口的 sizing 仍需指挥官拍板（gap #5）。

## 漏斗（聚合器线索 → 链上验证 → 多窗口）
1. **Stage 1（0 RPC，DefiLlama）**：全网 Base 池 → 21 个干净 quality-B 候选（一条主流腿、
   过 TVL/vol 闸、非刷量/farm 嫌疑）。
2. 从中选 **4 个"费用驱动而非奖励农场"**（apyReward=0、有真实成交量）做链上验证：
   VIRTUAL-USDC、WETH-DEGEN、USDC-MAG7.SSI、WETH-AERO(uni)。
3. **Stage 2 桥（链上，1 天窗口）**：factory.getPool 解析 + 实测 σ/range/fee_apr/il_apr/yield_cover。
4. **多窗口稳定性（6×1 天）**：对通过 yc≥1 的存活者复测，剔除单窗口巧合。

## 结果
| 池 | fee_apr(链上) | il_apr | yield_cover | 6窗稳定 | enter_frac | 结论 |
|---|---|---|---|---|---|---|
| **VIRTUAL-USDC** (uni 0.3%) | 136.8% | 16.7% | **8.2** | **YES** | 5/6 (mean fc 3.19, σ 4.89%) | ✅ **入选 B 菜单** |
| WETH-DEGEN (uni 0.3%) | 162.8% | 11.4% | 14.3 | no | 2/6 (cv 1.65, σ 8.65%) | ❌ 单窗口巧合，波动太大 IL 常吞费用 |
| USDC-MAG7.SSI (uni 0.3%) | 39.6% | 103.2% | 0.38 | — | — | ❌ IL 远超费用（指数代币） |
| WETH-AERO (uni 0.3%) | 159.5% | 348.6% | 0.46 | — | — | ❌ σ 巨大(±60% range)，IL 吞没费用 |

**4 选 1 通过**（连同已有的 USDC-SAPIEN，gap #2 多窗口同样 6/6 稳定）。

## 当前 vetted Tier-B 菜单
- **USDC-SAPIEN** (aerodrome, ±17.8%, yc 9.4, 6/6 稳定) — 已在 run_final
- **VIRTUAL-USDC** (uniswap-v3, 0x529d2863…, ±18.1%, yc 8.2, 5/6 稳定, σ 4.89%) — **本次新增**

两者都过三闸：质量-B（一条主流腿）+ 链上 yield_cover≥1 + 多窗口稳定。

## 第二批验证（batch2/，2026-06-17 指挥官回来后扩到 3 仓）
再验 4 个 fee-driven quality-B：
| 池 | yc(链上) | 6窗稳定 | 结论 |
|---|---|---|---|
| **WETH-BRETT** (aero) | 28.5 | **YES** 5/6, mean fc 5.90 | ✅ **入选**（B 第 3 仓）|
| DEFI.SSI-USDC (uni) | 6.45 | no 2/6, cv 1.99 | ❌ 均值高但极不稳定 |
| CBBTC-ZEN (aero) | 0.95 | — | ❌ yc<1 |
| WETH-ZEN (aero) | 0.59 | — | ❌ yc<1 |

## 最终 vetted Tier-B 菜单（3 仓已满，每仓 1000U）
按 yc 排序:
1. **WETH-BRETT** (aero, 0x4e829f8a…, ±13.5%, yc 28.5, 5/6 稳)
2. **USDC-SAPIEN** (aero, 0x80cc0871…, ±17.8%, yc 9.4, 6/6 稳)
3. **VIRTUAL-USDC** (uni, 0x529d2863…, ±18.1%, yc 8.2, 5/6 稳)

全部三闸通过 + 指挥官政策:**B 档击穿自动退出换回本币**(exit_on_breach=True)。
组合启动分配见 reports/lp_portfolio_allocator/run_launch/allocation.json
(A 7000U/3 池被动 + B 3000U/3 池自动退出, 共 10000U)。

## 复盘:多窗口闸的价值
4 个"链上单窗口 yc 很高"的池被多窗口闸剔除(WETH-DEGEN 14×、DEFI.SSI-USDC 69× 均值
但只 2/6 稳)。**单窗口 yc 高 ≠ 可入选**,和 BNKR-WETH/TIG-USDC 一个教训。
