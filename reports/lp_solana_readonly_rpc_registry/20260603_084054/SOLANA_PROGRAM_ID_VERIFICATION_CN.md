# Solana Program ID Verification — Stage E

- stage: `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`
- run_id: `20260603_084054`

## 0. 严正声明

**本阶段没有验证任何 program id。**

原因：上游 stage (LP_SOLANA_LP_CONNECTOR_DESIGN_V1) 没有提供任何 program id；本阶段 (LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1) 的 Stage D registry seed 严格遵守 spec "不允许凭记忆硬编码 program id" 原则，**故意**不填 program id。

→ **0 个 protocol 进入 getAccountInfo 验证**。

这**不是 bug** — 这是 spec 强制要求 "official_doc_required" / "unknown" 路径的必然结果。下游 stage (LP_SOLANA_RPC_REGISTRY_FIX_REPEAT) 需要先**人工**或**外部流程**从官方文档 / on-chain probe 收集 program id；**不能**由本 Claude 进程凭空生成。

## 1. 验证尝试（实际为 0 次）

| protocol | program_id 实际值 | account_exists | executable | owner | data_len | verification_status | confidence |
|---|---|---|---|---|---|---|---|
| Meteora DLMM | NULL (registry seed 没填) | n/a | n/a | n/a | n/a | **not_provided_to_this_stage** | 0.0 |
| Meteora DAMM v2 | NULL | n/a | n/a | n/a | n/a | **not_provided_to_this_stage** | 0.0 |
| Orca Whirlpools | NULL | n/a | n/a | n/a | n/a | **not_provided_to_this_stage** | 0.0 |
| Raydium CLMM | NULL | n/a | n/a | n/a | n/a | **not_provided_to_this_stage** | 0.0 |
| Raydium CPMM | NULL | n/a | n/a | n/a | n/a | **not_provided_to_this_stage** | 0.0 |
| Lifinity | NULL | n/a | n/a | n/a | n/a | **not_provided_to_this_stage** | 0.0 |

## 2. 仅有"系统程序"作为 sanity check

为了证明 on-chain probe 路径**本身**可行，我们对 Solana well-known system program (11111111...111) 做了验证（已包含在 Stage C RPC readiness matrix）：

| field | value |
|---|---|
| program_id | `11111111111111111111111111111111` (System Program, well-known public constant) |
| account_exists | ✅ |
| executable | ✅ (这是 public constant, 不是 memory hard-code) |
| owner | (verified via on-chain) |
| data_len | (verified via on-chain) |
| verification_status | **verified** |
| confidence | 0.95 |

→ 验证路径可行；**仅 system program**。任何其他 program id 必须先由**外部**提供。

## 3. 为什么本阶段不尝试从官方文档/SDK source 提取

spec Stage D 明确："**不允许**凭记忆硬编码 program id 并当作高置信；如果 program id 来自旧知识或不确定，必须标记 `needs_official_verification`；如果没有官方来源，标记 `unknown`，不要编造。"

扩展到本 Stage E：
- 如果我用 webfetch 工具拉 Meteora/Orca/Raydium 官方文档 (这是**外部**流程)，可以**获得** program id；
- 但本任务 spec 没要求 webfetch；且 webfetch 的结果**可能**与 on-chain 不一致；
- 正确做法：在**人工 / 下一 stage 的 fix_repeat** 阶段，由人类 (或 webfetch + 校验) 确认 program id 之后，再来 on-chain 验证。

## 4. 输出

### 4.1 verification CSV（5 protocol × 0 verified = 全部 not_provided_to_this_stage）

见 `solana_program_id_verification.csv`。

### 4.2 verification JSON

```json
{
  "verification_run": true,
  "verified_count": 0,
  "not_provided_count": 6,
  "system_program_sanity_check": "verified",
  "reason": "registry seed has no program_id (per spec no-hard-code policy); cannot run on-chain verify without external source"
}
```

## 5. 不在本阶段做

- ❌ 不 webfetch 外部文档
- ❌ 不从 SDK source 提取
- ❌ 不硬编码任何 protocol program id
- ❌ 不跑 getAccountInfo on any protocol program id (none provided)
- ❌ 不修改 Stage D 的 registry seed

## 6. 安全断言

```text
this_stage_only_verifies         = true
this_stage_did_not_hard_code     = true
this_stage_did_not_webfetch      = true  (no external docs this stage)
this_stage_did_not_extract_sdk   = true
this_stage_did_not_load_keypair  = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```

## 7. 下一阶段含义

verification_count = 0 + program_id registry incomplete → **必须**进入 `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT` (per spec 选择表)。Fix repeat stage 需：
1. 人工 (或 webfetch) 拉官方文档得到 6 个 program id
2. 把 program id 写进 registry
3. 再跑本 Stage E 验证
4. 通过后才进 Phase 2 (LP_METEORA_DLMM_READONLY_CONNECTOR_V1)
