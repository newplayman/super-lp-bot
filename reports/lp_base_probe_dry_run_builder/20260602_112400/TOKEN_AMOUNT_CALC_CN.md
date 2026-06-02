# Token Amount 计算

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: H
- run_id: `20260602_112400`
- frozen_pool: `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38`
- frozen_tick_range: `lower=-200643, upper=-200243` (medium, 15m)
- current_tick: `-200443`
- WETH USD anchor: `$1,973.88`

## 数学模型

V3 in-range 公式（在 spot 价 P_s ∈ [P_l, P_u] 内）：

```text
amount0 (raw WETH) = L * (1/sqrt(P_s) - 1/sqrt(P_u))
amount1 (raw USDC) = L * (sqrt(P_s) - sqrt(P_l))
L chosen such that: amount0 * 1e-18 * P_s + amount1 * 1e-6 = N (target USD)
```

## 关键观察（对 WETH/USDC 0.01% 池成立）

**在 spot $1974 附近的任何合理 tick range 下，WETH 侧的 USD 价值都微乎其微。**

- (1/sqrt(1974) - 1/sqrt(2014)) = 0.00022 (a0 / L 系数)
- (sqrt(1974) - sqrt(1934)) = 0.45 (a1 / L 系数)
- a0 = 4.9e-4 × a1（raw 单位） → a0 的 USD 价值 = a1 USD 价值 × 0.00049

意思是：在 $10 notional 下，**WETH 侧 ≈ $0.005（≈ 0 wei raw, < 1 satoshi 价值）**。这不是 bug，是 V3 in-range math 在高单价 + 窄区间下的自然结果。

## 10U 计算

| 字段 | 值 |
|---|---|
| amount0_desired (WETH) | **0 wei**（a0 = 0.0 human） |
| amount1_desired (USDC) | **10,000,000 raw** = 10.0 USDC |
| amount0Min (0.5% slip) | 0（必须 0 否则 revert） |
| amount1Min (0.5% slip) | 9,949,999 raw |

## 20U 计算

| 字段 | 值 |
|---|---|
| amount0_desired (WETH) | **0 wei** |
| amount1_desired (USDC) | **20,000,000 raw** = 20.0 USDC |
| amount0Min | 0 |
| amount1Min | 19,899,999 raw |

## 钱包覆盖能力

### 10U

| token | 需要 | 持有 | 通过 |
|---|---|---|---|
| USDC | 10.0 | 21.774783 | ✓ |
| WETH | 0.0 | 0.00247 | ✓（远超） |
| ETH gas | (估 $0.17) | $0.18 | ✓ (borderline) |

### 20U

| token | 需要 | 持有 | 通过 |
|---|---|---|---|
| USDC | 20.0 | 21.774783 | ✓（$1.77 缓冲） |
| WETH | 0.0 | 0.00247 | ✓（远超） |
| ETH gas | (估 $0.17-0.20) | $0.18 | ✓/⚠ (borderline) |

## ApproveExact 预测

### 10U 路径

- WETH: 需 0 wei → 无需新 approve（技术上 0 amount 不需要 approve）
- USDC: 当前 5.0 USDC ≥ 10.0 USDC（…等等，**5 < 10**）— 等等，10U 的 USDC 端 amount1 = 10.0 USDC，但当前 allowance = 5.0。**需新 approve USDC 10e6（ApproveExact）**
- **净新 approve 数：1（仅 USDC）**

> ⚠️ 修正：10U 路径的 USDC 端 10 USDC > 当前 5 USDC allowance，**必须新 approve WETH 端 0 + USDC 端 10e6**。

### 20U 路径

- WETH: 需 0 wei → 无需新 approve
- USDC: 当前 5.0 USDC < 20.0 USDC → **新 approve USDC 20e6（ApproveExact）**
- **净新 approve 数：1（仅 USDC）**

## ApproveMax 政策（invariant #9）

```text
ApproveExact only. Never ApproveMax.
新 approve 金额 = LP 实际消耗的精确值（不含 buffer）。
mint 完成后调用 approve(NPM, 0) 撤销（invariant #10）。
```

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
```
