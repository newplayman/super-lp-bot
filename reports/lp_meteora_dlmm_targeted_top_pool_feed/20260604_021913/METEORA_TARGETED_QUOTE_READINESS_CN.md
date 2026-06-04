# Meteora Targeted Quote Readiness — Stage G

- stage: `LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1`
- run_id: `20260604_021913`

## 0. 关键结果 (本轮 vs 上一轮)

| 维度 | 上一轮 (50 candidates, 16 verified) | 本轮 (60 candidates, 56 verified, 27 quote-eligible) |
|---|---|---|
| quote_ready_pool_count | **0** | **27** ✓ |
| quote_10u_success_count | 0 | 27 |
| quote_20u_success_count | 0 | 27 |
| high_fee_quote_ready_count (base>=50bps OR max>=2000bps) | 0 | 4 |
| no_liquidity_near_active_count | 16 (100%) | **0** ✓ |

**结构性突破**: 上一轮 16 池 active bin ±10% 范围 0 bins with liquidity，本轮 27 池 active bin 附近 28–242 bins with liquidity。**关键差别**: 上一轮是 random/known pool feed (low-fee, SOL/USDC 类 bin_step=2)，本轮是 targeted high-volume 池 (base_fee 20–100bps, bin_step 20–100, 主流 + memecoin)。

## 1. 关键发现

### 1.1 Path 走通 (V8)

- `getBinArrayKeysCoverage(lower, upper, lbPair, programId)` 返回确定性 pubkey 数组 (不需要 GPA)
- `getMultipleAccountsInfo` 一次拿 5 个 bin array
- `DLMM.decodeAccount(program, "binArray", buffer)` 解码出 BinArray shape
- `pool.swapQuote(inAmount, swapForY, slippage, binArrays, isPartialFill, maxExtra)` 出 quote
- SwapQuote 字段: `outAmount`, `fee`, `protocolFee`, `minOutAmount`, `priceImpact`, `endPrice`, `binArraysPubkey`

### 1.2 真实 quote 数据 (top 4 high-fee)

| pool | base/max (bps) | bin_step | 10u in (raw) | 10u out | 10u fee | 20u out | 20u fee |
|---|---|---|---|---|---|---|---|
| `CnK82s8exdsK` (three/SOL) | 100/1000 | 80 | 7.69e7 lamports | 7,433,895 | 692,308 | 14,867,791 | 1,384,616 |
| `9bL8Pptpb8M2` (GACHA/SOL) | 100/1000 | 100 | 1.0e7 | 850,368 | 21,137 | 1,700,736 | 42,273 |
| `HuPRxaBcjQYr` (MET/USDC) | 100/1000 | 80 | 1.0e7 | 1,188,853 | 90,108 | 2,377,707 | 180,216 |
| `9uTgLv3Ya7sr` (three/SOL) | 50/1000 | 50 | 7.69e7 | 7,526,657 | 355,491 | 15,053,314 | 710,981 |

**fee 10u 在 1.8e4–6.9e5 raw 之间**。换算 USD:
- `CnK82s8exdsK` (3池中 fee 最高): 10u SOL in, fee 692,308 lamports ≈ $0.0053 USD (按 130 USD/SOL)
- `HuPRxaBcjQYr` (MET/USDC): 10u USDC in, fee 90,108 raw ≈ $0.0901 USD
- `9uTgLv3Ya7sr`: 10u SOL in, fee 355,491 lamports ≈ $0.00273 USD
- `6qz7THwQvcjF` (BP/USDC): 10u USDC in, fee 23,301 raw ≈ $0.0233 USD

**max_fee_bps = 1000 (10%) for ALL 56 pools** — Meteora DLMM 硬上限。base_fee 5/50/100 bps (0.05%–1%) 远低于 5% 阈值。

## 2. 27 池 quote 全部成功明细 (sorted by base_fee desc)

(完整见 `meteora_targeted_quote_readiness.csv`)

## 3. 4 池 high_fee_quote_ready (base>=50bps OR max>=2000bps)

```text
CnK82s8exdsK   base=100 max=1000 bin=80 (three/SOL)      bins_with_liq=195
9bL8Pptpb8M2   base=100 max=1000 bin=100 (GACHA/SOL)     bins_with_liq=76
HuPRxaBcjQYr   base=100 max=1000 bin=80 (MET/USDC)       bins_with_liq=107
9uTgLv3Ya7sr   base=50  max=1000 bin=50 (three/SOL)      bins_with_liq=165
```

**注意**: max_fee=1000bps=10% 仅是 dynamic peak，不是 static base。base_fee 1% 是 Meteora DLMM 当前最现实的"高费率"边界。

## 4. 安全断言

```text
this_stage_only_quote        = true
this_stage_no_tx             = true
this_stage_no_keypair        = true
this_stage_no_signer         = true
solana_wallet_or_keypair_touched = false
transaction_sent             = false
can_run_probe_now            = false
```

## 5. 下一阶段

进入 Stage H — survival EV preview 在 27 池上跑完整 grid (6 notionals × 7 hold × 4 scenario = 168 cells per pool = 4536 cells total)。
