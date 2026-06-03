# Meteora DLMM SDK Feasibility Next-Stage Decision — Stage I

- stage: `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1`
- run_id: `20260603_130532`

## 0. 决策

```text
recommended_next_stage = LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1
default_when_no_explicit_choice = LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1
```

## 1. 4 选项评估

| next stage | 触发条件 | 是否触发 |
|---|---|---|
| `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1` | SDK installed + known pool decode smoke success + quote smoke success OR path clearly implementable + known_pool_feed recommended | **✅ 触发** (V3 全满足; quote blocked on public RPC, but documented + connector V1 can write 3/6 tables without quotes) |
| `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT` | SDK path promising but smoke incomplete | ❌ (V3 已完成 SDK install + full decode + schema + decision; no work to repeat) |
| `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` | known-pool feed insufficient AND paid RPC required | ❌ (known-pool feed sufficient for Phase 2A; paid RPC is Phase 2B concern, not stage gate) |
| `STOP_LP_RESEARCH_NOW` | no safe read-only Meteora path | ❌ (read-only path fully viable: 2/2 pools decoded, schema designed) |

## 2. entry conditions for LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1

| condition | V3 状态 | 证据 |
|---|---|---|
| SDK installed/inspected | ✅ | Stage C: npm install @meteora-ag/dlmm@1.9.10 in /tmp/lpbot_meteora_dlmm_sdk_probe_20260603_130532 |
| known pool decode smoke success | ✅ | Stage E: 2/2 pools full LbPair decode (token mints + decimals + bin_step + active_bin + fees + reserves) |
| quote smoke success OR path feasible | ⚠️ | Stage F: 0/4 quote success (blocked on public RPC); path feasible with paid RPC or known bin array cache (Phase 2B) |
| known_pool_feed recommended | ✅ | Stage D + H: 2 pools from official SDK examples; recommended as near-term path |

→ **3/4 conditions fully met, 1/4 partial (quote blocked on public RPC, documented; not blocking connector V1 because V1 only writes 3/6 tables)**

## 3. 进步 (V2 → V3)

| metric | V2 (FIX_REPEAT_V2) | V3 (this round) | improvement |
|---|---|---|---|
| SDK install | not done (V2 used stdlib-only Python equivalent) | **done** (npm install @meteora-ag/dlmm@1.9.10 in /tmp) | **full fix** |
| known pool decode | partial (Python bytes-level; struct fields misaligned) | **full** (2/2 pools real LbPair decode via SDK) | **full fix** |
| quote smoke | not done | done (0/4 quote success; root cause documented) | **documented blocker** |
| connector schema | not designed | **designed** (6 tables; field coverage 14/14) | **new artifact** |
| discovery strategy decision | not decided (V2 recommended paid_rpc_gpa without comparing) | **decided** (3 paths evaluated; known_pool_feed_sdk_decode selected for Phase 2A) | **decided** |

## 4. 风险 (per spec 边界)

- connector V1 risk: 实现 6 张表需要写 research-only storage (Postgres shadow or sqlite); 3/6 表活跃, 3/6 blocked on public RPC (data_confidence='blocked'); **不**做 quote / EV
- paid RPC: Phase 2B 补; 不在 connector V1
- 已知 pool feed: 2 pools only; operator 可扩 to 10+; connector V1 frozen feed 维持 2

## 5. 不在本阶段做

- ❌ 不实现 6 张表
- ❌ 不跑 connector V1 代码
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不调 swap / open LP / close LP / collect fee / bridge
- ❌ 不 paid RPC call

## 6. 安全断言

```text
this_stage_only_decision       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 7. 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`（无需操作员声明）
- 关键 input 需求（建议下个 prompt 提供）:
  1. **research-only storage 选择** (Postgres shadow / sqlite / JSON file); 默认建议 sqlite (简单, 可迁移到 Postgres shadow)
  2. **known pool feed 扩展** (operator 可人工 curate 5-10 个 Meteora UI top pools; 否则维持 2)
  3. (optional) **paid RPC 决策** (Phase 2B; 不在 connector V1 必须)
  4. (optional) **是否同意 connector V1 + paid RPC 合并** (即 "一阶段" 同时实现表 + quote; 风险复杂 stage)
- 不建议改选 connector V1 + paid RPC 合并 (3/6 表先跑稳, 再补 paid RPC; 风险隔离)
- 不建议 STOP (2/2 pool full decode + 6-table schema + strategy decided = 显著进步; 不是 structural failure)
- 即便选 connector V1, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
