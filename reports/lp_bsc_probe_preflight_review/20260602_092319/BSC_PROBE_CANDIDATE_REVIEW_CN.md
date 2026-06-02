# BSC 10/20U Probe 候选池审查

- stage: `LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`
- pool: `0x172fcd41e0913e95784454622d1c3724f546f849`
- pair: `USDT/WBNB`
- fee tier: `100` (0.01%)
- notional: `10–20 USD`
- hold_window: initial `15m`, max extension `30m`

## 12 维就绪审查

| # | 维度 | 状态 | 证据 |
|---|---|---|---|
| 1 | quote readiness | ✅ ready | `lp_bsc_pancakeswap_v3_precise_quote/20260602_235959` + `lp_bsc_quoter_staticcall_amount_fix/20260601_173837` |
| 2 | tick-liquidity readiness | ✅ ready | `lp_bsc_overnight_realdata_pipeline/20260601_180812/BSC_TICK_LIQUIDITY_RESULTS_CN.csv`：slot0 / liquidity / tickBitmap / ticks / observe 全 yes |
| 3 | real cost readiness | ✅ ready | `BSC_REAL_COST_MODEL_RESULTS_CN.csv`：total_fixed_cost_usd = `$0.01526` (diagnostic_low) |
| 4 | fee velocity readiness | ✅ ready | `lp_bsc_fee_velocity_recovery_probe_preflight/20260602_060633`：24h decoded=50,860；72h decoded=145,642 |
| 5 | realistic EV status | ❌ **未转正** — 全部 hold 在 realistic 情境下都是负的（最佳 -$0.0156） |
| 6 | near-break-even status | ⚠️ 仅 `zero_il_lvr` 情境且 20U/24h 才接近 0（-$0.0045）；`100U/24h/zero_il_lvr` 是唯一正 EV (+$0.038) |
| 7 | capacity at 10U / 20U | ✅ 容量充裕 — $27M/24h 量，1697 traders/24h，20U 是 active-tick liquidity 的极小份额 |
| 8 | expected entry/exit cost | $0.0062 entry + $0.0051 exit + $0.0024 collect + $0.0015 approval = **$0.0153 fixed** |
| 9 | expected pool-level fee proxy | 15m≈$0.0001；24h≈$0.0107（20U notional）—**远小于** $0.0153 fixed cost |
| 10 | expected IL/LVR proxy | realistic 20U 15m≈$0.0004；24h≈$0.04（按 20 bps/24h scenario） |
| 11 | expected gas/fixed cost | gas_price 0.05 gwei，gas_units ≈ 165k (entry) + 180k (mint) + 150k (remove) + 70k (collect) + 45k (approval) |
| 12 | main downside risks | 见下表 |

## 实测池子健康度（24h / 72h 真实链上数据）

| window | decoded swaps | unique traders | volume USD proxy | pool fee USD proxy |
|---|---|---|---|---|
| 24h | 50,860 | ~1,697 | $27,153,423 | $2,715.34 |
| 72h | 145,642 | ~3,898 | $80,550,470 | $8,055.05 |

池子非常健康，绝对不缺流量与做市机会。

## 6 个主要 downside risk

| # | 风险 | 严重度 | 缓解 |
|---|---|---|---|
| R1 | fixed cost 主导（$0.0153 比 15m fee proxy 大 100x） | medium | 接受这是研究成本，不当作 EV 交易 |
| R2 | RPC 单点（仅 publicnode 稳定） | **high** | probe 执行（未来阶段）**必须**注入 `BSC_RPC_PRIMARY` 付费 endpoint |
| R3 | actual fee 仍未实测 | medium | 这正是 probe 的目的；dry-run 必须输出 tickLower/tickUpper 选择供人工 review |
| R4 | swap-back 滑点不受控 | medium | Phase D 风控边界必须包含 swap_back_quote_drift_max |
| R5 | approval 持久化 | **high** | Phase E telemetry 强制要求 approval tx + revoke tx；Phase F dry-run 只允许 ApproveExact |
| R6 | reorg / 失败 tx | low | single-pool / single-tx-per-side / no auto-retry |

## EV 数字（candidate pool / 20U 全 hold × scenario）

| hold | scenario | fee_proxy | fixed | il_lvr | net_ev |
|---|---|---|---|---|---|
| 15m | zero_il_lvr | $0.000112 | $0.01526 | $0 | **-$0.01514** |
| 15m | realistic | $0.000112 | $0.01526 | $0.000417 | **-$0.01556** |
| 30m | realistic | $0.000224 | $0.01526 | $0.000833 | -$0.01587 |
| 1h | realistic | $0.000448 | $0.01526 | $0.001667 | -$0.01648 |
| 6h | realistic | $0.002685 | $0.01526 | $0.010000 | -$0.02257 |
| 24h | realistic | $0.010740 | $0.01526 | $0.040000 | -$0.04452 |

任何 hold 在 realistic 情境下都不正。唯一一个正 EV cell 是 **100U / 24h / zero_il_lvr = +$0.038**，**仅在零 IL/LVR 假设下**。

## Probe 目的（不要混淆）

```text
本 probe 不是 +EV 押注。
本 probe 是 ：
  (1) 验证 LP 开仓 / 关仓 的端到端通路
  (2) 拿到真实的 NFT position tokenId
  (3) 测量 actual position fee accrual（通过 feeGrowthInside / tokensOwed）
  (4) 用真实数字校准 EV 模型，让下一轮可以在 100 / 500 / 1000 / 2000U 上做信心更高的判断
```

## 当前状态

```text
realistic_positive_ev      = false  （绝不否认；本轮不试图蒙混）
near_break_even            = true   （但仅在某些非 realistic scenario）
fee_ready                  = true
quote_ready                = true
tick_ready                 = true
cost_ready                 = true
actual_fee_ready           = false  （只能通过 probe 拿到）
token_id_available         = false  （只能通过 probe 拿到）
execution_requires_manual_approval = true
can_run_probe_now          = false
edge_proven                = no
tiny_canary_allowed        = no
```
