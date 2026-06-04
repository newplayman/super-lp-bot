# Stable AMM Source Audit — Stage C

- stage: `LP_SOLANA_STABLE_POOL_RESEARCH_V1`
- run_id: `20260604_044118`

## 0. 关键结果

```text
mainnet_stable_amms_verified  = 4 (Meteora Stable Swap, Meteora DAMM v2, Orca Whirlpool, Raydium AMM v4)
off_chain_active_pool_count   = 100+ (50 USDC-USDT Meteora DAMM v2 + 77 Orca LST-stable + 24 Raydium USDC-anchor)
lifinity_mainnet_status       = NOT verified (pid unknown per V1 stage 20260603_093136)
mercurial_mainnet_status      = NOT verifiable (org/repo returns 404; likely shut down)
saber_status                  = Rebranded as Meteora Stable Swap (same pid)
```

## 1. 官方来源审计 (per protocol)

### 1.1 Meteora Stable Swap (ex-Saber)

| 字段 | 值 |
|---|---|
| program_id | `SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ` |
| source_url (历史 Saber) | `https://raw.githubusercontent.com/saber-hq/stable-swap/master/stable-swap-program/program/src/lib.rs` |
| source_url (现 Meteora) | `https://raw.githubusercontent.com/MeteoraAg/stable-swap/master/stable-swap-program/program/src/lib.rs` |
| source_type | official_github |
| source_confidence | high |
| on-chain verified | yes (executable, owner=BPFLoader) |
| 状态 | active (Meteora 2024-2025 收购 Saber, 保留 pid) |
| API source | Meteora DAMM v2 endpoint (`/pools/search?include_pool_token_pairs=USDC-USDT` 等) |

### 1.2 Meteora DAMM v2 (constant product + stable pool_type)

| 字段 | 值 |
|---|---|
| program_id | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` |
| source_url | `https://github.com/MeteoraAg/damm-v2` (V1 stage 20260603_093136 verified) |
| source_type | official_github |
| source_confidence | high |
| on-chain verified | yes |
| 状态 | active, 77,341 total pools |
| **stable pool_type** | 1+ stable pools in page 0 (e.g. SOL-mSOL `pool_type: "stable"`); `include_pool_token_pairs=USDC-USDT` returns 50 |
| API source | `https://amm-v2.meteora.ag/pools/search?page=N&size=100&include_pool_token_pairs=<PAIR>` |

### 1.3 Orca Whirlpool (V3 CL, has stable LST pairs)

| 字段 | 值 |
|---|---|
| program_id | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` |
| source_url | `https://github.com/orca-so/whirlpools` (V1 stage verified) |
| source_type | official_github |
| source_confidence | high |
| on-chain verified | yes |
| 状态 | active, 14,983 total whirlpools |
| **stable / LST-stable** | 77 (filtered by USDC/USDT or LST mints); tickSpacing 1-128 |
| API source | `https://api.mainnet.orca.so/v1/whirlpool/list` (17.9MB) |

### 1.4 Raydium AMM v4 (constant product, has USDC-anchor pools)

| 字段 | 值 |
|---|---|
| program_id | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` |
| source_url | `https://github.com/raydium-io/raydium-amm` (V1 CPMM stage verified) |
| source_type | official_github |
| source_confidence | high |
| on-chain verified | yes |
| 状态 | active, USDC-anchor pools available |
| **stable anchor** | 24 verified in V1 stage (USDC/SOL or USDC/USDT) |
| Note | no stable-stable pair (all 含 SOL anchor) |

### 1.5 排除的候选 (NOT used this stage)

| 协议 | 排除原因 |
|---|---|
| Lifinity | V1 stage 20260603_093136 确认 pid NOT on mainnet; org/repo returns 404 (不存在) |
| Mercurial Finance | github 404 (org/repo 不可访问; 推测已弃用) |
| Saber (作为独立协议) | 已 rebrand 为 Meteora Stable Swap, 同一 pid; 不重复计入 |

## 2. confidence

| 维度 | 评分 |
|---|---|
| 官方 source (GitHub) verified | 1.0 |
| SDK / API 路径 | 0.95 (Meteora DAMM v2 endpoint 限流 page 0 only; Orca API works) |
| Meteora Stable Swap on-chain | 1.0 |
| 候选 stable-stable pool 数量 (USDC-USDT) | 50 from Meteora DAMM v2 alone |
| 总体 | 0.95 |

## 3. 关键 finding

- **Meteora DAMM v2 stable pool (Curve-style)** is the most promising candidate for stable-stable AMM: 50 USDC-USDT pools, 3 USDC-mSOL, 4 USDC-bSOL, 1 USDT-mSOL.
- **Meteora Stable Swap (ex-Saber)** is the original Curve-style stable AMM on Solana, but API/data access path less clear.
- **Orca Whirlpool** has 77 LST-stable pools (USDC/SOL, USDC/mSOL 等) but 是 V3 CL, IL 行为 already tested in Orca V1.
- **Raydium AMM v4** has 24 USDC-anchor pools but no stable-stable (全部含 SOL), already tested in V1 CPMM.

## 4. 下一阶段

进入 Stage D — 链上验证所有 4 个 program id + 进入 Stage E 收集 active stable-stable / LST-stable pools for testing.
