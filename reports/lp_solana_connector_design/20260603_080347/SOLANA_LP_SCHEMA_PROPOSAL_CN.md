# Solana LP Normalized Schema Proposal — Stage H

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`

## 0. 设计目标

设计 7 个**只读** normalized table / JSONL 文件；**不**直接写 DB（spec 要求 "research-only tables / files"）；落盘到本地 JSONL + CSV。**不**触钱包 / **不**写生产 DB / **不**覆盖 shadow 原始表。

每个 table 字段对应 `ONEPAGE_CN.md` 中 spec 要求的 20 个核心字段。表与表通过 `pool_address` + `chain` + `protocol` 关联。

## 1. 7 个 table 概览

| 表 | 主要用途 | 行触发 | TTL |
|---|---|---|---|
| `solana_lp_pool_universe_v1` | pool discovery 列表 | discovery scan | 1h |
| `solana_lp_pool_metadata_v1` | pool 详细参数 (fee/decimals/vault) | per pool, on change | 1h |
| `solana_lp_liquidity_snapshot_v1` | bin/tick liquidity 时序 | per pool, every 5-10 min | 30s-5m |
| `solana_lp_fee_velocity_v1` | 24h/7d volume + fee | per pool, daily | 1h |
| `solana_lp_quote_snapshot_v1` | quote 测试结果 | per notional per pool | 30s |
| `solana_lp_virtual_position_preview_v1` | 模型化的 virtual LP EV | per (pool, notional, hold) | static |
| `solana_lp_probe_preflight_v1` | 10/20U probe 前置检查 | per probe attempt | per attempt |

## 2. table 字段

### 2.1 solana_lp_pool_universe_v1

| field | type | 含义 |
|---|---|---|
| chain | str | "solana" |
| protocol | str | "Meteora DLMM" / "Meteora DAMM v2" / "Orca Whirlpools" / "Raydium CLMM" / "Raydium CPMM" / "Lifinity" |
| pool_address | str (base58) | pool pubkey |
| token_a_mint | str (base58) | token A mint pubkey |
| token_b_mint | str (base58) | token B mint pubkey |
| token_a_symbol | str | e.g. "SOL" |
| token_b_symbol | str | e.g. "USDC" |
| pool_type | str | "DLMM" / "DAMM" / "CLMM" / "CPMM" / "PMM" |
| discovered_at_iso | str (ISO) | UTC ISO 8601 |
| last_seen_iso | str (ISO) | UTC ISO 8601 |
| pool_metadata | str (base64) | raw account data |
| invalid_reason | str | empty if valid |

### 2.2 solana_lp_pool_metadata_v1

| field | type | 含义 |
|---|---|---|
| chain | str | "solana" |
| protocol | str | 同上 |
| pool_address | str (base58) | pool pubkey |
| fee_bps | int | base fee in bps (e.g. 1-20 for DLMM; 25 for CPMM) |
| dynamic_fee_supported | bool | true if pool has dynamic fee |
| bin_step | int | DLMM only; bin step in bps |
| tick_spacing | int | CLMM only; tick spacing |
| token_a_decimals | int | SPL mint decimals |
| token_b_decimals | int | SPL mint decimals |
| token_a_vault | str (base58) | token A vault pubkey |
| token_b_vault | str (base58) | token B vault pubkey |
| quote_token | str | which token is the stable (USDC/USDT/DAI) |
| initializable | bool | true if pool can be added to (state flag) |
| last_updated_iso | str (ISO) | UTC ISO 8601 |
| data_confidence | float | 0.0-1.0 |
| invalid_reason | str | empty if valid |

### 2.3 solana_lp_liquidity_snapshot_v1

| field | type | 含义 |
|---|---|---|
| chain | str | "solana" |
| protocol | str | 同上 |
| pool_address | str (base58) | pool pubkey |
| snapshot_at_iso | str (ISO) | UTC ISO 8601 |
| active_bin | int | DLMM only; current active bin id |
| current_tick | int | CLMM only; current tick index |
| bin_array_start | int | DLMM; first bin id in loaded BinArray |
| tick_array_start | int | CLMM; first tick in loaded TickArray |
| liquidity | int | current active liquidity (Q64.64 raw) |
| bin_liquidity_distribution | list[dict] | DLMM; per-bin Q64.64 amount; [{bin_id, amount_x, amount_y}] |
| tick_liquidity_distribution | list[dict] | CLMM; per-tick; [{tick, liquidity_net}] |
| data_confidence | float | 0.0-1.0 |
| invalid_reason | str | empty if valid |

### 2.4 solana_lp_fee_velocity_v1

| field | type | 含义 |
|---|---|---|
| chain | str | "solana" |
| protocol | str | 同上 |
| pool_address | str (base58) | pool pubkey |
| window | str | "24h" / "7d" / "30d" |
| volume_usd_proxy | float | USD 24h volume proxy |
| fee_usd_proxy | float | USD 24h fee proxy |
| fee_apr_proxy | float | annualized fee APR proxy |
| swap_count | int | number of swap events |
| source | str | "jupiter" / "decoded_logs" / "birdeye" |
| last_updated_iso | str (ISO) | UTC ISO 8601 |
| data_confidence | float | 0.0-1.0 |
| invalid_reason | str | empty if valid |

### 2.5 solana_lp_quote_snapshot_v1

| field | type | 含义 |
|---|---|---|
| chain | str | "solana" |
| protocol | str | 同上 |
| pool_address | str (base58) | pool pubkey |
| quote_at_iso | str (ISO) | UTC ISO 8601 |
| notional_usd | float | 10 / 20 / 100 / ... |
| amount_in_token | str | which token is input (e.g. "USDC") |
| amount_in_raw | int | raw amount in (e.g. 10_000_000 for 10 USDC) |
| amount_out_raw | int | raw amount out |
| price_impact_pct | float | % slippage |
| quote_source | str | "jupiter" / "protocol_native" / "simulateTransaction" |
| data_confidence | float | 0.0-1.0 |
| invalid_reason | str | empty if valid |

### 2.6 solana_lp_virtual_position_preview_v1

| field | type | 含义 |
|---|---|---|
| chain | str | "solana" |
| protocol | str | 同上 |
| pool_address | str (base58) | pool pubkey |
| virtual_at_iso | str (ISO) | UTC ISO 8601 |
| notional_usd | float | 10 / 20 / ... |
| hold_window | str | "15m" / "30m" / ... |
| bin_range | list[int, int] | DLMM; [lower_bin_id, upper_bin_id] |
| tick_range | list[int, int] | CLMM; [lower_tick, upper_tick] |
| virtual_liquidity | int | liquidity provided |
| expected_fee_usd | float | expected fee income over hold_window |
| il_lvr_proxy_usd | float | expected IL/LVR over hold_window |
| net_ev_proxy_usd | float | expected fee - IL - cost - slippage |
| net_ev_proxy_pct | float | as % of notional |
| cost_proxy_usd | float | round trip cost (rent + tx + slippage) |
| survival_probability | float | 0.0-1.0; probability of staying in range |
| data_confidence | float | 0.0-1.0 |
| invalid_reason | str | empty if valid |

### 2.7 solana_lp_probe_preflight_v1

| field | type | 含义 |
|---|---|---|
| chain | str | "solana" |
| protocol | str | 同上 |
| pool_address | str (base58) | pool pubkey |
| probe_at_iso | str (ISO) | UTC ISO 8601 |
| notional_usd | float | 10 / 20 |
| hold_window | str | "15m" |
| wallet_pubkey | str (base58) | read-only check; no private key |
| sol_balance | float | lamports/1e9 |
| token_balance_usdc | float | raw/1e6 |
| ata_usdc_exists | bool | true if ata present |
| ata_creation_required | bool | true if ata needs creation |
| rent_required_sol | float | estimated rent for new accounts |
| expected_tx_fee_sol | float | base + priority fee estimate |
| expected_priority_fee_sol | float | priority fee component |
| simulated_open_tx | str (base64) | simulated open position tx (read-only) |
| simulated_open_result | dict | output of simulateTransaction |
| simulated_close_tx | str (base64) | simulated close position tx (read-only) |
| simulated_close_result | dict | output of simulateTransaction |
| preflight_pass | str | "yes" / "warn" / "no" |
| blocker | str | empty if pass |
| data_confidence | float | 0.0-1.0 |
| invalid_reason | str | empty if valid |

## 3. 与 EVM V3 schema 对比

| EVM V3 (upstream) | Solana LP (this design) | 关键差异 |
|---|---|---|
| `lp_pool_universe` | `solana_lp_pool_universe_v1` | 几乎相同；protocol 字符串 |
| `lp_pool_metadata` | `solana_lp_pool_metadata_v1` | fee_bps 替代 tier; bin_step/tick_spacing 分开 |
| `lp_liquidity_snapshot` | `solana_lp_liquidity_snapshot_v1` | bin/tick 分布分开 (per-protocol) |
| `lp_fee_velocity` | `solana_lp_fee_velocity_v1` | 几乎相同 |
| `lp_quote_snapshot` | `solana_lp_quote_snapshot_v1` | input token 是 stable (USDC) 而非 token0 |
| `lp_virtual_position_preview` | `solana_lp_virtual_position_preview_v1` | bin_range / tick_range 分开 |
| `lp_probe_preflight` | `solana_lp_probe_preflight_v1` | 加 rent/ata/priority fee 字段 |

## 4. 字段覆盖检查（spec 要求 20 个核心字段）

spec 列出 20 个核心字段；本设计覆盖情况：

| spec 字段 | 在哪个 table | OK |
|---|---|---|
| chain | 所有 table | ✅ |
| protocol | 所有 table | ✅ |
| pool_address | 所有 table | ✅ |
| token_a | universe, metadata | ✅ |
| token_b | universe, metadata | ✅ |
| token_a_symbol | universe | ✅ |
| token_b_symbol | universe | ✅ |
| pool_type | universe | ✅ |
| active_bin_or_tick | liquidity_snapshot | ✅ |
| liquidity | liquidity_snapshot | ✅ |
| fee_bps | metadata | ✅ |
| dynamic_fee | metadata (boolean) | ✅ |
| volume_proxy | fee_velocity | ✅ |
| quote_10u | quote_snapshot | ✅ |
| quote_20u | quote_snapshot | ✅ |
| fee_velocity | fee_velocity | ✅ |
| il_lvr_proxy | virtual_position_preview | ✅ |
| cost_proxy | virtual_position_preview | ✅ |
| data_confidence | 所有 table | ✅ |
| invalid_reason | 所有 table | ✅ |

**全部 20 字段覆盖**。

## 5. 不在本阶段做

- ❌ 实际写 schema 进 SQL
- ❌ 实际写 JSONL
- ❌ 跑任何 RPC
- ❌ 接 wallet

## 6. 安全断言

```text
this_stage_only_design_schema         = true
this_stage_does_not_create_tables     = true   (next stages 才 create)
this_stage_does_not_run_rpc           = true
solana_wallet_or_keypair_touched      = false
can_run_probe_now                     = false
```
