# Meteora Targeted Pool Source Strategy — Stage C

- stage: `LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1`
- run_id: `20260604_021913`

## 0. 核心判断

上一轮 16 池 base_fee 0.02–2.5 bps 全部远低于 LP 零售可盈利的 ~5% 阈值。本轮必须改为按 fee / volume / liquidity 排序后再选池。

## 1. 目标池五维 (must-pass)

### 1.1 high_fee_dlmm (hard filter, 链上 base_fee / max_fee 决定)

- base_fee_bps >= 500 (5%) → 必须
- 或 max_fee_bps >= 2000 (20%) → 必须
- 或 dynamic fee structure → 待 SDK 验证

理由: SOL/USDC 类 0.02%–0.25% base 在 10U notional × 0.5% daily turnover 下 gross fee ~$0.00025 < cost ~$0.156，结构性亏损。
要打平 5% 阈值：gross fee = 10 × 0.005 × 0.05 = $0.0025；2000U notional × 0.005 × 0.05 = $0.5 → 接近 cost。

### 1.2 high_volume_dlmm (soft preference)

- 24h volume >= $1M 优先
- 24h volume >= $100k 可接受
- 24h volume < $10k 标记 watch only

### 1.3 high_liquidity_near_active (smoke 关键)

- active bin 附近 ±5% 必须有 liquidity
- 10/20U quote 必须能成功 → 否则不进 EV model
- 上一轮 16 池全部 0 liquidity at ±10% → 本轮要直接淘汰该批

### 1.4 quote_friendly (Meteora DLMM 物理)

- bin_step 适中 (50–2000)
- 避免 bin_step=2 (SOL/USDC 类极密) — 上一轮死因
- 避免 bin_step >= 5000 (单 bin 太宽，零售 quote 落不到 bin)

### 1.5 token_quality

- A 级: USDC / SOL / USDT (稳定 / 主流) — 池 search 优先
- B 级: 主流 LST (mSOL, jitoSOL, bSOL) — 池
- C 级: bluechip SPL (BONK, JUP, WIF, JTO 等) — 池
- D 级: memecoin (高 vol + 高 fee 但 IL 极高) — 仅作 watch

## 2. Source priority

### 2.1 A 类 (高 confidence, 必须用)

1. **Meteora UI top pools page** — `https://app.meteora.ag/clmm-api/pair/all` (公开) 或 `https://dlmm-api.meteora.ag/pair/all` (历史路径)
2. **Meteora dlmm-sdk ts-client GitHub** — `MeteoraAg/dlmm-sdk` raw repos 拿 example 池 (V3 已知做法)
3. **Meteora 官方文档** — `https://docs.meteora.ag` 中的 example / known addresses

### 2.2 B 类 (中等 confidence, 必须 chain verify)

1. **DexScreener** — `https://api.dexscreener.com/latest/dex/pairs/solana/<addr>` 或 search endpoint
2. **GeckoTerminal** — `https://api.geckoterminal.com/api/v2/networks/solana/dexes/meteora/pools` (历史 endpoint) 或 new endpoint
3. **Jupiter** — `https://quote-api.jup.ag/v6/quote` (作为 token list 验证)

B 类要求: chain getAccountInfo owner == `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` AND data_len == 904 才进 decode。

### 2.3 黑名单

- 已经失败的 bin_step=2 类 (SOL/USDC 衍生)
- 上一轮 reject bucket 全部 16 池 (避免浪费 cycles)
- 任何 token 24h volume < $1k 的池

## 3. Source collection target

| 维度 | 目标 |
|---|---|
| candidate_raw_count | 30–80 |
| source_count_by_type.A | >= 10 (Meteora UI) |
| source_count_by_type.B | >= 20 (DexScreener/GeckoTerminal/Jupiter) |
| high_fee_candidate_count (UI 列表 front-page) | >= 15 |
| high_volume_candidate_count (24h vol > $100k) | >= 10 |
| duplicate_count | 标记不阻断 |
| invalid_count (chain verify fail) | 不阻断 (后续 stage 处理) |

## 4. Pre-filter logic (D 阶段 chain verify 前)

按以下降序排列 candidate 优先级:

1. base_fee_hint >= 5% AND token_pair 含 USDC 或 SOL
2. base_fee_hint >= 1% AND 24h_volume_hint >= $100k
3. base_fee_hint >= 5% (不论 token)
4. 24h_volume_hint >= $1M
5. 其它

## 5. Meteora DLMM program 验证

```text
program_id = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
data_len   = 904 bytes (LbPair struct)
owner      = program_id
```

任何 owner != program_id 或 data_len != 904 的池直接 reject。

## 6. 决策约束 (继承)

- can_run_probe_now = false
- tiny_canary_allowed = no
- 不读 keypair / seed / private key
- 不调用 sendTransaction / open_lp / close_lp / addLiquidity
- 不接 wallet
- 不启动 live / canary / paper

## 7. 失败模式 (诚实)

- 如果 0 candidate 命中 high_fee threshold → 本轮立即转 Orca
- 如果 candidate 命中 high_fee 但 chain verify 后全部 0 verified → 仍转 Orca
- 如果 0 quote_ready (即所有 high-fee 池也都没 liquidity near active) → 转 Orca
- 如果有 quote_ready 但 EV 全负 → 转 Orca (高 fee memecoin 池 IL 主导)
- 仅当 realistic scenario 出现 positive 且池 not memecoin → 10/20U probe preflight

## 8. 下一阶段

进入 Stage D — 定向候选源收集 (30-80 个候选池，UI top + UI high-fee + Jupiter popular + DexScreener search)。
