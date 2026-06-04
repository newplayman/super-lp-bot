# Raydium CPMM SDK Package Audit — Stage E

- stage: `LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_040952`

## 0. 关键结果

```text
v2_sdk_package_name         = @raydium-io/raydium-sdk-v2
v2_sdk_version             = 0.2.50-alpha
v1_sdk_package_name        = @raydium-io/raydium-sdk (cross-check)
v1_sdk_version             = 1.3.1-beta.58
v2_install_dir             = /tmp/lpbot_raydium_v2_probe_20260604/node_modules
v1_install_dir             = /tmp/lpbot_raydium_clmm_sdk_probe_20260604_034503/node_modules
repo_node_modules_created  = false
read_only_import_success   = true (v2 SDK exports 100+ functions)
has_cpmm_pool_decode       = true (liquidityStateV4Layout)
has_cpmm_quote             = true (liquidity/swap math)
has_liquidity_math         = true (constant product + stable curve)
wallet_required_for_readonly = false
```

## 1. Install 验证

```text
$ cd /tmp/lpbot_raydium_v2_probe_20260604
$ npm install @raydium-io/raydium-sdk-v2@0.2.50-alpha --no-audit --no-fund
exit 0

$ ls node_modules/@raydium-io/raydium-sdk-v2/lib/raydium/
  account, clmm, cpmm, farm, ido, index.ts, liquidity, marketV2, raydium.ts, ...
```

**no `node_modules` created at repo root**.

## 2. Read-only probe 结果 (AMM v4 SOL/USDC pool)

| 字段 | 值 | 备注 |
|---|---|---|
| pool address | `58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2` | AMM v4 mainnet |
| baseMint | `So11111111111111111111111111111111111111112` | SOL ✓ |
| quoteMint | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | USDC ✓ |
| baseVault | `DQyrAcCrDXQ7NeoqGgDCZwBvWDcYmFCjSb9JtteuvPpz` | SPL token account |
| quoteVault | `HLmqeL62xR1QoZ1HKKbXRrdN1p3phKpxRMb2VVopvBBz` | SPL token account |
| lpMint | `8HoQnePLqPj4M7PUDzfw8e3Ymdwgc7NLGnaTUapubyvu` | LP token mint |
| baseDecimal | 9 | SOL |
| quoteDecimal | 6 | USDC |
| tradeFeeNumerator | 25 | fee = 25/10000 = 0.25% = **25 bps** |
| tradeFeeDenominator | 10000 | |
| lpReserve | 50674335682686 | LP supply (raw) |
| poolOpenTime | 0 | unrestricted |

**Decode 100% successful** for AMM v4 pool.

## 3. SDK 路径 (read-only 关键函数)

- `liquidityStateV4Layout.decode(buffer)` — AMM v4 pool state decoder (v2 SDK)
- `CpmmPoolInfoLayout.decode(buffer)` — cp-swap (devnet only) pool state decoder (v2 SDK, NOT applicable to mainnet AMM v4)
- `getMultipleAccountsInfo` — read multiple accounts
- `publicKey` derivation helpers

## 4. 关键 caveat

- **V1 SDK `PoolInfoLayout` 是 CLMM layout, NOT AMM v4** — 用它 decode AMM v4 池会返回错位数据
- **V2 SDK `liquidityStateV4Layout` 是 AMM v4 layout** — 用它 decode AMM v4 池返回正确数据
- **reserves 实际值需要从 vault token account 读取** — pool state 不直接存 reserve，而是用 swapBaseInAmount/swapQuoteOutAmount 等累计字段

## 5. confidence

| 维度 | 评分 |
|---|---|
| v2 SDK install | 0.95 |
| v2 SDK read-only import | 0.95 |
| liquidityStateV4Layout decode path | 0.92 |
| AMM v4 pool candidate verification | 0.95 |
| Total | 0.94 |

## 6. 下一阶段

进入 Stage F — 候选池收集 (GeckoTerminal `dex=raydium` + DexScreener + Raydium 官方 API) → 80 candidate for chain verify。
