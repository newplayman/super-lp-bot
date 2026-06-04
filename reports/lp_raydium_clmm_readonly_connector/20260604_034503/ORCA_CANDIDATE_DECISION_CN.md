# Raydium CLMM Candidate Decision — Stage K

- stage: `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_034503`

## 0. 七项判断

| # | 问题 | 答案 | 证据 |
|---|---|---|---|
| 1 | 是否出现 10/20U realistic positive? | **否** | positive_realistic_count = 0 / 8400 |
| 2 | 是否出现 near-break-even? | **是** | 部分 7d/2000 cells 接近 break-even |
| 3 | 是否出现 high-fee quote-ready candidate? | **是, 50 池 (liquidity > 0)** | fee 默认 25bps (Raydium 标准) |
| 4 | 是否值得进入 Raydium 10/20U probe preflight design? | **否** | positive_realistic=0 |
| 5 | 是否应该切到 Raydium CPMM / stable pool / non-CL LP? | **是** | 3/3 V3 CL AMM 都 reject; per user instruction |
| 6 | 是否需要 paid RPC? | **否** | public RPC 够用 (走通 50 quote) |
| 7 | 是否应该 stop? | **否** | Raydium CPMM 是合理下一步 |

## 1. V3 CL AMM 累计结论 (3/3 reject)

| 协议 | best cell | positive_realistic | positive_zero_il_lvr | 备注 |
|---|---|---|---|---|
| Meteora DLMM (V8) | +$0.544 | 0 | 15 | dynamic fee, IL binary |
| Orca Whirlpools (V1) | +$0.106 | 0 | 29 | 16bps fee, lazy tick array |
| **Raydium CLMM (V1)** | **+$0.167** | **0** | (TBD) | 25bps fee, 50 quote-ready |

**3/3 V3 CL AMM 都验证 positive_realistic=0** → 完成 V3 CL 累计 reject 验证逻辑。

## 2. Spec decision rule 应用

```text
rule_1: positive_realistic_count > 0 OR strong near-break-even high-fee pool
        → LP_RAYDIUM_CLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1

rule_2: quote_ready_pool_count > 0 but all negative
        → LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1 (per user instruction)

rule_3: quote_ready_pool_count = 0
        → LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1 or LP_SOLANA_PAID_RPC_SETUP_REQUIRED
```

**本轮结果**:
- positive_realistic_count = 0 → rule_1 不触发
- quote_ready_pool_count = 50 (50/53 with liquidity) → rule_3 不触发
- best cell in zero_il_lvr only → 不满足 strong near-break-even
- best cell margin $0.167 比 Orca V1 $0.106 高 (因为 fee 25bps vs 16bps), 但仍只有 zero_il_lvr 假设下 positive

→ **应用 rule_2 + user instruction**: 切到 **Raydium CPMM** 或 **stable pool** 或 **non-CL LP**

## 3. 为什么不是 Raydium 10/20U probe preflight

positive_zero_il_lvr cells exist (best $0.167) but:
- **仅 zero_il_lvr**: optimistic/realistic/conservative 全部 0 positive
- best 池都是 SOL/USDC 0.01% 或 SOL/USDT 类, 25bps fee
- $0.167 margin 在 2000 USD notional / 7d = 0.0084% return, 任何 IL/LVR 压成负
- 3/3 V3 CL AMM 都 reject → 强烈支持切到 non-CL

## 4. 为什么是 Raydium CPMM 而不是 paid RPC

- **public RPC 走通 50 quote 池** — RPC 不是阻塞
- **paid RPC 不解决 IL 问题** — IL 是协议结构失败
- **Raydium CPMM (constant product)** 是不同 AMM 模型:
  - 100% IL inside LP (binary, not gradual)
  - Fee tier 通常 25bps (standard)
  - Constant product x*y=k, 池结构简单
- **stable pool** 是 3rd 选项 (Curve-style), 主要面向 USDC/USDT/DAI, 极低 IL
- Per user instruction: "推荐切到 Raydium CPMM / stable pool / non-CL LP，不再继续 V3 CL 无限扩展"

## 5. recommended_next_stage = `LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1`

理由:
1. 3/3 V3 CL AMM 累计 reject (Meteora DLMM V8 + Orca V1 + Raydium CLMM V1)
2. 每轮 V3 CL best cell 都 only in zero_il_lvr scenario — 不是偶然, 是 V3 CL 协议结构
3. 切换到 CPMM (constant product) 可验证 AMM 模型差异是否影响结论
4. user instruction 明确: 不再继续 V3 CL 无限扩展
5. stable pool 是另一选项 (但 stable pool 主要是 USDC pair, 不适合零售 memecoin LP)

## 6. 不建议的备选

- `LP_RAYDIUM_CLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1` — positive_realistic=0
- `LP_RAYDIUM_CLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT` — same protocol, no info gain
- `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` — RPC 不阻塞
- `STOP_LP_RESEARCH_NOW` — Raydium CPMM 是合理下一步

## 7. 安全边界继承

```text
can_run_probe_now               = false
tiny_canary_allowed             = no
solana_wallet_or_keypair_touched = false
transaction_sent                = false
v2_line_count                   = 992 (unchanged)
send_hard_disable_still_active  = true
```

## 8. 下一阶段

进入 Stage L — FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX。
