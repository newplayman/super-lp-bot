# 四个 ETF 候选池：身份验证 + 首次真实费率测算（2026-09-08 07:0x UTC，主脑亲跑）

## 1. 身份闸全部通过（锚定区块 57,505,038）

对每个池调 `token0()/token1()/fee()/tickSpacing()`，再用 `factory.getPool(token0,token1,fee)` 反查，要求回指自身。

| 标的 | 池地址 | fee | tickSpacing | token0 | token1 | 身份 |
|---|---|---|---|---|---|---|
| SGOV | `0xfab5…1bfe` | 3000 | 60 | USDG(6) | SGOV(18) `0x92fd…f9b5` | **ATTESTED_SAME_BLOCK** |
| GLD | `0x7a6a…97ec` | 3000 | 60 | USDG(6) | GLD(18) `0xc9a9…fc4e` | **ATTESTED_SAME_BLOCK** |
| SPY | `0xddcb…ab5e` | 500 | 10 | WETH(18) | SPY(18) `0x117c…4c0c` | **ATTESTED_SAME_BLOCK** |
| QQQ | `0xd60a…597d` | 500 | 10 | USDG(6) | QQQ(18) `0xd5f3…de68` | **ATTESTED_SAME_BLOCK** |

四个池运行时代码均为 22142 字节，与已验证的 USDG/WETH 池一致（同一 V3 池实现）。

**精度不对称实证**：三个 USDG 计价池是 `6位/18位`，SPY/WETH 是 `18位/18位`。同一套价格代码若写死精度，会出现 USDG 池全错而 WETH 池正常的"一半对一半错"。

## 2. 首次真实费率测算（不是网页 APR）

方法：`eth_getLogs` 取 V3 `Swap` 事件（topic `0xc42079f9…cca67`），解 `amount0` 求成交额，乘费档得费用。窗口 5000 区块 = **504 秒（8.4 分钟）**。

| 池 | 费档 | swaps | 窗口成交额 | 窗口费用 | 年化费/TVL |
|---|---|---|---|---|---|
| USDG/WETH | 0.01% | **1,496** | $1,258,049 | $125.80 | 24.68% |
| SGOV/USDG | 0.30% | 12 | $6,035 | $18.10 | 21.18% |
| GLD/USDG | 0.30% | 2 | $269 | $0.81 | 1.02% |
| SPY/WETH | 0.05% | 65 | $22,871 | $11.44 | **42.56%** |
| QQQ/USDG | 0.05% | 26 | $2,163 | $1.08 | 4.73% |

## 3. 这些数字**不是**收益证据

| 为什么不能当结论 | 依据 |
|---|---|
| 样本仅 **8.4 分钟** | PRD §21.1 要求 ≥72h 正向观测；单窗口外推年化在数学上无意义 |
| 是**全池**费用，不是本 LP 份额 | PRD §11.2：不能按 TVL 占比直接乘全池 volume；须回放头寸在有效区间的实际 fee-growth |
| 未扣任何成本 | 无 gas、无换腿、无滑点、无 IL、无逆向选择。PRD §11.3 的全成本清单一项未计 |
| TVL 是粗估 | 计价腿×2，非精确 CLMM TVL；`active_liquidity` 未测 |
| 未验证有机性 | PRD §10.3 与 §18.2：raw volume 不等于有机成交量 |

**正确用法**：这组数字只说明**量级**——USDG/WETH 8 分钟内 1496 笔成交、125 美元费用，是真实活跃的池；GLD 8 分钟只有 2 笔，流动性存在但订单流稀薄。仅用于排序候选，不进任何经济判定。

## 4. RH-05 剩余必补证据

已补：① 身份验证 ✓　④ 真实费率量级 ✓（量级而非结论）

仍缺：
- ② **Chainlink 股票参考价**与 `updatedAt`（PRD R06，token-equivalent 口径）
- ③ token 合约的 `uiMultiplier()` / `oraclePaused()` / `newUIMultiplier()` / `effectiveAt()` ABI 读取
- ⑤ **实际 size 的退出报价深度**——目前只知池里有多少钱，不知能撤出多少
- ⑥ 头寸级 fee-growth 回放（把全池费用换算成本 LP 应得份额）

在 ②③⑤⑥ 补齐前，终闸十项里 `data_complete_and_fresh`、`netcover_pass`、`position_and_exit_depth_pass` 三项**必然为 False**，任何股票池都无法进入可部署终态。这与 PRD §8.4 的 fail-closed 设计一致，不是缺陷。
