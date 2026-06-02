# Dry-run Candidate 冻结

- stage: `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: C

## 候选（不可变）

```text
chain                       = BSC (chain_id = 56)
protocol                    = PancakeSwap V3
pool_address                = 0x172fcd41e0913e95784454622d1c3724f546f849
pair                        = USDT/WBNB
fee_tier_raw                = 100  (0.01%)
```

## 资金（不可变）

```text
max_notional_usd            = 20
preferred_notional_usd      = 10
single_pool_only            = yes
single_position             = yes
no_compounding              = yes
no_auto_repeat              = yes
```

## 持有时间（不可变）

```text
initial_hold_window         = 15m
max_hold_window             = 30m  (仅 manual extension)
```

## 用途澄清（绝不混淆）

```text
is_positive_ev_proof        = false
is_edge_proven_assertion    = false

purpose 仅是：
  1. 验证端到端 LP 通道：approve → mint → in-range hold → decreaseLiquidity → collect → revoke
  2. 获取真实 NFT position tokenId（PositionManager NFT Transfer event）
  3. 测量 actual position fee accrual（feeGrowthInside / tokensOwed 增量）
  4. 用真实数字校准 EV 模型，让后续 100/500/1000/2000U 尺度判断有信心

expected_outcome：
  小净亏（~$0.02 best case，~$1.00 worst case），换取 actual_fee + tokenId 数据点
```

## 本轮严格不做

```text
this_round_executes_probe   = false
this_round_loads_wallet     = false
this_round_creates_signer   = false
this_round_sends_any_tx     = false
```

## 用法

下游 Phase D / E / F / G / H / I 所有计算与文档**必须**引用以上数值的字面值。
本 candidate freeze 是 dry-run 包的"权威坐标"，不允许任何 phase 修改。
