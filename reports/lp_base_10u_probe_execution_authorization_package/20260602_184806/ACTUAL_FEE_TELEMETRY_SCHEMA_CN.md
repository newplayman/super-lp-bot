# Actual Fee Telemetry Schema

- stage: `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1`
- phase: G
- run_id: `20260602_184806`
- deviation 落地: `feeGrowth_tokensOwed_telemetry_mode_not_implemented`
- **本阶段不执行任何 chain 读取写入 — 仅定义未来执行如何采集 actual fee state。**

## 必须读取的字段

### `NFPM.positions(tokenId)` 12-tuple

| field | type | 用途 |
|---|---|---|
| `nonce` | uint96 | 调试用 |
| `operator` | address | 通常 0 |
| `token0` | address | 校验 WETH |
| `token1` | address | 校验 USDC |
| `fee` | uint24 | 校验 100 |
| `tickLower` | int24 | 校验 == mint 输入 |
| `tickUpper` | int24 | 校验 == mint 输入 |
| `liquidity` | uint128 | **关键** — 用于 IL/PnL 计算 |
| `feeGrowthInside0LastX128` | uint256 | **关键** — fee accrual baseline |
| `feeGrowthInside1LastX128` | uint256 | **关键** — fee accrual baseline |
| `tokensOwed0` | uint128 | **关键** — 已积累待 collect 的 WETH 数量 |
| `tokensOwed1` | uint128 | **关键** — 已积累待 collect 的 USDC 数量 |

### `POOL.slot0()` 7-tuple（与 fee state 同时记录）

| field | type | 用途 |
|---|---|---|
| `sqrtPriceX96` | uint160 | 用于价格折算 |
| `tick` | int24 | 用于 in-range 判定 |
| `observationIndex` | uint16 | n/a |
| `observationCardinality` | uint16 | n/a |
| `observationCardinalityNext` | uint16 | n/a |
| `feeProtocol` | uint8 | 调试用 |
| `unlocked` | bool | sanity |

### `POOL.feeGrowthGlobal0X128()` / `feeGrowthGlobal1X128()`（pool-level）

- 配合 positions(tokenId).feeGrowthInside*LastX128 计算实际 accrual:
  ```text
  accrued_fee0 = (feeGrowthGlobal0X128 - feeGrowthInside0LastX128) * liquidity / Q128
  ```
  仅作 sanity comparison；**真正的 actual fee 来自 collect 返回值**。

### 可选 tick data — `POOL.ticks(tickLower)` / `ticks(tickUpper)`

- 用于精确计算 in-range vs total fee delta（仅当 hold 期间发生 tick 跨越事件时需要）。

## 4 个时间点必须记录

| time point | when | 必读字段 |
|---|---|---|
| `entry_fee_state` | mint receipt 解析成功后立刻 | positions(tokenId)全部 + slot0 + pool_feeGrowthGlobal |
| `hold_fee_state` | hold 期间至少 1 次（建议 7-8 分钟时） | positions(tokenId)全部 + slot0 + pool_feeGrowthGlobal |
| `pre_exit_fee_state` | decreaseLiquidity 发起前 | positions(tokenId)全部 + slot0 + pool_feeGrowthGlobal |
| `post_collect_fee_state` | collect tx 成功 receipt 之后 | positions(tokenId)全部（liquidity 应为 0，tokensOwed 应为 0）+ slot0 |

## telemetry 落盘 schema

```text
reports/lp_base_10u_probe_execution_runtime/<RUN_ID>/actual_fee_state_{point}.json

{
  "schema": "lp_probe_actual_fee_state_v1",
  "point": "entry|hold|pre_exit|post_collect",
  "ts_unix": <int>,
  "run_id": "<RUN_ID>",
  "tokenId": <int>,
  "positions": {
    "nonce": <int>,
    "operator": "0x...",
    "token0": "0x4200...0006",
    "token1": "0x8335...2913",
    "fee": 100,
    "tickLower": <int>,
    "tickUpper": <int>,
    "liquidity": <int>,
    "feeGrowthInside0LastX128": <int>,
    "feeGrowthInside1LastX128": <int>,
    "tokensOwed0": <int>,
    "tokensOwed1": <int>
  },
  "slot0": {
    "sqrtPriceX96": <int>,
    "tick": <int>,
    "feeProtocol": <int>,
    "unlocked": true|false
  },
  "pool_feeGrowthGlobal0X128": <int>,
  "pool_feeGrowthGlobal1X128": <int>,
  "computed_accrued_fee0_via_delta": <int|null>,
  "computed_accrued_fee1_via_delta": <int|null>,
  "in_range": true|false,
  "read_ok": true|false,
  "read_error_repr": null|"<err>"
}
```

post-collect 还需额外的 `collect_receipt.json`：

```text
reports/lp_base_10u_probe_execution_runtime/<RUN_ID>/collect_receipt.json
{
  "schema": "lp_probe_collect_receipt_v1",
  "tx_hash": "0x...",
  "amount0_collected_wei": <int>,
  "amount1_collected_raw_USDC": <int>,
  "via_decoded_event": "Collect(uint256 indexed tokenId, address recipient, uint256 amount0, uint256 amount1)",
  "topic0_collect": "0x40d0efd1a53d60ecbf40971b9daf7dc90178c3aadc7aab1765632738fa8b8f01"
}
```

## 失败处理

| 失败 | 必须 |
|---|---|
| `positions(tokenId)` RPC 调用失败（任一时间点） | telemetry 文件设 `read_ok=false`、`read_error_repr` 记录；`actual_fee_ready = false`；不允许伪造 |
| `slot0` 读取失败 | 同上 |
| `feeGrowthGlobal*` 读取失败 | `computed_accrued_fee*_via_delta = null`；其它字段仍记录；`actual_fee_ready = false` |
| collect tx 失败 / receipt timeout | 写 `collect_failed=true`；进入 manual intervention |

**严禁** 把 pool-level fee growth 当作 position-level actual fee 写入 `actual_fee_*` 字段。pool fee 是上游量，position fee 必须通过 `tokensOwed` 或 collect 返回值。

## actual_fee_ready 判定

```text
actual_fee_ready = (
    entry_read_ok AND
    pre_exit_read_ok AND
    post_collect_read_ok AND
    collect_receipt_present AND
    not collect_failed
)
```

任何一项 false ⇒ `actual_fee_ready = false`，前端 dashboard 显示 "actual fee unavailable，本轮数据不完整"。

## 计算 actual fee earned

```text
actual_fee_earned_WETH_wei  = collect_receipt.amount0_collected_wei  - (decreaseLiquidity 释放的 amount0_wei)
actual_fee_earned_USDC_raw  = collect_receipt.amount1_collected_raw - (decreaseLiquidity 释放的 amount1_raw)
```

(collect 同时收 burn 后的 principal + 累积 fee；要从中扣除 principal 才是 fee；`decreaseLiquidity` 输出的 amount0/amount1 是 principal。)

## 本轮不执行声明

本 stage 是文档定义；**未** 调用任何 `eth_call`，**未** 读取任何 `positions(tokenId)`，**未** 写入任何 actual_fee_state_*.json。所有 schema 都是给未来执行 runner 看的。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
positions_called_this_round   = false
actual_fee_ready              = false  # 还未执行
can_run_probe_now             = false
execution_allowed_now         = false
```
