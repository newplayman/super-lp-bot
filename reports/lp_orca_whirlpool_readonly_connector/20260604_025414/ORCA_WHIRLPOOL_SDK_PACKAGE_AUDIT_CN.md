# Orca Whirlpool SDK Package Audit — Stage D

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`

## 0. 关键结果

```text
package_name             = @orca-so/whirlpools
resolved_version         = 8.0.0
install_attempted        = true
install_success          = true
install_dir              = /tmp/lpbot_orca_whirlpool_sdk_probe_20260604_025414/node_modules
repo_node_modules_created = false
has_context_required     = true  (setRpc or createSolanaRpc passed per call)
wallet_required_for_readonly = false
read_only_import_success = true (42 exports loaded)
read_only_decode_proof   = true  (fetchConcentratedLiquidityPool works on SOL/USDC across 4 tickSpacings)
```

## 1. Install 验证

```text
$ cd /tmp/lpbot_orca_whirlpool_sdk_probe_20260604_025414
$ npm install @orca-so/whirlpools@8.0.0 --no-audit --no-fund
exit 0

ls node_modules/@orca-so/
  tx-sender
  whirlpools             8.0.0
  whirlpools-client      7.0.0
  whirlpools-core        7.0.0

ls node_modules/@solana-program/
  address-lookup-table
  compute-budget
  memo
  system
  token
  token-2022
```

**no `node_modules` created at repo root**.

## 2. Read-only probe 结果 (SOL/USDC 4 个 tickSpacing)

| tickSpacing | pool address | feeRate (raw) | feeRate (bps) | tickCurrentIndex |
|---|---|---|---|---|
| 4 | `Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE` | 400 | 4 | -26570 |
| 8 | `7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm` | 500 | 5 | -26567 |
| 64 | `HJPjoWUrhoZzkNfRpHuieeFk9WcZWjwy6PBjZ81ngndJ` | 3000 | 30 | -26573 |
| 128 | `DFVTutNYXD8z4T5cRdgpso1G3sZqQvMHWpW2N99E4DvE` | 10000 | 100 | -26640 |

**feeRate 编码说明**: Orca Whirlpools 用 `u16` feeRate, value = bps * 100 (e.g. 4bps = 400, 100bps = 10000)。

pool object 字段 (from SDK):
- `address` — pool pubkey
- `price` — current price
- `tickSpacing`
- `feeRate`, `protocolFeeRate`
- `liquidity` (Q64.64)
- `sqrtPrice` (Q64.64)
- `tickCurrentIndex`
- `tokenMintA`, `tokenVaultA`, `feeGrowthGlobalA`
- `tokenMintB`, `tokenVaultB`
- `protocolFeeOwedA`, `protocolFeeOwedB`

## 3. SDK 不需要 keypair 验证

- `fetchConcentratedLiquidityPool` 接收 `rpc` 和 `address` 参数, 无 signer
- `fetchSplashPool` 同上
- `fetchWhirlpoolsByTokenPair` 同上 (但内部用 GPA — public RPC 会 fail)
- `getPayer`, `loadWallet`, `setPayerFromBytes` 是 write 路径 helpers, 本轮不用

## 4. Orca 官方 API (辅助源)

```text
URL:    https://api.mainnet.orca.so/v1/whirlpool/list
HTTP:   200
bytes:  17,979,106
count:  14983 whirlpools
fields: address, tokenA, tokenB, tickSpacing, price, lpFeeRate, protocolFeeRate,
        tvl, volume {day, week, month}, feeApr {day, week, month}, whirlpoolsConfig
```

这是补充 source, 给 candidate collection 提供 14983 池的 metadata 索引 (不再依赖 GeckoTerminal / DexScreener 第三方数据)。

## 5. SDK 限制 (接受)

- `fetchWhirlpoolsByTokenPair` 内部用 GPA → public RPC fail。本轮用 Orca official API 拿到 14983 池 metadata, 再用 SDK decode 真实链上 state (read-only fetchConcentratedLiquidityPool)。
- `getSwapQuote` 是 internal, 通过 `swapInstructions` 的 quote-only 模式访问, 或直接用 SDK helper。

## 6. 路径

- `/tmp/lpbot_orca_whirlpool_sdk_probe_20260604_025414/node_modules` — SDK isolated install
- `NODE_PATH=/tmp/...` 用于 runner scripts
- repo root 0 changes

## 7. 下一阶段

进入 Stage E — Orca candidate source collection。
