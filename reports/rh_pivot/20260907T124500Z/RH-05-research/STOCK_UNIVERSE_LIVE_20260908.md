# Robinhood Chain 股票代币宇宙实测（2026-09-08 06:1x UTC，主脑亲跑）

只读 REST + JSON-RPC，无签名无广播无付费。原始快照：`RH_ASSETS_SNAPSHOT.json`（194 资产 + 41 公司行动）、`STOCK_POOLS_LIVE.json`（367 池含流动性）。

## 1. 资产层：194 个股票代币，全部 ACTIVE

| 维度 | 实测 |
|---|---|
| 资产总数 | **194**，`status` 全部 `ASSET_STATUS_ACTIVE` |
| `tokenDecimals` | **194 个全是 18**（与 USDG 的 6 位形成对比，见 §4） |
| `tradingCapabilities` schema | **100% 是 `SESSION_NESTED`**，`LEGACY_FIELDS` 命中数为 **0** |
| 时段能力分布 | 191 个三时段全可交易；**3 个 `fractional` 为 `UNTRADABLE` 而 `whole` 为 `TRADABLE`** |
| `currentMultiplier ≠ 1` | **12 个**（CRWD 为 **4.0**，即已发生 1:4 拆股；其余 11 个是分红导致的微调，如 CCL 1.0215、UPS 1.0022、AAPL 1.00057） |
| `pendingMultiplier` 非空 | **0 个**（当前无待生效公司行动） |
| 公司行动 | **41 条，全部 `CASH_DIVIDEND`**，无拆股/合并类型 |

## 2. 池层：367 个 V3 池，其中 192 个有流动性

扫描方式：194 资产 × {USDG, WETH} × {0.01%, 0.05%, 0.30%, 1.00%} 共 1552 次 `factory.getPool`。

| 维度 | 实测 |
|---|---|
| 存在的池 | **367**，覆盖 **191 / 194** 个代币 |
| 计价币 | USDG **292**，WETH **75** |
| 费档 | 1.00% **215**，0.30% **95**，0.05% **39**，0.01% **18** |
| `liquidity > 0` | **192 / 367（52%）**，覆盖 **96 个**代币 |

流动性最深的 12 个（原始 L，非 USD TVL）几乎全是 WETH 计价：SPCX、AMC、SPY、RDDT、NVDA、COIN、GME、MSTR、HIMS、GLD、TSLA。

## 3. 对 PRD 的四条修正

### 3.1 D08 的双 schema 适配在当前链上是**死代码**

PRD §9.1 与 D08 要求同时支持 `LEGACY_FIELDS` 与 `SESSION_NESTED`。实测 **194 个资产 100% 是 SESSION_NESTED，legacy 命中 0**。RH-01a 已实现的双适配仍应保留（防 API 回退），但**不得因为"legacy 分支从未被真实数据触发"就认为它被验证过**——它目前只有合成 fixture 覆盖。应在 `SCHEMA_COMPATIBILITY.md` 标注该分支为 `SYNTHETIC_ONLY_NEVER_OBSERVED`。

### 3.2 AMC 有真实深池，但 PRD D09 的"首版只观察"仍应维持

AMC/WETH 1.00% 池 `L=1.996e22`，是全链第二深的股票池。**深度不等于可做**：PRD §10.2 要求先有参考价、时段、退出报价三件证据，目前一件都没有。维持 D09 的"AMC 仅事件观察"。

### 3.3 `fractional` 与 `whole` 不一致确实存在，保守取值规则被实测支持

3 个资产 `whole=TRADABLE` 而 `fractional=UNTRADABLE`。RH-01a 的 `normalize_capability` 已实现"取更保守者"（`NOT_TRADABLE > UNKNOWN > TRADABLE`），实测证明该分支**会被真实数据触发**，不是防御性死代码。

### 3.4 乘数只应用一次的规则有真实反例可测

CRWD `currentMultiplier = 4.0` 是链上唯一的整数倍拆股样本。PRD §9.2 与用例 T18（Chainlink 已是 token-equivalent 价则不得再乘）现在**有真实标的可验证**，不必只依赖合成 fixture。RH-05 应把 CRWD 作为乘数口径的实测对照组。

## 4. 精度不对称是全局风险

股票代币 194 个全是 **18** 位，USDG 是 **6** 位。任何 `股票代币/USDG` 池的价格换算都跨越 10¹² 量级；`股票代币/WETH` 池则两边都是 18 位、无需缩放。**同一套价格代码必须按 pair 动态读 decimals**，否则 292 个 USDG 池会全部算错而 75 个 WETH 池看起来正常——这种"一半对一半错"的失败模式最难发现。

## 5. 对 RH-05 的直接输入

- 候选池全集已固化在 `STOCK_POOLS_LIVE.json`（367 条含 pool 地址、fee、quote、liquidity）。
- 首批研究标的建议按 PRD §10.2「数据完整、可退出的 ETF／高流动性标的」筛：**SPY、QQQ、GLD、SLV、SOXX、SMH、XLK、VTI、SCHD** 等 ETF 类已确认有活池，优于单股。
- 仍缺的证据（RH-05 必须补）：每个池的 USD TVL、Chainlink 参考价、`oraclePaused()`、实际退出报价深度。当前只证明了"池存在且 L>0"，**这不构成任何经济结论**。
