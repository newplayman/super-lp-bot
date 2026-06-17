# LP 分层策略研究总结(2026-06 续)

> 状态:研究仍处于 `20260531_124000` 冻结期。本文记录的全部工作均为**只读研究管线**
> (`scripts/lp_*_readonly.py` + 配套测试 + HTTP 读取公开聚合器),不触碰钱包/签名/广播/链上写入,
> 不构成解冻。指挥者 = 操作员;代码由 codex/opencode 协助、经审查后落盘。

本文承接 D4 纸面验证之后的策略推进,把"对冲移除 → 分层 range 引擎 → 全网筛选漏斗"这条线
的关键发现固化下来,供后续(以及记忆)参考。

---

## 0. 前提决策:彻底移除对冲

操作员在早期 LP 工作中已论证:delta 对冲在现实中被各种磨损吃掉,不可行。对冲是 AI 推进过程中
"自作聪明"加入的,非原始设计。原始设计 = **感知波动 + 自动跟踪保持在区间内 + 即时捕获优质 LP 收益,
不做对冲**。据此 D4 验证器已彻底去对冲(连纸面列也删),改为纯 LP 净值口径。

---

## 1. 分层(Tier A/B/C)设计

按收益/风险带分层,**退出机制按层不同**:

- **Tier A**:稳定可靠资产(如 ETH/USDC),APR ~30–80%。再平衡用滞后/冷却。
- **Tier B**:APR ~80–800%,中等风险。
- **Tier C**:APR >800%,新出世(>24h)代币,日收益近翻倍但有归零风险。严格及时止损,**不再平衡**
  (给濒死代币再平衡 = 接飞刀)。

Tier-C 退出可行性回测结论:绝大多数新池"出生即死";可评估的击穿样本里,**清洁退出率 0%(全部跳价穿过)**
→ 价格下限止损**不是**可靠的 Tier-C 安全网,**入场筛选**才是 EV 的主导。

---

## 2. 核心纠正:再平衡不降 IL(LVR)

再平衡**不会降低 IL**,它**实现(realize)IL + 付 gas/swap**。一次再平衡成本(含已实现 IL)约 ~1% 本金,
需 **5–12 天手续费**(30–80% APR)才能补回。因此:**再平衡频率必须远低于补本周期**,目标每次间隔 ≥ 30–60 天。

---

## 3. 用波动率定 Range(替代"拍脑袋")

工具:`scripts/lp_vol_range_sizer_v1_readonly.py`

模型(随机游走首次穿越):双边 ±L 边界的期望首达时间 `E[τ] = (L/σ)²`,反解得

```
range_pct = 100 · k · σ_daily · √H        (k = 1.2 安全系数)
```

- **σ 必须用"该池价格比值"的波动率**(token1/token0),不是单币对美元。相关对(cbBTC/WETH、wstETH/WETH)
  比值波动小 → 窄 range 也几乎不出界;对美元的对(WETH/USDC)吃满单币波动 → 需更宽 range。
- 实测 σ_daily(Base,2026-06-17):cbBTC/USDC ~1.7%、cbBTC/WETH ~2.2%、WETH/USDC ~3.5%、VVV/WETH ~6.8%(年化~130%)。
- H=30 推荐 range:WETH/USDC ±22.7%、VVV/WETH ±44.9%。**数学证明高波动中盘结构性难做**
  (要月级免调需 ±45% 宽 → 费用密度塌到 0.22x;要保费用就得频繁调 → 流血。没有免费午餐)。

---

## 4. ⚠️ 关键 Bug:手续费 decimal 尺度算错(已修)

**操作员质疑"周级 vs 月级差异太小"时发现。** 把 net 拆成"手续费 + IL/市值"两列,发现 **4 池里 3 池手续费=0**。

- 根因:`position_liquidity_raw` 把"人类价格"流动性换成链上原始单位时乘了 `10^(dec0-dec1)`;
  正确应是 **`10^((dec0+dec1)/2)`**(链上 V3 `L = √(x·y)`,x、y 为原始单位)。
- 旧因子**只在 (18,6) 巧合相等**(18=3×6);(18,18) 差 10^18 倍、(8,18) 差 10^23 倍 → 仓位占比≈0 → 费用=0。
- 第二 bug:cbBTC/WETH 配置 decimals 配反((8,18) 应为 (18,8),链上 token0=WETH/token1=cbBTC),价格被算反,整条作废。
- 修复:commit 6c0e859,加跨 decimal 回归测试。**教训:net 必须拆成费用 vs IL;差异过小/过干净就是危险信号。**
  早期任何非 (18,6) 池的"含费用"结论已作废;价格/IL/再平衡次数等比值类结论一直有效。

---

## 5. 周级 vs 月级、滞后/冷却(修复后)

工具:`scripts/lp_tier_b_level2_replay_v1_readonly.py`(active 模式加了 `hysteresis_pct` 死区 + `cooldown_blocks`)

- **vol-sizing 本身就消灭了再平衡**:周级(窄)与月级(宽)两队列在正常窗口里都 **0 再平衡、100% 在区间内**。
  之前 VVV −3.03% 惨案纯粹是 ±5% 对 σ=6.8% 太窄的人为产物。
- **周级 vs 月级 = 费用 vs IL 的权衡**(非免费午餐):平静窗口里周级(窄)每池都赢
  (费用翻倍 > 多吃的 IL,且都没击穿);但**只在"没击穿"时成立**——波动上来、窄 range 被击穿而宽没有时,
  周级要吃再平衡/IL realize,可能反转。**周级 = 平静期收益更高、击穿风险也更高。**
- **滞后不是万能解**:压力测试(故意 ±5% 跑波动窗口)里,趋势行情下**滞后比激进还差**
  (延迟 = 在区间外干等零费用 + 深度再平衡实现更大亏损)。被动 vs 激进**路径依赖**
  (回升→被动赢;单边跌→激进反而赢,因为持续 50/50 而非死握下跌币)。
  **结论:没有哪种再平衡策略通吃 → 按 σ 放宽 range + 选币筛选,比调再平衡逻辑重要得多。**

---

## 6. Range 决策层(σ + 趋势 + 可行性)

工具:`scripts/lp_tier_range_policy_v1_readonly.py`

把"拍脑袋"彻底替换为一条可执行决策链,输出可直接喂 replay/模拟的配置:

1. **σ → range**(第 3 节模型)。
2. **趋势判别(Kaufman 效率比 ER)** `ER = |净对数移动| / Σ|每步对数移动|`(1=趋势,0=震荡)。
   闸:区间(ER<0.25)→ H7 窄(周级);中性 → H14;趋势(ER>0.5)→ H30 宽;高波动+趋势 → AVOID。
3. **费用-IL 可行性闸** `fee_cover = fees / |IL|`(经 replay 被动跑窗口得真实值):
   `fee_cover ≥ 1` = "LP 比直接持币好"(结构性 alpha)。**它把结构性优势与方向性运气分开**:
   - VIRTUAL:fee_cover 2.47 → 结构性 ENTER(LP 本身赚),但 net −1.97% 来自 VIRTUAL 币价方向性下跌(另一回事)。
   - WETH/USDC-0.3%:fee_cover 0.70 → AVOID(0.3% 档没量,LP 不如持币),尽管 net +2.49% 全是 WETH 涨价。
4. Tier-A 额外硬挡过度方向性的对(|move|≥15%)。

---

## 7. 全网筛选漏斗(聚合器优先,RPC 只在底层)

**原则:聚合器做"宽而便宜",RPC 只做"窄而深"。绝不全链 getLogs 扫。**

- **第 1 层(0 RPC,HTTP)** `scripts/lp_universe_screener_v1_readonly.py`:DefiLlama yields `/pools`
  (免 key,Base 2577 池)给每池 **apyBase(费)+ apyReward(排放)+ TVL + 量 + sigma + ilRisk + rewardTokens + poolMeta**。
  过滤 Base CLMM、TVL/量闸、从 poolMeta 解析 fee/tickSpacing、按 APR 分档、打分(30d均值锚定、尖峰打折)、
  **标记刷量/激励农场**(实测 Tier-C 全是 apyReward 高达 153688% 的农场,已自动隔离)。
  **奖励常是大头**(aero WETH-USDC:费 31% + 排放 68%)——这是之前忽略的关键收益。
- **第 2 层(有界 RPC,top~30)**:`factory.getPool` 解析链上地址
  (Uni V3 工厂 `0x33128a8f...` getPool(address,address,uint24)=`0x1698ee82`;
   Aerodrome CL 工厂 `0x5e7BB104...` getPool(address,address,int24)=`0x28af8d0b`)+ `decimals()`;
  抓真实 swap 跑 σ/ER/fee_cover + **链上量 vs 聚合器量反刷量交叉核对** + **把 AERO 排放并入收益覆盖率**。
- **第 3 层(深,top~5-10)**:完整 Level-2 replay(含奖励)+ 真实仓位深度/滑点 + 击穿行为 → top-N + 10000U 分配。

RPC 预算:第 1 层 0;第 2 层约 ~10万 CU;整轮全网筛 ≈ 几十万 CU = 免费 300M/月额度的零头。

---

## 8. 10000U 起始配置(标准基准)

- **Tier A 70%(~3 池)**:WETH/USDC、cbBTC/WETH(相关对,费用密度更高)、近锚定对(wstETH/WETH)。
  range 按 σ 放宽到月级,再平衡近乎关闭。
- **Tier B 30%(~2 池)**:只碰有深度的池,滞后/冷却必开,绝不触边即调。
- 共 ~5 池(Base gas 极廉,约束是单池最小规模+监控,不是 gas)。

---

## 9. Tier-B 跑长测前仍缺的(就绪缺口)

1. **多窗口稳定性** —— 现有结论来自单个平静窗口;需 ~30 天滚动重测 σ/ER/fee_cover。
2. **奖励/排放并入可行性** —— 第 1 层已拿到 apyReward;第 2 层 fee_cover 需升级为
   `yield_cover = (费用 + 排放) / |IL|`(进行中,Stage 1→2 桥)。
3. **真实仓位深度/滑点** —— replay 用归一化 size=1.0;需按 1000–3000U 对真实深度测建/平仓滑点。
4. **击穿后退出策略未定** —— 滞后在趋势里有害、再平衡路径依赖、Tier-C 止损跳价穿过;Tier-B 仍无定案。
5. **方向性敞口仓位规则** —— 中盘/WETH = 净多高风险币,需"小仓 + 接受 or 筛掉"的明确规则。
6. **Tier-B 纸面 shadow 跑手** —— 策略层是时点快照;需一个像 D4 那样的循环,定期重测并按 10000U
   跟踪组合净值(现有 D4 只跟单池 Tier-A)。

---

## 关键文件与提交

- `scripts/lp_vol_range_sizer_v1_readonly.py`(f5135d8)
- `scripts/lp_v3_fee_share.py` decimal 修复(6c0e859)+ 回归测试
- `scripts/lp_tier_b_level2_replay_v1_readonly.py` 滞后/冷却(3a3d218)
- `scripts/lp_tier_range_policy_v1_readonly.py` 决策层 + 可行性闸(c528886 / 11b662a)
- `scripts/lp_universe_screener_v1_readonly.py` 全网第 1 层(414158a)
- `scripts/lp_pool_resolve_and_rank_v1_readonly.py` Stage 1→2 桥(进行中,codex)
- 报告:`reports/lp_vol_range_sizer/`、`reports/lp_tier_b_level2/{weekly_H7_fixed,monthly_H30_fixed,stress_tight5_fixed}/`、
  `reports/lp_tier_range_policy/run2_viability/`、`reports/lp_universe_screener/run1/`
