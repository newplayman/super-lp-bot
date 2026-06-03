# Orca + DAMM Registry Readiness — Stage I

- stage: `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`
- run_id: `20260603_084054`

## 1. Orca Whirlpools (P1)

### program id status

**unknown / oficial_doc_required**.

Stage D registry seed 标 `program_id_source: oficial_doc_required`（spec 禁止凭记忆硬编码）。
Stage E on-chain verify **没跑**（无 program id）。

### account discovery readiness

**NO**（无 program id → GPA 不可跑）。

- public RPC 路径**可行** (Stage F sanity check passed)
- 但 Orca Whirlpools-specific GPA 不可跑

### SDK / decode need

**YES** (按 upstream design):

- Orca IDL 公开 on GitHub (TypeScript)
- Account layout 公开 (Whirlpool state, TickArray, PositionBundle, Position)
- v1 Python 路径需用 TypeScript SDK helper 或自己 parse IDL

### next action

| step | 描述 | 状态 |
|---|---|---|
| 1 | 拉 Orca 官方 docs 得到 Whirlpools program id | **need human/webfetch** |
| 2 | on-chain verify executable flag | blocked by step 1 |
| 3 | GPA smoke with dataSize filter | blocked by step 2 |
| 4 | connector | blocked by step 3 |

**结论**: **cannot proceed to Orca Whirlpools connector**.

## 2. Meteora DAMM v2 (P1)

### program id status

**unknown / oficial_doc_required**.

同上。

### account discovery readiness

**NO**（无 program id）。

- DAMM v2 是 2025 launch; account layout 可能没 Meteora DLMM 成熟
- 上游 design 标 complexity = medium

### SDK / decode need

**YES** (按 upstream design):

- Meteora SDK 含 DAMM v2 decoder
- 但**仍需** program id (sdk 不知道 program id)

### next action

| step | 描述 | 状态 |
|---|---|---|
| 1 | 拉 Meteora docs (DAMM v2 部分) 得到 program id | **need human/webfetch** |
| 2 | on-chain verify | blocked |
| 3 | GPA smoke | blocked |
| 4 | connector | blocked |

**结论**: **cannot proceed to Meteora DAMM v2 connector**.

## 3. shared blockers (both Orca + DAMM v2)

1. **No verified program id** — **唯一**关键 blocker
2. **No SDK installed** in v1 (Python only; Meteora/Orca SDK are TypeScript)
3. **No on-chain verify** performed (no pid)
4. **No GPA smoke** performed (no pid)
5. **No token / quote test** performed (depends on protocol's pool universe)

## 4. readiness summary

| protocol | pid_status | discovery_readiness | sdk_need | can_enter_connector |
|---|---|---|---|---|
| Orca Whirlpools | unknown | ❌ | yes (TypeScript) | NO |
| Meteora DAMM v2 | unknown | ❌ | yes (Meteora SDK) | NO |

## 5. 不在本阶段做

- ❌ 不 webfetch 任何官方 docs
- ❌ 不跑 on-chain verify
- ❌ 不接任何 SDK
- ❌ 不调任何 protocol API
- ❌ 不调 Jupiter Quote

## 6. 安全断言

```text
orca_registry_ready              = false
damm_v2_registry_ready          = false
this_stage_did_not_webfetch       = true
this_stage_did_not_run_onchain    = true
this_stage_did_not_call_sdk      = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```

## 7. 下一阶段建议

同 Stage H (Meteora DLMM) — **不能**进 P1 connector。必须先 **LP_SOLANA_RPC_REGISTRY_FIX_REPEAT** 补 program id。
