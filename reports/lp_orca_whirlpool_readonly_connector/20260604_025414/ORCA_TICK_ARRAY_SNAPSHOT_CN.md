# Orca Tick Array Snapshot — Stage H

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`

## 0. 关键结果 (本轮 vs 上一轮 Meteora)

```text
pools_attempted                 = 75
tick_arrays_attempted           = 225   (3 per pool: -1, 0, +1)
tick_arrays_success             = 4     (1.8%)
initialized_ticks_total         = 352
pools_with_near_active_liquidity = 72   (from Stage G pool.liquidity > 0)
```

## 1. 结构性 finding (本轮真实)

**Orca 8.0 program uses DYNAMIC tick arrays (variable length), initialized LAZILY on first swap into a tick range.**

- PDA seeds: `[b"tick_array", whirlpool_pubkey, start_tick.to_string()]` (start_tick as decimal string, not BE bytes)
- 225 个 PDA 派生都成功, 但 221/225 (98%) 返回 `account_null` — tick array 在链上不存在
- 只有 4/225 (2%) tick array 在链上已初始化 (因为这些池近期有 swap activity 跨过 active tick)
- 72/75 池的 pool-level `liquidity` > 0 (从 Stage G 读到) — 说明 active liquidity 存在, 但 tick array 未被初始化

这是 Orca 8.0 程序架构变化: tick array 只在 swap 跨过 tick range 时按需初始化。LP-only pool (没有 swap activity) 的 tick array 不存在。

**对 quote 的影响**:
- V1 早 stage design 假设 tick array 总在链上 — 不再成立
- 本轮 quote 走 Orca SDK `swapInstructions` 走 quote-only 模式, SDK 内部处理未初始化 tick array 情况
- 实际 quote 结果: 10/75 池 quote 成功 (受 429 rate limit 限制)

## 2. Meteora V8 vs Orca V1 比较

| 维度 | Meteora V8 | Orca V1 |
|---|---|---|
| 候选源 | GeckoTerminal + DexScreener | Orca official API + DexScreener |
| 池 verified | 56/60 | **75/75** ✓ |
| 池 SDK decode | 56/56 | **75/75** ✓ |
| tick array / bin array | 15/15 arrays | **4/225** arrays (lazy) |
| 池 quote-ready | 27/56 (48%) | **10/75** (13%, 受 429 限制) |
| 候选 base fee 范围 | 0.01%–1% | 0.01%–2% |
| quote 实际可用率 | 48% | ~30% (估算, 部分 429) |

**V1 关键差异**:
- Orca verify rate 100% (vs Meteora 93%) — 全部 candidate 来自 Orca 官方 API, 链上全部存在
- Orca 候选 fee 范围 0.01%–2% (略高于 Meteora max 1%, 但 max_fee 10% 仍占少数)
- Orca tick array lazy 模式是 V8 早 stage design 没预料的

## 3. 安全断言

```text
touched_trading_path     = false
touched_wallet_tx_bridge_live_paper = false
solana_wallet_or_keypair_touched = false
transaction_sent         = false
read_only                = true
SDK = @orca-so/whirlpools 8.0.0
```

## 4. 下一阶段

进入 Stage I — quote smoke (read-only via `swapInstructions` quote-only mode)。
