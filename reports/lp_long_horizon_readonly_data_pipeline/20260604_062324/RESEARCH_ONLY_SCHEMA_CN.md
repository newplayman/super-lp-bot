# Stage E — Research-only 存储 Schema

- stage: `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- run_id: `20260604_062324`

## 0. 目的

定义长期只读数据采集的本地存储 schema. 三种格式:
1. **jsonl** (line-delimited JSON, 每行一条 record) — 适合 git diff + 流式处理
2. **csv** — 适合 Excel / pandas 一次性分析
3. **sqlite** — 适合中等规模 (1M records) 关系查询 + 索引

三种格式 schema 等价, 数据内容一致. 写入策略:
- 默认 jsonl (主存储)
- 同时导出 csv (snapshot for dashboard)
- sqlite 可选, 30d+ 数据才启用

## 1. 6 张表 (jsonl + csv)

### 1.1 pool_snapshots

jsonl record 模板:
```json
{
  "pool_address": "CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa",
  "chain": "solana",
  "protocol": "meteora_dlmm",
  "program_id": "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
  "token_mint_a": "FeMbDo...",
  "token_mint_b": "So11111111111111111111111111111111111111112",
  "token_symbol_a": "FMB",
  "token_symbol_b": "SOL",
  "fee_tier_bps": 100,
  "reserve_a_raw": 1234567890,
  "reserve_b_raw": 9876543210,
  "liquidity": 0,
  "active_tick": null,
  "active_bin": 12345,
  "tvl_usd": 1234.56,
  "snapshot_at": "2026-06-04T06:30:00Z"
}
```

csv header:
```
pool_address,chain,protocol,program_id,token_mint_a,token_mint_b,token_symbol_a,token_symbol_b,fee_tier_bps,reserve_a_raw,reserve_b_raw,liquidity,active_tick,active_bin,tvl_usd,snapshot_at
```

### 1.2 quote_snapshots

jsonl:
```json
{
  "pool_address": "CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa",
  "notional_usd": 10,
  "quote_success": true,
  "amount_in_raw": 12345,
  "amount_out_raw": 54321,
  "price_impact_pct": 0.05,
  "slippage_pct": 0.04,
  "fee_raw": 30,
  "fee_usd": 0.003,
  "error_code": null,
  "quote_at": "2026-06-04T06:30:01Z"
}
```

csv:
```
pool_address,notional_usd,quote_success,amount_in_raw,amount_out_raw,price_impact_pct,slippage_pct,fee_raw,fee_usd,error_code,quote_at
```

### 1.3 fee_velocity

jsonl:
```json
{
  "pool_address": "CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa",
  "window": "7d",
  "volume_proxy_usd": 12345.67,
  "fee_capture_proxy_usd": 12.35,
  "volume_to_tvl_pct": 0.5,
  "sample_count": 720,
  "window_end_at": "2026-06-04T06:30:00Z"
}
```

csv:
```
pool_address,window,volume_proxy_usd,fee_capture_proxy_usd,volume_to_tvl_pct,sample_count,window_end_at
```

### 1.4 liquidity_distribution

jsonl:
```json
{
  "pool_address": "CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa",
  "active_range_liquidity": 12345.67,
  "near_active_liquidity": 23456.78,
  "sparse_liquidity_warning": false,
  "out_of_range_risk": 0.15,
  "tick_spacing": null,
  "bin_step": 80,
  "snapshot_at": "2026-06-04T06:30:00Z"
}
```

csv:
```
pool_address,active_range_liquidity,near_active_liquidity,sparse_liquidity_warning,out_of_range_risk,tick_spacing,bin_step,snapshot_at
```

### 1.5 market_regime

jsonl:
```json
{
  "regime": "downtrend",
  "lookback_days": 7,
  "price_change_pct": -8.5,
  "realized_vol_pct": 12.3,
  "volume_to_tvl_pct": 0.7,
  "incentive_active": false,
  "regime_at": "2026-06-04T06:30:00Z"
}
```

csv:
```
regime,lookback_days,price_change_pct,realized_vol_pct,volume_to_tvl_pct,incentive_active,regime_at
```

### 1.6 future_actual_fee_accrual (R0 placeholder, R1 填 actual)

jsonl:
```json
{
  "token_id": null,
  "pool_address": "CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa",
  "entry_fee_growth_global": null,
  "entry_fee_growth_a": null,
  "entry_fee_growth_b": null,
  "entry_tick_lower": null,
  "entry_tick_upper": null,
  "entry_at": null,
  "exit_fee_growth_global": null,
  "exit_fee_growth_a": null,
  "exit_fee_growth_b": null,
  "exit_tick_lower": null,
  "exit_tick_upper": null,
  "exit_at": null,
  "tokens_owed_a_raw": null,
  "tokens_owed_b_raw": null,
  "actual_collected_a_raw": null,
  "actual_collected_b_raw": null,
  "actual_collected_at": null,
  "actual_pnl_usd": null,
  "il_realized_pct": null,
  "il_actual_pct": null
}
```

R0 阶段此表只有 schema, 不写任何实际 record (R1 阶段才写).
csv header 同字段 (逗号分隔).

## 2. sqlite (research.sqlite)

```sql
-- 仅供后续 R0 阶段 30d+ 数据使用. 本任务 smoke 不启用 sqlite 写入.

CREATE TABLE IF NOT EXISTS pool_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_address TEXT NOT NULL,
    chain TEXT NOT NULL,
    protocol TEXT NOT NULL,
    program_id TEXT NOT NULL,
    token_mint_a TEXT NOT NULL,
    token_mint_b TEXT NOT NULL,
    token_symbol_a TEXT,
    token_symbol_b TEXT,
    fee_tier_bps INTEGER,
    reserve_a_raw INTEGER,
    reserve_b_raw INTEGER,
    liquidity INTEGER,
    active_tick INTEGER,
    active_bin INTEGER,
    tvl_usd REAL,
    snapshot_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pool_snapshots_pool ON pool_snapshots(pool_address, snapshot_at);
CREATE INDEX IF NOT EXISTS idx_pool_snapshots_protocol ON pool_snapshots(protocol, snapshot_at);

CREATE TABLE IF NOT EXISTS quote_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_address TEXT NOT NULL,
    notional_usd REAL NOT NULL,
    quote_success INTEGER NOT NULL,
    amount_in_raw INTEGER,
    amount_out_raw INTEGER,
    price_impact_pct REAL,
    slippage_pct REAL,
    fee_raw INTEGER,
    fee_usd REAL,
    error_code TEXT,
    quote_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quote_snapshots_pool ON quote_snapshots(pool_address, quote_at);
CREATE INDEX IF NOT EXISTS idx_quote_snapshots_notional ON quote_snapshots(notional_usd, quote_at);

CREATE TABLE IF NOT EXISTS fee_velocity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_address TEXT NOT NULL,
    window TEXT NOT NULL,
    volume_proxy_usd REAL,
    fee_capture_proxy_usd REAL,
    volume_to_tvl_pct REAL,
    sample_count INTEGER,
    window_end_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fee_velocity_pool ON fee_velocity(pool_address, window_end_at);

CREATE TABLE IF NOT EXISTS liquidity_distribution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_address TEXT NOT NULL,
    active_range_liquidity REAL,
    near_active_liquidity REAL,
    sparse_liquidity_warning INTEGER,
    out_of_range_risk REAL,
    tick_spacing INTEGER,
    bin_step INTEGER,
    snapshot_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_liquidity_dist_pool ON liquidity_distribution(pool_address, snapshot_at);

CREATE TABLE IF NOT EXISTS market_regime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regime TEXT NOT NULL,
    lookback_days INTEGER NOT NULL,
    price_change_pct REAL,
    realized_vol_pct REAL,
    volume_to_tvl_pct REAL,
    incentive_active INTEGER,
    regime_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_regime_at ON market_regime(regime_at);

CREATE TABLE IF NOT EXISTS future_actual_fee_accrual (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT,
    pool_address TEXT NOT NULL,
    entry_fee_growth_global INTEGER,
    entry_fee_growth_a INTEGER,
    entry_fee_growth_b INTEGER,
    entry_tick_lower INTEGER,
    entry_tick_upper INTEGER,
    entry_at TEXT,
    exit_fee_growth_global INTEGER,
    exit_fee_growth_a INTEGER,
    exit_fee_growth_b INTEGER,
    exit_tick_lower INTEGER,
    exit_tick_upper INTEGER,
    exit_at TEXT,
    tokens_owed_a_raw INTEGER,
    tokens_owed_b_raw INTEGER,
    actual_collected_a_raw INTEGER,
    actual_collected_b_raw INTEGER,
    actual_collected_at TEXT,
    actual_pnl_usd REAL,
    il_realized_pct REAL,
    il_actual_pct REAL
);
CREATE INDEX IF NOT EXISTS idx_actual_fee_token ON future_actual_fee_accrual(token_id);
CREATE INDEX IF NOT EXISTS idx_actual_fee_pool ON future_actual_fee_accrual(pool_address, entry_at);
```

## 3. smoke_summary.json

```json
{
  "stage": "LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1",
  "run_id": "20260604_062324",
  "mode": "smoke",
  "executed_at": "2026-06-04T06:30:00Z",
  "protocol_count": 5,
  "pool_per_protocol": 3,
  "notional_levels": [10, 20, 100, 500, 1000, 2000],
  "expected_cells": 90,
  "executed_cells": 90,
  "skipped_cells": 0,
  "source_aborted": false,
  "sources": {
    "solana_rpc_public": {"ok": 15, "rate_limited": 0, "error": 0},
    "coingecko_public": {"ok": 15, "rate_limited": 0, "error": 0},
    "protocol_sdk_quote": {"ok": 90, "rate_limited": 0, "error": 0},
    "dex_screener_public": {"ok": 15, "rate_limited": 0, "error": 0}
  },
  "wallet_or_tx_touched": false,
  "transaction_sent": false,
  "send_hard_disable_still_active": true,
  "next_stage": "manual_review_of_smoke_artifacts"
}
```

## 4. 写路径约束 (safety guard)

- 必须以 `data/lp_long_horizon/<run_id>/` 开头
- 禁止写到 `migrations/` `cmd/` `internal/` `web/` `configs/` `reports/`
  `data/dryrun.*` `data/shadow.*` `data/live.*` 路径
- 禁止写 production db (postgres dsn, sqlite live_* / shadow_* 前缀)
- 禁止覆盖 shadow 原始表

## 5. 字段命名约定

- `*_raw` = on-chain 原始 integer (raw amount, 不乘 decimals)
- `*_usd` = 已换算 USD 浮点
- `*_at` = ISO 8601 timestamp (UTC)
- 必填字段在 schema 中 explicit `NOT NULL` (sqlite) 或 absent key (jsonl)

## 6. 长期 archive 策略 (R0 阶段后续, 不在本任务)

- 每月 1 号 archive 上月数据到 `data/lp_long_horizon/archive/<YYYY-MM>/`
- sqlite 超过 100MB 触发 vacuum + 索引重建
- 12 个月以上数据按 `pool_address` 分桶, 备份到外部 cold storage
- jsonl 文件 gzip 压缩后保留, csv 转 parquet
- **任何 archive 操作都不写到 production db**

## 7. 结论

- 6 张表 schema (jsonl + csv) 定义完成
- sqlite schema 定义完成, R0 阶段 30d+ 数据启用
- smoke_summary.json 锁定 safety 字段
- 写路径约束明确, 不污染 production / shadow / migration
- 字段命名规范: `*_raw` / `*_usd` / `*_at`
- 长期 archive 策略定义, 不在本任务执行
