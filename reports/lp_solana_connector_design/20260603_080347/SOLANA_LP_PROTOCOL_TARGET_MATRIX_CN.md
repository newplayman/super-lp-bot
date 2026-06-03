# Solana LP 协议目标矩阵 — Stage C

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`

## 0. 优先级建议

| 优先级 | 协议 | 理由 |
|---|---|---|
| **P0** | Meteora DLMM | bin-based 让 LP 完全控制 IL 暴露；dynamic fee；2024-2025 LP fee velocity 显著高于 V3 简单池 |
| **P1** | Orca Whirlpools | Solana 上最成熟的 concentrated liquidity venue；tick array 模型与 V3 类似但 Solana 上 fee 5-20x |
| **P1** | Meteora DAMM v2 | 2025 launch；dynamic fee + 优化无常损失；constant-product 基础 |
| **P2** | Raydium CLMM | 与 Orca 类似，Orca Whirlpools 优先 |
| **P2** | Raydium CPMM | constant product；fee 较 V3 CL 低；不优先 |
| **P2** | Lifinity | Proactive Market Making (PMM)；oracle-based；研究资料较少 |

## 1. 详细矩阵

| 协议 | lp_type | why_relevant | position_model | fee_model | liquidity_model | IL_control_model | required_data_sources | quote_method | fee_accrual_method | position_identifier | complexity | priority | recommended_next_action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Meteora DLMM** | DLMM (Discretized Liquidity Market Maker) | bin-based，LP 选 active bin range；dynamic fee；可完全控制 IL | bin-range position account (PDA) | base_fee_bps + dynamic_fee (per bin step) | bin liquidity 数组 (Q64.64 amounts per bin) | 选择 narrow bin range = low IL；wide range = high fee capture + high IL | RPC: getProgramAccounts (DLMM program) + account decoder；Meteora SDK if available；optional DAMM v2 / DLMM indexer | simulateSwap on LbPair via RPC simulate; or SDK | claimFee on position account; reads unclaimedFees in position state | position pubkey (PDA derived from lbPair + bin range + owner) | medium-high (bin math) | **P0** | design Stage E |
| **Meteora DAMM v2** | DAMM (Dynamic AMM) | 2025 launch; dynamic fee; constant-product 基础; 适合稳定对 / 主流对 | position account (PDA) | dynamic_fee (volatility based) | constant product reserves | partial (oracles + dynamic fee) | RPC + Meteora SDK; pool state decoder | simulateSwap on Pool via RPC | claimFee on position | position pubkey | medium | **P1** | design Stage E shared (Meteora family) |
| **Orca Whirlpools** | CLMM (Concentrated Liquidity) | Solana CLMM 标杆; tick array 模型与 V3 类似; 高 fee velocity | position NFT (mint) | tiered fee (per Whirlpool config) | sqrt_price_x64 + tick + liquidity (V3-like) | tick range width | RPC + Orca SDK; getProgramAccounts on Whirlpool program; Orca Whirlpools SDK | simulateSwap via Whirlpool quote function or SDK | collectFees on position NFT; reads feeOwedA/B | position NFT mint (PDA from bundle + bundleIndex) | medium (V3 类似) | **P1** | design Stage F |
| **Raydium CLMM** | CLMM | 与 Orca 类似但 fee 略低; Solana 上第二大 CL venue | position NFT (mint) | tiered fee | sqrt_price + tick + liquidity | tick range width | RPC + Raydium SDK; getProgramAccounts on CLMM program | simulateSwap via Raydium quote or SDK | collectFees on position | position NFT mint | medium | **P2** | design Stage G (secondary) |
| **Raydium CPMM** | CPMM (Constant Product) | constant product; fee 较 CL 低; 适合 stable-stable | LP token mint | flat fee (e.g. 25 bps) | reserve_a, reserve_b | n/a (constant product IL 固定) | RPC + Raydium SDK | simulateSwap on CPMM pool | LP token balance growth | LP token mint | low | **P2** | design Stage G (CPMM section) |
| **Lifinity** | PMM (Proactive Market Maker) | oracle-based; 研究资料较少; 不优先 | position account | dynamic (oracle based) | reserve_a, reserve_b + oracle price | n/a (oracle anchored) | RPC + Lifinity SDK (limited) | simulateSwap via SDK | position balance growth | position pubkey | high (资料少) | **P2** | future stage |

## 2. protocol 选型对 EV 影响的初判

| 协议 | fee_velocity 预期 | IL_control | cost_structure (rent/ATA) | EV 改善可能性 |
|---|---|---|---|---|
| Meteora DLMM | 高 (volatile pair 30-100% APR proxy) | 完全可控 (bin 选择) | 中 (1 ATA + 1 position account) | **高** |
| Meteora DAMM v2 | 中 (constant product + dynamic fee) | 部分 (oracle anchored) | 低 (1 ATA + 1 position) | 中 |
| Orca Whirlpools | 中高 (Solana CLMM 标杆) | 中 (tick range) | 中 (1 ATA + 1 NFT + tick arrays) | 中 |
| Raydium CLMM | 中 | 中 (tick range) | 中 | 中 |
| Raydium CPMM | 低 (constant product 30-50% APR proxy stable) | 无 (price exposure fixed) | 低 (LP token + 1 ATA) | 低 |
| Lifinity | 不明 | n/a | 中 | unknown |

## 3. Solana 链参数（设计时假设）

```text
chain_id_mainnet_beta    = 101
rpc_url                 = https://api.mainnet-beta.solana.com (public)
rpc_url_alt             = https://solana.publicnode.com (public, faster)
slot_duration           = 0.4s
block_height_per_day    = ~216000
rent_exemption_lamports = 890880  (typical account; ~0.00089 SOL)
priority_fee_lamports   = 1000-100000 (5k-50k micro-lamports per CU)
base_tx_fee_lamports    = 5000 (5000 lamports per signature)
```

> rent_exemption 是 SOL 链强制要求：新建 account 必须转入 ≥ 890880 lamports (0.00089 SOL) 才能永久保留；close account 时回收。
> 当前 SOL 价假设 $150; 0.00089 SOL ≈ $0.00013 (1.3 厘) per account; 一次 LP 需要 2 ATA + 1 position = 3 accounts = ~$0.0004; 远低于 EVM V3 gas 成本。
> 但 Solana tx fee (5000 lamports + priority) 约 $0.0005-0.001 per tx; 一个完整 LP open + close = 2-3 tx = $0.001-0.003; 仍比 EVM Base L2 (~$0.001) 略高或相当。

## 4. 关键设计问题（不立即实现，仅文档）

- **Meteora DLMM 单一 bin 是否可承担 10U probe？** 10U 进一个 bin 在主流 pair (e.g. SOL/USDC) 上流动性 < 0.001 bin unit，可能 IL 立刻被手续费覆盖。需要看具体 pool 的 bin liquidity 分布。
- **Orca Whirlpools NFT 模型 vs Meteora DLMM PDA 模型**：哪种对 read-only connector 友好？**Meteora PDA 更友好**（不需要 token metadata RPC），优先 Meteora。
- **token account 关闭回收**：Meteora DLMM 关闭 position + claimFee 后可关闭 position account，rent 回收 ~0.0014 SOL。**Orca NFT** 不一定能 close (NFT 不能 burn 标准上)，rent 不可回收。→ 优先 Meteora。
- **Solana 没有 `tick` 标准**：每协议自定义；design 必须按 protocol 区分。

## 5. 排除 / 不做

- ❌ Marinade / Lido (LST 协议，非 LP)
- ❌ Friktion / Katana (衍生品)
- ❌ Drift / Mango / Zeta (永续 / perp)
- ❌ Solend / Mango (借贷)
- ❌ Phoenix (order book DEX)

## 6. 不在本阶段做

- ❌ 实际写 Meteora/Orca/Raydium connector 代码
- ❌ 跑任何 Solana RPC（设计阶段）
- ❌ 接任何 Solana wallet
- ❌ 准备 SOL/USDC 资金
