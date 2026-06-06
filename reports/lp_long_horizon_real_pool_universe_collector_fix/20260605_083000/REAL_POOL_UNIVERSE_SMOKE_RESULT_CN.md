# Real Pool Universe Smoke Result

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1`
- check_stage: `D_REAL_POOL_UNIVERSE_SMOKE_RESULT`
- checked_at_utc: `2026-06-06T08:12:30Z`
- smoke_ran: **true** (`data/lp_long_horizon_real_pool_smoke/20260605_083000/`)

## 0. 总结

✅ **PASS** — 修复后 collector 不再跑 placeholder. 5 个真实池 selected, 全部 real on-chain Solana addresses, real TVL/volume proxies, real source_artifact. 0 placeholder, 0 wallet/tx, 0 forbidden process.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `real_pool_universe_used` | **true** |
| `real_pool_universe_path` | `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json` |
| `selected_real_pool_count` | **5** (all 5 stable, 来自 orca_whirlpool) |
| `placeholder_pool_count` | **0** |
| `all_pools_are_real_on_chain` | **true** |
| `all_pool_addresses_real` | **true** |
| `any_smoke_placeholder_in_output` | **false** |
| `all_pool_addresses_pass_format_check` | **true** (43-44 char base58 Solana format) |
| `all_pool_addresses_unique` | **true** |
| `all_have_source_artifact` | **true** |
| `all_have_selection_reason` | **true** |

## 2. 5 个 selected_real_pools (全部 stable, 来自 orca_whirlpool)

| # | Chain | Protocol | Pool Type | Pool Address | Token Pair | Fee (bps) | TVL (USD) | 24h Vol (USD) |
|---|---|---|---|---|---|---|---|---|
| 1 | solana | orca_whirlpool | stable | `Hp53XEtt4S8SvPCXarsLSdGfZBuUr5mMmZmX2DRNXQKp` | SOL/JitoSOL | 1 | 31,439,174 | 20,121,510 |
| 2 | solana | orca_whirlpool | stable | `G2FiE1yn9N9ZJx5e1E2LxxMnHvb1H3hCuHLPfKJ98smA` | JTO/JitoSOL | 30 | 6,752,812 | 2,010,289 |
| 3 | solana | orca_whirlpool | stable | `9tXiuRRw7kbejLhZXtxDxYs2REe43uH2e7k1kocgdM9B` | PYUSD/USDC | 30 | 5,372,197 | 4,039,707 |
| 4 | solana | orca_whirlpool | stable | `68soqftZg4HL1Dcis5hMgkLKU9qyC8qbn5JzLhrxhgi9` | FDUSD/USDT | 30 | 5,276,535 | 2,938,005 |
| 5 | solana | orca_whirlpool | stable | `5xfKkFmhzNhHKTFUkh4PJmHSWB6LpRvhJcUMKzPP6md2` | wfragSOL/JitoSOL | 1 | 3,665,596 | 1,265,672 |

**注**: 5 池全部 `stable_classified=true` (per `_select_universe_pools` 的 `stable first` 排序). 短 smoke (`--max-pools 5`) 优先选 stable 池, 验证 fix 正确. 大 smoke (e.g. `--max-pools 33`) 可覆盖 4 类协议 (orca clmm + stable, raydium_clmm, raydium_cpmm).

## 3. row counts (5 pools × 1 snapshot)

| 类别 | count |
|---|---|
| pool_snapshot_rows | **5** (real pool addresses, no `<smoke_pool_`) |
| quote_snapshot_rows | **30** (5 × 6 notional) |
| fee_velocity_rows | **25** (5 × 5 windows) |
| liquidity_distribution_rows | **5** (5 × 1) |
| market_regime_rows | **7** (7 regime classifications) |
| actual_fee_accrual_placeholder_rows | **1** (R0 schema only) |

## 4. R0 限制 (诚实披露)

| 字段 | 状态 |
|---|---|
| `no_live_RPC` | **true** (无 live RPC, pool addresses / TVL / volume 全部从 universe JSON) |
| `tvl_volume_are_proxies_from_universe_JSON` | **true** |
| `no_feeGrowth_snapshot` | **true** (R0 无 tokenId) |
| `no_tokensOwed` | **true** |
| `no_real_fee_accrual` | **true** |
| `actual_fee_data_available` | **false** (R0 仅 schema) |
| `fee_proxy_used` | **true** |
| `heuristic_used` | **true** |
| `fee_estimate_confidence` | **`"low"`** (R0 无 tokenId, 升级到 R1 需用户单独批准) |

quote / fee / EV **仍** 不真实可用 (R0 read-only + 无 live RPC). 但**关键**: 池 universe (pool_address / token_pair / TVL / volume / source_artifact) 是真实的, **不**是 placeholder.

## 5. smoke_placeholder 排除验证

| 字段 | 值 |
|---|---|
| `no_smoke_pool_in_addresses` | **true** |
| `no_smoke_mint_in_token_mints` | **true** |
| `smoke_placeholder_marker_check` | **PASS** — no `<smoke_pool_` or `<smoke_mint_` markers in any pool_snapshots / quote_snapshots / fee_velocity / liquidez_distribution / market_regime row |

## 6. 安全检查

| 字段 | 值 |
|---|---|
| `wallet_or_tx_touched` | **false** |
| `transaction_sent` | **false** |
| `no_canary_live_paper` | **true** |
| `no_wallet_keypair_signer` | **true** |
| `no_production_write` | **true** |
| `no_shadow_overwrite` | **true** |

## 7. 结论

✅ **PASS** — collector CLI fix (`--pool-universe`) + stage runner fix (forward `--pool-universe` to collector) 全部工作. 短 smoke 证明:

1. collector 不再跑 placeholder
2. 真实池 universe 被实际使用 (5 unique real on-chain addresses)
3. TVL / volume 是真实 proxy (来自 universe JSON)
4. source_artifact / selection_reason 全部保留
5. placeholder marker (`<smoke_pool_` / `<smoke_mint_`) 在所有 output 中 0 出现
6. 无 wallet / tx / probe / canary / live / paper

**修复确认**: 12h 阶段"声明 universe vs 实际 placeholder" gap 已修复. 但**仅** 短 smoke 验证. 12h 实际数据 (84 文件) **仍**是 placeholder (12h supervisor 跑的是 commit 23fed9d **之前**的 collector, 当时没有 `--pool-universe` CLI). 12h 节点报告 (commit 90cb18a) 的 `all_pools_are_smoke_placeholder=true` 仍正确, **不**应被本短 smoke 覆盖.

**next stage**: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` (用户单独审批 12h 重跑, 这次 collector 用 `--pool-universe` 写真实池), 需**先**修 V3 supervisor finalize bug (line 435 + 493: bash `${REAL_GATE_PASS}` → `${REAL_GATE_PASS^^}`) 否则 supervisor 仍会 fail-safe trap 写 default-zeros.

**Stage D PASS** → 进入 Stage E (测试 + 安全).
