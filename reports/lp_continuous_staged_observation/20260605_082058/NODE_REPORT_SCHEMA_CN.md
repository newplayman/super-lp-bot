# Stage D: 节点报告 Schema

- schema: `lp_long_horizon_node_report_schema_v1`
- schema_version: `1.0`
- designed_at_utc: `2026-06-05T08:22:00Z`

## 0. 目的

定义 6h / 12h / 24h / 48h / 72h / 7d 节点的阶段报告标准 schema. 每个节点报告必须包含以下字段, 任何字段缺失 = 节点报告 schema invalid = gate FAIL.

## 1. 顶层必填字段

| 字段 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `node_stage` | string enum [6h,12h,24h,48h,72h,7d] | ✅ | 节点标识 |
| `run_id` | string | ✅ | 对应 collector run_id |
| `generated_at_utc` | string ISO8601 | ✅ | 节点报告生成 UTC 时间 |
| `node_window_start_utc` | string ISO8601 | ✅ | 节点 wallclock 窗口起点 = collector T0 |
| `node_window_end_utc` | string ISO8601 | ✅ | 节点 wallclock 窗口终点 ≈ generated_at_utc |
| `runtime_minutes` | number | ✅ | 实际 wallclock 分钟数 |
| `expected_runtime_minutes` | number | ✅ | 期望分钟数 (6h=360, 12h=720, 24h=1440, 48h=2880, 72h=4320, 7d=10080) |
| `runtime_within_tolerance` | boolean | ✅ | runtime >= expected - tolerance (默认 60) |
| `short_mode_used` | boolean | ✅ | 必须 false; true = schema invalid |
| `collection_continuity` | boolean | ✅ | collector 节点期间是否连续运行 |
| `single_supervisor` | boolean | ✅ | 是否只有 1 个 supervisor 进程 |

## 2. Coverage Block (链 / DEX / 池 三层)

### 2.1 `chain_coverage[]`

| 字段 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `chain` | string enum [base, bsc, solana, ethereum, arbitrum, optimism, polygon] | ✅ |  |
| `observed` | boolean | ✅ | collector 实际观察过该链 |
| `pool_count` | integer | ✅ | 该链池数 |
| `quote_ready_count` | integer | ✅ | quote 数据就绪的池数 |
| `fee_ready_count` | integer | ✅ | fee 数据就绪的池数 |
| `ev_ready_count` | integer | ✅ | EV 估算就绪的池数 |
| `invalid_reason` | string | (if observed=false) | e.g. `no_connector_implemented_yet` / `rpc_rate_limited` / `chain_skipped_for_safety` |

### 2.2 `dex_coverage[]`

| 字段 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `chain` | string | ✅ |  |
| `protocol` | string enum | ✅ | uniswap_v3 / aerodrome / pancakeswap_v3 / pancakeswap_v2 / pancakeswap_v3_solana / meteora_dlmm / orca_whirlpool / raydium_clmm / raydium_amm_v4 / raydium_cpmm |
| `pool_type` | string enum | ✅ | v3 / clmm / v2_cpmm / dlmm / stable |
| `observed_pool_count` | integer | ✅ |  |
| `quote_ready_count` | integer | ✅ |  |
| `fee_ready_count` | integer | ✅ |  |
| `ev_ready_count` | integer | ✅ |  |
| `connector_used` | string | ✅ | e.g. `internal/adapters/pool/raydium_clmm/readonly.py`; 如果未实现, 写 `null` |
| `data_source` | string enum | ✅ | public_rpc / public_indexer / design_placeholder / smoke_placeholder |
| `invalid_reason` | string | (if observed=false) |  |

### 2.3 `pool_coverage[]`

| 字段 | 类型 | 必填 | 描述 |
|---|---|---|---|
| `chain` | string | ✅ |  |
| `protocol` | string | ✅ |  |
| `pool_address` | string | ✅ |  |
| `token_pair` | string | ✅ | e.g. `SOL/USDC` |
| `pool_type` | string | ✅ |  |
| `fee_tier_or_fee_bps` | number | ✅ | V3 fee tier / DLMM bin_step / CPMM fee_bps |
| `tvl_proxy` | number (USD) | ✅ | R0 是 proxy |
| `volume_proxy` | number (USD/window) | ✅ | R0 是 proxy |
| `liquidity_near_active` | number | (v3/clmm/dlmm) | active tick 范围 / bin 范围 |
| `quote_ready` | boolean | ✅ |  |
| `fee_ready` | boolean | ✅ |  |
| `ev_ready` | boolean | ✅ |  |
| `selected_for_candidate_review` | boolean | ✅ | 是否进入候选池 |
| `reject_reason` | string | (if not selected) | fee_proxy_negative / il_proxy_dominates / regime_5_dominated / low_liquidity_proxy / concentrated_holder_proxy / no_quote_ready / no_fee_ready / missing_connector / other |

## 3. Row Count Block

| 字段 | 必填 | 描述 |
|---|---|---|
| `checkpoint_count_observed` | ✅ | data_dir 实际有 checkpoint_N 目录数 |
| `checkpoint_count_expected` | ✅ | 6h=6, 12h=12, 24h=24, 48h=48, 72h=72, 7d=168 |
| `pool_snapshot_rows` | ✅ |  |
| `quote_snapshot_rows` | ✅ |  |
| `fee_velocity_rows` | ✅ |  |
| `liquidity_distribution_rows` | ✅ |  |
| `market_regime_rows` | ✅ |  |
| `actual_fee_accrual_placeholder_rows` | ✅ | R0 = 0 (无 tokenId) |
| `row_count_match_expected` | ✅ | rows >= expected * min_rows_per_ckpt |

## 4. Market Regime Block

`market_regime_distribution`: 7 regime 计数 (per data_pipeline/20260604_062324/FINAL_VERDICT.json regime_count=7)

- regime_1_calm_trending
- regime_2_calm_ranging
- regime_3_volatile_trending
- regime_4_volatile_ranging
- regime_5_high_vol_chop
- regime_6_low_liquidity
- regime_7_stress_event

`regime_diversity_score` = 观察到的 regime 种类数 / 7
`regime_distribution_warning` (可选) = 如果某 regime > 80%, 警告 `regime_dominated_by_<name>`

## 5. Candidate Block

### `best_candidates[]` (max 10)

| 字段 | 描述 |
|---|---|
| `rank` | 排名 |
| `chain` / `protocol` / `pool_address` / `token_pair` | 池身份 |
| `ev_proxy_usd_per_day` | EV proxy (USD/天) |
| `ev_proxy_confidence` | low / medium / high |
| `fee_proxy_basis` | 引用 FEE_ESTIMATION_BASIS_CN.md |
| `il_proxy_basis` | IL proxy 公式 |
| `range_sensitivity_summary` | 窄/中/宽 fee proxy 范围 |
| `regime_split` | 7 regime 下的 fee proxy 拆分 |

### `rejected_candidates[]`

`reject_reason` enum: fee_proxy_negative / il_proxy_dominates / regime_5_dominated / low_liquidity_proxy / concentrated_holder_proxy / no_quote_ready / no_fee_ready / missing_connector / other

## 6. Fee Estimation Block

| 字段 | 必填 | 描述 |
|---|---|---|
| `actual_fee_data_available` | ✅ | R0 = false |
| `fee_proxy_used` | ✅ | R0 = true |
| `heuristic_used` | ✅ | R0 = true |
| `v3_clmm_fee_proxy_formula` | ✅ | 详细公式 |
| `meteora_dlmm_fee_proxy_formula` | ✅ | 详细公式 |
| `cpmm_fee_proxy_formula` | ✅ | 详细公式 |
| `stable_pool_fee_proxy_formula` | ✅ | 详细公式 |
| `future_actual_fee_requirement[]` | ✅ | 6 项: tokenId / positionId, entry feeGrowth / exit feeGrowth, tokensOwed, collected fee, actual add/remove cost, realized PnL |

## 7. Range Sensitivity Block

| 字段 | 必填 | 描述 |
|---|---|---|
| `range_assumption_used` | ✅ | narrow / medium / wide / all_three_compared |
| `range_sensitivity_available` | ✅ | 本节点是否对每候选池计算了窄/中/宽 |
| `v3_clmm_range_sensitivity[]` | ✅ | 9 字段: pool_address, narrow/medium/wide_fee_proxy, in_range_time_ratio, out_of_range_time_ratio, active_liquidity_share_proxy, tick_liquidity_density, range_width, range_risk |
| `meteora_dlmm_range_sensitivity[]` | ✅ | 7 字段: pool_address, narrow/medium/wide_bin_fee_proxy, active_bin_distance, bin_liquidity_density, bins_with_liquidity_count, sparse_liquidity_warning |
| `cpmm_range_sensitivity[]` | ✅ | 5 字段: pool_address, full_range_fee_proxy, lp_share, price_impact, il_proxy |
| `fee_estimate_confidence` | ✅ | R0 = low (proxy only) |

## 8. Data Quality Block

| 字段 | 必填 | 描述 |
|---|---|---|
| `data_quality_status` | ✅ | data_quality_ok / data_quality_warn / data_quality_fail |
| `data_quality_issues[]` | (optional) | e.g. `rpc_429_streak_3_at_2h` |
| `error_indicator_count` | ✅ | error/traceback/exception/failed/NameError grep 命中数 |
| `rpc_429_count` | ✅ |  |
| `checkpoint_completeness_pct` | ✅ | observed/expected × 100 |

## 9. Gate Block (locked 字段)

| 字段 | 必填 | 锁定值 / 描述 |
|---|---|---|
| `gate_pass` | ✅ | PASS / WARN_ACCEPTABLE / FAIL |
| `gate_status` | ✅ | 同上 |
| `can_continue_collection` | ✅ | true / false |
| `can_enter_preflight_design` | ✅ | R0 = false (节点报告 ≠ preflight 设计) |
| `can_use_for_preflight` | ✅ | FAIL 节点 = false |
| `can_run_probe_now` | ✅ | **ALWAYS false (locked)** |
| `tiny_canary_allowed` | ✅ | **ALWAYS "no" (locked)** |
| `edge_proven` | ✅ | **ALWAYS "no" (locked)** |
| `wallet_or_tx_touched` | ✅ | **ALWAYS false (R0 数据采集)** |
| `transaction_sent` | ✅ | **ALWAYS false (R0 数据采集)** |

## 10. Recommended Next Action Block

`recommended_next_action` enum:

- `continue_collection_to_next_node` (gate=PASS)
- `continue_collection_with_note` (gate=WARN_ACCEPTABLE)
- `continue_collection_but_mark_node_invalid_for_preflight` (gate=FAIL 但仍可继续采集)
- `raise_fix_repeat_to_user` (gate=FAIL + 强烈建议修 bug)
- `raise_pause_to_user` (gate=FAIL + 强烈建议暂停)
- `raise_stop_to_user` (gate=FAIL + 强烈建议停止 LP research)

## 11. Schema Validation Rules

### Required Top-Level Fields

21 个必填顶层 block, 任何缺失 = schema invalid = gate FAIL = node report generator 退出码 7.

### Forbidden Top-Level Keys

绝对**不得**出现以下 keys (R0 数据采集阶段无任何 wallet/tx/签名相关):

- `tx_hash`
- `wallet_address`
- `private_key`
- `keypair`
- `mnemonic`
- `seed`
- `signed_transaction`

如果 grep 命中 → schema invalid + 报告 "SECRET_LEAK_DETECTED" → 退出 8.

### Schema Invalid Action

- node report generator 退出 7
- gate_status = FAIL
- can_continue_collection = false (但仍允许 collector 继续采集, 只是不写新节点报告)
- recommended_next_action = `raise_fix_repeat_to_user`

## 12. 结论

Schema 设计完成. 21 个顶层必填 block, 7 个 forbidden key, 3 类 gate 状态 (PASS / WARN_ACCEPTABLE / FAIL). R0 阶段所有 locked 字段保持 `can_run_probe_now=false`, `tiny_canary_allowed="no"`, `edge_proven="no"`, `wallet_or_tx_touched=false`, `transaction_sent=false`.

**Stage D PASS** → 进入 Stage E (覆盖范围 manifest spec).
