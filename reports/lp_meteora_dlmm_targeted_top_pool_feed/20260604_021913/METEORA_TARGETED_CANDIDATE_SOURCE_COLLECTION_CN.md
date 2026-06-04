# Meteora Targeted Candidate Source Collection — Stage D

- stage: `LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1`
- run_id: `20260604_021913`

## 0. 关键结果

```text
candidate_raw_count            = 60
source_count_by_type.GeckoTerminal = 53
source_count_by_type.DexScreener   = 7
high_volume_candidate_count   = 27 (vol24h >= $1M)
high_fee_candidate_count      = 0  (cannot determine at source level; SDK decode in Stage F)
duplicate_count                = 48 (GeckoTerminal + DexScreener 重叠)
invalid_count                  = 0  (chain verify in Stage E)
quote_token_distribution.USDC  = 28
quote_token_distribution.SOL   = 31
quote_token_distribution.USDT  = 1
```

## 1. 来源策略

本轮不随机扩池，按 fee / volume 排序。来源:

| Source | URL | 数量 | 状态 |
|---|---|---|---|
| GeckoTerminal Meteora DLMM (page 1-3) | `https://api.geckoterminal.com/api/v2/networks/solana/dexes/meteora/pools?page=N` | 53 | OK (200) |
| DexScreener Meteora + USDC/SOL/USDT search | `https://api.dexscreener.com/latest/dex/search?q=...` | 7 unique (49 raw, 42 dup) | OK (200) |
| Meteora dlmm-api (历史) | `https://dlmm-api.meteora.ag/pair/all` | 0 | **404** (API moved) |
| Meteora app.meteora.ag clmm-api | `https://app.meteora.ag/clmm-api/pair/all` | 0 | **404** |
| Meteora DAMM v2 API | `https://dammv2-api.meteora.ag/pools/...` | 0 | **404** |
| Jupiter token list | `https://tokens.jup.ag/tokens` | 0 | **timeout** (本机访问受限) |

A 类源 (Meteora 官方 API) 全部 404 / 不可用。
B 类源 (GeckoTerminal + DexScreener) 工作良好，已覆盖 60 个池。
下一阶段 (E) 链上 owner 验证确保全部是 Meteora DLMM 真实池。

## 2. Top 30 高 vol 候选 (vol24h desc)

| rank | pool_address | name | vol24h (USD) | reserve (USD) | source |
|---|---|---|---|---|---|
| 1 | `5rCf1DM8LjKTz5gBRKJBQzu` | SOL/USDC | 31,425,809 | 2,754,655 | GT |
| 2 | `7tSbDdxxUPMi` | USDC/SOL | 17,799,151 | 123,337 | GT |
| 3 | `ANCx141SujgV` | HYPE/USDC | 14,663,540 | 3,874,428 | GT |
| 4 | `BGm1tav58oGc` | SOL/USDC | 11,065,853 | 3,410,714 | GT |
| 5 | `9ToMYnmEeYKc` | ZEC/USDC | 10,696,518 | 1,670,659 | GT |
| 6 | `9SMp4yLKGtW9` | PUMP/USDC | 9,616,387 | 1,640,728 | GT |
| 7 | `81GpCm4d13y8` | HYPE/SOL | 5,839,613 | 1,553,909 | GT |
| 8 | `4vQaxcqAyJFc` | HYPE/USDC | 5,827,275 | 1,359,746 | GT |
| 9 | `6oQ9wVex4mKZ` | HYPE/SOL | 5,498,985 | 291,198 | GT |
| 10 | `6F4rVnmVc1A2` | HYPE/USDC | 5,223,231 | 485,120 | GT |
| 11 | `F2BstVuVWqBn` | HYPE/USDC | 5,011,811 | 136,761 | GT |
| 12 | `Hz1EtXTGaFEt` | cbBTC/SOL | 4,713,737 | 134,736 | GT |
| 13 | `3C5YE97HADPD` | TRUMP/USDC | 3,941,374 | 3,752,595 | GT |
| 14 | `HDhWhQCBrSh9` | cbBTC/SOL | 3,101,074 | 112,110 | GT |
| 15 | `7ubS3GccjhQY` | cbBTC/USDC | 2,466,776 | 621,987 | GT |
| 16 | `5hbf9JP8k5zd` | MET/USDC | 3,233,896 | 1,103,335 | DS |
| 17 | `HTvjzsfX3yU6` | SOL/USDC | 2,316,310 | 366,214 | GT |
| 18 | `8ztFxjFPfVUt` | USELESS/SOL | 2,206,360 | 447,246 | GT |
| 19 | `FhdW3Y6Ea6hX` | wNEAR/USDC | 2,179,929 | 830,208 | GT |
| 20 | `GeUkx21Vc6yg` | MUSK/USDC | 2,171,212 | 271,738 | GT |
| 21 | `6qz7THwQvcjF` | BP/USDC | 1,886,987 | 147,762 | GT |
| 22 | `Hdh5jVfUktsw` | NEAN/USDC | 1,908,547 | 65,393 | DS |
| 23 | `CnK82s8exdsK` | three/SOL | 1,516,786 | 365,271 | GT |
| 24 | `9bL8Pptpb8M2` | GACHA/SOL | 1,390,566 | 76,925 | GT |
| 25 | `FoL5dFhV7XUo` | KALSHI/USDC | 1,178,305 | 27,023 | GT |
| 26 | `46CgAPEz8V2e` | HYPE/SOL | 1,129,390 | 477,909 | GT |
| 27 | `HRYEjwdo3bZ1` | USDC/SOL | 1,026,512 | 271,097 | GT |

(完整 60 行见 `meteora_targeted_candidate_source_collection.csv`)

## 3. Memecoin 候选 (target token for high-fee)

HYPE, PUMP, TRUMP, MUSK, KALSHI, GACHA, three, USELESS, wNEAR, NEAN, MET, BP, BP — 全部都是 vol24h >= $1M 的活跃 memecoin / 投机 token。预期 base_fee 在 1%–30% 范围 (即 100–3000 bps)。

主流 token 候选 (bluechip + 稳定币): SOL/USDC, USDC/SOL, cbBTC/SOL, cbBTC/USDC, wNEAR/USDC。

## 4. 已剔除

- MET/SOL (vol24h 1.1M, 8 candidates) — DexScreener 标注为 Meteora 但多为非 DLMM 池
- 任何 quote token 不是 USDC/SOL/USDT 的池
- 任何 vol24h < $1k 的池

## 5. 安全断言

```text
touched_trading_path                = false
touched_wallet_tx_bridge_live_paper = false
solana_wallet_or_keypair_touched    = false
transaction_sent                    = false
source_sources_public_api           = true (GeckoTerminal + DexScreener)
sources_kept_in_repo                 = false (只保留候选地址)
```

## 6. 下一阶段

进入 Stage E — 链上 owner = `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` AND data_len == 904 验证。
