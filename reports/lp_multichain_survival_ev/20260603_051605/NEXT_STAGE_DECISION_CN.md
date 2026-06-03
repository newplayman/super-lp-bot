# Next Stage Decision — Stage J

- stage: `LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1`
- run_id: `20260603_051605`

## 1. 决策

```text
recommended_next_stage = LP_SOLANA_LP_CONNECTOR_DESIGN_V1
allowed_next_stages    = [
  LP_MULTICHAIN_TOP_CANDIDATE_PROBE_PREFLIGHT_V1,   # 不选 (0/19,980 正 EV)
  LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1,           # 不选 (cost 仍负)
  LP_EVM_MULTICHAIN_DISCOVERY_FIX_REPEAT,            # 不选 (V3 已饱和; P1 还有空间但优先级低)
  LP_SOLANA_LP_CONNECTOR_DESIGN_V1,                 # 选
  STOP_LP_RESEARCH_NOW                                # 不选 (operator 未表态停)
]
```

## 2. 为什么 5 选 1

| next stage | 选/不选 | 理由 |
|---|---|---|
| `LP_MULTICHAIN_TOP_CANDIDATE_PROBE_PREFLIGHT_V1` | ❌ | spec 要求"有候选在 realistic 或 conservative 下表现优于当前 Base"；当前 model 0/19,980 positive。强行进入 = 越过 model 结论。 |
| `LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1` | ❌ | upstream 推荐的 base 10U wait；但本阶段 model 显示即便 Base 回到 frozen center，cost structure 仍负 EV。再等只是"等市场回更接近 EV 负但不那么大"。**V3 简单 LP 路线**已结构性失败。 |
| `LP_EVM_MULTICHAIN_DISCOVERY_FIX_REPEAT` | ❌ | V3 142 池已覆盖；next frontier 是 **P1 (Curve/Balancer/PancakeSwap V2)** 与 **P2 (Solana)**。但 P1 仍属 EVM 范畴；model proxy 同样会预测 negative EV。**优先级低于 P2 (Solana 新 venue)**。 |
| `LP_SOLANA_LP_CONNECTOR_DESIGN_V1` | ✅ | Solana Meteora DLMM / DAMM v2 / Orca Whirlpool / Raydium CLMM 是**完全不同的 pool layout**——bin-based / tick-array-based / concentrated liquidity w/ dynamic fees。结构性 IL 可能低（DLMM 的 bin 选择让 LP 完全控制暴露）；fee velocity 通常远高于 V3。 |
| `STOP_LP_RESEARCH_NOW` | ❌ | operator 未表态停；本阶段已澄清问题不在 Base 单池而在 V3 范式。 |

## 3. 选 LP_SOLANA_LP_CONNECTOR_DESIGN_V1 的具体动因

### 3.1 V3 范式失败 (本阶段实证)

- 142 池 × 5 scenario × 6 notional × 9 hold = 19,980 行
- positive_realistic_count = 0
- 即使 zero_il_lvr ceiling at $2000 BSC = -$2.51
- 含义：V3 简单 LP 在 $10-$2000 notional × 15m-7d hold 上**结构性负 EV**

### 3.2 P1 (Curve/Balancer) 仍 EVM V3-like

- Curve stable pools IL 极低，但 fee 也很低（10-30 bps/年 stable）→ 期望 fee 不会比 V3 高很多
- Balancer weighted 比 V3 更复杂；model proxy 一样会负 EV
- PancakeSwap V2 (constant product) — fee 比 V3 低

### 3.3 P2 (Solana) 是真正的 venue 创新

- **Meteora DLMM** 用 bin-based 流动性；LP 可**自定义**暴露在哪个 bin range — **完全控制 IL**
- **Meteora DAMM v2** 2025 推出，dynamic fee + 优化无常损失
- **Orca Whirlpool** 与 Uniswap V3 类似但 Solana 上 fee velocity 高 5-20x (per upstream benchmark)
- **Raydium CLMM** 同样 CL V3 fork；fee velocity 介于 Uniswap V3 与 Orca 之间

### 3.4 wallet 状态

- wallet 仅在 Base ($26.84)
- 切换 Solana 链需要先 bridge / swap — **本阶段不**自动
- 下一阶段 (LP_SOLANA_LP_CONNECTOR_DESIGN_V1) 只做 **design spec**，不实际跑链上

## 4. 下一阶段预期动作 (LP_SOLANA_LP_CONNECTOR_DESIGN_V1)

根据 spec："EVM 未发现优质候选，开始设计 Solana Meteora/Orca/Raydium。"

具体：
1. **connector spec 文档**（不写实际代码）
   - Solana RPC endpoint list
   - Meteora DLMM account layout (bin arrays, position accounts)
   - Meteora DAMM v2 account layout
   - Orca Whirlpool tick array layout
   - Raydium CLMM pool layout
2. **quote 方法**
   - Meteora quote via static simulateSwap on DLMM pool
   - Orca/Raydium CLMM quote via Quoter program staticcall
3. **position model**
   - DLMM: bin-range position
   - CLMM: tick-range position (like V3 but Solana)
4. **fee / reward 提取**
   - Solana 没有 ERC20 `transferFrom` 模式；fee 累积在 token accounts
5. **token account 准备**
   - Solana LP 必先 ATA (Associated Token Account)
6. **fee_velocity proxy 数据源**
   - Helius / Triton / QuickNode 公共 RPC
   - 不引入私 RPC
7. **不**实现实际 connector；仅 spec
8. **不**自动 swap / bridge；wallet 仍在 Base

## 5. 5 个 next stage 触发条件表

| next stage | 触发条件 | 当前是否触发 |
|---|---|---|
| `LP_MULTICHAIN_TOP_CANDIDATE_PROBE_PREFLIGHT_V1` | 候选在 realistic 或 conservative 下表现优于当前 Base | ❌ (0/19,980) |
| `LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1` | Base 仍是最好，但当前市场不安全 | ❌ (Base 仍是 wallet-funded best，但 model 显示任何 V3 都负 EV) |
| `LP_EVM_MULTICHAIN_DISCOVERY_FIX_REPEAT` | 多链数据源 / RPC / metadata 不足 | ⚠️ partial (v1 QuoterV2 编码有 bug, swap log RPC 限制)，但 P0 V3 已饱和 |
| `LP_SOLANA_LP_CONNECTOR_DESIGN_V1` | EVM 未发现优质候选，开始设计 Solana | ✅ (本阶段确认) |
| `STOP_LP_RESEARCH_NOW` | 市场持续不适合 或 operator 不想继续 | ❌ (operator 未表态停) |

## 6. 阶段决策签名

```text
recommended_next_stage                  = LP_SOLANA_LP_CONNECTOR_DESIGN_V1
multichain_discovery_ran                = true
chain_count                             = 6
protocol_count                          = 7
candidate_pool_count                    = 142
readiness_probe_ran                     = true
survival_ev_model_ran                   = true
survival_risk_model_ran                 = true
candidate_scoring_ran                   = true
positive_realistic_count                = 0
positive_conservative_count             = 0
near_break_even_count                   = 0
top_candidate_chain                     = Base
top_candidate_protocol                  = PancakeSwap V3
top_candidate_pool                      = 0x...WETH/DAI
top_candidate_pair                      = WETH/DAI
top_candidate_notional                  = 10
top_candidate_hold_window               = 7d
recommended_probe_chain                 = Base
can_run_probe_now                       = false
edge_proven                             = "no"
wallet_or_tx_touched                    = false
tiny_canary_allowed                     = "no"
```
