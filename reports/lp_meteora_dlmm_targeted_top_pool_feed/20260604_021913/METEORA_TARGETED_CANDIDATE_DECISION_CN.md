# Meteora Targeted Candidate Decision — Stage I

- stage: `LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1`
- run_id: `20260604_021913`

## 0. 七项判断

| # | 问题 | 答案 | 证据 |
|---|---|---|---|
| 1 | 是否出现 10/20U realistic positive? | **否** | positive_realistic_count = 0 / 4536 |
| 2 | 是否出现 near-break-even? | **是, 19 cells** | 但全部在 zero_il_lvr + 7d + 2000 USD |
| 3 | 是否出现 high-fee quote-ready candidate? | **是, 4 pools** | base=50/100 bps × bin_step=50/80/100 |
| 4 | 是否值得进入 Meteora 10/20U probe preflight design? | **否** | positive_realistic=0, best cell in zero_il_lvr only |
| 5 | 是否应该切到 Orca Whirlpools? | **是** | Meteora DLMM 在零售 10–20U 10–2000 USD 范围 IL 主导 |
| 6 | 是否需要 paid RPC? | **否 (本轮)** | public RPC 27/27 quote 成功, 通路走通 |
| 7 | 是否应该 stop? | **否** | Orca 是合理下一步, 还有协议维度可探索 |

## 1. Spec decision rule 应用

```text
rule_1: positive_realistic_count > 0 OR strong near-break-even high-fee pool
        → LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1

rule_2: quote_ready_pool_count > 0 but all negative, candidate quality still insufficient
        → LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1

rule_3: quote_ready_pool_count = 0
        → LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1 or LP_SOLANA_PAID_RPC_SETUP_REQUIRED
```

**本轮结果**:
- positive_realistic_count = 0 → rule_1 不触发
- quote_ready_pool_count = 27, **but best cell in zero_il_lvr only** → 不满足 strong near-break-even
- best 3 池 (CnK82s8, 9bL8Pp, HuPRxa) 是 memecoin (three, GACHA, MET) — 即使 positive 也属高风险 IL

→ **应用 rule_2**: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`

## 2. 为什么不是 Meteora 10/20U probe preflight

positive_zero_il_lvr = 15 (best +$0.544 at 2000/7d) 但:

- **仅 zero_il_lvr**: optimistic/realistic/conservative 全 0 positive
- 0.5%/day 假设的 daily turnover 比 10/20u single-swap observed fee 推导的 0.005%/day **高 100×**
- best cell margin **$0.544** 在 2000 USD notional / 7d 是 0.0272% return — 任何 IL/LVR 都压成负
- three / GACHA / MET 是 memecoin, base_fee 1% 是 dynamic floor, 实际 fee 在 volatility 时段会 ramp 到 10% (max_fee=1000bps), 但同样带来更大 IL

**核心判断**: Meteora DLMM 的"high base fee 池"几乎都是 memecoin。base 1% × 7d 才能打平 cost $0.156。这在 7d 持有可能勉强 positive，但 retail LP 不会持 7d 这种高 vol memecoin 池。

## 3. 为什么是 Orca 而不是 paid RPC

- **public RPC 27/27 quote 成功**: V7 阻断的"active bin 0 liquidity"在本轮被定向 high-volume 池解决
- **paid RPC 不是阻塞因素**: 真阻塞是 Meteora DLMM 的结构性 IL 而非 RPC 性能
- **Orca Whirlpool 是不同协议**: 集中流动性 (Concentrated Liquidity, V3 类), 单 bin 跨价格区间更小, IL 行为不同
- **如果 Orca 同样失败**, 才是 paid RPC + 长期 cross-pool TVL exploration

## 4. recommended_next_stage = `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`

理由:
1. Meteora DLMM 零售 LP 10/20U → 2000 USD 已被 V1–V8 多个 stage 验证 negative
2. 走通了 V8 path (targeted feed → 27 quote-ready) — 不是 path 失败, 是协议失败
3. Orca 是 Solana 上第二大 AMM, 集中流动性, 池子结构不同, 应作下一轮独立探索

## 5. 不建议的备选

- `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT` — 本轮 V8 已是 targeted, repeat 同策略不会再有信息
- `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` — public RPC 够用, paid RPC 不解决 IL 问题
- `STOP_LP_RESEARCH_NOW` — Orca 是合理下一步, 不是死路
- `LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1` — best cell 仍受 IL 主导, 不满足 spec 触发条件

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

进入 Stage J — FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX。
