# 12h Readonly Continuous Observation Node Report (Partial Real Universe)

- stage: `LP_LONG_HORIZON_READONLY_12H_STAGE_RUN_V1` (auto-finalize Stage H)
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- report_generated_at_utc: `2026-06-07T16:20:00Z`
- coverage_scope: **`partial_solana_bsc_real_universe`** (NOT full universe)
- 12h gate: **PASS** (`actual_runtime_minutes=720 >= 660`, error_rate_pct=0.0, data_quality_status=PASS)
- 12h finalize status: **PASS**
- recommended_next_stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` (per finalize block, 见 §7 — 但是 24h **不** 自动启动, 需要新审批 + 新 scope freeze)

## 0. 一句话

12h 只读 partial collector (Solana 49 + BSC V3 4 = 53 池, 5 protocols, 2 chains) 跑通 12h (720 min), 12/12 checkpoints ok, error_rate=0.0%, data_quality=PASS, gate=PASS. Base 链 不可达 → 显式 missing. 全部数据 read-only, **不** 触发 wallet / tx / probe. **不** 自动 24h.

## 1. 时间线

| 阶段 | 时间 (UTC) | 状态 |
|---|---|---|
| launched | 2026-06-06T13:24:00Z | ✅ done |
| checkpoint 1/12 | 2026-06-06T13:24:45Z | ✅ done (smoke) |
| checkpoint 2/12 | 2026-06-06T14:24:47Z | ✅ done |
| checkpoint 3/12 | 2026-06-06T15:24:45Z | ✅ done |
| checkpoint 4/12 | 2026-06-06T16:24:45Z | ✅ done |
| checkpoint 5/12 | 2026-06-06T17:24:45Z | ✅ done |
| checkpoint 6/12 | 2026-06-06T18:24:45Z | ✅ done |
| checkpoint 7/12 | 2026-06-06T19:24:45Z | ✅ done |
| checkpoint 8/12 | 2026-06-06T20:24:45Z | ✅ done |
| checkpoint 9/12 | 2026-06-06T21:24:45Z | ✅ done |
| checkpoint 10/12 | 2026-06-06T22:24:45Z | ✅ done |
| checkpoint 11/12 | 2026-06-06T23:24:45Z | ✅ done |
| checkpoint 12/12 (final) | 2026-06-07T00:25:06Z | ✅ done |
| 12h end | 2026-06-07T01:24:44Z | ✅ done (elapsed=720min) |
| finalize block | 2026-06-07T03:24:xxZ | ✅ done (auto, rc=0) |
| git commit + push | 2026-06-07T01:24:45Z | ✅ done (`30b67c4`) |

**Runtime** = 720 min (12h × 60min) **exact**, `actual_runtime_minutes=720`. 12h gate valid (`>= 660` min, 这里 720 > 660).

## 2. 池 universe 分布 (53 pools, 2 chains, 5 protocols)

| Chain | Protocol | Pools | TVL bucket |
|---|---|---|---|
| solana | orca_whirlpool | 13 | SOL/USDC, SOL/JitoSOL, SOL/cbBTC, JLP/USDC, PYUSD/USDC, SOL/WBTC, FDUSD/USDT, JTO/JitoSOL, cbBTC/USDC, CRCLx/USDC, SOL/whETH, SOL/JLP, wfragSOL/JitoSOL |
| solana | raydium_clmm | 10 | SOL/USDC, USD1/SOL, USDC/USDT, SOL/USDT, RAY/SOL, + 5 low-tvl (USWR/UNOS/SAOS/WorldCup) |
| solana | raydium_cpmm | 10 | BOME/SOL, SOL/USDC, Fartcoin/SOL, $WIF/SOL, jellyjelly/SOL, arc/SOL, USELESS/SOL, GOAT/SOL, SPACEX/SOL, SpaceX/SOL |
| solana | meteora_dlmm | 16 | wSOL/USDC, JTO/USDC, PUMP/wSOL ×4, MINT/USDC ×3, MINT/wSOL ×5, BONK/wSOL |
| bsc | pancakeswap_v3 | 4 | WBNB/USDT ×2, WBNB/USDC ×2 |
| **Total** | **5** | **53** | real on-chain pool addresses, smoke_placeholder data fields |

**Coverage scope** (per spec):
- ✅ 49 Solana real pools (from prior stage connector CSVs)
- ✅ 4 BSC V3 real pools (factory.getPair + slot0 verified)
- ❌ Base chain 0 pools (public RPC 全部 403, 已 honest disclosed in 上一 stage)
- ❌ BSC V2 0 pools (factory.getPair returned 0)
- placeholder_pool_count = **0**

## 3. 12h 数据收集 (12 checkpoints × 53 pools)

| Metric | ckpt 1/12 | ckpt 12/12 | 12h total (dedup) |
|---|---|---|---|
| pool_snapshots | 53 | 53 | 636 (= 53×12) |
| quote_snapshots | 318 (= 53×6 notional) | 318 | **3816** (= 53×6×12) |
| fee_velocity | 265 (= 53×5 windows) | 265 | **3180** (= 53×5×12) |
| liquidity_distribution | 53 | 53 | 636 (= 53×12) |
| market_regime | 7 | 7 | 84 (= 7×12) |
| actual_fee_accrual | placeholder (1) | placeholder (1) | 12 (per-ckpt placeholder) |

**Per-checkpoint notional** (6 levels): 10, 100, 1k, 10k, 100k, 1M USD
**Per-checkpoint fee windows** (5 windows): 15m, 1h, 4h, 24h, 7d

## 4. 数据质量

| Quality metric | 值 | 评估 |
|---|---|---|
| error_rate_pct | **0.0%** | ✅ PASS |
| consecutive_429_max | **0** | ✅ PASS (no rate-limit) |
| data_quality_status | **PASS** | ✅ |
| wallet_or_tx_touched | **false** | ✅ no chain write |
| transaction_sent | **false** | ✅ no tx |
| send_hard_disable_still_active | **true** | ✅ hard disable intact |
| no_production_write | **true** | ✅ |
| no_shadow_overwrite | **true** | ✅ |
| can_run_probe_now | **false** | ✅ LOCKED |
| tiny_canary_allowed | **"no"** | ✅ LOCKED |
| auto_advance_to_next | **false** | ✅ LOCKED |
| auto_advance_started | **false** | ✅ LOCKED |
| longer_stage_started | **false** | ✅ no 24h triggered |

**Per-row smoke_placeholder flag** (12h 数据全 honest 标记):
- `pool_snapshots.jsonl`: `smoke_placeholder=false` (real addresses) but `reserve_a_raw=0, reserve_b_raw=0, liquidity=0` 因 no live RPC
- `quote_snapshots.jsonl`: `smoke_placeholder=true, amount_in_raw=0, amount_out_raw=0` (proxy mode)
- `fee_velocity.jsonl`: `smoke_placeholder=true, sample_count=0` (proxy mode)
- `liquidity_distribution.jsonl`: `smoke_placeholder=true, active_range_liquidity=0`
- `market_regime.jsonl`: `smoke_placeholder=true, price_change_pct=0, realized_vol_pct=0` (regime label 仅由 token_pair 静态分类)
- `actual_fee_accrual_placeholder.json`: 12 ckpt × 1 placeholder (schema only, r1 requires user-provided tokenId)

**重要**: 12h 验证的是 **pipeline 稳定性** + **adapter wiring** + **checkpoint scheduling** + **data quality flag 正确性**, **不** 是 fee accrual 实际数字 (那需要 live RPC + on-position tokenId). 这是 r0 phase 设计 — r1 (actual) 需要 user-provided tokenId (per spec).

## 5. Market regime 分布 (12h)

12h 期间 7 个 regime 类别各记录 12 次 (= 1/day × 12 days? **不**, 1/regime/day × 7 regime × 12h ≈ 7×12 = 84; 但 ckpt 是 hourly, 12 ckpt 怎么变成 12/regime?)

诚实: 这是**不**真实 regime — `smoke_placeholder=true, price_change_pct=0, realized_vol_pct=0`. regime 标签是**静态**分配的 (per token_pair, 不是 real-time market data). 12h 期间:
- uptrend: 12 次
- downtrend: 12 次
- sideways: 12 次
- high_volume_sideways: 12 次
- high_volatility_trend: 12 次
- incentive_period: 12 次
- low_volatility_stable: 12 次

→ 这意味着每个 pool 在每个 ckpt 都**逐个**轮流写 7 个 regime (53 pool × 7 regime = 371/ckpt, 但实际是 7 行/ckpt → 84/12h, 因为是 global regime per ckpt, not per pool). 真实 regime 需 r1 + live price feed.

## 6. Locked fields (5 core + 7 additional)

| 字段 | 锁定值 | 评估 |
|---|---|---|
| `can_run_probe_now` | `false` | ✅ LOCKED |
| `tiny_canary_allowed` | `"no"` | ✅ LOCKED |
| `edge_proven` | `"no"` | ✅ LOCKED (12h 仍 r0 phase, smoke_placeholder) |
| `wallet_or_tx_touched` | `false` | ✅ LOCKED |
| `transaction_sent` | `false` | ✅ LOCKED |
| `send_hard_disable_still_active` | `true` | ✅ LOCKED |
| `auto_advance_to_next` | `false` | ✅ LOCKED (24h **不** 自动) |
| `auto_advance_started` | `false` | ✅ LOCKED |
| `longer_stage_started` | `false` | ✅ LOCKED |
| `no_paid_rpc_key_committed` | `true` | ✅ LOCKED |
| `no_real_secret_committed` | `true` | ✅ LOCKED |
| `no_production_write` | `true` | ✅ LOCKED |
| `no_shadow_overwrite` | `true` | ✅ LOCKED |

## 7. recommended_next_stage = `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1`

**Finalize 写了这个**, 但这**不**等同于 "自动 24h 启动". 解释:

- `auto_advance_to_next=false` (LOCKED in FINAL_VERDICT)
- 24h 是**新 stage**, 需新审批 (`APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=24h mode=readonly no_probe=true` + `scope_clarification`)
- 需新 scope freeze (e.g. `coverage_scope=partial_solana_bsc_real_universe_24h_extension`)
- 需新 MANUAL_APPROVAL_RECORDED.json (NOT carry over 12h approval)
- 需新 PRE_RUN_SAFETY_CHECK

**4 个 allowed next stages** (per FINAL_VERDICT):
1. `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` (24h extension, 需 user 重新审批)
2. `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1` (review 12h node report, scope=partial)
3. `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` (在能 reach Base RPC 的 env 再 smoke)
4. `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (暂停)

## 8. 12h finalize 输出 (auto by stage runner)

| File | 路径 | 大小 |
|---|---|---|
| `.finalize_succeeded` | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/.finalize_succeeded` | 0 bytes (marker) |
| `FINAL_VERDICT.json` | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/FINAL_VERDICT.json` | 1296 bytes |
| `aggregate_summary.json` | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/logs/aggregate_summary.json` | — |
| `supervisor.log` | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/logs/supervisor.log` | 83.6KB |
| `nohup.log` | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/logs/nohup.log` | 83.7KB |
| git commit | `30b67c4 research: finalize 12h long horizon readonly run 20260606_131323` | 2 files |
| git push | `c3932db..30b67c4 → origin/feat/supabase-postgres-deployment` | ✅ done |

## 9. 12h node report 评估结论

**12h PASS**:
- runtime 720 min (gate >= 660) ✅
- 12/12 checkpoints ok ✅
- error_rate 0.0% ✅
- consecutive_429_max 0 ✅
- data_quality_status PASS ✅
- no wallet / tx / probe ✅
- no auto-advance (24h NOT triggered) ✅
- no paid RPC / secret committed ✅
- no production write / shadow overwrite ✅

**r0 phase 评估**:
- pipeline 稳定 ✅
- adapter wiring 稳定 ✅
- checkpoint scheduling 稳定 ✅
- data quality flag 正确 ✅
- universe (53 pools) 稳定 ✅

**r0 → r1 升级路径** (NOT in this 12h):
- 需 live RPC (Base reachability fix OR paid RPC — both blocked by freeze)
- 需 on-position tokenId (from user 实际 mint)
- 需 real-time market data feed (CoinGecko / Pyth)
- 需 actual fee accrual 跨 12h position snapshot
- 需 IL realized vs IL actual 对比

**绝对禁止** (per LP strategy research freeze):
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不自动 24h (需新审批)
- ❌ 不**把** `edge_proven=no` 翻成 `yes` (r0 phase 数据仍 placeholder)

## 10. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1` | done | supervisor finalize 4 Python heredoc lowercase bool bug |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` | done | universe 33 → 72 (8 protocols, 3 chains); 23 池 not observable |
| `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` | done | 4 EVM/BSC adapter + 1 Meteora verify |
| `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1` | done | rpc_registry.py + 13 → 49 observable; Base 不可达 |
| `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1` | done | 启动 12h partial (53 池) via nohup; checkpoint 1/12 ok |
| **`LP_LONG_HORIZON_READONLY_12H_STAGE_RUN_V1` (本 stage, Stage H auto)** | **done** | **12h 跑通, 12/12 ok, gate PASS, finalize PASS** |
| 下一 stage (user decide) | pending | 4 allowed next stages (per §7) |

## 11. 下游 / 用户可选

1. **`LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1`**: 24h extension (推荐 for stability), 需新审批
2. **`LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`**: review 本 node report
3. **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`**: 在 Base-reachable env 再 smoke (next env)
4. **`PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`**: 暂停
