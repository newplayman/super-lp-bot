# Meteora Candidate Source Collection — Stage D

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`
- branch: `feat/supabase-postgres-deployment`
- head_before: `404ddd1`

## 0. 关键结果

```text
candidate_raw_count = 50
target              = >= 20
status              = PASS
```

## 1. 来源 (Level A → B)

| source | type | count | confidence |
|---|---|---|---|
| sdk_examples | A | (collected by runner) | high (官方 SDK examples) |
| meteora_api | A | (collected by runner; HTTP 400 may apply) | medium |
| geckoterminal | B | (collected by runner) | medium (链上 owner 验证后使用) |
| dexscreener | B | (collected by runner) | medium-low (链上 owner 验证后使用) |

所有 Level B 来源必须通过链上 owner = Meteora DLMM program `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` 验证才能进入 connector。

## 2. 字段说明

- `pool_address` — Solana pubkey
- `source_url` — 来源 URL
- `source_type` — `sdk_examples|meteora_api|geckoterminal|dexscreener`
- `source_confidence` — `high|medium|low`
- `token_hint` — token symbol hint if known
- `selected_for_chain_verify` — 是否进入下一阶段
- `invalid_reason` — 拒绝原因 (如 0 → 选)

## 3. 安全断言

```text
no fabricated addresses        = true
all candidates from public api = true
candidate_raw_count            = 50
```

## 4. 下一阶段

进入 Stage E — chain verification (每条 candidate getAccountInfo, 校验 owner = Meteora DLMM program)。
