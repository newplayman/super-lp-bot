# Input Evidence Audit — LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1`
- run_id: `20260603_093136`
- branch: `feat/supabase-postgres-deployment`
- head before: `9c46813` (research: add solana readonly rpc registry 20260603_084054)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/FINAL_VERDICT.json` | `status=WARN`, `usable_rpc_count=2`, `verified_program_count=0`, `not_provided_count=6`, `recommended_next_stage=LP_SOLANA_RPC_REGISTRY_FIX_REPEAT` | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/ONEPAGE_CN.md` | primary endpoint `public_publicnode-110e5a18`; 6 protocols; 0 verified | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/SOLANA_RPC_READINESS_MATRIX_CN.md` | 2/2 endpoints usable; 8/8 methods; solana-core 4.0.0; slot 423,992,924; epoch 981 | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/solana_rpc_readiness_matrix.json` | structured probe results | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/SOLANA PROTOCOL_REGISTRY_SEED_CN.md` | 6 protocols; 0 hard-coded pids | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/solana_protocol_registry_seed.json` | 6 registry entries; program_id_source=oficial_doc_required (5) or sdk_required (1) | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/SOLANA_PROGRAM_ID_VERIFICATION_CN.md` | 0/6 verified; path verified via System Program | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/solana_program_id_verification.json` | structured; 0 verified; System Program sanity OK | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/SOLANA_READONLY_RPC_REGISTRY_NEXT_STAGE_DECISION_CN.md` | 4-option evaluation; FIX_REPEAT selected | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/solana_readonly_rpc_registry_next_stage_decision.json` | structured decision + fix_repeat responsibilities | OK |
| `reports/lp_solana_connector_design/20260603_080347/FINAL_VERDICT.json` | upstream connector design; 6 protocols P0/P1/P2 | OK |

## 2. 关键事实（继承）

```text
previous_stage                     = LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1
previous_status                   = WARN
previous_run_id                   = 20260603_084054
previous_commit                   = 9c46813
recommended_next_stage            = LP_SOLANA_RPC_REGISTRY FIX_REPEAT
usable_rpc_count                  = 2 (public_publicnode-110e5a18; public_mainnetbeta-d6092b5f)
primary_endpoint_id              = public_publicnode-110e5a18
primary_avg_latency_ms           = 314.54
verified_program_count            = 0
not_provided_count                = 6
system_program_sanity_verified    = true
target_protocols                  = 6 (Meteora DLMM, Meteora DAMM v2, Orca Whirlpools, Raydium CLMM, Raydium CPMM, Lifinity)
can_run_probe_now                 = false
solana_wallet_or_keypair_touched = false
tiny_canary_allowed               = "no"
edge_proven                       = "no"
send_hard_disable_still_active   = true
v2_modified_by_this_task         = false
v2_line_count_unchanged          = true (992)
```

## 3. 上一轮阻断原因

- RPC 可用（2/2 public RPC usable; 8/8 methods verified）
- **但 6 protocol program id 全部没填**（spec 明确禁止凭记忆硬编码 program id）
- 所以 program verification / GPA smoke / connector readiness 全部无法继续

## 4. 本轮目标（来自 operator prompt）

1. **修复 Solana protocol registry** — 6 protocol 全部从官方来源获取 program id
2. **只接受 Level A 来源**：
   - 协议官方 docs 域名
   - 协议官方 GitHub org/repo
   - 协议官方 npm package / SDK source
   - Solana explorer 只作为链上验证辅助，**不**单独作为 program id 来源
3. **链上只读验证**（getAccountInfo + 可选 GPA smoke）
4. **不接 wallet / 不读 keypair / 不签 / 不发 tx / 不开 LP / 不 swap / 不 bridge**
5. 仍只读；不进入 connector / 不 probe

## 5. 已知风险与约束

1. **webfetch 可用性**：当前环境**可能不**支持 webfetch（spec 明确"如果 webfetch 不可用，必须写 WEBFETCH_UNAVAILABLE_CN.md"）
2. **当前 Stage C 之前没有 webfetch 调用** — 如有网络访问，需要实测
3. **模型记忆**: spec 明确禁止凭模型记忆填 program id；只接受外部来源
4. **protocols 必须有官方公开来源**：Lifinity 公开资料少；可能维持 unknown

## 6. 官方来源等级（spec 定义）

| Level | 来源 |
|---|---|
| **A** | 协议官方 docs 域名 / 官方 GitHub org / 官方 SDK / 官方 npm package |
| B (allowed) | 协议官方 SDK 常量 / 协议官方 example code |
| **禁止** | blog / Twitter / 论坛 / 非官方 GitHub fork / 模型记忆 / 单看 explorer 猜协议 |

## 7. 安全不变式（继承 + 本轮）

```text
can_run_probe_now                = false
execution_allowed_now            = false
transaction_sent                = false
wallet_or_tx_touched             = false
solana_wallet_or_keypair_touched = false
tiny_canary_allowed              = "no"
edge_proven                      = "no"
manual_approval_required         = true
send_hard_disable_still_active   = true
v2_modified_by_this_task         = false
v2_line_count_unchanged          = true
```

本阶段**不**改任何上述值。

## 8. 决定

继续 Stage C — 官方来源发现。
