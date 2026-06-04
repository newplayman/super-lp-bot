# Stable AMM Program Verify — Stage D

- stage: `LP_SOLANA_STABLE_POOL_RESEARCH_V1`
- run_id: `20260604_044118`

## 0. 关键结果

```text
4/4 mainnet programs verified:
  Meteora Stable Swap (ex-Saber)     SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ  ✓ executable
  Meteora DAMM v2                    cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG  ✓ executable
  Orca Whirlpool                     whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc  ✓ executable
  Raydium AMM v4                     675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8  ✓ executable

all 4 owner = BPFLoaderUpgradeab1e11111111111111111111111, data_len = 36 (program metadata)
```

## 1. 链上验证详情

```text
Meteora Stable Swap:  exists=true  executable=true  owner=BPFLoaderUpgradeable
Meteora DAMM v2:      exists=true  executable=true  owner=BPFLoaderUpgradeable
Orca Whirlpool:       exists=true  executable=true  owner=BPFLoaderUpgradeable
Raydium AMM v4:       exists=true  executable=true  owner=BPFLoaderUpgradeable
```

## 2. 重要 caveat: Meteora API 误标

**Meteora DAMM v2 API 错误标记** — `amm-v2.meteora.ag/pools/search?include_pool_token_pairs=USDC-USDT` 返回的池子实际是 Orca Whirlpool 池 (owner=`Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB`), 不是 `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG`. 

```text
32D4zRxNc1EssbJieVHfPhZM3rH6CzfUPrWUuWxD9prG  (Meteora API says USDC-USDT, $1M TVL)
  actual_owner: Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB (Orca Whirlpool)
  data_len: 1387 (Orca V3 CL size, not Meteora DAMM v2)
```

**Spec "B 类 source 必须链上验证" 再次被印证** — Meteora API 返回 metadata 是不可信的, 必须 on-chain owner verify.

## 3. 排除的 candidate (实测 null on mainnet)

- `5dVKb63X9CJD2fmvq2yLKaRcm5ZNEFLc5LxPVLJxuqp7` (potential Saber USDC-USDT, but null on mainnet)
- Meteora DAMM v2 API "USDC-USDT" pools (32D4z, VeUxoU, 2DCJ3F) — all return null or Orca-owned

## 4. confidence

| 维度 | 评分 |
|---|---|
| 4 mainnet programs on-chain verified | 1.0 |
| Meteora DAMM v2 stable pool 实测访问 | 0.6 (API mislabels Orca pools) |
| Orca stable / LST-stable pools | 0.95 (Orca API 14,983 pools) |
| 总体 | 0.85 |

## 5. 路径决策 (Stage E 调整)

由于 Meteora DAMM v2 API 不准, 本轮 **不再依赖 Meteora DAMM v2 API**, 改用:
1. **Meteora Stable Swap (ex-Saber) program** `SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ` — on-chain 验证后, 通过 getProgramAccounts (单 pool fetch via PDA) 找 stable 池
2. **Orca official API** (`api.mainnet.orca.so/v1/whirlpool/list`) — 14,983 池, 过滤 LST-stable → 已有 77 候选
3. **GeckoTerminal `dex=orca_whirlpools`** — 交叉验证
4. **Saber historical data (idempotent)** — `api.saber.so/pools` returns 308 redirect (likely deprecated)

## 6. 下一阶段

进入 Stage E — collect stable-stable / LST-stable pool candidates from **Orca API** (Meteora DAMM v2 stable / Orca Whirlpool stable). Try to find real Meteora Stable Swap (ex-Saber) pool addresses.
