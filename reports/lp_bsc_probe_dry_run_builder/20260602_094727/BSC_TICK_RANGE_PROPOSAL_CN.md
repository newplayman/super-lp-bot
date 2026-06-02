# BSC Tick Range 提案

- stage: `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: E
- current tick: `-65180`
- tick_spacing: `1`
- WBNB price at proposal time: `$676.96`

## 三档候选

| 名称 | 半宽 (ticks) | tickLower | tickUpper | 价格范围 (USD/WBNB) | 价格 % 范围 | exit_risk (15m) | 说明 |
|---|---|---|---|---|---|---|---|
| **narrow** | ±20 | `-65200` | `-65160` | $675.61 – $678.32 | -0.200% / +0.200% | **high** | ultra-tight；fee 密度极高但 15m 内大概率 OOR |
| **medium** ✅ | ±100 | `-65280` | `-65080` | $670.27 – $683.81 | -0.989% / +1.011% | medium | 平衡档；推荐用于本 probe |
| **wide** | ±500 | `-65680` | `-64680` | $643.97 – $711.79 | -4.873% / +5.144% | low | lazy；几乎无 IL 但 fee 信号弱 |

## 推荐：`medium`

```text
selected_tier        = medium
selected_tickLower   = -65280
selected_tickUpper   = -65080
price_range          = $670.27 – $683.81  (≈ ±1.0%)
```

### 理由

1. **narrow (±20 ticks ≈ ±0.20%)** — 15m 内 USDT/WBNB 移动 >0.20% 经常发生；exit OOR ⇒ **0 fee + 全 IL** — 违背 probe 目的（要测 actual fee accrual）。
2. **wide (±500 ticks ≈ ±5%)** — 安全但 15m 内 fee 几乎为零，给不到信号 — 但 probe 本来就是要校准 fee 模型。
3. **medium (±100 ticks ≈ ±1%)** — goldilocks：0.01% 主对儿 15m 内大概率 in-range；且足够集中，能观察到 `feeGrowthInside` 非零增量，可校准 EV 模型。

### 如果用户偏要改 tier

- **改 narrow**：可接受 — 但只在想压力测试 exit S3 (tick out-of-range stop) 时；必须在 approval phrase 里写明。
- **改 wide**：不建议用于 probe — fee accrual 信号太弱无法校准 sizing；仅适用于"纯通道验证不测 fee"的情况。

## IL / fee_capture proxy（粗估）

| tier | IL 最坏 @ 边界 | fee_capture proxy (相对值) |
|---|---|---|
| narrow | ~0.00005% | 1.00 |
| medium | ~0.00125% | 0.20 |
| wide | ~0.0313% | 0.04 |

## 安全

```text
wallet_or_tx_touched         = false
can_run_probe_now            = false
```
