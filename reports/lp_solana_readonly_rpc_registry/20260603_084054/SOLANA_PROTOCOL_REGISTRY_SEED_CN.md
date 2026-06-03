# Solana Protocol Registry Seed — Stage D

- stage: `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`
- run_id: `20260603_084054`

## 0. 严正声明

**本阶段不**凭记忆硬编码 program id。

spec 明确：
> "**不允许**凭记忆硬编码 program id 并标高置信；如果 program id 来自旧知识或不确定，必须标记 `needs_official_verification`；如果没有官方来源，标记 `unknown`，不要编造。"

本 stage 输出 6 个 protocol 全部标 `program_id_source: official_doc_required` 或 `unknown`，**不**预先填 program id。Stage E (on-chain verification) 才通过 `getAccountInfo` 反查 + executable flag 验证。

## 1. 6-protocol registry seed

| protocol | priority | expected_program_id_status | program_id_source | registry_confidence | must_verify_onchain | selected_for_this_phase |
|---|---|---|---|---|---|---|
| **Meteora DLMM** | P0 | `unknown` (待 Stage E 反查) | `official_doc_required` | 0.3 | yes | yes |
| **Meteora DAMM v2** | P1 | `unknown` | `official_doc_required` | 0.3 | yes | yes |
| **Orca Whirlpools** | P1 | `unknown` | `official_doc_required` | 0.3 | yes | yes |
| **Raydium CLMM** | P2 | `unknown` | `official_doc_required` | 0.3 | yes | yes (smoke only) |
| **Raydium CPMM** | P2 | `unknown` | `official_doc_required` | 0.3 | yes | yes (smoke only) |
| **Lifinity** | P2 | `unknown` | `sdk_required` (资料少) | 0.1 | yes | no (out of scope v1) |

## 2. 为什么 program_id_source 都不是 `existing_artifact`

- 当前 repo `lpbot-v3-origin-check` **没有**任何 artifact 显式提供 Solana program id
- 上游 stage (LP_SOLANA_LP_CONNECTOR_DESIGN_V1) 提到"publicly available; 6 protocols"但**不**给具体 pubkey
- 公开 Solana program id (e.g. Meteora DLMM = `LBUZKhRxbaWWWKDStzLTwpzH4kV5K4Tez5BzJw62T8`) 在我(Claude) 的 training data 截止 2026-01 之前的资料中**可能**出现
- 但 spec 明确要求"不要凭记忆硬编码"
- 正确做法：标 `official_doc_required` → Stage E 用 `getAccountInfo` 在链上反查

## 3. program_id_source 取值定义

| 取值 | 含义 |
|---|---|
| `existing_artifact` | repo 已有 artifact (代码/JSON/MD) 显式记录 |
| `official_doc_required` | 需要从官方文档 (Meteora/Orca/Raydium docs) 获取 |
| `sdk_required` | 需要从 SDK source code / IDL 提取 |
| `unknown` | 没有任何来源；需 on-chain probe |

## 4. 6 个 protocol 详细信息

### 4.1 Meteora DLMM (P0)

- `program_id_source: official_doc_required` (Meteora docs / GitHub)
- `expected_program_id_hint`: 不写入（spec 禁止）
- `must_verify_onchain: yes` (Stage E)
- `selected_for_this_phase: yes`
- `registry_confidence: 0.3` (placeholder, Stage E 验证后提升到 0.95 if executable)

### 4.2 Meteora DAMM v2 (P1)

- 同 DLMM；Meteora 家族 → 共用 SDK / docs
- `program_id_source: official_doc_required`
- `must_verify_onchain: yes`
- `selected_for_this_phase: yes`

### 4.3 Orca Whirlpools (P1)

- `program_id_source: official_doc_required` (Orca docs)
- IDL 公开 (on Orca GitHub); 但 spec 要求**先** on-chain 验证
- `must_verify_onchain: yes`
- `selected_for_this_phase: yes`

### 4.4 Raydium CLMM (P2)

- `program_id_source: official_doc_required`
- `must_verify_onchain: yes` (smoke only; 优先 P0/P1)
- `selected_for_this_phase: yes` (smoke only)

### 4.5 Raydium CPMM (P2)

- 同 CLMM
- `program_id_source: official_doc_required`
- `must_verify_onchain: yes` (smoke only)

### 4.6 Lifinity (P2)

- `program_id_source: sdk_required` (公开 SDK 但资料少; IDL 可能不公开)
- `must_verify_onchain: yes` but **not selected for this phase** (out of scope v1)
- `selected_for_this_phase: no`

## 5. 不在本阶段做

- ❌ 不写 program id 进 artifact
- ❌ 不引用 Meteora/Orca/Raydium 文档 (本阶段不查文档)
- ❌ 不从 SDK source 提取 program id
- ❌ 不从任何来源 hard-code program id
- ❌ 不跑 on-chain probe (Stage E 才做)

## 6. 安全断言

```text
this_stage_only_seeds_registry     = true
this_stage_did_not_run_rpc         = true  (Stage E 才跑 getAccountInfo)
this_stage_did_not_hard_code_pids  = true
solana_wallet_or_keypair_touched   = false
can_run_probe_now                  = false
```
