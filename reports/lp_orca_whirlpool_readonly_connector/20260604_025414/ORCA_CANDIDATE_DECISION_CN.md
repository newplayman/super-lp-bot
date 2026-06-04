# Orca Candidate Decision — Stage K

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`

## 0. 七项判断

| # | 问题 | 答案 | 证据 |
|---|---|---|---|
| 1 | 是否出现 10/20U realistic positive? | **否** | positive_realistic_count = 0 / 1680 |
| 2 | 是否出现 near-break-even? | **是, 928 cells** | 但全部在 zero_il_lvr + 2000 USD + 7d |
| 3 | 是否出现 high-fee quote-ready candidate? | **是, 4-6 pools** (feeRate 30-200bps) | C9U2Ksk6 16bps, CeaZcxBN 16bps, 等 |
| 4 | 是否值得进入 Orca 10/20U probe preflight design? | **否** | positive_realistic=0, best cell in zero_il_lvr only |
| 5 | 是否应该切到 Raydium CLMM? | **是** | Meteora V8 + Orca V1 都已经 reject |
| 6 | 是否需要 paid RPC? | **不是关键** | public RPC 拿到 10 quote (实际可到 ~30); 池子 fee data 已经清楚 |
| 7 | 是否应该 stop? | **否** | Raydium CLMM 是合理下一步 |

## 1. Spec decision rule 应用

```text
rule_1: positive_realistic_count > 0 OR strong near-break-even high-fee pool
        → LP_ORCA_WHIRLPOOL_10_20U_PROBE_PREFLIGHT_DESIGN_V1

rule_2: quote_ready_pool_count > 0 but all negative, candidate quality still insufficient
        → LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1

rule_3: quote_ready_pool_count = 0
        → LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1 or LP_SOLANA_PAID_RPC_SETUP_REQUIRED
```

**本轮结果**:
- positive_realistic_count = 0 → rule_1 不触发
- quote_ready_pool_count = 10 (实际可到 ~30, 受 429 限制) → rule_3 不触发
- best cell in zero_il_lvr only → 不满足 strong near-break-even
- 4-6 池 high_fee_quote_ready (30-200bps feeRate) — 但 best ev 仍 only $0.106

→ **应用 rule_2**: `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`

## 2. 为什么不是 Orca 10/20U probe preflight

positive_zero_il_lvr = 29, best cell +$0.106 但:
- **仅 zero_il_lvr**: optimistic/realistic/conservative 全部 0 positive
- best 池 feeRate 16bps (SOL/Fartcoin) — 0.106 USD margin 在 2000 USD notional / 7d
- 即使是 zero_il_lvr, 7d 持有高 vol SOL/Fartcoin 池是不现实的 (Fartcoin 是 memecoin)
- SOL/USDC 4bps (Czfqq) best 0.022 USD — 更小

**核心判断**: Orca V1 best cell margin **比 Meteora V8 best (0.544) 还小 5×**。两个 V3 类 CL AMM 都被验证 negative。

## 3. 为什么是 Raydium CLMM 而不是 paid RPC

- **public RPC 拿到 10 quote 池, 实际可到 ~30** — V1 早 stage 设计的 public RPC limit 没想象中阻塞
- **paid RPC 不解决 IL 问题** — 协议是结构失败, RPC 是连接器失败, 不同维度
- **Raydium CLMM 是 3rd V3 类 CL AMM** — 不同 fee tier (默认 25bps), 不同流动性集中机制
- 三个 V3 类 CL 都 negative 才能 stable 结论"零售 LP 在 Solana 10-20U 2000 USD 不可行"

## 4. V1 / V2 / V3 V3 类 CL 累计结论

| 阶段 | 协议 | quote_ready | best ev | positive_realistic |
|---|---|---|---|---|
| Meteora DLMM (V8) | DLMM, dynamic fee, IL binary | 27 | +$0.544 | 0 |
| Orca Whirlpools (V1) | V3 CL, 1-200bps fee, IL gradual | 10+ | +$0.106 | 0 |

**两个 V3 类 CL 都 negative** → 强烈支持转到 Raydium CLMM 第 3 个独立验证, 而非重复 Meteora / Orca。

## 5. recommended_next_stage = `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`

理由:
1. Meteora DLMM + Orca Whirlpools 两个 V3 类 CL AMM 零售 10-20U 2000 USD 已被验证 negative
2. Orca V1 SDK 走通 (read-only), quote 真实 fee data 采集成功
3. 0.106 USD best cell margin (zero_il_lvr only) 远低于 practical LP 操作成本
4. Raydium CLMM 是 Solana 上 第 3 大 CL AMM, fee tier 不同, IL 行为略有差异, 应作独立验证
5. 3rd 独立 AMM negative 后可稳定结论"零售 LP 在 Solana 不可行", 而非"某个协议失败"

## 6. 不建议的备选

- `LP_ORCA_WHIRLPOOL_KNOWN_POOL_FEED_EXPANSION_REPEAT` — 本轮 75 verified + 10 quote, repeat 同策略无信息
- `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` — public RPC 够用, paid RPC 不解决 IL
- `STOP_LP_RESEARCH_NOW` — Raydium 是合理下一步, 3rd 协议尚未验证
- `LP_ORCA_WHIRLPOOL_10_20U_PROBE_PREFLIGHT_DESIGN_V1` — best cell 仍受 IL 主导, 不满足 spec 触发条件

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
