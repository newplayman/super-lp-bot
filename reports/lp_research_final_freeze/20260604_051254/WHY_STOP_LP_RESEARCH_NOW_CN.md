# Why Stop LP Research Now — Stage D

- stage: `LP_RESEARCH_FINAL_FREEZE_AND_HANDOFF_V1`
- run_id: `20260604_051254`

## 0. 大白话总结

LP research 当前主线**正式收口**。不是因为没努力, 也不是因为连接器没跑通, 也不是因为没钱。是因为 **在当前数据、当前资金规模、当前自动化模型下, retail 10-20U 2000 USD LP 在所有 5 个 Solana AMM protocols 都无法获得 realistic positive EV**。

## 1. 9 大原因 (plain language)

### 1.1 不是因为连接器没跑通

5 个 LP research stage 全部 connector_status = **complete**:
- Meteora DLMM V8: SDK decode 56/56, 81 verified
- Orca Whirlpools V1: SDK decode 75/75, 10 quote-ready
- Raydium CLMM V1: SDK decode 65/65, 50 quote-ready
- Raydium CPMM V1: SDK decode 81/81, 73 quote-ready
- Solana stable V1: SDK decode 25/25, 10 quote-ready

**多数 connector 已经跑通**, 失败的不是 path, 是协议结构。

### 1.2 多数 connector 已经跑通

- 4 mainnet programs (Meteora Stable Swap / DAMM v2 / Orca / Raydium AMM v4) on-chain verified executable
- SDK decode paths 都通过
- Quote path 都通过 (10-75 quote-ready pools per stage)
- 没有 RPC rate limit 阻塞
- 没有 protocol 集成 error

### 1.3 问题是 realistic EV 不成立

EV model (heuristic, common across all 5 stages):
```
gross_fee_usd = notional * daily_turnover * days * (fee_bps / 10000)
il_lvr_cost_usd = notional * IL_LVR_PCT[scenario] * days
total_cost_usd = fixed_round_trip_cost
net_ev_usd = gross_fee - il_lvr - cost
```

Across 5 stages, all 28560 cells:
- 1898 positive in zero_il_lvr scenario
- **0 in optimistic / realistic / conservative** scenarios

任何 IL > 0 都让所有 cells 变负。

### 1.4 zero_il_lvr 微正不等于真实正 EV

zero_il_lvr 假设: 7d 持有期间 IL/LVR = 0. 在 V3 CL / constant product / LST-stable 都不可能:
- V3 CL: 即使 zero price change, tick boundary 跨过仍有 IL
- Constant product: x*y=k 任何 price change 都有 IL
- LST-stable: LST 几乎总是 depeg 0.01-0.1% per day

所以 zero_il_lvr_positive 仅仅是**理论上限**, 实际必 IL, 必负。

### 1.5 10/20U 小资金 fixed cost / slippage / IL/LVR / fee capture 不够

10 USD notional:
- gross fee at 25bps × 0.5%/day = $0.00125/day
- 7d gross = $0.00875
- minus fixed cost $0.006 = $0.00275
- minus IL 0.5% (realistic) × 7d × $10 = $0.35
- **net = -$0.35** (heavily negative)

20 USD notional 类似: net = -$0.69 at 7d realistic.

小资金 = fee capture 太小, fixed cost 占太大比例. 这是结构性, 不是 fee 费率问题.

### 1.6 100/500/1000/2000U 放大后仍未出现 realistic positive

Across 5 stages, **2000 USD notional / 7d** 是最高的 notional 测试:
- Meteora DLMM: best +$0.544 (zero_il_lvr, 7d, 2000 USD, memecoin 100bps)
- Orca Whirlpools: best +$0.106
- Raydium CLMM: best +$0.167
- Raydium CPMM: best +$0.172
- Solana stable: best +$0.204

**所有 best cell 都在 zero_il_lvr only**, 在 optimistic / realistic / conservative 全部负。
放大 notional 不解决 IL 主导问题。

### 1.7 没有任何池满足 probe preflight

per spec rule_1 触发条件:
> "positive_realistic_count > 0 OR strong near-break-even high-fee pool"

5 stages 全部不满足。**没有任何池**满足 probe preflight 条件。

### 1.8 继续自动扩协议属于低价值重复

5 个 Solana AMM protocols (DLMM, V3 CL x 3, CPMM, stable) 全部 reject。剩余可选:
- Meteora DAMM v2 stable (实际 API mislabel, 0 真池)
- Lifinity (pid unknown, not on mainnet)
- Mercurial (org returns 404, deprecated)
- Saber (rebrand as Meteora Stable Swap, 0 active pool)
- native Curve on Solana (不存在)

继续自动扩协议边际信息价值低 (已经覆盖所有已知 protocol)。

### 1.9 所以 STOP_LP_RESEARCH_NOW

5/5 reject 累计, 加上上面 1.1-1.8 论证:
- connector path 没阻塞
- IL 结构主导
- 任何 LP 在 retail 10-20U 2000 USD 范围内都负 EV
- 进一步 auto-expand 无信息价值

**结论: STOP_LP_RESEARCH_NOW 是 stable 结论**, 累计 5 stages 的 28560 cells 都验证.

## 2. 累计 cost 总结 (5 stages 总投入)

| stage | 5/5 reject 累计 cells | 投入类型 |
|---|---|---|
| Meteora DLMM V8 | 4536 cells | 56 pools, 27 quote-ready, 16bps-100bps fee range |
| Orca Whirlpools V1 | 1680 cells | 75 pools, 10 quote-ready, 1-200bps fee range |
| Raydium CLMM V1 | 8400 cells | 65 pools, 50 quote-ready, 1-200bps fee range |
| Raydium CPMM V1 | 12264 cells | 81 pools, 73 quote-ready, 25bps constant |
| Solana stable V1 | 1680 cells | 25 pools, 10 quote-ready, 1-30bps fee range |
| **TOTAL** | **28560 cells** | **302 pools, 170 quote-ready** |

## 3. STOP_LP_RESEARCH_NOW 含义 (for operator)

- LP research 当前主线**收口** (不再继续 auto-expand)
- can_run_probe_now 保持 **false**
- tiny_canary_allowed 保持 **no**
- edge_proven 保持 **no**
- hard-disable executor 保持 **active**
- 任何后续 LP 决策必须基于 **manual operator approval**
- 重开 LP research 需满足 Stage F 列出的所有条件
- 任何 probe 必须先 restart LP research stage

## 4. 重要 caveat

STOP_LP_RESEARCH_NOW 是 **research-only 决策**, 不影响:
- project code (lpbot) 仍存在, 可用于其他 purpose
- 已读-only 验证的 connector 代码 (reusable)
- docs / artifacts / 测试 / 安全 gates
- hard-disable executor 的 active 状态
