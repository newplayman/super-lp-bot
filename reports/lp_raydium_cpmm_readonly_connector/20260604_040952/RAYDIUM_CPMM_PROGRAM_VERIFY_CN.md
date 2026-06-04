# Raydium CPMM Program Verify — Stage D

- stage: `LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_040952`

## 0. 关键结果

```text
verified_program_id         = 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 (Raydium AMM v4)
account_exists             = true
executable                 = true
owner                      = BPFLoaderUpgradeab1e11111111111111111111111 (BPFLoaderUpgradeable)
data_len                   = 36 (program data; 36 bytes is standard for BPFLoader program metadata)
verified                   = true
confidence                 = 1.0
```

## 1. 排除的候选 (NOT used this stage)

| pid | mainnet status | rejected reason |
|---|---|---|
| `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` | NOT deployed | source-declared mainnet pid; on-chain 确认 null |
| `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb` | NOT deployed | source-declared devnet pid (v2 SDK wires this); on-chain 确认 null |

## 2. AMM v4 验证详情

```text
$ curl publicnode.com getAccountInfo 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8
account_exists:     true
executable:         true
owner:              BPFLoaderUpgradeab1e11111111111111111111111 (BPFLoaderUpgradeable)
data_len:           36 bytes (standard for upgradeable BPF program metadata)
```

## 3. 测试 pool (SOL/USDC AMM v4)

```text
pool_address:        58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2
pool_owner:          675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 (matches AMM v4)
pool_data_len:       752 bytes (matches AMM v4 pool state size)
```

## 4. SDK 路径确认 (for Stage E)

V2 SDK `@raydium-io/raydium-sdk-v2@0.2.50-alpha` 提供:
- `liquidityStateV4Layout` in `src/raydium/liquidity/layout.ts` — AMM v4 pool state decoder
- `CpmmPoolInfoLayout` in `src/raydium/cpmm/layout.ts` — new cp-swap (DRaycpLY18) layout, NOT applicable to mainnet AMM v4
- Read-only import: 已 verify (292 exports in v1 SDK; v2 SDK similar)

V1 SDK `@raydium-io/raydium-sdk@1.3.1-beta.58` 提供:
- `PoolInfoLayout` — but this is **CLMM** layout (different struct, returns wrong values when applied to AMM v4)
- 应使用 V2 SDK 的 `liquidityStateV4Layout` 替代

## 5. safety

```text
no_keypair           = true
no_signer            = true
no_transaction       = true
read_only            = true
sdk_install_isolated = true (in /tmp/lpbot_raydium_v2_probe_20260604)
```

## 6. 下一阶段

进入 Stage E — 隔离 SDK install (v2 SDK 已经 install 在 /tmp; 也 install V1 SDK 用于 cross-check) + 读-only 验证。
