# Orca Whirlpool Connector Design — Stage F

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`

## 0. 为什么选 Orca Whirlpools 作为 P1

| 维度 | 评价 |
|---|---|
| Solana CLMM 标杆 | Whirlpools 是 Solana 上最成熟的 CL venue; 公开 SDK; account layout 公开 |
| V3-like math | sqrt_price + tick + liquidity; 已熟悉 |
| Position model | NFT (mint); 可序列化 |
| fee velocity | SOL/USDC, ORCA/USDC 等主流 pair typical 25-60% APR proxy (per upstream benchmark) |
| documentation | 公开 SDK + 公开 IDL; TypeScript SDK 维护 |
| complexity | medium (V3-like) |

## 1. pool discovery

```python
# pseudo
program_id = "Whirlpools program pubkey"  # need to look up
filters = [
  { dataSize: <Whirlpool exact size> },  # ~ 800 bytes
  # optional: filter by token mint via memcmp
]
accounts = await solanaRpc.getProgramAccounts(programId, filters)
```

## 2. tick array

- Orca Whirlpools 把 tick 切成 TickArray，每个 TickArray 包含 N (e.g. 88) 个 tick
- TickArray 是 PDA: `[whirlpool_pubkey, start_tick_index]`
- discovery: 不需要枚举所有 TickArray；只读 current tick 附近 ±N 个

```python
current_tick = whirlpool.tick_current_index
tick_array_start = (current_tick // TICK_SIZE) * TICK_SIZE  # TICK_SIZE = 88
tick_array_pda = derive_tick_array_pda(whirlpool_pubkey, tick_array_start)
```

## 3. current tick / liquidity / fee growth

- `whirlpool.tick_current_index` — 当前 tick
- `whirlpool.liquidity` — 当前 active liquidity (Q64.64)
- `whirlpool.fee_growth_global_x` / `fee_growth_global_y` — 累计 fee growth (Q64.64)
- per-position fee owed = `fee_growth_inside_last - position.fee_growth_inside_checkpoint`

## 4. position NFT / position account

- Position 是 NFT (mint)
- Position account 包含: `position_mint`, `position_index_in_bundle`, `whirlpool`, `tick_lower_index`, `tick_upper_index`, `liquidity`, `fee_growth_inside_last`
- Position account 是 PDA from `[whirlpool, position_mint]`

## 5. token vaults

- 每个 Whirlpool 有 `token_vault_a` 和 `token_vault_b` (SPL token accounts)
- Vault 持有 LP 资金

## 6. quote model

- Whirlpool 公开 quote function: `whirlpool.swap_quote(...)` (off-chain 或 on-chain simulate)
- output: `amount_out`, `cross_tick_upper`, `cross_tick_lower`, `fee_amount`
- read-only: 通过 `simulateTransaction(swapTx)` 模拟

## 7. fee accrual

- read `position.fee_owed_a` / `position.fee_owed_b` (SPL token amount)
- collectFees 时: `fee_owed` 转给 owner; 累计 `fee_growth_inside_last` 更新

## 8. exit model

- decreaseLiquidity: 移除 liquidity → token_a / token_b 转入 position owner
- collectFees: claim 累计 fees
- closePosition: burn position NFT; 关闭 position account; 回收部分 rent

## 9. 10/20U probe preflight requirements

```text
- balance_check: getBalance(wallet) >= 1.5 SOL (covers rent + tx + slippage)
- token_balance: USDC >= 10 + slippage
- ata_readiness: getAccountInfo(ata_usdc) existence
- pool_metadata: cached; current_tick, fee_rate known
- tick_range_decision: based on volatility forecast (heuristic)
- deposit_quote: simulateTransaction(removeLiquidityTx) returns 10U + 0.5U slippage OK
- exit_quote: simulateTransaction returns 9.5-11U OK
- expected_fee_24h: >= 0.05 USDC (heuristic)
- expected_il_24h: <= 0.10 USDC
- preflight_pass: all above
```

## 10. complexity / blocker

| 维度 | 评价 |
|---|---|
| SDK 公开 | @orca-so/whirlpools-sdk |
| Account layout 公开 | IDL 在 Orca GitHub |
| Public RPC 限制 | getProgramAccounts 范围过滤; 大程序有 rate limit |
| TickArray 解析 | 需自己实现 (SDK 闭源 binary) |
| Quote | 公开 quote function; 可通过 simulateTransaction |
| Rent | position account + token vault (LP 持有) + 2 ATA |
| NFT 成本 | NFT mint ~0.001 SOL + ~0.002 SOL rent (NFTs 不回收) |
| 整体 cost | $0.005-0.008 round trip (vs Meteora $0.003, V3 $0.012) |

## 11. 不在本阶段做

- ❌ 实际写 connector 代码
- ❌ 跑 RPC
- ❌ 接 wallet
- ❌ 准备 SOL/USDC 资金

## 12. 与 Meteora DLMM 对比

| 维度 | Meteora DLMM | Orca Whirlpools |
|---|---|---|
| IL 控制 | 0 IL inside chosen bin range; binary | gradual IL (V3-like) inside tick range |
| fee velocity | 30-100% APR proxy (volatile pair) | 25-60% APR proxy |
| position cost | position PDA → closeable → rent 回收 | NFT mint → 不回收 (NFT 模型) |
| round trip cost | ~$0.003 | ~$0.005-0.008 |
| SDK | TypeScript; closed source binary | TypeScript; IDL 公开 |
| 适合 probe | **更好** (low cost + IL control) | 较好 (V3-like familiarity) |

**结论**: P0 应该仍是 Meteora DLMM; Orca Whirlpools 是 P1 backup; 同样支持 P1 的 Meteora DAMM v2 也是 backup。
