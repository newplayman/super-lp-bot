# Stable Pool Decision — Stage J

- stage: `LP_SOLANA_STABLE_POOL_RESEARCH_V1`
- run_id: `20260604_044118`

## 0. 七项判断

| # | 问题 | 答案 | 证据 |
|---|---|---|---|
| 1 | 是否出现 10/20U realistic positive? | **否** | positive_realistic_count = 0 / 1680 |
| 2 | 是否出现 near-break-even? | **是** | 1067 cells (含 zero_il_lvr 30 + 实际 0 IL 假定) |
| 3 | 是否出现 high-fee / stable quote-ready? | **是** | 10 quote-ready, 3 high-fee (>=30bps), 全部 USDC-anchor LST-stable |
| 4 | 是否值得进入 10/20U probe preflight design? | **否** | positive_realistic=0, best cell +$0.204 in zero_il_lvr only |
| 5 | 是否应该扩 stable pool? | **否** | 25 stable pools tested, 没有 strong near-break-even in realistic |
| 6 | 是否需要 paid RPC? | **否** | public RPC 够用, Meteora API 误标已被 chain verify 过滤 |
| 7 | 是否应该 STOP? | **是** | 5/5 Solana AMM protocols (Meteora DLMM + Orca Whirlpool + Raydium CLMM + Raydium CPMM + Orca stable LST) 全部 reject |

## 1. Spec decision rule 应用

```text
rule_1: positive_realistic_count > 0 OR strong near-break-even stable pool
        → LP_STABLE_POOL_10_20U_PROBE_PREFLIGHT_DESIGN_V1

rule_2: quote_ready_pool_count > 0 but all negative
        → STOP_LP_RESEARCH_NOW (per spec)

rule_3: quote_ready_pool_count = 0
        → STOP_LP_RESEARCH_NOW
```

**本轮结果**:
- positive_realistic_count = 0 → rule_1 不触发
- quote_ready_pool_count = 10 → rule_3 不触发
- best cell +$0.204 in zero_il_lvr only → 不满足 strong near-break-even
- 没有任何 stable-stable 池 (全部 USDC-anchor)
- 多次 IL 假设下全负

→ **应用 rule_2**: `STOP_LP_RESEARCH_NOW`

## 2. 5 AMM protocol 累计 5/5 reject 总结

| 协议 | 类型 | best cell | positive_realistic | 备注 |
|---|---|---|---|---|
| Meteora DLMM V8 | DLMM (V3) | +$0.544 | 0 | dynamic fee, IL binary |
| Orca Whirlpools V1 | V3 CL | +$0.106 | 0 | 16bps fee, lazy tick array |
| Raydium CLMM V1 | V3 CL | +$0.167 | 0 | 25bps fee, lazy tick array |
| Raydium CPMM V1 (AMM v4) | constant product | +$0.172 | 0 | 25bps fee, 100% IL |
| **Orca stable (this)** | **V3 CL LST-stable** | **+$0.204** | **0** | 30bps mSOL/USDC |

**5/5 Solana AMM protocols 全部 reject retail 10-20U 2000 USD LP** 在 zero_il_lvr only。

## 3. Stable pool 找不到的根因

- **active stable-stable 池极度稀少**: Solana 上 stable-stable 池要么已 deprecated (Saber), 要么 Meteora DAMM v2 API mislabel (实际是 Orca), 要么 TVL=0
- **LST-stable 池仍受 IL 主导**: 即使 LST depeg 很小 (0.05% per day), 累计 7d 也压制 best cell 到 < $0.21
- **Meteora API 误标**: Stage D finding 显示 `amm-v2.meteora.ag` 返回的 USDC-USDT 池实际 owner 是 Orca (Eo7Wj...), 不是 Meteora DAMM v2
- **Saber 老 API 308 redirect**: `api.saber.so/pools` redirect to 实际不可达 endpoint

## 4. Why STOP_LP_RESEARCH_NOW is the stable 结论

- 5/5 Solana AMM protocols 验证 positive_realistic=0
- 任何 stable pool structure (Curve-style stable-stable 或 LST-stable) 也无法让 retail 10-20U 2000 USD LP positive
- 即使 zero_il_lvr 假设下 best cell margin < $0.21, 远低于 practical LP 操作成本
- Meteora API 不准; paid RPC 不解决 IL 结构问题
- 进一步的 V3 CL / CPMM / stable pool 重复, 边际信息价值低

**结论**: 在 Solana 生态, retail 10-20U 2000 USD LP 在所有已知 AMM protocols 都无法获得 realistic positive EV。LP research 该停下。

## 5. 不建议的备选

- `LP_STABLE_POOL_10_20U_PROBE_PREFLIGHT_DESIGN_V1` — positive_realistic=0
- `LP_STABLE_POOL_KNOWN_POOL_FEED_EXPANSION_REPEAT` — 25 pool tested, no info gain
- `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` — 不解决 IL, 且 public RPC 已够用

## 6. recommended_next_stage = `STOP_LP_RESEARCH_NOW`

理由 (累计 5/5 reject):
1. Meteora DLMM V8: +$0.544 (zero_il_lvr), 0 realistic
2. Orca Whirlpools V1: +$0.106 (zero_il_lvr), 0 realistic
3. Raydium CLMM V1: +$0.167 (zero_il_lvr), 0 realistic
4. Raydium CPMM V1: +$0.172 (zero_il_lvr), 0 realistic
5. Orca stable (this): +$0.204 (zero_il_lvr), 0 realistic

**All best cells only in zero_il_lvr scenario, all under $0.55 even at 7d 2000 USD notional**.

## 7. STOP_LP_RESEARCH_NOW 含义 (per spec)

按 spec 列表:
- `LP_STABLE_POOL_10_20U_PROBE_PREFLIGHT_DESIGN_V1` (本轮 reject)
- `LP_STABLE_POOL_KNOWN_POOL_FEED_EXPANSION_REPEAT` (本轮 reject)
- `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` (本轮 reject)
- **`STOP_LP_RESEARCH_NOW` (本轮 selected)**

STOP_LP_RESEARCH_NOW 意味着:
- 累计 5 AMM protocols 都验证 negative
- Solana 生态对 retail 10-20U 2000 USD LP 不可行
- LP research 该阶段完成, 不再继续类似探索
- 任何后续 LP 决策必须基于 manual operator 决策 (not auto)

## 8. 安全边界继承

```text
can_run_probe_now               = false (locked)
tiny_canary_allowed             = no    (locked)
solana_wallet_or_keypair_touched = false (locked)
transaction_sent                = false (locked)
v2_line_count                   = 992 (unchanged)
send_hard_disable_still_active  = true
```

## 9. 下一阶段

进入 Stage K — FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX (本轮是 LP research 收口阶段, FINAL_VERDICT 标志 LP research 状态)。
