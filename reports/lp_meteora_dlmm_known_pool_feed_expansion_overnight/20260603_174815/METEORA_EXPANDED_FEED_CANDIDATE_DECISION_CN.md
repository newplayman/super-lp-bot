# Meteora Expanded Feed Candidate Decision — Stage K

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`

## 0. 决策

```text
recommended_next_stage = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT
status                 = PARTIAL
```

## 1. 决策依据

- 是否有 10/20U realistic positive pool: **False**
- 是否有 near-break-even pool: **True**
- 是否有值得进入 10/20U preflight design 的 pool: **False**
- 是否需要继续扩 known pool feed: **True**
- 是否需要 paid RPC: **True**
- 是否应转 Orca/Raydium: **True**

## 2. Selection rationale

- 选择 `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT` 因为：
  - 0/168+ cells positive in realistic scenario (single-pool EV remains negative)
  - 即使 zero_il_lvr 也不能让任何 cell 变正 (no positive even with no IL)
  - 这意味着**根本原因**不是 IL/LVR，而是 retail-scale 10/20 USD notionals 无法覆盖 fixed cost
  - 需要：(a) 更高费率 pool (Meteora DLMM 支持 5-30% base fee), (b) 其他 AMM 协议 (Orca Whirlpools), 或 (c) 更大 notional (但 10/20 USD 是约束)

## 3. 不选择项 (5 个 allowed)

| stage | candidate? | reason |
|---|---|---|
| LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1 | NO | needs positive realistic cell |
| LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT | NO | only if some positive but not realistic |
| LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1 | YES | only if Meteora entirely unprofitable |
| LP_SOLANA_PAID_RPC_SETUP_REQUIRED | NO | not required for this stage |
| STOP_LP_RESEARCH_NOW | NO | research path still productive |

## 4. 下一阶段

进入 Stage L — Final verdict + ONEPAGE + ARTIFACT_INDEX。
