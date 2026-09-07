# Robinhood Chain LP-Bot 全面转向设计文档 v1.0

> **用途**：交给现有 LP-Bot Agent 作为“Robinhood Chain 专用化改造”的主设计文档。  
> **原则**：不推翻现有工程；保留 Scanner → Audit → Strategy → Risk → Simulation → Execution → PnL → Watchdog → Dashboard 主骨架，重点替换数据源、链适配、策略层与风控层。  
> **组合预算**：50% Core Crypto LP + 30% Stock Token LP + 20% MEME LP。  
> **目标**：不是追网页 APR，而是最大化长期、可审计的 `Net PnL / Capital / Time`，并把 IL、adverse selection、rebalance、gas、slippage、depeg、rug 全部算进去。

---

## 0. 一句话架构结论

现有 LP-Bot 不需要重写。

把原来的“多链通用 Alpha LP Bot”改造成：

**Robinhood Chain 单链、多策略资金桶、Oracle/Fair-Value 感知、自动撤退型 LP Portfolio Manager。**

核心结构：

```text
Robinhood Chain
    │
    ├─ Onchain RPC / WS / Sequencer Feed
    ├─ Robinhood Stock Token Registry / Price API
    ├─ Chainlink Stock Token + Crypto Feeds
    └─ Uniswap AMM pools
          │
          ▼
┌─────────────────────────────────────────────┐
│ M9 Data Connector                          │
│ + RH Asset Registry                        │
│ + Oracle / Multiplier / Corp Action Guard  │
│ + Sequencer Health                         │
│ + DEX Pool Indexer                         │
└─────────────────┬───────────────────────────┘
                  ▼
┌─────────────────────────────────────────────┐
│ M1 Scanner + M2 Audit                      │
│ PoolProfile = CORE / STOCK / MEME          │
│ 三套完全不同的评分与一票否决规则             │
└─────────────────┬───────────────────────────┘
                  ▼
┌─────────────────────────────────────────────┐
│ M15 Portfolio Strategy                     │
│ 50% Core / 30% Stock / 20% MEME            │
│ Bucket Budget + Dynamic Deployment          │
│ Range / Rebalance / Exit                    │
└─────────────────┬───────────────────────────┘
                  ▼
┌─────────────────────────────────────────────┐
│ M3 Risk Gate                               │
│ Asset / Bucket / Portfolio / Chain Risk     │
│ Fair-value deviation / halt / rug / depeg  │
└─────────────────┬───────────────────────────┘
                  ▼
┌─────────────────────────────────────────────┐
│ M5 Simulation → M4 Execution               │
│ direct sequencer preferred                  │
│ add/remove/rebalance/atomic-exit             │
└─────────────────┬───────────────────────────┘
                  ▼
┌─────────────────────────────────────────────┐
│ M13 PnL + M8 Watchdog + M6 Dashboard       │
│ Fee / IL / Adverse Selection / Net Alpha   │
└─────────────────────────────────────────────┘
```

---

# 1. 为什么要从旧设计改成“三策略资金桶”

旧系统的 Tier-A / Tier-B / Tier-C 主要按 TVL、波动率、APR、Rug 风险划分。

Robinhood Chain 上更关键的区别不是“池大还是池小”，而是**资产价格形成机制完全不同**：

1. **ETH/USDG**
   - 24/7 Crypto
   - 两边都是连续交易资产
   - 适合做组合的收益底仓

2. **Stock Token/USDG**
   - 链上 24/7
   - 但底层美股和 Chainlink Stock Token feed 有市场时段
   - 存在交易暂停、公司行动、multiplier、AP mint/burn、链上溢价/折价
   - 需要 fair-value aware LP

3. **MEME/USDG 或 MEME/WETH**
   - 没有外部 fair value
   - 收益靠高 turnover / 高 fee
   - 最大问题是 rug、假量、单边下跌、LP 被动接垃圾资产

因此：

> **Tier 不再是主策略分类；Asset Profile 才是主分类。**

新增：

```go
type PoolProfile string

const (
    ProfileCoreCrypto PoolProfile = "CORE_CRYPTO"
    ProfileStockToken PoolProfile = "STOCK_TOKEN"
    ProfileMeme       PoolProfile = "MEME"
)
```

原 Tier A/B/C 可以保留，但降级为各 Profile 内部的“质量等级”。

---

# 2. 资金架构：50 / 30 / 20 是预算桶，不是强制满仓

## 2.1 总预算

设总策略资金为：

```text
TOTAL_CAPITAL = C
```

固定预算：

| Bucket | 预算 | 目标 |
|---|---:|---|
| CORE | 50% C | ETH/USDG 等主流池，提供基础 fee 收益 |
| STOCK | 30% C | AMC、指数/ETF、活跃 Stock Token |
| MEME | 20% C | 多笔小额捕获高 turnover |
| 合计 | 100% C | — |

但是：

**100% 被分配到资金桶 ≠ 100% 必须处于 active LP。**

每个资金桶必须允许保留 USDG / ETH idle reserve。

## 2.2 默认 active deployment cap

第一版建议：

| Bucket | Budget | Active 上限 | 对总资金最大实际部署 |
|---|---:|---:|---:|
| CORE | 50% | 85% | 42.5% |
| STOCK | 30% | 70% | 21.0% |
| MEME | 20% | 40% | 8.0% |
| **总计** | 100% | — | **71.5%** |

因此正常情况下最多约 **71.5% 总资金在 LP 中**。

其余资金仍属于对应 Bucket，只是处于：

```text
IDLE_USDG
IDLE_WETH
GAS_RESERVE
COOLDOWN
WAIT_FOR_ENTRY
```

而不是被重新挪到其他 Bucket。

## 2.3 为什么不能三个桶长期满仓

因为 LP Bot 最危险的时候不是“没有收益”，而是：

- 所有池同时偏离 Range；
- Stock Token 美股发生 gap / halt；
- MEME 连续单边砸盘；
- USDG 出现风险；
- Robinhood Chain sequencer / oracle 异常；
- 多个 position 同时需要撤池和 swap。

如果没有 dry powder，机器人会在最需要操作的时候失去资产配置自由。

---

# 3. 默认组合结构

## 3.1 CORE 50%

第一优先：

```text
WETH / USDG
```

Robinhood Chain 官方 canonical token：

```text
WETH = 0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73
USDG = 0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168
```

之后允许 Scanner 自动加入符合标准的主流资产池，但必须经过 allowlist。

CORE 的职责不是追最高 APR。

目标：

```text
稳定贡献 Fee
+ 降低组合波动
+ 提供 ETH / USDG 两侧库存
+ 作为 STOCK/MEME 的资金缓冲
```

---

## 3.2 STOCK 30%

优先结构：

```text
StockToken / USDG
ETF-StockToken / USDG
```

例如候选：

```text
AMC / USDG
SPY-like ETF Stock Token / USDG
QQQ-like ETF Stock Token / USDG
AAPL / USDG
NVDA / USDG
...
```

**实际 symbol 和地址必须运行时从 Robinhood canonical asset registry 获取。不得写死第三方 token 地址。**

### 关于 AMC / 指数 Stock Token 这种双风险资产对

如果“AMC/美股指数股币”指：

```text
AMC / SPY
AMC / QQQ
```

此类 pair 不作为 30% Stock Bucket 的基础配置。

原因：

- 两边都会变化；
- LP 的 fair-value ratio 需要两套 oracle；
- 不能直接通过 USDG 看净库存；
- 相关性在 meme-stock 事件中会突然失效；
- 退出时仍需要再 swap 一次才能回到 USDG。

因此：

```text
Stock / Stock
```

只能作为 `STOCK_RELATIVE_VALUE_EXPERIMENTAL`：

- ≤ Stock Bucket 15%
- 即 ≤ 总资金 4.5%
- Shadow 通过后才允许 Tiny Live
- 不得占用 AMC 的基础额度

---

# 4. 新增 Robinhood Chain 专用 Asset Registry

这是本次改造的 P0。

所有 Stock Token 必须经过：

```text
Robinhood Canonical Registry
          ↓
contractAddress
tokenSymbol
uid
currentMultiplier
pendingMultiplier
effectiveAt
asset status
tradingCapabilities
          ↓
Chainlink Feed
          ↓
AMM Pool
```

禁止：

```text
symbol == AMC → 认为是真的 AMC
```

必须：

```text
pool.token.address == registry.deployments[chainId=4663].contractAddress
```

否则一票否决。

---

# 5. Stock Token 数据模型

新增：

```go
type StockTokenMeta struct {
    Symbol                  string
    ContractAddress         common.Address
    UID                     string

    CurrentMultiplier       *big.Int
    PendingMultiplier       *big.Int
    MultiplierEffectiveAt   time.Time

    OracleAddress           common.Address
    OraclePrice             Decimal
    OracleUpdatedAt         time.Time
    OracleHeartbeat         time.Duration
    OraclePaused            bool

    UnderlyingBid           Decimal
    UnderlyingAsk           Decimal
    UnderlyingGeneratedAt   time.Time
    IsTradingHalt           bool

    FractionalTradable      bool
    AllDayTradable          bool
    ExtendedHoursTradable   bool

    RawTotalSupply          *big.Int
    TotalSupplyUI           *big.Int
}
```

再派生：

```go
type StockFairValue struct {
    UnderlyingMid       Decimal
    TokenFairBid        Decimal
    TokenFairAsk        Decimal
    TokenFairMid        Decimal

    ChainlinkTokenPrice Decimal
    DexSpotPrice        Decimal
    DexTwapPrice        Decimal

    PremiumToFairBps    int64
    PremiumToOracleBps  int64

    Regime              MarketRegime
    Confidence          float64
}
```

---

# 6. Stock Token fair value 不能写错

Robinhood REST `/prices/{symbol}` 返回的是：

```text
raw underlying share bid / ask
```

而 Chainlink Stock Token feed 返回：

```text
underlying share price × current multiplier
```

因此：

```text
token fair value
≈ underlying mid × currentMultiplier
```

如果直接拿：

```text
AMC DEX price
vs Robinhood raw AMC share price
```

比较而忽略 multiplier，迟早会在 dividend / split / corporate action 后产生严重误判。

机器人内部必须规定：

```text
所有 Stock Token 风控与策略统一使用 TOKEN-EQUIVALENT PRICE。
```

禁止不同模块各自解释 multiplier。

---

# 7. Market Regime 状态机

Stock Token 不允许用一个 Range 策略跑 24 小时。

新增：

```go
type MarketRegime string

const (
    RegimeRTH               = "RTH"
    RegimeExtended          = "EXTENDED"
    RegimeClosedWeekday     = "CLOSED_WEEKDAY"
    RegimeWeekend           = "WEEKEND"
    RegimeTradingHalt       = "TRADING_HALT"
    RegimeCorpAction        = "CORP_ACTION"
    RegimeOracleStale       = "ORACLE_STALE"
    RegimeSequencerDegraded = "SEQUENCER_DEGRADED"
)
```

策略必须先判断 Regime，再决定 Range。

### RTH

```text
美股正常交易
oracle 正常
underlying quote 正常
```

允许最积极的 Stock LP。

### Extended

流动性和 fair price 质量下降：

```text
size × 0.7
range × 1.5
```

### Closed Weekday

只允许：

- 高流动性 ETF / 大盘 Stock Token；
- 缩小 active capital；
- 放宽 Range；
- 不主动追随链上短时价格重心。

### Weekend

默认：

```text
AMC / 单股高波动资产：不新开窄 Range
ETF：仅宽 Range + 小仓
```

### Trading Halt

```text
禁止开仓
禁止 rebalance
已有 Stock Token position → REMOVE-ONLY
```

### Corporate Action

当出现：

```text
pendingMultiplier
effectiveAt
oraclePaused()
```

进入：

```text
CORP_ACTION_GUARD
```

在 effectiveAt 前提前减仓/撤池。

Oracle 恢复且：

```text
multiplier
Chainlink
Robinhood API
DEX
```

重新一致后才恢复。

### Oracle Stale

不能把 stale oracle 当 fair value。

进入：

```text
NO_NEW
NO_REBALANCE
REMOVE_ALLOWED
```

---

# 8. 50% CORE 策略

## 8.1 目标

CORE 的 KPI：

```text
Net Fee Yield
− IL
− Rebalance Cost
− Gas
− Adverse Selection
```

而不是单独看：

```text
Fee APR
```

## 8.2 Scanner 评分

第一版：

```text
CoreScore =
    0.30 × NetFeeYieldScore
  + 0.20 × VolumeTVLScore
  + 0.15 × LiquidityStability
  + 0.15 × VolatilityFit
  + 0.10 × FlowQuality
  + 0.10 × ExecutionQuality
```

必须同时记录：

```text
24h / 6h / 1h volume
TVL
active liquidity around tick
realized volatility
fee tier
fee / active-liquidity
swap count
unique trader estimate
price impact
```

## 8.3 Range

不再使用旧版：

```text
current price ± 1σ
```

作为全局固定规则。

改为：

```text
range = volatility + fee-density + inventory + trend
```

初始 shadow 参数：

```text
normal:
    1.5σ ~ 2.5σ

high fee density:
    可适当收窄

strong directional trend:
    自动放宽 / 降低仓位

range edge > 80%:
    进入 rebalance evaluation
```

## 8.4 Rebalance 条件

必须满足：

```text
ExpectedFutureFeeGain
>
RebalanceCost
+ ExpectedExtraIL
+ Slippage
+ SafetyMargin
```

否则即使触边，也不机械 rebalance。

---

# 9. 30% STOCK 策略

## 9.1 Stock Bucket 再分层

建议：

| 子桶 | Stock Bucket 内比例 | 总资金 |
|---|---:|---:|
| INDEX/ETF | 40% | 12% |
| Mega-cap / liquid single-stock | 30% | 9% |
| Event / high-volatility，如 AMC | 20% | 6% |
| Experimental Stock/Stock | ≤10% | ≤3% |

不是固定强制，Strategy 可以动态调整。

但必须满足：

```text
单个高波动 Stock Token ≤ 总资金 6%
Stock Token 单资产总暴露 ≤ 总资金 8%
```

AMC 默认使用更严格的：

```text
AMC_ACTIVE_CAP <= 6% TOTAL_CAPITAL
```

## 9.2 为什么 AMC 不能占满 30%

AMC 的核心机会是：

```text
DEX turnover 高
+ fair value 有外部锚
+ 偏离时产生套利流
```

但同样意味着：

```text
LP 是套利者的对手盘。
```

当 AMC 真正下跌时：

```text
套利者卖 AMC 给池
→ LP USDG 下降
→ AMC inventory 上升
```

因此 Stock Bucket 绝不能等于 AMC Bucket。

---

# 10. Stock Pool 的核心评分

```text
StockScore =
    0.25 × NetFeeYield
  + 0.20 × VolumeTVL
  + 0.20 × FairValueTrackingQuality
  + 0.15 × OracleAndSessionQuality
  + 0.10 × SupplyStability
  + 0.10 × LiquidityQuality
```

同时单独计算：

```text
ToxicityPenalty
PremiumPenalty
HaltPenalty
CorpActionPenalty
SupplyShockPenalty
```

最终：

```text
AdjustedStockScore =
    StockScore
  - penalties
```

---

# 11. Stock Token Range 必须锚定 fair value，不锚定 DEX spot

这是整个改造最重要的策略原则之一。

错误：

```text
DEX AMC 从 $2.6 → $8
机器人看到 spot = $8
重新把 LP Center 移到 $8
```

这样相当于机器人主动追高。

正确：

```text
FairValue = Robinhood underlying × multiplier
Chainlink = token-equivalent oracle price
DEX = market price

如果 DEX 与 fair value 极端偏离：
    不允许把 range center 跟着 DEX 走。
```

定义：

```text
center =
weighted_median(
    ChainlinkTokenPrice,
    RobinhoodTokenEquivalentMid,
    DEX_TWAP
)
```

但：

```text
DEX 权重必须受 PremiumToFair 限制。
```

当：

```text
abs(PremiumToFair) > threshold
```

DEX 不再参与 center，只用于风险判断。

---

# 12. Stock Token Premium / Discount Guard

初始 Shadow 阈值：

```text
|DEX - Fair| < 1%
    NORMAL

1% ~ 3%
    REDUCE_SIZE

3% ~ 7%
    NO_NEW + WIDEN / REMOVE_EVAL

> 7%
    DISLOCATION
    禁止重新居中
    Existing position 进入强制风险评估
```

这些只是 **shadow initial parameters**，最终阈值必须用 Robinhood Chain 实际历史数据校准。

AMC 可以使用更严格的动态规则：

```text
threshold = f(
    realized volatility,
    market regime,
    underlying spread,
    current turnover,
    oracle freshness
)
```

---

# 13. Stock Token Supply Shock Detector

AMC 类事件必须新增供应量监控。

每个区块 / 固定窗口追踪：

```text
raw totalSupply
totalSupplyUI
mint/burn events
supply delta 5m
supply delta 1h
supply delta 24h
```

定义：

```text
SupplyShockScore
```

例如：

```text
5m supply increase > 5%
    WARN

1h supply increase > 20%
    HIGH

极端扩张
    DISLOCATION MODE
```

Supply expansion 不一定是 rug。

在 Stock Token 中，它可能代表授权参与者正在用 primary market 修复链上溢价。

因此：

```text
Stock supply shock != Meme mint risk
```

必须由 Profile-specific Risk 分开处理。

---

# 14. Stock Token Adverse Selection 指标

传统 `Fee - IL` 不够。

新增：

```text
AdverseSelectionCost
```

对每笔影响 LP 的 swap：

```text
PostTradeFairMove =
FairPrice(t + Δt) - LPExecutionPrice
```

按方向计算：

```text
LP 被 informed flow 交易掉的损失
```

累计：

```text
FeeIncome
− AdverseSelectionCost
```

如果一个池：

```text
Fee APR = 500%
```

但：

```text
AdverseSelection = 480%
```

它根本不是好池。

Dashboard 必须显示：

```text
Gross Fee
Adverse Selection
Fee After Toxic Flow
```

---

# 15. 20% MEME 策略

MEME Bucket 的目标不是长期持币。

而是：

```text
短生命周期
高 turnover
高 fee density
严格撤退
```

核心原则：

> **宁愿错过，不允许“为了回到 range 不断接下跌 MEME”。**

## 15.1 单笔限制

第一版：

```text
单 MEME position:
0.5% ~ 2.0% TOTAL_CAPITAL

hard max:
2.0%

同时 active:
4 ~ 10 pools

单 token 聚合:
<= 2%
```

20% Bucket 不代表必须同时投 20%。

---

# 16. MEME 一票否决规则

必须保留并强化旧版 Audit：

```text
fork simulate sell 失败 → REJECT
blacklist → REJECT
transfer tax 超阈值 → REJECT
owner 可任意 mint → 高危/默认 REJECT
owner 可 blacklist → REJECT
owner 可改 tax → REJECT
proxy implementation 可随时换 → 高危
LP 单地址集中度过高 → REJECT
流动性突然下降 → EXIT
```

新增：

```text
wash trading score
unique trader growth
same-funder wallet cluster
buy/sell asymmetry
top holder concentration
deployer-associated flow
volume half-life
```

---

# 17. MEME 不允许“追跌 Rebalance”

旧策略如果：

```text
price out of range → rebalance
```

在 MEME 上会形成灾难性行为：

```text
价格下跌
→ Range 下移
→ LP 再次买入 MEME
→ 再跌
→ 再 Range 下移
→ 持续把 USDG 换成垃圾币
```

因此 MEME 专用规则：

```text
if exit_lower_bound:
    REMOVE
    CONVERT TO USDG
    COOLDOWN
```

不是：

```text
REMOVE → recenter lower → ADD
```

只有当：

```text
trend recovered
volume recovered
liquidity stable
organic traders growing
cooldown completed
```

才允许重新入场。

---

# 18. MEME Volume Quality，不信网页 24h Volume

定义：

```text
OrganicVolumeEstimate
```

特征至少包括：

```text
unique traders
repeat-wallet ratio
same-size trade ratio
same-block circular flow
buy/sell symmetry
wallet funding clusters
median trade size
trade-size entropy
volume concentration top-N
```

评分里使用：

```text
OrganicVolume / TVL
```

而不是：

```text
RawVolume / TVL
```

这是防止机器人被 wash-volume APR 诱骗的关键。

---

# 19. Robinhood Chain 数据层改造

## 19.1 RPC

Chain:

```text
chainId = 4663
native gas = ETH
```

Data Connector 至少维护：

```text
RPC_PRIMARY
RPC_SECONDARY
PUBLIC_RPC_FALLBACK
WS_PRIMARY
SEQUENCER_FEED
SEQUENCER_ENDPOINT
```

**public RPC 只作为 fallback / shadow 使用，不作为长期生产唯一节点。**

## 19.2 Sequencer

Robinhood Chain 为 Arbitrum L2，采用 sequencer soft confirmation。

执行层新增：

```go
type BroadcasterMode string

const (
    BroadcasterSequencerDirect BroadcasterMode = "rh-sequencer-direct"
    BroadcasterManagedRPC      BroadcasterMode = "managed-rpc"
)
```

优先：

```text
direct sequencer
```

fallback：

```text
managed RPC
```

不要把 Base 旧配置里的：

```text
Flashbots Protect
```

直接复制过来。

Robinhood Chain 的排序模型和 Base/ETH 不同，本项目必须以 Robinhood Chain 自身 sequencer 行为为准。

---

# 20. Transaction 状态机

Robinhood Chain transaction finality 分三层：

```text
SOFT_CONFIRMED
L1_POSTED
L1_FINALIZED
```

Position 可在 soft confirmation 后进入：

```text
ACTIVE_SOFT
```

然后后台继续确认：

```text
ACTIVE_L1_POSTED
ACTIVE_FINAL
```

高价值操作：

```text
bridge out
cold wallet settlement
大额资金回收
```

需要更高 finality。

日常 LP add/remove：

```text
soft confirmation 可驱动策略状态
但必须继续 reconcile。
```

---

# 21. Execution：必须新增 Atomic Exit

特别是 MEME / AMC 异常时：

传统：

```text
remove LP
等待
collect
等待
swap risky token → USDG
```

太慢。

目标：

```text
remove liquidity
+ collect
+ swap risky leg → USDG
```

尽量一笔交易完成。

新增：

```go
type ExitMode string

const (
    ExitRemoveOnly       ExitMode = "REMOVE_ONLY"
    ExitToUSDG           ExitMode = "EXIT_TO_USDG"
    ExitToWETH           ExitMode = "EXIT_TO_WETH"
    ExitEmergencyAtomic  ExitMode = "EMERGENCY_ATOMIC"
)
```

如果 Uniswap Router / Position Manager 可组合完成，则优先使用官方合约。

否则开发：

```text
LPExitExecutor
```

小型自有 helper contract。

要求：

```text
non-upgradeable
no custody
no arbitrary call
token/router allowlist
slippage hard bound
deadline mandatory
reentrancy guard
```

必须先 Testnet / fork sim。

---

# 22. Approve / Permit2

延续旧系统的原则：

```text
禁止 unlimited approval
exit 后 revoke
```

如果使用 Permit2：

```text
amount-bound
expiration-bound
spender allowlist
```

不能因为 Robinhood Chain 官方部署了 Permit2 就放弃 approve 风控。

---

# 23. USDG 风险必须单独建模

这个组合大量使用：

```text
XXX / USDG
```

因此真正的组合集中风险可能不是 AMC，而是 USDG。

新增：

```text
StablecoinGuard
```

追踪：

```text
USDG/USD reference
USDG pool imbalance
bridge liquidity
mint/burn anomaly
onchain oracle if available
cross-venue price
```

状态：

```text
NORMAL
DEPEG_WARN
DEPEG_FREEZE
DEPEG_EMERGENCY
```

Shadow 初始阈值：

```text
> 30 bps deviation:
    WARN

> 75 bps:
    FREEZE NEW

> 150 bps:
    reduce quote concentration / emergency evaluation
```

最终阈值根据实际数据校准。

---

# 24. 组合级 Risk Budget

旧版：

```text
max_single_chain_pct = 50%
max_single_protocol_pct = 40%
```

在 Robinhood Chain 单链专用系统中已经没有意义。

必须删除/替换。

新组合风险：

```text
Bucket Risk
Asset Risk
Quote Asset Risk
DEX/Contract Risk
Sequencer Risk
Oracle Risk
Market-Regime Risk
```

---

# 25. 新的组合硬限制

推荐初始值：

```text
Core budget              = 50%
Stock budget             = 30%
Meme budget              = 20%

Max deployed total       = 71.5%

Max single high-vol stock = 6%
Max single normal stock   = 8%
Max single meme           = 2%

Max meme active deployed  = 8% total
Max stock active deployed = 21% total
Max core active deployed  = 42.5% total
```

Bucket 之间默认不能借钱。

只有人工修改 signed config 才能改：

```text
50 / 30 / 20
```

---

# 26. Portfolio Drawdown Circuit Breaker

默认：

```text
Daily realized + unrealized drawdown >= 2%
    FREEZE_NEW

>= 3%
    CLOSE MEME
    REDUCE STOCK
    CORE hold/evaluate

>= 5%
    GLOBAL RISK-OFF
    remove all non-essential LP
    manual unlock required
```

周级：

```text
Weekly drawdown >= 8%
    LIVE LOCK
```

具体值要经过 Shadow 校准，但机制必须在第一版就存在。

---

# 27. Robinhood Chain 级 Kill-Switch

以下任何一个成立：

```text
Sequencer down
Sequencer uptime grace period 未结束
RPC 多源状态冲突
chain head 长时间不推进
critical contract address mismatch
Uniswap router / manager bytecode mismatch
```

进入：

```text
CHAIN_DEGRADED
```

动作：

```text
NO_NEW
NO_REBALANCE
REMOVE only if chain can safely execute
```

---

# 28. Stock Token 一票否决

任一成立：

```text
not canonical registry
asset inactive
oraclePaused == true
oracle stale
sequencer unavailable
underlying trading halt
pending corporate action near effectiveAt
price source disagreement > threshold
```

则：

```text
禁止新仓
```

Trading halt / corp action 对 active position：

```text
进入 REMOVE-ONLY / REDUCE 模式。
```

---

# 29. PnL 账本必须升级

旧：

```text
Net PnL = Fee - IL - Gas
```

新：

```text
NetPnL =
    FeeIncome
  + Incentives
  - ImpermanentLoss
  - AdverseSelectionCost
  - RebalanceSwapFee
  - PriceImpact
  - Gas
  - Slippage
  - ExitConversionCost
  - RugLoss
  - DepegLoss
```

同时计算：

```text
LPAlpha =
LPPortfolioValue
- BenchmarkHoldValue
```

这样才能回答：

> “这个 LP 到底赚了钱，还是仅仅因为资产本身上涨？”

---

# 30. 三个 Benchmark

## CORE

```text
Benchmark = 50% WETH + 50% USDG HODL
```

## STOCK

入场时记录：

```text
Benchmark =
same initial StockToken amount
+ same initial USDG amount
```

## MEME

同时记录：

```text
HODL benchmark
USDG-only benchmark
```

因为对 MEME：

```text
LP 正收益
```

仍可能：

```text
远逊于直接持有 USDG。
```

---

# 31. Fee APR 改成 Realized Fee Density

Dashboard 不再把：

```text
APR
```

当第一指标。

新增：

```text
GrossFeePerDay
FeePerActiveLiquidity
FeePerCapitalHour
NetFeeAfterIL
NetFeeAfterToxicFlow
NetPnLPerCapitalDay
```

Pool 排名默认按：

```text
ExpectedNetPnL / ActiveCapital / Hour
```

排序。

---

# 32. Scanner 三套算法

## CORE Scanner

重点：

```text
fee density
TVL stability
active liquidity
volatility
flow toxicity
```

## STOCK Scanner

重点：

```text
canonical token
fair-value tracking
oracle quality
market regime
supply changes
fee density
```

## MEME Scanner

重点：

```text
organic volume
rug risk
LP concentration
holder growth
volume decay
one-way trend
```

三者不能共享一条总评分公式。

---

# 33. 数据源优先级

## Tier 0 — 链上 source of truth

```text
Robinhood Chain RPC
Uniswap Pool contracts
Token contracts
Chainlink feeds
Sequencer status
```

## Tier 1 — Robinhood 官方

```text
Stock Token /assets
/prices/{symbol}
/corporate actions
canonical contracts
```

## Tier 2 — Index / analytics

```text
GeckoTerminal
DexScreener
other indexer
```

Tier 2 只能做：

```text
发现
粗筛
交叉验证
```

不能单独触发真实资金操作。

---

# 34. State Store 新增 Schema

保留现有：

```text
positions
pnl_ledger
risk_events
tx_log
config_snapshots
reconciliation_log
pool_scores
```

新增：

```sql
CREATE TABLE rh_assets (
    symbol                TEXT NOT NULL,
    contract_address      TEXT PRIMARY KEY,
    uid                   TEXT,
    asset_type            TEXT NOT NULL,
    status                TEXT NOT NULL,
    current_multiplier    NUMERIC,
    pending_multiplier    NUMERIC,
    multiplier_effective_at TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE oracle_health (
    asset_address         TEXT NOT NULL,
    feed_address          TEXT NOT NULL,
    price                 NUMERIC,
    updated_at_chain      TIMESTAMPTZ,
    heartbeat_seconds     INTEGER,
    oracle_paused         BOOLEAN,
    sequencer_ok          BOOLEAN,
    status                TEXT NOT NULL,
    sampled_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE market_regimes (
    asset_address         TEXT NOT NULL,
    regime                TEXT NOT NULL,
    underlying_bid        NUMERIC,
    underlying_ask        NUMERIC,
    token_fair_mid        NUMERIC,
    dex_spot              NUMERIC,
    dex_twap              NUMERIC,
    premium_bps           INTEGER,
    is_trading_halt       BOOLEAN,
    sampled_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE supply_snapshots (
    asset_address         TEXT NOT NULL,
    raw_total_supply      NUMERIC,
    total_supply_ui       NUMERIC,
    delta_5m_pct          NUMERIC,
    delta_1h_pct          NUMERIC,
    delta_24h_pct         NUMERIC,
    sampled_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE bucket_ledger (
    bucket                TEXT NOT NULL,
    total_budget_usd      NUMERIC NOT NULL,
    deployed_usd          NUMERIC NOT NULL,
    idle_usdg             NUMERIC NOT NULL,
    idle_weth             NUMERIC NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE position_marks (
    position_id           UUID NOT NULL,
    marked_at             TIMESTAMPTZ NOT NULL,
    position_value_usd    NUMERIC,
    accrued_fee_usd       NUMERIC,
    il_usd                NUMERIC,
    adverse_selection_usd NUMERIC,
    net_pnl_usd           NUMERIC,
    benchmark_value_usd   NUMERIC,
    lp_alpha_usd          NUMERIC,
    PRIMARY KEY(position_id, marked_at)
);
```

---

# 35. Position 需要增加的字段

```go
type Position struct {
    ...

    Profile         PoolProfile
    Bucket          CapitalBucket

    EntryFairPrice  Decimal
    EntryDexPrice   Decimal
    EntryRegime     MarketRegime

    InitialFeeAPR   float64
    InitialVol      float64

    Benchmark       BenchmarkSnapshot

    ExitMode        ExitMode
    CooldownUntil   time.Time
}
```

---

# 36. StrategyDecision 新字段

```go
type StrategyDecision struct {
    Action      string
    PoolID      PoolID
    Profile     PoolProfile
    Bucket      CapitalBucket

    AmountUsd   Decimal

    RangeLower  Decimal
    RangeUpper  Decimal
    RangeCenter Decimal

    FairValue   *StockFairValue
    MarketRegime MarketRegime

    ExpectedFeeUsd24h Decimal
    ExpectedILUsd24h  Decimal
    ExpectedASCostUsd24h Decimal
    ExpectedNetUsd24h Decimal

    Reasoning   string
}
```

所有 live decision：

```text
Reasoning != ""
```

并保存完整 snapshot。

---

# 37. Dashboard 改造

现有监控面板整体框架保留。

首页顶部改为：

```text
Total Capital
Deployed Capital
Idle Capital

CORE Budget / Deployed / PnL
STOCK Budget / Deployed / PnL
MEME Budget / Deployed / PnL

Gross Fees
IL
Adverse Selection
Rebalance Cost
Gas
Net PnL
LP Alpha
```

新增 Robinhood Chain 专用健康区：

```text
Sequencer
RPC Primary
RPC Secondary
Robinhood Asset API
Robinhood Price API
Chainlink
Uniswap Indexer
```

---

# 38. Dashboard：STOCK 专属表

必须显示：

| Symbol | Pool | Regime | DEX | Fair | Premium | Oracle Age | Multiplier | Supply Δ1h | Fee | IL | AS Cost | Net |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

AMC 一眼就能看出：

```text
DEX 是否脱锚
oracle 是否 stale
是否发生 supply shock
当前 LP 是在赚 fee，还是在被套利者收割
```

---

# 39. Dashboard：MEME 专属表

```text
Pool
Age
TVL
OrganicVolume
RawVolume
WashScore
LP Concentration
Holder Growth
Buy/Sell
RugScore
Range
Trend
Fee
IL
Net
TTL
```

---

# 40. Dashboard：资金桶

显示：

```text
CORE
████████████████░░ 42.5 / 50

STOCK
██████████████░░░░ 21 / 30

MEME
████████░░░░░░░░░░ 8 / 20
```

同时显示：

```text
Idle
Cooldown
Frozen
Reserved
```

---

# 41. 原系统哪些东西直接复用

以下保留：

```text
M0 Shared Types
M10 State Store
M11 Event Bus
M12 Wallet & Signer
M13 PnL framework
M14 Reconciliation
M6 Dashboard framework
M7 Artifact
M8 Watchdog
```

以下改造：

```text
M9 Data Connector
M1 Scanner
M2 Audit
M15 Strategy
M3 Risk
M5 Simulation
M4 Execution
```

---

# 42. 旧系统哪些规则必须删除

## 删除 1：多链集中度

旧：

```text
max_single_chain_pct = 50
```

新项目是 Robinhood Chain 专用。

删除。

---

## 删除 2：协议 40% 上限硬规则

如果 Robinhood Chain 的主流公开 LP 流量集中在 Uniswap：

```text
max_single_protocol_pct = 40%
```

会导致机器人无法正常运行。

改为：

```text
contract allowlist
router health
manager health
venue liquidity risk
```

---

## 删除 3：所有 Tier 共用 σ Range

删除：

```text
A = 1.5~2σ
B = 1~1.5σ
C = 0.5~1σ
```

作为跨资产统一规则。

保留 σ 作为输入，但策略由 Profile 决定。

---

## 删除 4：Out-of-range 就 Rebalance

特别是 MEME。

改成：

```text
Profile-aware exit/rebalance
```

---

## 删除 5：Fee APR 作为核心 Scanner 指标

换成：

```text
Expected Net Fee
```

---

# 43. Simulation 改造

所有 live action 仍必须 simulation。

Robinhood Chain：

```text
Anvil fork
```

覆盖：

```text
add
remove
collect
rebalance
atomic exit
Permit2
approve/revoke
```

对于 Stock：

额外 simulation invariant：

```text
fair-value metadata valid
oracle not stale
regime allows action
```

对于 MEME：

额外：

```text
simulate sell must pass
```

---

# 44. Reconciliation

启动：

```text
chain positions
wallet balances
approvals
local DB
```

必须一致。

再增加：

```text
bucket ledger sum
=
wallet capital
+ positions
```

否则：

```text
live refuses to start
```

---

# 45. 新系统不变量

以下必须写成 property tests + runtime assertions。

### I-01

```text
CORE_BUDGET + STOCK_BUDGET + MEME_BUDGET = 100%
```

### I-02

```text
deployed(bucket) <= active_cap(bucket)
```

### I-03

```text
Stock Token not in canonical registry
→ no live position
```

### I-04

```text
oracle stale || oraclePaused || trading halt
→ no Stock open/rebalance
```

### I-05

```text
corp action guard active
→ no Stock open
```

### I-06

```text
Meme simulateSell failed
→ no live position
```

### I-07

```text
Meme exits lower range in downtrend
→ cannot auto-recenter lower
```

### I-08

```text
live tx requires simulation PASS
```

### I-09

```text
slippage limit != 0
deadline != 0
```

### I-10

```text
unlimited approval forbidden
```

### I-11

```text
position exit
→ approval expired/revoked
```

### I-12

```text
startup reconciliation failed
→ live cannot start
```

### I-13

```text
sequencer degraded
→ no new LP
```

### I-14

```text
global drawdown kill
→ no new LP until signed/manual unlock
```

### I-15

```text
Stock range center cannot follow DEX price
when dislocation guard is active
```

---

# 46. 推荐 config v1

```toml
[chain.robinhood]
chain_id = 4663
native_gas = "ETH"
rpc_primary = "${RH_RPC_PRIMARY}"
rpc_secondary = "${RH_RPC_SECONDARY}"
rpc_public_fallback = "https://rpc.mainnet.chain.robinhood.com"
ws_primary = "${RH_WS_PRIMARY}"
sequencer_feed = "wss://feed.mainnet.chain.robinhood.com"
sequencer_endpoint = "https://sequencer.mainnet.chain.robinhood.com"

[portfolio]
total_capital_usd = 1000

[portfolio.bucket.core]
budget_pct = 50
max_active_pct_of_bucket = 85

[portfolio.bucket.stock]
budget_pct = 30
max_active_pct_of_bucket = 70

[portfolio.bucket.meme]
budget_pct = 20
max_active_pct_of_bucket = 40

[risk.asset]
max_high_vol_stock_pct_total = 6
max_normal_stock_pct_total = 8
max_meme_pct_total = 2

[risk.drawdown]
freeze_new_daily_pct = 2
risk_off_daily_pct = 3
kill_daily_pct = 5
weekly_lock_pct = 8

[stock]
registry_required = true
oracle_stale_reject = true
oracle_pause_reject = true
halt_reject = true
corp_action_guard = true

[stock.premium]
warn_bps = 100
reduce_bps = 300
dislocation_bps = 700

[stock.session]
extended_size_multiplier = 0.70
closed_size_multiplier = 0.40
weekend_high_vol_new_positions = false

[meme]
max_positions = 10
min_position_pct_total = 0.5
max_position_pct_total = 2.0
sell_sim_required = true
no_downtrend_recenter = true

[meme.audit]
fee_on_transfer_max_pct = 5
max_lp_concentration_pct = 70
wash_score_reject = 80
rug_score_reject = 70

[execution]
simulation_required = true
broadcaster_primary = "rh-sequencer-direct"
broadcaster_fallback = "managed-rpc"
default_deadline_seconds = 60
default_slippage_bps = 50
atomic_exit_enabled = true

[approval]
unlimited_forbidden = true
revoke_on_exit = true
permit2_max_expiry_minutes = 60

[pnl]
mark_interval_seconds = 30
track_adverse_selection = true
track_benchmark = true
track_lp_alpha = true
```

注意：

```text
total_capital_usd = 1000
```

只是 config 示例，不是建议实际本金。

---

# 47. $1,000 组合示例，仅用于验证比例

如果总资金是：

```text
$1,000
```

预算：

```text
CORE  = $500
STOCK = $300
MEME  = $200
```

正常最大 active：

```text
CORE  ≈ $425
STOCK ≈ $210
MEME  ≈ $80
```

剩余：

```text
≈ $285 idle / reserve
```

Stock 里：

```text
ETF/index       ≈ $120 budget
mega-cap        ≈ $90
AMC/event       ≈ $60
experimental    <= $30
```

这比：

```text
$300 全压 AMC
```

合理得多。

---

# 48. 开发任务拆分

## RH-P0 — Existing Code Audit

Agent 必须先检查当前仓库：

```text
已有模块
真实语言
接口
测试
DB schema
Uniswap adapter
EVM tx builder
PnL
Dashboard
```

输出：

```text
reports/rh_pivot/P0_EXISTING_CODE_MAP.md
```

禁止未审计就重写。

验收：

```text
现有 16 模块 → Robinhood 改造映射清楚
```

---

## RH-P1 — Chain Adapter

新增：

```text
Robinhood Chain 4663
RPC
WS
sequencer feed
sequencer broadcaster
finality state
```

验收：

```text
block stream stable
soft confirmation tracked
fallback RPC works
```

---

## RH-P2 — Canonical Asset Registry

实现：

```text
Robinhood /assets
token contract validation
WETH / USDG allowlist
Stock Token metadata
```

验收：

```text
给 AMC 地址
能判断 canonical / fake
```

---

## RH-P3 — Oracle / Fair Value Engine

实现：

```text
Chainlink
Robinhood /prices
multiplier
oraclePaused
staleness
sequencer uptime
premium/discount
```

验收：

```text
StockFairValue snapshot 可复现
```

---

## RH-P4 — Uniswap Pool Indexer

发现：

```text
V3/V4 pools
token pair
fee
TVL
active liquidity
volume
swaps
fees
```

注意：

```text
合约地址从可信 deployment / onchain 验证获取
不得抄第三方网页后写死。
```

---

## RH-P5 — Core Strategy

先只做：

```text
WETH/USDG shadow
```

跑通：

```text
scan
score
range
PnL
rebalance evaluation
```

---

## RH-P6 — Stock Strategy

先：

```text
AMC/USDG
+ 1 个 ETF Stock Token/USDG
```

Shadow 对比。

必须验证：

```text
RTH
closed
weekend
premium
supply shock
oracle pause
halt
```

---

## RH-P7 — MEME Strategy

实现：

```text
organic volume
audit
small-size allocator
no-downtrend-recenter
TTL/cooldown
```

---

## RH-P8 — Execution

实现：

```text
add
remove
collect
rebalance
atomic exit
approve/revoke
Permit2 optional
sequencer direct
```

---

## RH-P9 — Portfolio Risk

实现：

```text
50/30/20 bucket
active cap
asset concentration
drawdown circuit breaker
USDG guard
chain kill
```

---

## RH-P10 — PnL v2

实现：

```text
fee
IL
adverse selection
rebalance
gas
benchmark
LP alpha
bucket attribution
```

---

## RH-P11 — Dashboard

基于现有 UI 改。

必须加入：

```text
3 bucket
fair premium
market regime
oracle health
supply shock
organic meme volume
adverse selection
LP alpha
```

---

# 49. 测试路线

不要直接把旧 Live Bot 切到 Robinhood Chain。

### Stage A — Read Only

至少：

```text
3 天
```

验证：

```text
registry
pool indexer
oracle
market regime
scanner
```

### Stage B — Shadow

建议至少：

```text
14 天
```

覆盖至少一个周末。

因为 Stock Token 的核心风险之一就是：

```text
TradFi closed
但 DEX 继续交易
```

不跨周末的 Shadow 没有意义。

### Stage C — Tiny Live

使用：

```text
目标最终资金的 5% ~ 10%
```

而不是直接全量 50/30/20。

### Stage D — Scale

每一级扩大前要求：

```text
Net PnL > 0
LP Alpha 可解释
无漏 kill
PnL 对账正确
```

---

# 50. Shadow 毕业条件

系统级：

```text
>= 14 days continuous
>= 1 weekend
0 unknown reconciliation mismatch
0 invariant violation
0 missed critical risk event
```

数据：

```text
Oracle state correctly classified
Stock fair-value error < configured tolerance
PnL accounting error < 2%
```

策略：

```text
CORE expected net > 0
STOCK expected net > 0
MEME strategy can remain 0 allocation when no qualified pools
```

特别注意：

> MEME Bucket **没有好池时允许 100% idle**。

“20% MEME”是风险预算，不是强制亏钱指标。

---

# 51. Tiny Live 毕业条件

至少：

```text
30 天
```

要求：

```text
Portfolio Net PnL > 0
Core Net > 0
Stock Fee > AS Cost + IL + Cost
Meme realized loss within budget
No rug beyond configured max exposure
All exits / approvals reconcile
```

再决定是否扩大。

---

# 52. Agent 不允许做的事情

1. 不允许为了“适配 Robinhood Chain”把整个仓库重新生成。
2. 不允许删除旧测试后重新写一个更容易通过的测试。
3. 不允许把第三方 APR 当真实收益。
4. 不允许把 Stock Token 当普通 ERC-20 meme 处理。
5. 不允许忽略 multiplier。
6. 不允许在 oracle stale / paused 时自动重新居中。
7. 不允许在 MEME 单边下跌时自动追跌 Range。
8. 不允许使用 raw 24h volume 直接给 MEME 高分。
9. 不允许 public RPC 单点成为 live 唯一数据源。
10. 不允许无 fork simulation 的 live transaction。
11. 不允许 unlimited approve。
12. 不允许在 reconciliation FAIL 后进入 live。
13. 不允许为了“满足 50/30/20”强制开没有正期望的池。

---

# 53. 本项目真正的第一性原理

机器人不是：

```text
自动找 APR 最高的池。
```

而是：

```text
在可控库存风险下，
用最少资本占用，
尽可能长时间处于有真实订单流的有效价格区间，
把真实交易者 / 套利者支付的 fee，
在扣除 IL、toxic flow、rebalance、gas 和尾部风险后
留下正 Net PnL。
```

三个 Bucket 的角色：

```text
CORE
= 组合发动机 / 基础收益

STOCK
= Robinhood Chain 的独特 Alpha
  fair-value arbitrage flow → LP fee

MEME
= 高风险短周期可选 Alpha
  没机会就空仓
```

---

# 54. 设计验收结论

这次“全面转向 Robinhood Chain”不是简单：

```text
chains = ["robinhood"]
```

而是必须完成 5 个实质变化：

### 1.

```text
Generic Tier Strategy
→ Asset Profile Strategy
```

### 2.

```text
Fee APR
→ Expected Net PnL
```

### 3.

```text
DEX Spot Center
→ Oracle/Fair-Value Aware Center
```

### 4.

```text
Out-of-range Rebalance
→ Profile-aware Rebalance / Exit / Cooldown
```

### 5.

```text
Multi-chain generic risk
→ Robinhood-specific:
   Stock Token
   Oracle
   Multiplier
   Market Session
   Sequencer
   USDG
   MEME integrity
```

做到这些以后，这才算真正从旧 LP-Bot 转成：

> **Robinhood Chain 专用、三资金桶、自动选池 + 自动做 LP + 自动撤退 + 可审计 PnL 的组合机器人。**

---

# 55. 现有项目文件映射

本设计基于现有项目的以下结构继续演化：

```text
M0  Shared Types
M1  Alpha Scanner
M2  Security Audit
M3  Risk Management
M4  LP Execution
M5  Simulation
M6  Dashboard
M7  Artifact
M8  Watchdog
M9  Data Connector
M10 State Store
M11 Event Bus
M12 Wallet & Signer
M13 PnL & Accounting
M14 Reconciliation
M15 Strategy
```

保持已有：

```text
PostgreSQL + Redis
NATS JetStream
Go core services
Rust math/core
TypeScript Dashboard
Anvil fork
dryrun / shadow / live 隔离
Artifact / VERDICT
```

本次只对 Robinhood Chain 业务逻辑做深度改造。

---

# 56. 参考资料

## 项目内部基线

- 《链上 AMM LP 自动套利机器人 PRD（升级版）》
- 《链上 AMM LP 自动套利机器人 – 模块化任务包（Sub-Agent 可执行版）》
- 《链上 AMM LP 自动套利机器人 PRD（MVP版）》
- 《链上 AMM LP 自动套利机器人 – 模块化任务包（MVP版）》
- 《LP机器人技术栈及服务层级架构.mmd》
- 《LP机器人监控面板设计稿2.png》

## Robinhood Chain 官方资料（2026-09-07 核对）

- https://docs.robinhood.com/chain/
- https://docs.robinhood.com/chain/connecting/
- https://docs.robinhood.com/chain/stock-tokens/
- https://docs.robinhood.com/chain/building-with-stock-tokens/
- https://docs.robinhood.com/chain/stock-token-apis/
- https://docs.robinhood.com/chain/oracles-and-price-feeds/
- https://docs.robinhood.com/chain/contracts/
- https://docs.robinhood.com/chain/protocol-contracts/
- https://docs.robinhood.com/chain/transaction-finality/
- https://docs.robinhood.com/chain/gas-and-fees/

---

# 57. 给执行 Agent 的首条总任务指令

```text
任务名：
LP_BOT_ROBINHOOD_CHAIN_PORTFOLIO_PIVOT_V1

目标：
在不重写现有 LP-Bot 的前提下，将项目从多链通用 LP 系统全面转向 Robinhood Chain 专用系统。

先完整阅读：
1. 本文档
2. 现有升级版 PRD
3. 现有 Sub-Agent 模块任务包
4. 当前仓库真实代码、tests、migration、config、reports

严禁先写代码。

第一步必须完成：
reports/rh_pivot/P0_EXISTING_CODE_MAP.md

内容必须包括：
- 当前 git branch / HEAD
- 当前模块真实实现状态
- 当前 DB schema
- 当前 EVM / Uniswap 支持情况
- 当前 Scanner / Strategy / Risk / PnL / Execution 接口
- 当前 Dashboard 数据接口
- 与本文档 RH-P0 ~ RH-P11 的逐项 gap analysis
- 可直接复用 / 需修改 / 需新增 / 应删除的文件清单
- 推荐实施顺序
- 风险和 blocker
- 测试基线

P0 报告完成前：
禁止大规模 refactor。
禁止删除旧逻辑。
禁止进入 live。
禁止使用真实资金。

P0 完成后再按：
RH-P1 → RH-P2 → RH-P3 → RH-P4
→ RH-P5/RH-P6/RH-P7
→ RH-P8 → RH-P9 → RH-P10 → RH-P11
推进。

每个阶段：
代码 + 单测 + 集成测试 + Artifact + PASS/WARN/FAIL verdict。
```
