# Stage F — 长期验证重开计划 (Long Horizon Reopen Plan)

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_060659`

## 0. 写在最前

本计划**不**是"自动重启 LP research" 的触发器, 而是一份路线图. **重开 ≠ 直接实盘**.
任何 R0-R5 阶段的输出, 本身仍是 read-only 报告, 不触发任何 probe / canary / live.

重开决策树:
```
R0 长期 read-only 数据基线 (7d / 14d / 30d / 90d / 180d / 365d)
  └─ PASS?
     └─ R1 真实 fee accrual 设计 (tokenId / collect fee / dynamic fee activation)
        └─ PASS?
           └─ R2 市场 regime 分类 + 加权 EV (uptrend / downtrend / sideways / 激励期 / 低波稳态)
              └─ PASS?
                 └─ R3 重开候选池 review (激励 / vault / managed LP / bribe / 私有池)
                    └─ PASS?
                       └─ R4 10U tokenId probe preflight (单池 / 单假设 / 边界)
                          └─ PASS?
                             └─ R5 手动 probe only (manual operator approval 必需)
                                └─ 经过 5 个 stage 全 PASS 后, 才考虑 can_run_probe_now = true
```

任何 stage 失败, 回到上一 stage 或直接 STOP, **不允许跳过**.

## 1. 阶段总览

| 阶段 | 名称 | 输入 | 输出 | 阻断条件 |
|---|---|---|---|---|
| R0 | 长期 read-only 数据基线 | paid RPC, paid indexer | 7/14/30/90/180/365d baseline dataset | 任一窗口数据缺失 → STOP |
| R1 | 真实 fee accrual 设计 | position tokenId (user 提供) 或 paid indexer | tokenId lineage + collect fee + dynamic fee | tokenId 无法恢复 → STOP |
| R2 | 市场 regime split | R0 dataset | 7 regime 分类 + 加权 EV | 单一 regime 占 > 90% → STOP |
| R3 | 重开候选池 review | R0 + R1 + R2 | incentive / vault / bribe / managed list | 候选 < 5 池 → STOP |
| R4 | 10U tokenId probe preflight | R3 候选 | 单池单假设 preflight doc | 任一边界失败 → STOP |
| R5 | 手动 probe only | R4 preflight | manual operator approval 记录 | 无 manual approval → 0 probe |

## 2. 阶段详细

### 2.1 PHASE_R0_LONG_READONLY_DATA

**目标**: 建立 7d / 14d / 30d / 90d / 180d / 365d 的 read-only 数据基线, 全部跨 regime 覆盖.

**数据需求**:
- paid RPC (Helius / Triton / QuickNode) + paid indexer (Shyft / helloMoon)
- 7 个 regime 标识 (uptrend / downtrend / sideways / high volume sideways / high vol trend /
  incentive period / low vol stable)
- per-pool: daily volume, daily fees, daily TVL, OHLC, on-chain LP events
- 5 类 protocol × 6 窗口 × 7 regime = 210 cell minimum

**判定**:
- 数据缺失率 < 5% → PASS
- 5% - 20% → WARN (人工 review 缺失分布)
- > 20% → STOP (data pipeline 没准备好)

**不允许**:
- 任何自动 probe
- 任何 heuristic 改动
- 任何 heuristic 数据采集 (必须真实 on-chain)

**预计周期**: 2-3 周 (paid indexer 接入 + 跨 regime 标识)

### 2.2 PHASE_R1_REAL_FEE_ACCRUAL_DESIGN

**目标**: 设计真实 position-level fee accrual 抓取, 解决 tokenId lineage 缺失.

**方法**:
- 方案 A: user 提供已有 position tokenId (历史 LP NFT)
- 方案 B: paid indexer 抓所有 wallet's LP positions (需要 user wallet pubkey)
- 方案 C: paid indexer 抓 pool-level recent positions (取最近 N 个 tokenId, 不完整但可用)

**数据**:
- position tokenId
- entry time / exit time
- collect fee events
- IL actual (用 entry / exit 价 + 持有量推)
- dynamic fee activation rate (Meteora DLMM)

**判定**:
- 方案 A 或 B 至少 1 个拿到 ≥ 10 个历史 position → PASS
- 仅方案 C 拿到 < 10 个 → WARN
- 全部失败 → STOP

**不允许**: 任何链上主动开 / 平仓.

**预计周期**: 1-2 周 (indexer 接入 + position 抓取)

### 2.3 PHASE_R2_MARKET_REGIME_SPLIT

**目标**: 把 R0 + R1 数据按 regime 切分, 算每个 regime 的 weighted EV.

**方法**:
- 用 on-chain OHLC + volume 标识 7 个 regime
- per regime per protocol per window 算 EV 矩阵
- 加权 (按 regime 在历史 365d 出现概率) 得到 weighted long-horizon EV
- 跟 short-window (7d) 结论对比, 验证是否 regime split 后会改变结论

**判定**:
- weighted EV 在 4+ regime 都正 → 提示 long-term 价值存在 → 进入 R3
- weighted EV 仅在 1-2 regime 正 → 高度 regime dependent → 提示需要 active regime
  switching 策略, 进 R3 但带 caveat
- weighted EV 在 0 regime 正 → 长期仍负 → STOP, 不再重开

**不允许**: 任何自动 regime switch 实施.

**预计周期**: 1-2 周 (regime classifier + weighted EV 跑)

### 2.4 PHASE_R3_REOPEN_CANDIDATE_REVIEW

**目标**: 从 R0-R2 数据中筛出真正可重开的候选池, 排除 vanilla LP 已知 negative.

**候选类别**:
- 激励池 (LM / LM-bonus / IFO reward) — 必须验证 LM 数据
- vault / managed LP (Meteora DAMM v2 vault, Orca farm vault) — 必须 TVL + strategy
- bribe marketplace 池 (veRAMM 等) — 必须 bribe 数据
- 私有池 / permissioned LP — 不可公开数据, 默认排除
- 结构性策略 (delta-hedged / JIT / single-sided / covered-call) — 必须 hedge 工具数据

**判定**:
- 候选 ≥ 5 池 (覆盖 ≥ 3 类别) → PASS, 进入 R4
- 候选 1-4 池 → WARN, 仍可进 R4 但只针对 1 类
- 候选 0 池 → STOP

**不允许**: 任何激励合约 / vault 实际接入.

**预计周期**: 2-3 周 (激励合约 audit + vault strategy 分析 + bribe 数据)

### 2.5 PHASE_R4_10U_TOKENID_PROBE_PREFLIGHT

**目标**: 设计 10U tokenId probe 的 preflight 文档, 不实施.

**preflight 内容**:
- 单池 / 单假设 / 边界条件 / stop-loss / take-profit
- 失败时如何 rollback
- 监控指标 (fee / IL / position health)
- kill switch (任何 invariant 失败 → 立即撤出)
- manual operator approval checklist

**判定**:
- preflight doc 完整覆盖 11 项 (per Stage F 11 checklist) → PASS
- preflight doc 缺失 1-3 项 → WARN (补完后 PASS)
- preflight doc 缺失 > 3 项 → STOP

**不允许**: 任何 probe 实际发起, 任何 tx 构造.

**预计周期**: 1 周 (preflight 文档化)

### 2.6 PHASE_R5_MANUAL_PROBE_ONLY

**目标**: 在 R0-R4 全 PASS 之后, 进入 manual probe only 状态.

**manual probe 规则**:
- 每次 probe 必须 manual operator approval
- probe 上限 10U / 次, 总额 50U, 7d 周期
- probe 失败 3 次 → 自动 STOP
- probe 成功 N 次后, 才考虑 can_run_probe_now = true

**判定**:
- manual approval 记录 ≥ 1 次 probe → 状态转为 MANUAL_PROBE_ACTIVE
- 0 manual approval → 保持 STOP

**不允许**: 任何自动 probe, 任何 unattended 调度.

**预计周期**: 不定, 视 manual decision 而定.

## 3. 重开总流程 (从 7 条件到 probe)

```text
[Final Freeze STOP] 
  → R0 长期 read-only 数据基线
  → R1 真实 fee accrual 设计
  → R2 市场 regime split
  → R3 重开候选池 review
  → R4 10U tokenId probe preflight
  → R5 手动 probe only (manual approval)
  → 多次 manual probe 成功
  → can_run_probe_now = true (有条件)
  → tiny_canary_allowed = yes (仅 manual approval)
  → canary / probe / live
```

每一步都有 STOP 出口. **任何阶段失败 → STOP, 不允许跳过**.

## 4. 与 final freeze 7 条件的对应

| 7 条件 | 对应 R 阶段 |
|---|---|
| 1. 真实 fee accrual / actual position tokenId | R1 |
| 2. 协议激励 / external rewards / bribe | R3 |
| 3. 稳定高 fee velocity 池 | R3 |
| 4. 更低成本链路 | R4 (preflight) + R5 (manual) |
| 5. paid RPC / indexer | R0 |
| 6. 用户主动提供具体池 / 资金 / 策略 | R1 (tokenId) + R3 (specific pool) |
| 7. 非普通 LP 结构性策略 | R3 (候选类别) |

也就是说, final freeze 的 7 条件 == R 阶段必须满足的输入. 顺序也对应: R0 (data) → R1
(fee) → R2 (regime) → R3 (candidates) → R4 (preflight) → R5 (manual).

## 5. 硬性禁止 (any R 阶段)

- 不启动 new research runner
- 不继续换协议 (除非 R3 阶段明确需要扩展候选类别)
- 不 probe / canary / live / paper
- 不读取私钥 / seed / keypair
- 不创建 signer
- 不发送 transaction
- 不 bridge / swap / open LP / close LP / collect fee
- 不写 production positions
- 不覆盖 shadow 表
- can_run_probe_now 必须保持 false
- tiny_canary_allowed 必须保持 no

## 6. 结论

- 长期重开路径: 6 阶段 R0-R5, 任一失败 STOP
- 7 条件对应 R 阶段输入, 顺序匹配
- 任何 R 阶段都禁止 probe / canary / live / paper / tx
- 重开 ≠ 直接实盘, 必须 R5 manual probe 多次成功后才考虑 can_run_probe_now
- 本计划本身不触发任何 R 阶段, 仅是路线图
