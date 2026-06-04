# Meteora Targeted Pool Snapshot — Stage F

- stage: `LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1`
- run_id: `20260604_021913`

## 0. 关键结果

```text
attempted_count           = 56
sdk_decode_success_count  = 56    (100% decode success)
sdk_decode_failure_count  = 0
high_fee_pool_count       = 0     (base_fee >= 5% = 0; per Stage C 5% threshold)
high_max_fee_pool_count   = 56    (max_fee >= 20% = ALL pools, since Meteora DLMM max=10%=1000bps)
```

## 1. Base fee 分布

| base_fee_bps | count | 含义 |
|---|---|---|
| 1 | 9 | 0.01% — 极低 (超稳定池) |
| 2 | 1 | 0.02% |
| 3 | 7 | 0.03% |
| 4 | 6 | 0.04% |
| 5 | 3 | 0.05% |
| 10 | 10 | 0.10% |
| 15 | 1 | 0.15% |
| 20 | 11 | 0.20% — 主流 (5rCf1 SOL/USDC 31M vol/d) |
| 25 | 4 | 0.25% |
| 50 | 1 | 0.50% |
| 100 | 3 | 1.00% — high tier (3 池，HYPE/CnK/9bL/三个 memecoin) |

**max_fee_bps = 1000 (10%) for ALL 56 pools** — Meteora DLMM dynamic-fee 设计的硬上限 10%。

## 2. Bin step 分布

| bin_step | count | 备注 |
|---|---|---|
| 2 | 5 | 极密 — 上一轮死因 |
| 4 | 6 | 密 |
| 5 | 1 | |
| 8 | 3 | |
| 10 | 9 | 适中 |
| 15 | 1 | |
| 16 | 1 | |
| 20 | 11 | 主流 |
| 25 | 2 | |
| 50 | 4 | 较宽 — quote 友好 |
| 80 | 8 | 宽 — quote 友好 |
| 100 | 2 | 极宽 — 单 bin 价格区间很大 |

## 3. 结构性发现 (本轮真实)

**Meteora DLMM 没有 5% static base fee 的池**。所有 56 个 GeckoTerminal top 池 + DexScreener top 池的 base_fee 都在 0.01%–1% 范围，max_fee (dynamic 峰值) 统一 10%。

这是 Meteora DLMM 的设计: **dynamic fee**，不是 static high fee。当 volatility 上升时 fee 自动 ramp up (1% base → 10% max)，但 base 始终低。10/20U 零售 LP 在 base 0.2% 下 gross fee = 20 × 0.005 × 0.002 = $0.0002 < cost $0.156 → 结构性亏损。

**结论: 静态 base_fee 路径打不出 5%+ 的池。**

候选替代指标 (后续 Stage G 用):
- **max_fee_bps >= 1000** (10%): 56/56 (100%) — 不是区分指标
- **base_fee_bps >= 20** (0.2%): 19/56 (主流)
- **base_fee_bps >= 50** (0.5%): 4/56 — high tier
- **base_fee_bps >= 100** (1%): 3/56 — 最高 tier memecoin
- **bin_step >= 20** (宽 bin): 28/56 — quote 友好候选
- **bin_step in [50, 200]**: 14/56 — 黄金区间

## 4. Top 高 base_fee 候选 (进 G 阶段 quote)

| rank | pool | name | base/max (bps) | bin_step | active_bin |
|---|---|---|---|---|---|
| 1 | `CnK82s8exdsK` | three/SOL | 100/1000 | 80 | -295 |
| 2 | `9bL8Pptpb8M2` | GACHA/SOL | 100/1000 | 100 | -432 |
| 3 | `HuPRxaBcjQYr` | MET/USDC | 100/1000 | 80 | 266 |
| 4 | `9uTgLv3Ya7sr` | ?/USDC | 50/1000 | 50 | -470 |
| 5 | `6qz7THwQvcjF` | BP/USDC | 25/1000 | 50 | -1649 |
| 6 | `8eDUNVrNUZ87` | ?/USDC | 25/1000 | 80 | -294 |
| 7 | `8pKt3mAE3KVY` | ?/USDC | 25/1000 | 25 | -1092 |
| 8 | `Eqv1tJGkLFeH` | ?/USDC | 25/1000 | 25 | -2963 |
| 9 | `ANCx141SujgV` | HYPE/USDC | 20/1000 | 20 | -1311 |
| 10 | `9SMp4yLKGtW9` | PUMP/USDC | 20/1000 | 20 | -3192 |

## 5. 主流 base_fee 20bps + 宽 bin_step 候选 (quote 友好)

`5rCf1DM8LjKTz5gBRKJBQzu` (SOL/USDC, vol 31M/d, base 20bps, bin_step 20) — 即使是 V1 已知失败的 SOL/USDC 类，bin_step=20 而非 2；本轮如能 quote 成功可能打破 V1–V7 阻断。

## 6. 安全断言

```text
no_keypair_loaded                = true
no_signer_constructed            = true
no_transaction_sent               = true
solana_wallet_or_keypair_touched = false
SDK @meteora-ag/dlmm v1.9.10     = used for decode only
repo_node_modules                = NOT created (SDK in /tmp isolated install)
```

## 7. 下一阶段

进入 Stage G — bin liquidity / quote targeted smoke。
- Coverage 5/9/15 (max 15 hard cap)
- Notionals 10/20 优先 (本轮目标)
- Quote direction: USDC/SOL → token (anchor → volatile) only
- 输出: `meteora_targeted_quote_readiness.{json,csv}`
