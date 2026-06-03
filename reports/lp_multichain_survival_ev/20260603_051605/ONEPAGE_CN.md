# Multichain DEX LP Discovery + Survival EV — 总览

```text
stage                                       = LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1
run_id                                      = 20260603_051605
status                                      = WARN (no execution; only discovery + modeling)
branch                                      = feat/supabase-postgres-deployment
head_before                                 = 9c3af43 (LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1)

multichain_discovery
  chain_count                               = 6
  protocol_count                            = 7
  candidate_pool_count                      = 192
  pool_exists_count                         = 142
  state_ready_pools                         = 134

readiness_probe
  pools_probed                              = 142
  state_ready                               = 134
  tick_ready                                = 142
  cost_ready                                = 142
  quote_ready                               = 0     (v1 QuoterV2 encoding known gap)
  high_confidence                           = 134

survival EV model
  pools_evaluated                           = 74
  row_count                                 = 19980 (5 scen × 6 notional × 9 hold × 74 pool)
  positive_realistic_count                  = 0
  positive_conservative_count               = 0
  near_break_even_count                     = 0
  zero_il_lvr ceiling at $2000 BSC          = -$2.51

survival OOR risk
  pools_evaluated                           = 74
  row_count                                 = 666
  high_risk_count                           = 164
  medium_risk_count                         = 148
  low_risk_count                            = 354
  base historical samples (anchor)           = 47
  base historical p95 abs drift             = 664 ticks

candidate scoring
  pools_scored                              = 134
  score_count                               = 804
  candidate_now_count                       = 0
  watch_count                               = (5 per notional × 6 notional = 30 top; "watch" class)
  needs_data_count                          = (4 per notional × 5 = 20 top; "needs_data" class)

top candidates (per notional, model rank 1)
  notional  chain    protocol          pair        fee  score  class
  10        Base     PancakeSwap V3    WETH/DAI    500  0.638  watch
  20        Base     PancakeSwap V3    WETH/DAI    500  0.422  needs_data
  100       Base     PancakeSwap V3    WETH/DAI    500  0.422  needs_data
  500       Base     PancakeSwap V3    WETH/DAI    500  0.422  needs_data
  1000      Base     PancakeSwap V3    WETH/DAI    500  0.422  needs_data
  2000      Base     PancakeSwap V3    WETH/DAI    500  0.422  needs_data

structural_finding
  V3 simple LP on 6 EVM chains × $10-$2000 notional × 15m-7d hold
  shows 0/19,980 positive EV combinations under realistic assumptions.
  Cost structure (gas + slippage + failure buffer) dominates fee yield.
  Even zero_il_lvr theoretical ceiling is negative at $2000.

next stage decision
  recommended_next_stage = LP_SOLANA_LP_CONNECTOR_DESIGN_V1
  reason: V3 paradigm exhausted on 6 EVM chains; next frontier is
          Solana Meteora DLMM / DAMM v2 / Orca / Raydium — completely
          different pool layout with potentially lower structural IL.

safety locks (all intact)
  can_run_probe_now                          = false
  execution_allowed_now                      = false
  tiny_canary_allowed                        = no
  edge_proven                                = no
  wallet_or_tx_touched                       = false
  hard_disable_still_active                  = true
  manual_approval_required                   = true
  private_key_loaded                         = false
  eth_sendTransaction_called                 = false
  eth_sendRawTransaction_called              = false
  any_funds_spent                            = false
  v2_line_count_unchanged                    = true (992)
```

## 一句话

6 EVM chain × 7 protocol × 142 V3 pool × 19,980 行 survival EV model 显示 **0 个组合**能在 realistic scenario 下产生正 EV；cost structure 主导；structural frontier 已转移到 P1 (Curve/Balancer) 与 P2 (Solana Meteora/Orca/Raydium)；下一阶段 = **LP_SOLANA_LP_CONNECTOR_DESIGN_V1**；本阶段**未**发任何交易、未构造 signer、未解除 v2 hard-disable、未触碰 live/canary/paper、未花任何资金。

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS |
| B input evidence audit | PASS |
| C multichain universe plan | PASS |
| D EVM V3 multichain discovery | PASS (192/142) |
| E pool readiness probe | PASS (134/142 state_ready) |
| F survival EV model | PASS (19,980 rows; 0 positive) |
| G out-of-range risk | PASS (164 high risk; 47 historical anchor) |
| H candidate scoring | PASS (804 scores; 0 candidate_now) |
| I cross-chain probe route decision | PASS (7 questions) |
| J next stage decision | PASS (SOLANA) |
| K FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX | (this file) |
| L tests + safety scan | pending |
| M git publish | pending |

## 严格禁区（本轮已遵守）

```text
× 未读私钥 / 助记词 / keystore
× 未创建 signer / wallet client
× 未调用 eth_sendTransaction / eth_sendRawTransaction
× 未真实 approve / mint / decreaseLiquidity / collect / burn / swap
× 未启动 live / canary / paper
× 未自动 bridge / swap (即便 spec 提到 Solana; 仍不自动)
× 未写 production DB / shadow 表 / positions
× 未修改 v2 executor 源码（line count 仍 992）
× send hard-disable 仍存在（未解除）
× 6 chains × 142 池 × 19,980 行仅 read-only RPC + in-memory model
```
