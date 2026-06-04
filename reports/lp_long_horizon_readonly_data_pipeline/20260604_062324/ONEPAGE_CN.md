# LP Long Horizon Read-only Data Pipeline — One-Pager

- stage: `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- run_id: `20260604_062324`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (设计 + smoke 通过, 不开 probe / canary / live / paper)

## 0. 一句话

本阶段不重开实盘, 不换协议, 不动 wallet. 只为 R0 阶段长期只读数据采集设计
6 类数据 schema + smoke collector 脚本, 写路径严格隔离到 `data/lp_long_horizon/`.
`can_run_probe_now` 仍 `false`, `tiny_canary_allowed` 仍 `no`.

## 1. 核心字段

| 字段 | 值 | 含义 |
|---|---|---|
| `global_lp_rejected` | `false` | (锁定, 沿用 scope_audit 060659) |
| `current_probe_allowed` | `false` | 当前不允许任何自动 probe |
| `long_horizon_pipeline_ready` | `true` | 本任务完成 (R0 阶段) |
| `collector_script_built` | `true` | smoke 脚本已实现 |
| `market_regime_classifier_spec_ready` | `true` | 7 regime spec 已完成 |
| `actual_fee_accrual_schema_ready` | `true` | 5 section schema 已完成 |
| `can_run_probe_now` | `false` | locked |
| `tiny_canary_allowed` | `no` | locked |
| `edge_proven` | `no` | locked |
| `wallet_or_tx_touched` | `false` | locked |
| `transaction_sent` | `false` | locked |
| `docs_updated` | `true` | 不改 docs/LPBOT_RESEARCH_STATUS_CN.md (因为本阶段是技术实施而非口径修正) |
| `recommended_next_stage` | `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1` | R0 阶段下一步 (长期 run, 需独立 stage) |

## 2. 6 类数据 schema

| 类别 | 字段数 | R0 状态 | R1+ 升级 |
|---|---|---|---|
| pool_snapshot | 16 | 完整 | 同 R0 |
| quote_snapshot | 11 | 完整 (6 notional) | 同 R0 |
| fee_velocity | 7 | proxy (quote 推导) | actual via tokenId (R1) |
| liquidity_distribution | 8 | 完整 | 同 R0 |
| market_regime | 7 | 1 sample / day | 同 R0 |
| future_actual_fee_accrual | 23 | schema only, 0 record | R1 需 user tokenId / paid indexer |

## 3. 7 类市场 regime (classifier spec)

1. low_volatility_stable (vol_7d < 1%) — 优先级最高
2. incentive_period (LM/bribe active) — 覆盖其他 trend
3. high_volatility_trend (vol_7d >= 10%)
4. high_volume_sideways (sideways + vol_tvl_30d >= 1%)
5. uptrend (px_7d > +5%)
6. downtrend (px_7d < -5%)
7. sideways (默认 fallback)

R0 阶段不实装, 仅 spec. 实装要等 collector 长期运行开始后, 单独 stage + 单独 audit.

## 4. actual fee accrual schema (5 section)

- **entry** 段 (21 字段): 用户进入 position 时的 on-chain 状态
- **exit** 段 (18 字段): 用户退出 position 时的 on-chain 状态
- **collect_fee** 段 (10 字段): R1 阶段 on-chain 抓 collect event
- **tokens_owed** 段 (6 字段): mid-position 24h 快照
- **derived** 段 (13 字段): 离线派生, 用于对比 heuristic vs actual

R0 阶段只写 schema, 不抓数据. R1 阶段需 user 提供 tokenId 或 paid indexer.

## 5. 采集器架构

```
[design mode] (default)
   └─ print schema preview + expected cells + exit 0
[smoke mode] (--mode smoke)
   └─ 1 pass × 5 protocol × 6 notional = 30 quote cells (1 pool per protocol)
   └─ 5 fee_velocity windows
   └─ 1 liquidity_distribution
   └─ 7 market_regime (per regime)
   └─ 1 actual_fee placeholder
   └─ 写 data/lp_long_horizon/<run_id>/
[long-running mode]
   └─ hard-rejected (daemon / 30d / long / loop / cron)
```

## 6. 安全 7 层审计

1. 架构层 (mode whitelist, daemon disable, write path constraint)
2. 代码层 (静态 token 检查, 30+ banned tokens)
3. 数据源层 (4 source adapter 全部 read-only, mutation patched)
4. 写路径层 (必须 data/lp_long_horizon/, 7 类路径不允许)
5. 锁存字段层 (7 字段保持 locked)
6. 进程层 (ps aux 检查 canary / live / paper / keypair)
7. 跨阶段隔离 (不污染 cmd/ internal/ configs/ migrations/ shadow/ live/ dryrun)

## 7. 与 scope_audit 060659 的接口

本任务**消费**了 scope_audit 的 7 个 boundary 字段 + 3 个 build target 字段, 并产出
5 个 R0 阶段可执行单元:

| scope_audit build target | 本任务对应 |
|---|---|
| needs_longer_horizon_validation | Stage C 数据需求 + Stage E schema |
| needs_actual_fee_accrual | Stage G actual fee schema |
| needs_market_regime_split | Stage F regime spec |

R1 / R2 / R3 / R4 / R5 阶段是后续任务, 不在本任务范围.

## 8. 后续路径

- `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1` — R0 阶段长期运行 (需独立 stage + manual approval)
- `LP_LONG_HORIZON_READONLY_PIPELINE_FIX_REPEAT` — R0 阶段后续修复 (如有问题)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` — 维持当前状态
- `STOP_LP_RESEARCH_NOW` — 彻底停止

本任务 `recommended_next_stage` = `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`.

## 9. 警示

- 当前不开 live / canary / paper / probe
- 当前不接 wallet / signer / keypair
- 当前不发 transaction / approve / swap / add_liquidity / remove_liquidity / collect_fee
- 当前不写 production positions / shadow 原始表
- 当前 collector 脚本默认 design mode, smoke 1 pass 即退
- 任何长期运行必须单独 stage + 单独 audit + 单独 manual approval
- `internal/core/execution/hard-disable` 仍 active, 不释放
