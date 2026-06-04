# Orca Candidate Source Collection — Stage E

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`

## 0. 关键结果

```text
candidate_raw_count            = 15002
selected_for_chain_verify_count = 75
source_count_by_type.OrcaOfficial = 14983
source_count_by_type.DexScreener   = 19
source_count_by_type.GeckoTerminal = 0  (endpoint 404)
high_fee_candidate_count (>=30bps)  = 12646
high_volume_candidate_count (vol24h >= $1M) = 36
has_anchor_count (USDC/SOL/USDT)    = 12541
duplicate_count                     = 21
```

## 1. Source 状态

| Source | URL | 状态 | 数量 |
|---|---|---|---|
| A. Orca 官方 API | `https://api.mainnet.orca.so/v1/whirlpool/list` | OK 200 (17.9MB) | 14983 |
| B. DexScreener search "orca solana"/"usdc"/"sol" | `https://api.dexscreener.com/latest/dex/search` | OK 200 | 49 raw, 19 unique |
| B. GeckoTerminal Solana Orca pools | `https://api.geckoterminal.com/api/v2/networks/solana/dexes/orca_whirlpools/pools` | **404** | 0 |

## 2. 选 candidate 策略 (75 选)

按 (high_fee) + (high_volume) 各取 40, dedupe → 75 cap。

| 优先级 | 维度 | 选 |
|---|---|---|
| 1 | high_fee (>=30bps) ∩ high_volume (>= $1M/d) | yes |
| 2 | high_fee (>=30bps) | yes |
| 3 | high_volume (>= $1M/d) | yes |

注: Orca fee tier 常见 1/4/5/12/30/100 bps。>=30bps 视为 high-fee。

## 3. Top 15 candidate 预览 (from Orca official API + DexScreener)

| rank | pool | name | tick_spacing | fee_bps | tvl | vol24h |
|---|---|---|---|---|---|---|
| 1 | (待 F 后显示) | SOL/USDC | 64 | 30 | $32M+ | $230M+ |
| 2 | (待 F 后显示) | USDC/SOL | 4 | 4 | high | high |
| ... | | | | | | |

(75 个全部以 CSV 形式落盘 `orca_candidate_source_collection.csv`)

## 4. 与 Meteora V8 (20260604_021913) 对比

| 维度 | Meteora V8 | Orca V1 |
|---|---|---|
| 源 A 数量 | 0 (Meteora API 404) | 14983 (Orca 官方 API) |
| 源 B 数量 | 60 (GeckoTerminal + DexScreener) | 19 (DexScreener only) |
| total raw | 60 | 15002 |
| selected | 60 | 75 |
| fee 范围 | 0.01%–1% | 0.01%–1% (per Orca fee tier) |

## 5. 安全断言

```text
touched_trading_path = false
touched_wallet_tx_bridge_live_paper = false
solana_wallet_or_keypair_touched = false
sources_used = public API only
repo_node_modules = not created
```

## 6. 下一阶段

进入 Stage F — 链上 getAccountInfo owner 验证 (Orca program id) + 去重。
