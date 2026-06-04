# Raydium CLMM SDK Package Audit — Stage D

- stage: `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_034503`

## 0. 关键结果

```text
package_name             = @raydium-io/raydium-sdk
resolved_version         = 1.3.1-beta.58
install_attempted        = true
install_success          = true
install_dir              = /tmp/lpbot_raydium_clmm_sdk_probe_20260604_034503/node_modules
repo_node_modules_created = false
has_context_required     = false  (pure math + Connection direct)
wallet_required_for_readonly = false
read_only_import_success = true (292 exports loaded)
read_only_decode_proof   = true  (PoolInfoLayout.decode works on 8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj)
```

## 1. Install 验证

```text
$ cd /tmp/lpbot_raydium_clmm_sdk_probe_20260604_034503
$ npm install @raydium-io/raydium-sdk@1.3.1-beta.58 --no-audit --no-fund
exit 0

ls node_modules/@raydium-io/
  raydium-sdk

ls node_modules/@solana/
  buffer-layout, buffer-layout-utils, codecs, codecs-core, ...
```

**no `node_modules` created at repo root**.

## 2. Read-only probe 结果 (SOL/USDC 0.01% CLMM)

| 字段 | 值 |
|---|---|
| pool address | `8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj` |
| owner | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` (Raydium CLMM) ✓ |
| data_len | 1544 bytes (matches `PoolInfoLayout.span`) |
| mintA | `So11111111111111111111111111111111111111112` (SOL) |
| mintB | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` (USDC) |
| mintDecimalsA | 9 |
| mintDecimalsB | 6 |
| tickSpacing | 1 |
| liquidity | 88939050044 |
| sqrtPriceX64 | 4928232675346191513 |
| tickCurrent | -26400 |
| ammConfig | `9iFER3bpjf1PTTCQCfTRu17EJgvsxo9pVyA9QWwEuX4x` |

**Decode works on real mainnet CLMM pool**. PoolInfoLayout handles 8-byte discriminator internally.

## 3. SDK 不需要 keypair 验证

- `PoolInfoLayout.decode(buffer)` — pure JS
- `getPdaTickArrayAddress(poolId, tickIndex)` — pure math, no signer
- `getMultipleAccountsInfo` — read-only RPC
- `getDxByDyBaseIn` / `getDyByDxBaseIn` — pure math, no signer

## 4. 关键 caveat

- **GeckoTerminal dex label**: `raydium` = Raydium AMM v4 (CPMM-like, 752 bytes data) **不是 CLMM**. 必须用 `raydium-clmm` 才是真正的 CLMM 池 (1544 bytes data).
- 上一轮 Meteora V8 中误标 dexId="meteora" 但实际是 Raydium AMM v4 的池也被错分类, 这印证了 spec "B 类 source 必须 chain verify" 的要求
- **AMM v4 池 (data_len=752) 不是 CLMM 池** — Stage F 必须严格按 data_len 1544 过滤

## 5. 路径

- `/tmp/lpbot_raydium_clmm_sdk_probe_20260604_034503/node_modules` — SDK isolated install
- `NODE_PATH=/tmp/...` 用于 runner scripts
- repo root 0 changes

## 6. 下一阶段

进入 Stage E — Raydium CLMM candidate source collection (GeckoTerminal `raydium-clmm` dex only, data_len=1544 only)。
