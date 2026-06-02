# Tick Range 提案

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: G
- run_id: `20260602_112400`
- frozen_pool: `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38`
- current_tick: **-200,443** (Phase F 实时 slot0)
- tick_spacing: 1
- WETH USD anchor: $1,973.88

## 三档 tick range

| tier | lower | upper | 价格下限 (USDC/WETH) | 价格上限 (USDC/WETH) | 半宽 ticks | 半宽 % | 区间 % | 预期 active share |
|---|---|---|---|---|---|---|---|---|
| **narrow** | -200493 | -200393 | $1,963.97 | $1,983.71 | ±50 | 0.50% | 1.00% | ~85% |
| **medium** ★ | -200643 | -200243 | $1,934.73 | $2,013.69 | ±200 | 2.00% | 4.00% | ~45% |
| **wide** | -200943 | -199943 | $1,877.56 | $2,075.01 | ±500 | 5.00% | 10.00% | ~18% |

## 推荐

```text
tier:   medium
horizon: 15m  (若 15m round-trip 干净再考虑 30m)
range:  lower_tick = -200643
        upper_tick = -200243
        ≈  USDC $1,934.73 - $2,013.69 per WETH
```

## 决策理由

1. **narrow (±50 ticks = ±0.5%)**：0.01% 费档下极易在 15m 内跳出范围；1-2 ticks 漂移就能让 LP 失效。适合 ≤5m 短期单边赌注，**不适合 probe**。
2. **medium (±200 ticks = ±2%)**：覆盖 15m 内 Base 上 WETH 典型漂移，~90% 概率保持在范围内；rebalance 成本摊销合理；fee per dollar 约为 narrow 的 1/4 但概率优势补偿。
3. **wide (±500 ticks = ±5%)**：30m 内几乎必然在范围内，但仅 18% 资本在活跃区间，接近 constant-product。

**唯一同时满足"明显在范围内"和"资本有可观活跃度"的档位是 medium**。

## Tick spacing 对齐

| tier | lower mod 1 | upper mod 1 |
|---|---|---|
| narrow | 0 | 0 |
| medium | 0 | 0 |
| wide | 0 | 0 |

所有 lower/upper 都是 `tick_spacing=1` 的整数倍，可直接下到链上。

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
```
