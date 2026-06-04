# Stage D — 只读采集器架构设计 (Read-only Collector Architecture)

- stage: `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- run_id: `20260604_062324`

## 0. 设计原则

1. **默认 design mode**: 脚本默认 `--mode design`, 不实际调用 RPC, 只输出 schema 与
   预期 cell 数. 必须显式 `--mode smoke` 才做 1 次最小采样.
2. **不允许 daemon**: 任何 long-running 模式 (cron / systemd / while-true) 全部 hard-disable.
   smoke 模式跑完即退.
3. **不自动跑 30d**: 不允许在脚本内用 timer / sleep 循环跨 30d 采集. 长期运行必须
   单独人工批准, 单独 stage, 单独 audit.
4. **read-only 强制**: 脚本中禁止任何写链路径 (eth_sendRawTransaction, sendTransaction,
   signTransaction, Keypair.from_secret_key, add_liquidity, remove_liquidity, swap,
   collect_fee, approve). 由 Stage H 安全审计 + pytest 双重验证.
5. **storage 隔离**: 数据写本地 sqlite / jsonl / csv, 路径默认 `data/lp_long_horizon/`,
   **不**写到 production db (migrations/postgres 路径) 或 shadow 表.

## 1. 架构组件

```
┌────────────────────────────────────────────────────────────────┐
│  scripts/lp_long_horizon_readonly_collector_v1.py               │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ design mode  │  │ smoke mode   │  │ safety guard          │  │
│  │ (default)    │  │ (--mode      │  │ - mode whitelist      │  │
│  │ - print spec │  │  smoke)      │  │ - dry-run flag        │  │
│  │ - validate   │  │ - 1 pass     │  │ - no-wallet flag      │  │
│  │   schema     │  │   90 cells   │  │ - no-tx flag          │  │
│  │ - exit 0     │  │ - exit 0     │  │                       │  │
│  └──────────────┘  └──────────────┘  └───────────────────────┘  │
│         │                │                  │                    │
│         ▼                ▼                  ▼                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Source Adapters (read-only)                              │   │
│  │  - solana_rpc_public (getMultipleAccountsInfo)            │   │
│  │  - coingecko_public (OHLC)                                │   │
│  │  - protocol_sdk_quote (Meteora / Orca / Raydium / Stable) │   │
│  │  - dex_screener_public (volume/TVL)                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Storage Layer                                            │   │
│  │  - data/lp_long_horizon/<run_id>/pool_snapshots.jsonl     │   │
│  │  - data/lp_long_horizon/<run_id>/quote_snapshots.jsonl    │   │
│  │  - data/lp_long_horizon/<run_id>/fee_velocity.jsonl       │   │
│  │  - data/lp_long_horizon/<run_id>/liquidity_distribution   │   │
│  │  - data/lp_long_horizon/<run_id>/market_regime.jsonl      │   │
│  │  - data/lp_long_horizon/<run_id>/smoke_summary.json       │   │
│  │  - data/lp_long_horizon/<run_id>/research.sqlite (schema) │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

## 2. CLI 接口

```bash
# 1) design mode (default, safe)
python scripts/lp_long_horizon_readonly_collector_v1.py
# 输出: schema preview + expected cells + mode confirmation

# 2) smoke mode (1 pass, no daemon, no auto-loop)
python scripts/lp_long_horizon_readonly_collector_v1.py --mode smoke \
    --pools-per-protocol 3 --notionals 10,20,100,500,1000,2000 \
    --out data/lp_long_horizon/<run_id>/

# 3) explicit disable flags (mandatory checks)
python scripts/lp_long_horizon_readonly_collector_v1.py --mode smoke \
    --no-wallet --no-tx --no-bridge --dry-run
```

参数说明:

| 参数 | 默认 | 说明 |
|---|---|---|
| `--mode` | `design` | `design` / `smoke`. 任何其它值 (e.g. `daemon`, `30d`, `long`, `loop`) 全部 hard-reject |
| `--pools-per-protocol` | 3 (smoke) | smoke 模式下每协议池数 |
| `--notionals` | `10,20,100,500,1000,2000` | 6 个 USD notional 等级 |
| `--out` | `data/lp_long_horizon/<run_id>/` | 本地输出目录 |
| `--no-wallet` | true | 显式 disable 任何 wallet 路径 (default-on) |
| `--no-tx` | true | 显式 disable 任何 tx 路径 (default-on) |
| `--no-bridge` | true | 显式 disable 任何 bridge 路径 (default-on) |
| `--dry-run` | true | 显式声明 dry-run (default-on) |

## 3. 速率限制与重试

| 数据源 | 速率 | 重试 | backoff |
|---|---|---|---|
| solana_rpc_public | 30 req / 10s (publicnode) | 3 次 | exponential 1s, 2s, 4s |
| coingecko_public | 10-30 req / min (free) | 3 次 | 60s, 120s, 240s |
| protocol_sdk_quote | 跟随 solana_rpc_public | 3 次 | exponential 1s, 2s, 4s |
| dex_screener_public | 60 req / min | 3 次 | 30s, 60s, 120s |

任何连续 5 个 429 错误 → 立即 abort 该 source, 不再 retry, 在 smoke_summary.json
记录 `source_aborted=true`.

## 4. 错误处理

- `solana_rpc_public` timeout (> 5s) → retry, 3 次后 skip
- `coingecko_public` 4xx (e.g. 429) → retry with backoff, 3 次后 skip
- SDK quote 失败 (e.g. tick_array_not_initialized) → 记 `quote_success=false`,
  继续下一个 notional
- storage 写失败 → 立即 abort, 不重试
- source 整体 abort → smoke_summary.json 标记 `partial=true`

## 5. 并发

默认 sequential (1 个池 → 6 个 notional → next). 任何 --parallel / --workers 参数
都 hard-reject, 避免触发 rate limit + 并发安全. R0 阶段不引入并发.

## 6. Storage 路径

| 文件 | 格式 | 大小估计 (90 cells smoke) |
|---|---|---|
| pool_snapshots.jsonl | jsonl | 15 records × 200B = 3KB |
| quote_snapshots.jsonl | jsonl | 90 records × 300B = 27KB |
| fee_velocity.jsonl | jsonl | 15 records × 200B = 3KB |
| liquidity_distribution.jsonl | jsonl | 15 records × 200B = 3KB |
| market_regime.jsonl | jsonl | 1 record × 200B = 200B |
| smoke_summary.json | json | 1KB |
| research.sqlite | sqlite | 50KB |

7d / 14d / 30d long-running (后续 R0 阶段, 不在本任务):
- pool_snapshots: 5 × 3 × 720 = 10800 records (10MB)
- quote_snapshots: 5 × 3 × 6 × 720 = 64800 records (20MB)
- 长期 sqlite 可能到 100MB+ → 月度 archive

## 7. Safety guard 实现要点 (in code)

1. `mode != "design" and mode != "smoke"` → `raise SystemExit("invalid mode")`
2. 任何匹配 `private_key|mnemonic|seed|keypair` 的 import / arg → `raise SystemExit`
3. 任何匹配 `sendTransaction|signTransaction|Keypair\.from|add_liquidity|remove_liquidity|swap|collect_fee|approve` 的 method call → `raise SystemExit`
4. 写路径必须以 `data/lp_long_horizon/` 开头, 其它路径 → `raise SystemExit`
5. `--mode daemon|30d|long|loop|cron|continuous` 全部 hard-reject

## 8. 与已有 connector 的关系

5 个 protocol connector (Meteora DLMM / Orca Whirlpools / Raydium CLMM / Raydium CPMM /
Meteora Stable + Orca LST) 已经在上一阶段 060659 验证:
- SDK decode path 100% 通
- on-chain verify executable
- 25-75 个 verify pool per protocol

collector 复用这些 connector 的 read-only SDK 入口, 但**不**调用任何 mutation method.
SDK 中 mutation method (add_liquidity, remove_liquidity, swap, collect_fee) 在 import 时
显式 monkey-patch 抛 `NotImplementedError`, 由 safety guard 验证.

## 9. 不在本任务范围

- 实际长期跑 (cron / systemd / while-true) — R0 阶段后续, 单独人工批准
- 任何 paid indexer / paid RPC — R0 阶段后续
- 任何 protocol 重新连接 (5 connector 已 verify, 复用即可)
- 任何 heuristic 改动
- 任何 R1 (actual fee accrual) 实际抓取
- 任何 R2 (regime split) 实际跑
- 任何 R3 (incentive / vault) 候选 review
- 任何 R4 (10U tokenId probe) preflight
- 任何 R5 (manual probe) 实际跑

## 10. 结论

- 架构 5 层: design / smoke mode / safety guard / source adapter / storage layer
- 强制 read-only, default design mode
- smoke 1 pass 90 cells, 不 daemon
- 长期运行必须单独 stage + 单独审计 + 单独人工批准
- storage 本地化, 不写 production db
- safety guard 在代码 + pytest 双重验证
