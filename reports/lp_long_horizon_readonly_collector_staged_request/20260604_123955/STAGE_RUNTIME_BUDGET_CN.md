# Stage F — Stage Runtime Budget (阶段运行时预算)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1`
- run_id: `20260604_123955`

## 0. 目的

定义 6 阶段 (6h/12h/24h/48h/72h/7d) 各自的运行时预算, 包含:
- 采样频率 (per pool per category)
- 估计 record 数 / sqlite 大小 / jsonl 大小
- 估计 disk 累计
- public RPC rate limit 估算
- CPU / RAM 估算
- paid RPC 必要性判定

## 1. 采样频率 (per pool, baseline)

| 类别 | 频率 | 6h 样本数 | 12h | 24h | 48h | 72h | 7d |
|---|---|---|---|---|---|---|---|
| pool_snapshots | 1 / 30 min | 12 | 24 | 48 | 96 | 144 | 336 |
| quote_snapshots | 1 / 5 min | 72 | 144 | 288 | 576 | 864 | 2016 |
| fee_velocity | rolling (5 windows) | 60 | 120 | 240 | 480 | 720 | 1680 |
| liquidity_distribution | 1 / 30 min | 12 | 24 | 48 | 96 | 144 | 336 |
| market_regime | 1 / 15 min | 24 | 48 | 96 | 192 | 288 | 672 |

## 2. record 数 (per pool × 6 notional)

quote_snapshots 实际行数 = pool × notional × sample:

| Stage | pool × notional × sample | 实际行数 |
|---|---|---|
| 6h | 5 × 6 × 72 = 2160 | 2160 |
| 12h | 5 × 6 × 144 = 4320 | 4320 |
| 24h | 5 × 6 × 288 = 8640 | 8640 |
| 48h | 5 × 6 × 576 = 17280 | 17280 |
| 72h | 5 × 6 × 864 = 25920 | 25920 |
| 7d | 5 × 6 × 2016 = 60480 | 60480 |

## 3. SQLite / JSONL 大小估算

| Stage | sqlite (KB) | jsonl (KB) | total (KB) | total (MB) |
|---|---|---|---|---|
| 6h | 100 | 250 | 350 | 0.34 |
| 12h | 200 | 500 | 700 | 0.68 |
| 24h | 400 | 1000 | 1400 | 1.37 |
| 48h | 800 | 2000 | 2800 | 2.73 |
| 72h | 1200 | 3000 | 4200 | 4.10 |
| 7d | 2800 | 7000 | 9800 | 9.57 |

(假设: pool_snapshot ~200B, quote_snapshot ~300B, fee_velocity ~250B,
liquidity ~200B, regime ~200B, actual_fee ~700B; sqlite overhead × 1.5)

注: 实际大小以 stage 跑出来为准. 估算是上限.

## 4. disk 累计 vs 阈值

| Stage | 估计累计 (MB) | disk_usage_max_mb (gate) | 距离上限 |
|---|---|---|---|
| 6h | 0.34 | 1 | 34% |
| 12h | 0.68 | 2 | 34% |
| 24h | 1.37 | 5 | 27% |
| 48h | 2.73 | 10 | 27% |
| 72h | 4.10 | 15 | 27% |
| 7d | 9.57 | 30 | 32% |

每阶段 gate 阈值留 ~3× 余量, 避免临界值.

## 5. public RPC rate limit 估算

solana_rpc_public.getMultipleAccountsInfo: 30 req / 10s (publicnode) = 3 req / s.
5 pool × 1 / 30 min pool_snapshots = 0.0028 req / s.
5 pool × 6 notional × 1 / 5 min = 1.0 req / s. (略超公共 RPC 限)

| Stage | quote 调用次数 | 平均 RPS | 5 连 429 风险 |
|---|---|---|---|
| 6h | 2160 | 0.10 | low |
| 12h | 4320 | 0.10 | low |
| 24h | 8640 | 0.10 | low |
| 48h | 17280 | 0.10 | low (margin 30×) |
| 72h | 25920 | 0.10 | low |
| 7d | 60480 | 0.10 | low |

注: 上表假设**仅**本地 5 pool + 仅 quote + 仅 public RPC. 如果加
coingecko_public (10-30 req/min) + dex_screener (60 req/min), RPS 仍 OK.
如果 R0 阶段扩展到 20+ pool, RPS 会升到 0.4+, 仍 OK 但余量小.

如果上 dex_screener OHLC + 7d 不间断, public RPC 总 RPS 估 0.3-0.5, 仍 OK.

## 6. paid RPC 必要性判定

| Stage | 是否需 paid RPC | 原因 |
|---|---|---|
| 6h | ❌ (no) | 5 pool + 5 req/s 余量充足 |
| 12h | ❌ (no) | 同上 |
| 24h | ❌ (no) | 同上 |
| 48h | ⚠️ (recommend) | 长期持有 pool 流动性变化, 部分 source 可能 429 |
| 72h | ✅ (yes) | 公共 RPC 72h 持续触发, 建议 paid (Helius free tier) |
| 7d | ✅ (yes, must) | 公共 RPC 7d 不间断必爆 429, 必须 paid |

注: 48h 起**建议** paid RPC, 72h 起**必须** paid RPC. paid RPC 接入是
paid_rpc_indexer_integrated readiness 那一项, 9 项 readiness 第 7 项.

## 7. CPU / RAM 估算

| Stage | CPU (avg) | RAM (peak) | notes |
|---|---|---|---|
| 6h | 5% | 50MB | 1 process, sqlite 7MB |
| 12h | 5% | 60MB | sqlite 14MB |
| 24h | 8% | 80MB | sqlite 28MB |
| 48h | 10% | 100MB | sqlite 56MB |
| 72h | 12% | 150MB | sqlite 84MB |
| 7d | 15% | 200MB | sqlite 200MB, 7d 不间断 |

注: 7d 不间断需要后台 (tmux / nohup). 本轮 tmux 模板 disabled, 实装在 6H_RUN_APPROVAL_V1.

## 8. 估算 vs 实际

实际数字以 stage 跑出来的 smoke_summary.json + run_summary.json 为准.
本表是 upper bound 估算. 如果实际超阈值, 走 fix_repeat, 调小采样频率
(e.g. quote 改 1/10 min) 或加 pool (无, R0 阶段固定 5 pool).

## 9. 5 pool 列表 (固定)

来自 fix_repeat_v1 local_artifact_replay:
- meteora_dlmm / `CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa`
- orca_whirlpool / `C9U2Ksk6KKWvLEeo5yUQ7Xu46X7NzeBJtd9PBfuXaUSM`
- raydium_clmm / `3nMFwZXwY1s1M5s8vYAHqd4wGs4iSxXE4LRoUMMYqEgF`
- raydium_cpmm / `vs6XUbGcVWG75Gv81qvDMBxkQ67Kr2eLrFNDTrCxxwk`
- solana_stable / `AiMZS5U3JMvpdvsr1KeaMiS354Z1DeSg5XjA4yYRxtFf`

## 10. 总结

| 维度 | 6h | 12h | 24h | 48h | 72h | 7d |
|---|---|---|---|---|---|---|
| 累计 sample (pool) | 12 | 24 | 48 | 96 | 144 | 336 |
| 累计 quote rows | 2160 | 4320 | 8640 | 17280 | 25920 | 60480 |
| 估计 disk 累计 (MB) | 0.34 | 0.68 | 1.37 | 2.73 | 4.10 | 9.57 |
| gate disk_max_mb | 1 | 2 | 5 | 10 | 15 | 30 |
| public RPC 余量 | 30× | 30× | 30× | 30× | 30× | 30× |
| paid RPC 必要 | no | no | no | recommend | yes | must |
| CPU avg | 5% | 5% | 8% | 10% | 12% | 15% |
| RAM peak | 50MB | 60MB | 80MB | 100MB | 150MB | 200MB |

## 11. 结论

6 阶段 runtime budget 完整定义. 数据量 / disk / RPC / CPU / RAM 估算覆盖.
48h 起建议 paid RPC, 72h 起必须 paid RPC. Stage F 通过. 进入 Stage G
(Failure / abort policy).
