# Raydium Connector Design — Stage G

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`

## 0. 范围

| 子协议 | 优先级 | 备注 |
|---|---|---|
| Raydium CLMM | **P2** | 与 Orca Whirlpools 类似；fee 通常略低 |
| Raydium CPMM | **P2** | constant product；stable-stable 路径 |

## 1. Raydium CLMM

### 1.1 pool discovery

```python
# pseudo
program_id = "Raydium CLMM program pubkey"  # need to look up
filters = [
  { dataSize: <PoolState exact size> },
  # optional: memcmp by token mint
]
accounts = await solanaRpc.getProgramAccounts(programId, filters)
```

### 1.2 pool state

```rust
struct PoolState {
    amm_config: Pubkey,
    pool_creator: Pubkey,
    token_mint_0: Pubkey,
    token_mint_1: Pubkey,
    token_vault_0: Pubkey,
    token_vault_1: Pubkey,
    observation_key: Pubkey,
    tick_current: i32,
    tick_spacing: u16,
    liquidity: u128,    // Q64.64
    sqrt_price_x64: u128,  // Q64.64
    fee_growth_global_0: u128,
    fee_growth_global_1: u128,
    // ...
}
```

### 1.3 liquidity / quote / fee

- liquidity: Q64.64 (Q64.64 same as V3)
- sqrt_price_x64: Q64.64
- tick array: 类似 Orca; TickArrayState contains N (60) 个 ticks
- fee: `pool.fee_rate` (per amm_config tier)
- position model: position NFT (类似 Orca)
- quote: simulateTransaction on swap tx
- fee accrual: position.fee_owed_0 / position.fee_owed_1 (direct read)

### 1.4 适合 first connector 吗？

**NO** — Orca Whirlpools 优先 (公开 SDK 更好, IDL 完整, fee velocity 略高)。

## 2. Raydium CPMM

### 2.1 pool discovery

```python
# pseudo
program_id = "Raydium CPMM program pubkey"
filters = [{ dataSize: <PoolInfo exact size> }]
accounts = await solanaRpc.getProgramAccounts(programId, filters)
```

### 2.2 pool state (constant product)

```rust
struct PoolInfo {
    base_mint: Pubkey,
    quote_mint: Pubkey,
    base_vault: Pubkey,
    quote_vault: Pubkey,
    base_reserve: u64,
    quote_reserve: u64,
    fee_rate: u16,  // bps; e.g. 25
    // ...
}
```

### 2.3 liquidity / quote / fee

- liquidity: reserve_a, reserve_b (constant product)
- quote: simulateTransaction on swap tx; x*y=k formula
- fee: pool.fee_rate (e.g. 25 bps)
- position model: **LP token mint** (持有 LP token; balance 增长 = fee 累积)
- exit: burn LP token to withdraw proportional reserves

### 2.4 适合 first connector 吗？

**NO** — 适合 stable-stable; 但 fee 比 V3 简单池还低; 不是 10/20U probe 高 EV 候选.

## 3. fee model / position model / exit

| 维度 | Raydium CLMM | Raydium CPMM |
|---|---|---|
| fee | tiered per amm_config; typically 0.05-1% | flat (e.g. 25 bps) |
| position model | NFT mint | LP token mint |
| IL | V3-like (gradual) | constant product (fixed) |
| fee accrual | position.fee_owed_0/1 | LP token balance growth |
| exit | decreaseLiquidity + collectFees | burn LP token |
| rent recovery | position account + NFT mint (NFT not recoverable) | LP token + 2 ATA |

## 4. blockers

- **CLMM**: SDK 公开但 IDL 复杂; getProgramAccounts 数据量大; 与 Orca 重复
- **CPMM**: 简单但 fee 低; 适合 stable-stable; 不是 10/20U probe 高 EV 候选

## 5. 不在本阶段做

- ❌ 实际写 connector 代码
- ❌ 跑 RPC
- ❌ 接 wallet
- ❌ 准备资金
- ❌ 任何交易

## 6. 建议

- **P2 优先级**：Meteora DLMM (P0) > Orca Whirlpools (P1) > Meteora DAMM v2 (P1) > Raydium CLMM (P2) > Raydium CPMM (P2) > Lifinity (P2 future)
- **先 P0 Meteora DLMM connector**；DAMM v2 共用 Meteora SDK; Orca CLMM 第二波
- **Raydium 留 v2 阶段** 或 实际 fee velocity 数据显示 Orca 不足时再上
