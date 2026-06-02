# BSC Token Amount 计算（基于推荐 medium range）

- stage: `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: F
- selected range: `tickLower = -65280`, `tickUpper = -65080` (medium, ≈ ±1%)

## 公式（V3 in-range）

```text
amount0 = L * (sqrtPriceUpper - sqrtPriceCurrent) * 2^96 / (sqrtPriceUpper * sqrtPriceCurrent)
amount1 = L * (sqrtPriceCurrent - sqrtPriceLower) / 2^96
```

## 估算结果

### 10U

| 字段 | 值 |
|---|---|
| L (target) | `38,532,348,599,457,512,490` |
| amount0_desired (USDT) | `4,971,672,871,026,643,667` wei (≈ **4.972 USDT**) |
| amount1_desired (WBNB) | `7,427,805,378,417,271` wei (≈ **0.007428 WBNB ≈ $5.03**) |
| total | **$10.0000** |
| amount0Min @ 50 bps | `4,946,814,506,671,510,449` wei (≈ 4.947 USDT) |
| amount1Min @ 50 bps | `7,390,666,351,525,185` wei (≈ 0.007391 WBNB) |

### 20U

| 字段 | 值 |
|---|---|
| L (target) | `77,064,697,198,915,024,980` |
| amount0_desired (USDT) | `9,943,345,742,053,287,335` wei (≈ **9.943 USDT**) |
| amount1_desired (WBNB) | `14,855,610,756,834,543` wei (≈ **0.014856 WBNB ≈ $10.06**) |
| total | **$20.0000** |
| amount0Min @ 50 bps | `9,893,629,013,343,020,899` wei (≈ 9.894 USDT) |
| amount1Min @ 50 bps | `14,781,332,703,050,370` wei (≈ 0.014781 WBNB) |

## Slippage 算法

- kind: `fixed_bps_floor`
- bps_used: **50** (0.5%)
- 推理：probe 用 0.5% 作为 `amountXMin` 防护底。0.01% PancakeSwap V3 pool 在 ~3.7e24 active liquidity 下，<$100 mint 实际滑点近 0；50 bps 是 quote-time → mint-confirm 之间 tick 漂移的防御缓冲。
- 操作员若有信心可在 approval phrase 里收紧到 10-20 bps
- 上限：**不得超过 100 bps**（更宽对 research probe 不可接受）

## 重要警示

> **本计算仅是估算**。真实 mint 前**必须**用 QuoterV2 重新 quote 一次（价格秒级变动），dry-run 阶段构造的 amount0Min/amount1Min 仅作 ballpark。
> 执行阶段（仍未授权）会重算，**不会**直接使用本文档的数字。

## 安全

```text
this_round_executes_approve_or_mint   = false
wallet_or_tx_touched                  = false
can_run_probe_now                     = false
```
