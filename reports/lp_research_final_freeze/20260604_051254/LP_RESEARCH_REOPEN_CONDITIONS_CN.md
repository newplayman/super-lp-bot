# LP Research Reopen Conditions — Stage F

- stage: `LP_RESEARCH_FINAL_FREEZE_AND_HANDOFF_V1`
- run_id: `20260604_051254`

## 0. 重开前提 (per spec)

LP research 在 `STOP_LP_RESEARCH_NOW` 状态下, 任何重开都**必须**先满足本节列出的 7 大类条件, **并且**仍然走完整 read-only → preflight → dry-run → manual approval 流程 (重开 ≠ 直接实盘)。

## 1. 7 大重开条件 (全部必须)

### 1.1 条件 1: 真实 fee accrual / actual position tokenId 数据

**背景**: 5 stages 全部使用 heuristic 0.5%/day turnover, **没有任何 actual position tokenId / actual fee accrual** 数据。
- LP position NFT / tokenId 实际 lifetime
- 实际 fee revenue (按 position)
- 实际 IL 实现 (按 position lifetime)
- 实际 entry / exit 时间

**why needed**: heuristic 0.5%/day 假设 100× 高于实际 10/20u quote 推导的 0.005%/day. 重开需要 on-chain 历史 position data.

**how to provide**:
- user 持有 LP NFT (Position NFT) 提供 minted position mint address
- 历史 fee claims / collects 数据
- 历史 IL 实现数据 (e.g. from orca sdk position query)
- 主网 paid RPC + indexer (Helius, Triton, QuickNode) 提供历史查询

### 1.2 条件 2: 协议激励 / 外部 reward / bribe

**背景**: 5 stages 全部用 pool.fee_rate 单一收入源。**协议激励 / bribe / IFO rewards** 都没纳入:
- Meteora LM (liquidity mining) 激励
- Orca LM rewards
- Raydium RAY emissions
- Saber bribes (historical)
- Vote-escrowed token bribes (veRAMM, etc.)

**why needed**: LP real yield 通常 = fee + LM + bribe. 只算 fee 严重低估正 EV. 一些 protocol 的 LM 实际 yield 可能是 fee 的 5-10×.

**how to provide**:
- specific protocol 的 LM 合约 (e.g. Meteora farm program)
- 历史 LM emission data
- 当前 bribe marketplace 数据 (bribes.sol, etc.)
- 假设 LP range / 持有时间对应的 LM 收入

### 1.3 条件 3: 稳定高 fee velocity 的池

**背景**: 5 stages best cell 都在 memecoin / 投机池 (YZai, Fartcoin, three, WorldCup) — 7d 持有不适合 memecoin.
- 真正 high-fee velocity 池: 持续 1%+ / day turnover × 25-100bps fee = 实际 high yield
- 但 high velocity = high price volatility = high IL
- Stable pools 有 low velocity × low fee = 负 EV
- 必须找到 velocity/fee/IL 三者平衡的池

**why needed**: 当前 heuristic turnover 0.5%/day 是平均, 不反映实际 high-fee-velocity 池. 需要在 1%/day+ 池中跑 EV.

**how to provide**:
- 筛选 vol/fee ratio top 50 池
- 历史 fee / TVL ratio > 0.5%/day
- 价格 volatility 估算 (twap, EMA, etc.)
- backtest 在 30d / 90d / 365d 数据上

### 1.4 条件 4: 更低成本链路

**背景**: 5 stages fixed_cost = $0.003-0.006 per round-trip. retail 10 USD notional 占比 0.06%. 必须降成本 10-100×:
- 优先 fee tier 1 / 0 (做市商 rebate)
- batch transactions (多 tx 一起)
- priority fee optimization (10k microlamports = 0.00001 SOL ≈ $0.0000013)
- 跳过 NFT mint (for V3 CL) — 0.0014 SOL rent
- 跳过 position account close (for V3 CL) — 0.0014 SOL rent
- Skip tick array init — assume existing

**why needed**: cost 占比过大直接压死 retail LP. 必须把 cost 压到 $0.0001 级别.

**how to provide**:
- precise cost breakdown (rent + priority fee + slippage + jito tip)
- batch transaction design (multi-pool in 1 tx)
- rebate model 假设 (Jupiter, etc.)

### 1.5 条件 5: paid RPC / indexer 支撑更完整数据

**背景**: 5 stages 全部用 public RPC (publicnode + mainnet-beta). 429 rate limit 限制 quote-ready count:
- Meteora DLMM V8: 27/56 = 48% quote-ready (rate limited)
- Orca V1: 10/75 = 13% quote-ready (very rate limited)
- Solana stable: 10/25 = 40% quote-ready

**why needed**: 完整 quote 覆盖需要 paid RPC (Helius, Triton) 或 indexer (solscan, birdeye). public RPC 429 阻断完整 LP research.

**how to provide**:
- paid RPC endpoint (Helius / Triton / QuickNode) with rate limit headroom
- 1inch / Birdeye / DexScreener API for pool metadata
- historical indexer (e.g. via Shyft, helloMoon) for backtest
- 或者: user 接受 partial quote coverage 限制

### 1.6 条件 6: 用户主动提供具体池或资金/策略假设

**背景**: 5 stages 全部 generic search, 没有 user-specific 上下文:
- user 想 LP 哪个池?
- user 资金规模 (10U? 100U? 1000U?)
- user 风险偏好 (保守 / 平衡 / 激进)
- user 持有时间 (1h? 1d? 1w? 1m?)

**why needed**: retail generic 不工作. 必须 user-specific 假设.

**how to provide**:
- specific pool address (e.g. user 已在 LP 的 pool)
- specific capital amount
- specific risk tolerance
- specific time horizon

### 1.7 条件 7: 非普通 LP 的结构性策略

**背景**: 5 stages 全部 vanilla LP (持有 → 收 fee → IL). 实际专业 LP 用结构性策略:
- **Incentive farming**: 同时 LP + claim LM rewards, 需要真实 LM data
- **Delta-hedged LP**: LP 一边 + perps/options 对冲, 需要 hedging cost + basis data
- **JIT liquidity**: swap-driven LP (just-in-time), 需要 mempool + per-tx simulation
- **Single sided / managed vault**: 1-token deposit, auto-rebalance, 需要 vault TVL data
- **Options / perp hedge**: covered call + LP combo, 需要 options pricing
- **Market maker rebate model**: 做市商 rebate + LP yield, 需要 rebate tier data

**why needed**: 普通 LP 在 retail 不 work. 结构性策略可能让 yield 翻 5-10× 同时减少 IL.

**how to provide**:
- 选择具体策略 (上面 6 类之一)
- 提供该策略的数据源 (LM contract, options dex, perps dex, vault TVL, etc.)
- EV model 修改 (fee + LM - hedge_cost, etc.)

## 2. 重开流程 (即使满足 7 条件)

**重开 ≠ 直接实盘**。必须走完整:

```
1. read-only EV 重新验证
2. preflight 设计 (单池 / 假设 / 边界)
3. dry-run (simulate tx, 不发)
4. manual operator approval
5. 才有 can_run_probe_now = true (有 condition)
6. tiny_canary_allowed = yes (only with approval)
7. 才有 canary / probe / live
```

## 3. 重开 7 条件 + 流程 checklist

```text
[ ] 1. 真实 fee accrual / actual position tokenId 数据 ✓
[ ] 2. 协议激励 / bribe ✓
[ ] 3. 稳定高 fee velocity 池 ✓
[ ] 4. 更低成本链路 ✓
[ ] 5. paid RPC / indexer ✓
[ ] 6. 用户主动提供具体池 / 资金 / 策略假设 ✓
[ ] 7. 非普通 LP 结构性策略 ✓
[ ] 8. read-only EV 重新验证 ✓
[ ] 9. preflight 设计 ✓
[ ] 10. dry-run ✓
[ ] 11. manual operator approval ✓
```

## 4. 重要 caveat

- **重开成本**: 7 条件收集 + EV 重新验证 可能 1-2 周工作
- **重开 ROI**: 即使 7 条件满足, retail 10/20U 仍可能 negative EV. 重开 ≠ 必然正 EV
- **manual decision**: 重开决定必须 manual operator, 不自动触发
- **再次 STOP**: 如果 7 条件满足但 EV 仍 negative, 必须再 STOP. 不允许强行 probe.

## 5. 未来可能的 alternative 重开路径

如果以上 7 条件任何一类无法满足, alternative:
- (a) 暂不重开 LP research
- (b) 转入其他 research (event-driven trading, arbitrage, options)
- (c) 转入 scanner / monitoring tool (无交易)
- (d) 归档当前仓库, 标 final tag
