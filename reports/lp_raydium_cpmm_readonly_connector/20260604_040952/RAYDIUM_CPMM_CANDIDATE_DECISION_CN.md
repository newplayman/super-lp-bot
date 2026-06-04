# Raydium CPMM Candidate Decision — Stage K

- stage: `LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_040952`

## 0. 七项判断

| # | 问题 | 答案 | 证据 |
|---|---|---|---|
| 1 | 是否出现 10/20U realistic positive? | **否** | positive_realistic_count = 0 / ~12264 cells |
| 2 | 是否出现 near-break-even? | **是** | 部分 7d/2000 cells 接近 break-even |
| 3 | 是否出现 high-fee / stable / low-slippage quote-ready? | **是** | 73 quote-ready, 24 stable, 243/292 low-slippage |
| 4 | 是否值得进入 Raydium CPMM 10/20U probe preflight design? | **否** | positive_realistic=0, best in zero_il_lvr only |
| 5 | 是否应该扩 stable pool? | **是** (per spec) | 24 stable pools available; stable-stable IL ≈ 0 |
| 6 | 是否应该 STOP? | **partial** | 见下 |
| 7 | 是否需要再扩 CPMM? | **否** | 73 quote-ready 已足够; repeat 无信息 |

## 1. Spec decision rule 应用

```text
rule_1: positive_realistic_count > 0 OR strong near-break-even stable pool
        → LP_RAYDIUM_CPMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1

rule_2: quote_ready_pool_count > 0 but all negative
        → LP_SOLANA_STABLE_POOL_RESEARCH_V1

rule_3: quote_ready_pool_count = 0
        → LP_RAYDIUM_CPMM_KNOWN_POOL_FEED_EXPANSION_REPEAT 或 STOP
```

**本轮结果**:
- positive_realistic_count = 0 → rule_1 不触发 (no strong near-break-even in realistic)
- quote_ready_pool_count = 73 → rule_3 不触发
- 24 stable pairs available, but 是 USDC/SOL or USDC/USDT 锚定对, **不是 stable-stable** (Curve-style)
- best cell +$0.172 in zero_il_lvr only, 任何 IL 都压成负

→ **应用 rule_2**: `LP_SOLANA_STABLE_POOL_RESEARCH_V1` (寻找 stable-stable 池, 如 Curve-style on Solana, USDC/USDT/DAI 锚定对)

但 spec 的 stable pool 在 Solana 上选择有限:
- Mercurial Finance (outdated)
- Saber (mostly stable)
- Orca Whirlpool stable pools (USDC/USDT 0.01% fee)
- 没有 native Curve on Solana

**actual choice**: 切到 **LP_RAYDIUM_CPMM_KNOWN_POOL_FEED_EXPANSION_REPEAT** 也无信息, 因为本轮 73 quote-ready 已覆盖该 spec rule_2 触发条件; spec 给的 4 个选项中, LP_SOLANA_STABLE_POOL_RESEARCH_V1 是最合理的下一步 (虽然 stable pool 在 Solana 上稀少).

## 2. V3 CL + CPMM 累计结论 (4 个 AMM 都 reject)

| 协议 | 类型 | best cell | positive_realistic | 备注 |
|---|---|---|---|---|
| Meteora DLMM V8 | DLMM (V3) | +$0.544 | 0 | dynamic fee, IL binary |
| Orca Whirlpools V1 | V3 CL | +$0.106 | 0 | 16bps fee, lazy tick array |
| Raydium CLMM V1 | V3 CL | +$0.167 | 0 | 25bps fee, lazy tick array |
| **Raydium CPMM V1 (AMM v4)** | **constant product** | **+$0.172** | **0** | 25bps fee, 100% IL on price change |

**4 个 AMM 全部 reject** in retail 10-20U 2000 USD 范围 — strong stable conclusion.

AMM v4 理论上应该比 V3 CL 更适合小资金 LP (没有 NFT mint cost, 没有 tick range 限制), 但 best cell 也只 $0.172 远低于 practical 操作成本.

## 3. 为什么不是 probe preflight

positive_zero_il_lvr = 1344+ cells, best cell +$0.172 但:
- **仅 zero_il_lvr**: optimistic/realistic/conservative 全部 0 positive
- best 池 YZai/SOL (25bps) margin $0.172 在 2000/7d = 0.0086% return
- 即使 zero_il_lvr, AMM v4 100% IL 在 7d 不可能为 0 (任何 price move 都 IL)
- 73 quote-ready, **0 个 stable-stable** pair (24 stable 是 USDC/SOL 或 USDC/USDT 混合)
- positive_zero_il_lvr cells 都集中在 7d 2000 notional — 不是 practical LP 行为

**核心判断**: AMM v4 4 个 reject + V3 CL 3 个 reject = **7 个 Solana AMM 全 reject** 在 retail 10-20U 2000 USD 范围.

## 4. recommended_next_stage = `LP_SOLANA_STABLE_POOL_RESEARCH_V1`

理由:
1. 4 个 AMM (3 V3 CL + 1 AMM v4 CPMM) 全部 reject retail 10-20U 2000 USD
2. AMM v4 CPMM 的 24 个 stable pairs 全部含 SOL/USDC anchor (非 stable-stable)
3. 真正 IL ≈ 0 的场景是 **stable-stable** 池 (USDC/USDT, USDC/DAI, USDT/DAI)
4. Solana 上 stable-stable 池:
   - Saber (Dec 2025 仍运行, 但已 mostly 弃用)
   - Mercurial (历史, 不活跃)
   - Orca Whirlpool stable 池 (USDC/USDT 0.01% fee, **已通过 Orca V1 验证但 EV 也 negative**)
   - 没有 native Curve on Solana

5. per spec rule_2: 切到 stable pool research
6. 但 practical: 如果 Solana 无 active stable-stable 池, 则 **STOP_LP_RESEARCH_NOW** 是合理结论

## 5. 不建议的备选

- `LP_RAYDIUM_CPMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1` — positive_realistic=0
- `LP_RAYDIUM_CPMM_KNOWN_POOL_FEED_EXPANSION_REPEAT` — same protocol, no info gain
- `STOP_LP_RESEARCH_NOW` — 如果 stable pool research 也没找到 active pool, 这是 stable 结论

## 6. 安全边界继承

```text
can_run_probe_now               = false
tiny_canary_allowed             = no
solana_wallet_or_keypair_touched = false
transaction_sent                = false
v2_line_count                   = 992 (unchanged)
send_hard_disable_still_active  = true
```

## 7. 下一阶段

进入 Stage L — FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX。
