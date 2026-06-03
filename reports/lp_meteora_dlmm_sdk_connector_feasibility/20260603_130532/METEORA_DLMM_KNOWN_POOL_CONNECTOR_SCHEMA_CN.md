# Meteora DLMM Known-Pool Connector Schema v1 — Stage G

- stage: `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1`
- run_id: `20260603_130532`
- schema_version: `v1`

## 0. 设计意图

**Research-only connector** — 6 张 read-only snapshot 表，用于 V3 后续阶段 + Phase 2A 的 EV 计算与池选择。**不**包含任何 execution / signer / wallet / position 路径。

## 1. 6 张表

| # | table_id | primary_key | 用途 |
|---|---|---|---|
| 1 | `meteora_dlmm_known_pool_universe_v1` | `pool_address` | 冻结的 known-pool feed, 带 source provenance |
| 2 | `meteora_dlmm_pool_snapshot_v1` | `pool_address + snapshot_at_utc` | per-pool LbPair state (来自 DLMM.create decode) |
| 3 | `meteora_dlmm_bin_liquidity_snapshot_v1` | `pool_address + bin_id + snapshot_at_utc` | per-bin xAmount/yAmount (V3 阻断 by public RPC) |
| 4 | `meteora_dlmm_quote_snapshot_v1` | `pool_address + notional + direction + snapshot_at_utc` | 10U/20U quote (V3 阻断) |
| 5 | `meteora_dlmm_fee_snapshot_v1` | `pool_address + snapshot_at_utc` | fee 参数 (V3 base/max 可用, protocol 需重读) |
| 6 | `meteora_dlmm_survival_ev_preview_v1` | `pool_address + notional + direction + preview_at_utc` | research-only survival EV; V3 缺 quote data, 不能算 |

## 2. 字段覆盖矩阵 (per spec)

| required field | 覆盖表 | 覆盖字段 |
|---|---|---|
| `pool_address` | (1)(2)(3)(4)(5)(6) | all primary_key 或 FK |
| `token_x` | (2) | `pool_snapshot.token_x` |
| `token_y` | (2) | `pool_snapshot.token_y` |
| `bin_step` | (2) | `pool_snapshot.bin_step` |
| `active_bin` | (2) | `pool_snapshot.active_bin_id` |
| `active_price` | (2) | `pool_snapshot.active_bin_price` |
| `fee_parameters` | (5) | `fee_snapshot.base_fee_bps, max_fee_bps, protocol_fee_bps` |
| `reserve_x` | (2) | `pool_snapshot.reserve_x_amount` |
| `reserve_y` | (2) | `pool_snapshot.reserve_y_amount` |
| `bin_liquidity` | (3) | `bin_liquidity_snapshot.x_amount, y_amount` (V3 blocked) |
| `quote_10u` | (4) | `quote_snapshot.notional_usd_approx='10U'` (V3 blocked) |
| `quote_20u` | (4) | `quote_snapshot.notional_usd_approx='20U'` (V3 blocked) |
| `data_confidence` | all 6 tables | — |
| `invalid_reason` | all 6 tables | — |

## 3. V3 known 状态

### 3.1 works (V3 实测)

| 表 | 状态 |
|---|---|
| `meteora_dlmm_known_pool_universe_v1` | 2/2 selected (Stage D) |
| `meteora_dlmm_pool_snapshot_v1` | 2/2 fields populated (Stage E) |
| `meteora_dlmm_fee_snapshot_v1` | 2/2 base + max populated; protocol_fee_bps 需重读 (Stage E SDK returned undefined) |

### 3.2 blocked by public RPC (V3 实测)

| 表 | 阻断 | 根因 |
|---|---|---|
| `meteora_dlmm_bin_liquidity_snapshot_v1` | getMultipleAccounts 403/410 | public RPC 限制 |
| `meteora_dlmm_quote_snapshot_v1` | swapQuote requires bin arrays (above) | 同上 |
| `meteora_dlmm_survival_ev_preview_v1` | no quote data → ev_confidence='no_quote_data' | 派生 blocked |

## 4. 设计原则

1. **Read-only**: 全部表是 read-only snapshot; 不写 position / 不动 shadow 表
2. **No wallet**: 任何字段都**不**引用 keypair / signer / wallet adapter
3. **No transaction**: 任何字段都**不**含 raw tx / signature
4. **Decimal string**: 所有 amount 是 u128 string 或 decimal string, **不**用 float64
5. **Frozen provenance**: 每个 pool address 有 source URL / source_type / source_confidence
6. **Data confidence honest**: 每张表有 `data_confidence` 字段; public RPC 阻断时默认为 "blocked"; **不**假成功

## 5. 不在本阶段做

- ❌ 不实装任何表到真 storage (research-only 设计)
- ❌ 不连任何 live database
- ❌ 不改任何 production table
- ❌ 不覆盖 shadow 表
- ❌ 不改 EVM executor v2
- ❌ 不释放 v2 hard-disable
- ❌ 不 instantiate Keypair (no signer needed for read-only design)

## 6. 安全断言

```text
schema_read_only         = true
schema_no_wallet         = true
schema_no_transaction    = true
schema_no_keypair        = true
schema_no_db_write       = true
solana_wallet_or_keypair_touched = false
transaction_sent         = false
can_run_probe_now        = false
v2_line_count_unchanged  = true (992)
```

## 7. 下一阶段

进入 Stage H — paid RPC vs known-pool feed decision. 关键发现: pool universe + pool snapshot + fee snapshot 已 V3 实测 works; bin liquidity + quote + EV 被 public RPC 阻断. **3 path decision 必须 reflect 这个二元状态**.
