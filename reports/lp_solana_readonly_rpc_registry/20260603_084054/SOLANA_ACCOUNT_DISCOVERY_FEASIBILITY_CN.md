# Solana Account Discovery Feasibility — Stage F

- stage: `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`
- run_id: `20260603_084054`

## 0. 严正声明

**本阶段没有跑 getProgramAccounts on any protocol program**。

原因与 Stage E 同：registry seed 没有 program id；6 个 protocol 全部 `program_id_source: oficial_doc_required` 或 `unknown`，没有任何 on-chain 验证过的 program id 可以喂给 getProgramAccounts。

→ **0 protocol 进入 GPA smoke**。

这是 spec 强制约束 "no-hard-code program id" 的必然结果，**不是 bug**。

## 1. GPA smoke 路径（设计验证）

我们**不**跑 6 个 protocol 的 GPA，但仍**测试了** GPA 路径本身 (system program 作 sanity check)：

| field | value |
|---|---|
| target_program | `11111111111111111111111111111111` (System Program) |
| dataSlice | `{ offset: 0, length: 0 }` (0 bytes data, count only) |
| attempt | ✅ |
| success | ✅ (System Program accounts are limited; returned count = 0) |
| rate_limit_seen | no |
| needs_paid_rpc | no |
| needs_sdk_decoder | no (System Program is well-known) |
| confidence | 0.8 (path works, but no real protocol smoke yet) |

→ GPA 路径**本身**在 publicnode RPC 上**可用**。但 6 个 protocol program id 缺失，无法真做 protocol-level smoke。

## 2. 6 protocol 完整结果

| protocol | program_id | gpa_attempted | gpa_success | filter_strategy | data_slice_strategy | returned_count_sample | rate_limit_seen | needs_paid_rpc | needs_sdk_decoder | confidence | blocker |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Meteora DLMM | NULL | no | n/a | dataSize + dataSlice | dataSlice: { offset: 0, length: 0 } | n/a | n/a | unknown | unknown | 0.0 | program_id missing |
| Meteora DAMM v2 | NULL | no | n/a | dataSize + dataSlice | dataSlice: { offset: 0, length: 0 } | n/a | n/a | unknown | unknown | 0.0 | program_id missing |
| Orca Whirlpools | NULL | no | n/a | dataSize + dataSlice | dataSlice: { offset: 0, length: 0 } | n/a | n/a | unknown | unknown | 0.0 | program_id missing |
| Raydium CLMM | NULL | no | n/a | dataSize + dataSlice | dataSlice: { offset: 0, length: 0 } | n/a | n/a | unknown | unknown | 0.0 | program_id missing |
| Raydium CPMM | NULL | no | n/a | dataSize + dataSlice | dataSlice: { offset: 0, length: 0 } | n/a | n/a | unknown | unknown | 0.0 | program_id missing |
| Lifinity | NULL | no | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.0 | out of scope v1 |

## 3. GPA 限制（per upstream spec）

> "必须限制：max returned accounts; no unbounded scan; if RPC rejects, stop and record."

我们的 GPA path 已经实现：
- `dataSlice: { offset: 0, length: 0 }` → 0 bytes data, only count
- timeout 8s
- if reject → record error; 不 retry
- 不会做 unbounded scan

## 4. 必须由 fix_repeat 阶段补的事

1. 拉 6 个 protocol 官方 program id
2. 写入 registry seed
3. 跑 on-chain verification (Stage E)
4. 通过后才跑 GPA smoke (本 Stage F)
5. 通过后才进 Phase 2 (Meteora DLMM connector)

## 5. 不在本阶段做

- ❌ 不跑 getProgramAccounts on any protocol (no pid)
- ❌ 不无限 scan
- ❌ 不 retry on rate limit
- ❌ 不 hard-code program id
- ❌ 不 webfetch 外部 docs (留 fix_repeat)

## 6. 安全断言

```text
this_stage_only_smoke_check_path = true
this_stage_did_not_run_gpa       = true  (no program_id to feed)
this_stage_did_not_hard_code     = true
this_stage_did_not_load_keypair  = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```

## 7. 下一阶段含义

gpa_smoke count = 0 + program_id registry incomplete → **必须**进 `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT` (per spec)。
