# Base 10U Probe Execution 候选冻结

- stage: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`
- phase: C
- run_id: `20260602_133221`
- wallet_address_masked: `0xb05b...d835`

## 冻结的范围

**本阶段只冻结 "未来如果人工批准执行 probe 的具体目标"。本阶段不授权执行；本阶段不构造 signer / 私钥 / 任何执行脚本。**

## 冻结的字段

| 字段 | 值 |
|---|---|
| chain | **base** (chain_id 8453) |
| pool | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` |
| pair | **WETH/USDC** |
| fee_tier | **100 (0.01%)** |
| tick_spacing | 1 |
| protocol | Uniswap V3 (Base) |
| npm | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` |
| wallet | `0xb05b2872ace4564ff247555b6f7b097d31f3d835` |
| notional options | 10 / 20 USD |
| **recommended first notional** | **10 USD** |
| hold window initial | 15 minutes |
| hold window max extension | 30 minutes |
| tick range (frozen for spec) | lower=-200643, upper=-200243 (medium) |
| token amount 10U | 0 WETH + 10 USDC |
| token amount 20U | 0 WETH + 20 USDC |
| known required action | USDC ApproveExact (allowance 5.0 < 10/20 needed) |

## 这**不是**正 EV 押注

| 字段 | 值 |
|---|---|
| upstream pool-level EV proxy (20U) | **-$0.0600** (real_fee_accrual) |
| upstream actual_position_fee | **未 lineage** (lineage missing) |
| expected realistic outcome | 负 PnL（gas + slippage + IL） |

## Probe 目的（不是盈利）

1. **验证完整 round-trip 路径**：mint → hold → decreaseLiquidity → collect → revoke
2. **捕获 tokenId**：让未来 pipeline 能 trace 这条 position
3. **捕获 actual_position_fee**（替代 pool-level proxy），feeds 进 real_fee_accrual 的 lineage
4. **测量真实 PnL**（gas + slippage + IL/LVR + fees），用来校准 cost model
5. **成功标准** = 完整记录 + 完整退出，**不是赚钱**

## 20U 路径

20U 路径**不**作为首轮执行；只有在 10U round-trip 完整跑过且所有 telemetry 完整落库后，**单独**走一次"20U probe 审批"才能启动。20U 仍要：
- 单独的审批短语（`notional=20`）
- 单独的目标退出标准
- 单独的风控检查
- 单独的 telemetry session_id

## 当前 tick 警告

dry-run 阶段 F 读到的 current_tick = -200443。**未来实际执行前必须重新读 slot0**，并重新评估 range 是否仍合理（同一池子 current_tick 可能在数小时内漂移几十个 tick；medium range [-200643, -200243] 漂移 ±200 ticks 仍 in-range）。

## 4 个 alternates 仍未冻结

| pool | pair | 否决理由 |
|---|---|---|
| `0x9c087eb7` | VIRTUAL/WETH | 钱包无 VIRTUAL；需 swap，超出本轮范围 |
| `0xd0b53d92` | USDC/WETH | upstream EV proxy 异常 |
| `0xb94b2233` | cbBTC/USDC | 钱包无 cbBTC + EV 异常 |
| `0xc211e1f8` | cbBTC/WETH | 钱包无 cbBTC + EV 异常 |

## 校验

```text
frozen_count = 1
expected     = 1
match        = true
```

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
execution_authorized_this_round = false
```

## 执行授权

```text
本阶段不授权执行。
next_required_artifact = LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1  (构建执行脚本，仍不执行)
执行仍需要用户在执行时点单独审批。
```
