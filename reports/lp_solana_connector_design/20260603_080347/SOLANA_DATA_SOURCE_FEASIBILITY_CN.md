# Solana 数据源可行性设计 — Stage D

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`

## 0. 设计原则

1. **只用 public RPC**（`api.mainnet-beta.solana.com` 或 `solana.publicnode.com`）；不依赖任何 private RPC
2. **不**接 wallet / 不读 keypair / 不签名 / 不发 tx
3. **read-only RPC methods only** — `getAccountInfo`, `getProgramAccounts`, `getSignaturesForAddress`, `getTransaction`, `getTokenLargestAccounts`, `getTokenAccountBalance`, `getMultipleAccounts`, `simulateTransaction`
4. 任何 indexer / API 接入都标 "read-only"; 不写

## 1. RPC methods 详细

| method | params | 用法 | read-only |
|---|---|---|---|
| `getAccountInfo` | pubkey, encoding=base64 | 读 single account (pool state, position state) | ✅ |
| `getProgramAccounts` | program_id, filters=[{dataSize, memcmp}] | 枚举某 program 下所有 accounts (discovery) | ✅ |
| `getMultipleAccounts` | [pubkeys] | 批量读 multiple accounts (高效) | ✅ |
| `getSignaturesForAddress` | pubkey, limit=N, before=signature | 读某 account 的最近 signatures (lifecycle events) | ✅ |
| `getTransaction` | signature, encoding=json | 读 single transaction (parse for swap events) | ✅ |
| `getTokenLargestAccounts` | mint | 读某 SPL token mint 的 largest holders | ✅ |
| `getTokenAccountBalance` | pubkey | 读 SPL token account 余额 | ✅ |
| `getTokenSupply` | mint | 读 SPL token mint supply | ✅ |
| `getSlot` / `getBlockHeight` | - | 链状态 | ✅ |
| `simulateTransaction` | base64 tx | simulate (不签名不发送) | ✅ |

### 1.1 getProgramAccounts 的限制与方案

`getProgramAccounts` 是关键 discovery 入口；但有 rate limit 风险：
- 公共 RPC 通常 100 req/min (Helius) 或 40 req/min (公共)
- 一次 getProgramAccounts 拉到 ~5-50 MB 数据（取决于 program）
- **必须用 memcmp filter + dataSize 限制**：

```json
{
  "program_id": "Meteora DLMM program",
  "filters": [
    {"dataSize": <expected LbPair size>},
    {"memcmp": {"offset": <token_x_offset>, "bytes": "<base58 token_mint>"}}
  ]
}
```

## 2. Indexer / API

### 2.1 Meteora

- **Meteora DLMM API** (https://dlmm-api.meteora.ag) — REST API, returns pool metadata, fee info, TVL
  - endpoints: `/pair/all`, `/pair/{address}`, etc.
  - **完全 read-only**; HTTP GET
- **Meteora DAMM v2 API** (https://dammv2-api.meteora.ag) — same pattern
- **Meteora SDK** (TypeScript / Rust) — wraps RPC + decoding; not a separate service

### 2.2 Orca

- **Orca Whirlpools SDK** (TypeScript) — wraps RPC
- 没有 public REST API; 主要靠 RPC + SDK
- Account layout public on Orca docs

### 2.3 Raydium

- **Raydium SDK** (TypeScript) — wraps RPC
- **Raydium CLMM API** (https://api.raydium.io/v2/...) — pool metadata, TVL
- **Raydium CPMM API** — same pattern

### 2.4 Jupiter (price/route reference)

- **Jupiter Quote API** (https://quote-api.jup.ag/v6/quote) — REST GET; returns best route for input/output mint + amount
  - **read-only**; **NOT** for actual swap; just price/route reference
  - 用于 Solana survival EV 模型的 quote_10u / quote_20u 字段

### 2.5 Birdeye / DexScreener / GeckoTerminal (optional)

- Birdeye API (key required for high rate limit) — price + liquidity snapshot
- DexScreener (no key) — popular pair info
- GeckoTerminal (no key) — pool metadata
- **本阶段**不强制接; 留 v2 选

## 3. Rate limits

| provider | rate limit | 备注 |
|---|---|---|
| api.mainnet-beta.solana.com | ~40 req/10s per IP | 适合 low-volume |
| solana.publicnode.com | ~50 req/10s per IP | 略快 |
| Helius (free tier) | 50 req/s | 需要 API key (不推荐) |
| Triton (free tier) | 25 req/s | 需要 API key |
| dlmm-api.meteora.ag | ~60 req/min unauthenticated | 可用 |
| quote-api.jup.ag | ~10 req/s unauthenticated | 可用 |

### 3.1 缓存策略

- **必须**在 connector 内部维护 24h rolling cache：
  - pool metadata: TTL 1h
  - bin/tick state: TTL 30s (但 getProgramAccounts 不要每 30s 跑)
  - fee velocity: TTL 1h
  - quote snapshot: TTL 30s
- 一次 discovery 完整 scan ~5-10 MB data; 缓存到本地 JSONL; 后续阶段读 cache

## 4. Required tables (read-only; 写到本地 JSONL / CSV)

```text
solana_lp_pool_universe_v1
  - chain ("solana")
  - protocol (Meteora DLMM / Meteora DAMM v2 / Orca Whirlpools / Raydium CLMM / Raydium CPMM)
  - pool_address (base58)
  - token_a_mint, token_b_mint (base58)
  - token_a_symbol, token_b_symbol
  - pool_type
  - discovered_at_iso, last_seen_iso
  - pool_metadata (raw account, base64)

solana_lp_pool_metadata_v1
  - pool_address
  - protocol
  - fee_bps
  - dynamic_fee_supported (bool)
  - bin_step (DLMM only) / tick_spacing (CLMM only)
  - token_a_decimals, token_b_decimals
  - token_a_vault, token_b_vault
  - quote_token (USDC / USDT / SOL)
  - initializable (bool)
  - last_updated_iso

solana_lp_liquidity_snapshot_v1
  - pool_address
  - snapshot_at_iso
  - active_bin (DLMM) / current_tick (CLMM)
  - bin_array / tick_array (DLMM / CLMM 各自)
  - liquidity
  - bin_liquidity_distribution (DLMM: per-bin Q64.64 amounts)

solana_lp_fee_velocity_v1
  - pool_address
  - window (24h / 7d)
  - volume_usd_proxy
  - fee_usd_proxy
  - fee_apr_proxy
  - swap_count
  - last_updated_iso

solana_lp_quote_snapshot_v1
  - pool_address
  - quote_at_iso
  - notional_usd (10/20/100/...)
  - amount_in_token (raw)
  - amount_out_token (raw)
  - price_impact_pct
  - quote_source (jupiter / protocol_native)

solana_lp_virtual_position_preview_v1
  - pool_address
  - virtual_at_iso
  - bin_range (DLMM) / tick_range (CLMM)
  - virtual_liquidity
  - expected_fee_24h_usd
  - expected_il_24h_pct
  - expected_net_ev_24h_usd
  - confidence

solana_lp_probe_preflight_v1
  - probe_at_iso
  - pool_address
  - notional_usd
  - hold_window
  - balance_check (read-only via getBalance)
  - ata_readiness_check (read-only via getAccountInfo)
  - rent_required_sol
  - expected_tx_fee_sol
  - expected_priority_fee_sol
  - simulated_open_tx
  - simulated_close_tx
  - preflight_pass (yes / no / warn)
  - blocker (string)
```

## 5. 钱包 / private key 要求

**NONE**。本阶段所有 read-only RPC + REST API 都不需要 wallet / private key。

唯一需要 wallet 的地方（**未来阶段** `LP_SOLANA_10_20U_PROBE_PREFLIGHT_REVIEW_V1` 之后的 actual execution 阶段）：
- balance check: `getBalance(wallet_pubkey)` ← read-only
- ATA existence: `getAccountInfo(ata_pubkey)` ← read-only
- simulate open tx: `simulateTransaction(base64_unsigned_tx)` ← read-only (不签名)
- 真正 open / close: 需要 signer (本阶段**不**涉及)

## 6. 不在本阶段做

- ❌ 实际写任何 connector Python 代码
- ❌ 实际跑 Solana RPC (本阶段是 design only)
- ❌ 引入 solana-py / solders / pyserum 依赖 (本阶段不安装)
- ❌ 接任何 paid RPC
- ❌ 接任何 wallet

## 7. 已知缺口

- **Meteora DLMM account layout** — 完整字段需要 on-chain inspection; 公开 SDK 闭源 / 仅有 IDL
- **Orca Whirlpools tick array layout** — 公开 IDL; 但具体 bit offset 需要实测
- **Jupiter quote API** — 偶尔 rate limit; v1 不依赖
- **indexer** — 没有任何 subgraphs-like 服务; 只能 raw RPC + cache

## 8. 安全断言

```text
this_stage_only_design                   = true
this_stage_does_not_run_rpc              = true
this_stage_does_not_read_keypair         = true
this_stage_does_not_sign                 = true
this_stage_does_not_send_tx              = true
solana_wallet_or_keypair_touched         = false
can_run_probe_now                        = false
```
