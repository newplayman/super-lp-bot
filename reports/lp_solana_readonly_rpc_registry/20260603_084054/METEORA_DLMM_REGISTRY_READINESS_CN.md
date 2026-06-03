# Meteora DLMM Registry Readiness — Stage H

- stage: `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`
- run_id: `20260603_084054`

## 0. 7 个必答问题

### Q1. 是否有 verified DLMM program id?

**NO.**

Stage D registry seed 标 `program_id_source: oficial_doc_required`（spec 禁止凭记忆硬编码 program id）。
Stage E on-chain verification **没跑**（无 program id 可验证）。
所以 verified program id = 0。

### Q2. 是否能读取 program account?

**路径可行 (verified via System Program)**；**DLMM 不可**（无 program id）。

Stage C RPC readiness 显示 `getAccountInfo` on System Program 工作正常（executable=true）。该路径**本身**可用于 DLMM（**前提**有 program id）。

### Q3. 是否能做 pool discovery?

**NO**（无 verified program id → getProgramAccounts 无法调用）。

Stage F GPA smoke 显示**路径本身**在 publicnode RPC 上**可用**（System Program 返回 0 accounts，dataSlice 0 字节，0 rate limit）。但 DLMM-specific GPA 不可跑（无 pid）。

### Q4. 是否需要 Meteora SDK?

**YES**（按 upstream design）。

- DLMM account layout (LbPair) 不是公开 IDL; 需要 Meteora SDK 内部 binary decoder
- 上游 design Stage E (connector) 推荐 Meteora SDK (TypeScript)
- v1 Python 路径只能**反查 IDL**或**用 TypeScript helper** sub-process

### Q5. 是否需要 indexer/API?

**MAYBE** (per upstream design)。

- `dlmm-api.meteora.ag` 提供 pool metadata; 公开 HTTP GET
- v1 可优先用 indexer (avoid GPA 全扫)
- 但**仍需** verify indexer 数据 vs on-chain

### Q6. 是否可进入 LP_METEORA_DLMM_READONLY_CONNECTOR_V1?

**NO**。

`LP_METEORA_DLMM_READONLY_CONNECTOR_V1` 的 spec 条件 (Stage J 后续):
> "Solana RPC usable AND Meteora DLMM program verified or enough registry confidence AND account discovery feasible or SDK/API path feasible"

当前状态：
- Solana RPC usable ✅
- Meteora DLMM program verified ❌
- account discovery feasible ❌ (no pid)
- SDK/API path feasible ✅ (in design; **not yet wired**)
- registry confidence = 0.3 (placeholder)

→ **3/4 条件不满足**。**不能**进 LP_METEORA_DLMM_READONLY_CONNECTOR_V1。

### Q7. 主要 blocker

1. **No verified program id** — 这是**唯一**关键 blocker
2. SDK 缺 / indexer 缺 — 次要，可由 fix_repeat 阶段解决
3. Public RPC rate limit — minor (cache + retry policy 即可)

## 1. readiness summary

| dimension | status | confidence |
|---|---|---|
| RPC usable | ✅ | 1.0 |
| Program id verified | ❌ | 0.0 |
| Pool discovery feasible | ❌ | 0.0 |
| SDK available | partial (design only) | 0.3 |
| Indexer/API available | partial (design only) | 0.3 |
| Token / quote reference | partial (design only) | 0.5 |
| **Overall readiness for connector** | **NO** | **0.3** |

## 2. 不在本阶段做

- ❌ 不 webfetch Meteora 官方 docs 拿 program id (留 fix_repeat)
- ❌ 不跑 on-chain verify (no pid)
- ❌ 不跑 GPA (no pid)
- ❌ 不接 Meteora SDK
- ❌ 不调 dlmm-api.meteora.ag
- ❌ 不调 Jupiter Quote

## 3. 安全断言

```text
meteora_dlmm_registry_ready        = false
this_stage_did_not_webfetch         = true
this_stage_did_not_run_onchain      = true  (no pid)
this_stage_did_not_run_gpa          = true
this_stage_did_not_call_sdk         = true
this_stage_did_not_call_indexer     = true
solana_wallet_or_keypair_touched   = false
can_run_probe_now                  = false
```

## 4. 下一阶段建议

不能进 LP_METEORA_DLMM_READONLY_CONNECTOR_V1（3/4 条件不满足）。
应先 **LP_SOLANA_RPC_REGISTRY_FIX_REPEAT** 来补 program id 之后，再来本 stage 重做 readiness。
