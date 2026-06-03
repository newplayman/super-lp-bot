# Meteora DLMM Connector Design — Stage E

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`

## 0. 为什么 Meteora DLMM 可能比 EVM V3 更适合

| 维度 | EVM V3 (Base) | Meteora DLMM (Solana) |
|---|---|---|
| **LP 暴露控制** | tick range; 但 V3 流动性沿 price 分布，边缘 IL 仍存在 | **bin 离散化**; LP 可选 narrow 几个 bin = 完全控制 IL |
| **bin step 灵活性** | 固定 tick spacing (10/60/200) | **bin_step 可配**; 主流 pair 1-20 bps |
| **fee** | tiered (0.01/0.05/0.30/1.00%) + tier 0.01% | base_fee_bps (1-20 bps) + **dynamic_fee** (per bin, vol-based) |
| **fee velocity** | Base Uniswap V3: ~20% APR proxy | Meteora DLMM SOL/USDC: 30-100% APR proxy (volatile pair 更高) |
| **cost structure** | EVM gas ($0.01-0.10 per open) | Solana rent+tx ($0.002-0.005 per open) |
| **position model** | NFT (token id) | position account (PDA) → closeable → rent 回收 |
| **fee accrual** | transfer event 读; 复杂 | position 状态内 unclaimedFees 直接读 |
| **bin liquidity** | uniform per tick | **per-bin** (Q64.64 amount) — 更细粒度 |
| **routing** | V3 single pool | Meteora bin-step routing 自动优化 |

**关键差异**：
1. **IL 完全可控** — 选择 narrow bin range = 当 price 出 range 立刻 0 fee + 0 IL 暴露；可主动控制 IL 而非被动承担
2. **dynamic fee** — 主流 pair 在 volatile 时 fee 自动调高 (5-50 bps)；LP 收入在 volatile 时是 V3 的 3-10x
3. **cost 极低** — Solana rent + tx fee 远低于 EVM Base L2

## 1. pool discovery

### 1.1 入口

```typescript
// pseudo
const programId = "Meteora DLMM program pubkey";  // need to look up
const filters = [
  { dataSize: <expected LbPair size> },           // exact size filter
  // optional: filter by token mint
  // { memcmp: { offset: <token_x_offset>, bytes: "<base58 token_mint>" } }
];
const accounts = await solanaRpc.getProgramAccounts(programId, filters);
```

### 1.2 解析 LbPair state

LbPair state struct (示意, need exact layout from Meteora SDK / IDL):

```rust
struct LbPair {
    parameters: StaticParameters,
    vault_token_x: Pubkey,           // token X vault
    vault_token_y: Pubkey,           // token Y vault
    oracle: Pubkey,
    mint_x: Pubkey,                  // token X mint
    mint_y: Pubkey,                  // token Y mint
    bin_step: u16,                   // bin step in bps
    active_id: i32,                  // current active bin
    bin_array_bitmap: [u64; 16],     // bin array existence bitmap
    // ...
}
```

### 1.3 active bin / bin step / token mints

- `active_id` = 当前 price 落在哪个 bin
- `bin_step` (bps) = 每个 bin 的宽度
- `mint_x`, `mint_y` = SPL token mints
- bin step × active_id → 推算当前 price

## 2. pair discovery

每条主流 pair 至少查：

| 优先级 | pair | 备注 |
|---|---|---|
| 1 | SOL/USDC | 高 fee velocity |
| 2 | SOL/USDT | 主流 stable |
| 3 | USDC/USDT | 稳定-稳定；low IL；fee 低 |
| 4 | JitoSOL/SOL | LST 路径 |
| 5 | jupSOL/SOL | LST 路径 |
| 6 | BONK/SOL | meme 高 vol |
| 7 | WIF/SOL | meme 高 vol |
| 8 | PYTH/USDC | oracle token |

## 3. active bin / bin liquidity / bin step

```python
# pseudo (read-only)
def get_active_bin_and_step(lb_pair_state):
    return {
        "active_id": lb_pair_state.active_id,
        "bin_step_bps": lb_pair_state.bin_step,
        "min_price": price_from_bin_id(active_id - 1, bin_step),
        "max_price": price_from_bin_id(active_id + 1, bin_step),
    }

def get_bin_liquidity(lb_pair_pubkey, active_id, num_bins_each_side=10):
    # need to load BinArray accounts
    bin_array_idx = active_id // BIN_ARRAY_SIZE  # BIN_ARRAY_SIZE = 256 typically
    bin_arrays = get_multiple_accounts([
        derive_bin_array_pda(lb_pair_pubkey, bin_array_idx - 1),
        derive_bin_array_pda(lb_pair_pubkey, bin_array_idx),
        derive_bin_array_pda(lb_pair_pubkey, bin_array_idx + 1),
    ])
    return parse_bin_liquidity_distribution(bin_arrays, active_id, num_bins_each_side)
```

## 4. fee parameters

- `base_fee_bps` (静态)
- `dynamic_fee` (per bin, 公式: `dynamic_fee = base_factor * volatility`)
- volatility 由 oracle 提供
- LP 实际 fee 收入 = base_fee × volume + dynamic_fee × volume

## 5. dynamic fee / base fee

- base_fee_bps: 1-20 bps; 不同 pool 不同
- dynamic_fee: 计算公式由 Meteora 公开
  - 简易: `dynamic_fee = base_factor * (volatility / reference_volatility) * bin_step`
- LP fee APR 实际 = `sum(base_fee + dynamic_fee) * 24h_volume / TVL`

## 6. position range / bins

- LP 选 bin range [lower_bin_id, upper_bin_id]
- 包含 active bin → 0 IL until price exits range
- 范围越窄 → 流动性越集中 → 更高 fee per volume
- 范围越宽 → 越像 full-range → 接近 constant product

## 7. deposit token ratio

- 当 deposit 时，按当前 price 决定 X/Y token 比例
- 算法: `amount_y = amount_x * price_in_bin_id(active_id, lower, upper)`
- Meteora SDK 提供 `getDepositQuote` 函数（read-only 模拟）

## 8. fee accrual model

- position account state 包含 `unclaimedFeesX` 和 `unclaimedFeesY`
- read: `position.unclaimedFeesX` / `position.unclaimedFeesY` (raw amounts)
- 不需要事件 log; 直接 read state

## 9. exit quote model

- removeLiquidity 时: SDK 返回 amount_x + amount_y + fees
- read-only 模拟: `simulateTransaction(removeLiquidityTx)` → return amounts

## 10. IL exposure control

- 选 narrow bin range → 高 fee 倍数，但 price 离开 range 立刻 0 fee
- 选 wide bin range → 低 fee 倍数，但 price 离开 range 概率低
- 0 IL 直到 price 出 range (vs V3 渐变 IL)

## 11. 10/20U probe preflight requirements

```text
- balance_check: getBalance(wallet) >= 2.0 SOL (covers rent + tx + slippage)
- token_balance: USDC >= 10 + slippage (10-20 USDC)
- ata_readiness: getAccountInfo(ata_usdc) != null OR expected creation fee reserved
- pool_metadata: cached; bin_step, active_id known
- bin_range_decision: based on volatility forecast (heuristic)
- deposit_quote: simulateTransaction returns 10U + 0.5U slippage acceptable
- exit_quote: simulateTransaction returns 9.5-11U acceptable
- expected_fee_24h: >= 0.05 USDC (heuristic threshold)
- expected_il_24h: <= 0.10 USDC
- preflight_pass: all above
```

## 12. required account decoding

- LbPair state (size ~ 900 bytes typically)
- BinArray state (size ~ 8000 bytes; 256 bins × 32 bytes)
- Position state (size ~ 250 bytes)
- Token vault accounts (read via getTokenAccountBalance)

## 13. required SDK or raw account parser

### 13.1 raw account parser (recommended for Python)

```python
# pseudo
def parse_lb_pair(base64_data: str) -> dict:
    # need to know exact offset for each field
    # best path: pull from Meteora IDL if public, else iterate + on-chain test
    ...
```

### 13.2 SDK option (TypeScript)

- `@meteora-ag/dlmm` package
- Wraps RPC + decoder + simulate
- Python can call via JSON-RPC to a small Node.js helper, or do raw parsing

## 14. data confidence

- on-chain decoded: high (if account layout 正确)
- dynamic fee: medium (公式反推需要 calibration)
- volume / fee velocity: medium (依赖 Jupiter 或 Birdeye 或 on-chain decoded swap events)
- IL 24h: low-medium (heuristic based on price range × volatility)

## 15. 为什么 Meteora DLMM 可能比 EVM V3 更适合（综合）

1. **bin/range 完全可控** → IL 风险从 "V3 gradual" 变为 "binary" → risk 0 until exit
2. **active liquidity 精打细算** → 每 bin 一个 Q64.64 amount，LP 完全知道 exposure
3. **higher fee velocity** → Meteora DLMM 在 SOL/USDC 上 typical 30-100% APR proxy
4. **lower cost structure** → Solana rent + tx ~$0.003 round trip vs EVM Base $0.012
5. **可回收 rent** → close position 时回收 ~0.0014 SOL

**但**需要新 connector + 实际 fee/account parser + bin math 复杂；不能直接套 EVM V3 model。

## 16. 不在本阶段做

- ❌ 实际写 connector 代码
- ❌ 跑任何 RPC
- ❌ 接 wallet
- ❌ 准备 SOL/USDC 资金
- ❌ 任何交易
