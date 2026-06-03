# Input Evidence Audit — LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1

- stage: `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`
- run_id: `20260603_084054`
- branch: `feat/supabase-postgres-deployment`
- head before: `bf92f4c` (research: design solana lp connector 20260603_080347)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_solana_connector_design/20260603_080347/FINAL_VERDICT.json` | `status=PASS`, `recommended_next_stage=LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`, `implementation_status=phase_1_pending`, `solana_connector_design_complete=true`, `can_run_probe_now=false` | OK |
| `reports/lp_solana_connector_design/20260603_080347/ONEPAGE_CN.md` | p0=Meteora DLMM; p1=Orca+Meteora DAMM v2; p2=Raydium+Lifinity | OK |
| `reports/lp_solana_connector_design/20260603_080347/SOLANA_LP PROTOCOL_TARGET_MATRIX_CN.md` | 6 protocols with quote/fee/position/il/SDK fields | OK |
| `reports/lp_solana_connector_design/20260603_080347/solana_lp_protocol_target_matrix.json` | 6 protocol entries with priority + recommended_next_action | OK |
| `reports/lp_solana_connector_design/20260603_080347/SOLANA_DATA_SOURCE_FEASIBILITY_CN.md` | 11 RPC methods; 5 indexer/API; rate limits; cache strategy | OK |
| `reports/lp_solana_connector_design/20260603_080347/solana_data_source_feasibility.json` | structured RPC + indexer data; rate limits; cache TTLs | OK |
| `reports/lp_solana_connector_design/20260603_080347/METEORA_DLMM_CONNECTOR_DESIGN_CN.md` | bin-based; preflight 12 gates | OK |
| `reports/lp_solana_connector_design/20260603_080347/meteora_dlmm_connector_design.json` | 10_20u_probe_preflight fields; data_confidence | OK |
| `reports/lp_solana_connector_design/20260603_080347/ORCA_WHIRLPOOL_CONNECTOR_DESIGN_CN.md` | tick array; NFT position; complexity/blockers | OK |
| `reports/lp_solana_connector_design/20260603_080347/orca_whirlpool_connector_design.json` | structured; vs_meteora_dlmm comparison | OK |
| `reports/lp_solana_connector_design/20260603_080347/RAYDIUM_CONNECTOR_DESIGN_CN.md` | CLMM + CPMM; P2 priority | OK |
| `reports/lp_solana_connector_design/20260603_080347/raydium_connector_design.json` | structured; both sub-protocols | OK |
| `reports/lp_solana_connector_design/20260603_080347/SOLANA_CONNECTOR_IMPLEMENTATION_ROADMAP_CN.md` | 6 phases; Phase 1 = RPC + registry | OK |
| `reports/lp_solana_connector_design/20260603_080347/solana_connector_implementation_roadmap.json` | structured phases with script_name + report_dir + safety_gate | OK |

## 2. 关键事实（继承）

```text
previous_stage                  = LP_SOLANA_LP_CONNECTOR_DESIGN_V1
previous_status                = PASS
previous_run_id                = 20260603_080347
recommended_next_stage         = LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1
implementation_status          = phase_1_pending
solana_connector_design_complete = true
evm_v3_path_paused             = true
target_protocol_count          = 6
p0_protocol                    = Meteora DLMM
p1_protocols                   = Orca Whirlpools, Meteora DAMM v2
p2_protocols                   = Raydium CLMM, Raydium CPMM, Lifinity
schema_proposal_ready          = true
survival_ev_adaptation_ready   = true
probe_preflight_design_ready   = true
implementation_roadmap_ready   = true
can_run_probe_now              = false
execution_allowed_now          = false
solana_wallet_or_keypair_touched = false
tiny_canary_allowed            = "no"
edge_proven                    = "no"
send_hard_disable_still_active = true
v2_modified_by_this_task       = false
v2_line_count_unchanged        = true (992)
```

## 3. 已知缺口（来自 upstream）

1. **Meteora DLMM account layout** 不全公开；需要 on-chain inspection 或 SDK
2. **Orca Whirlpools tick array layout** bit offset 需实测
3. **Jupiter Quote API** rate limit；v1 应有 fallback
4. **Meteora DAMM v2** 2025 launch；account layout 较新
5. **Lifinity** 公开资料少；out of scope v1

## 4. 本轮目标（来自 operator prompt）

1. **只读**实现 Solana RPC readiness + protocol registry + 4 个 program/account source registry
2. 不接钱包
3. 不读 keypair
4. 不签名
5. 不发交易
6. 不开 LP
7. 不 swap
8. 不 bridge

→ **确认 Solana 公开数据能不能读、哪些协议能进入下一层 connector**。

## 5. 关键设计约束（来自 spec）

### 5.1 RPC 来源

- env vars: `SOLANA_RPC_URL`, `SOLANA_RPC_PRIMARY`, `LPBOT_SOLANA_RPC_URL`
- env vars (RPC only, never print): `HELIUS_RPC_URL`, `QUICKNODE_SOLANA_RPC_URL`
- public fallback: `https://api.mainnet-beta.solana.com`, `https://solana.publicnode.com`

### 5.2 输出 redacted

**不得**打印完整 RPC URL；**只**输出 `endpoint_id` / `source_type` / `host_hash`。

### 5.3 验证 8 项 RPC 方法

`getHealth`, `getVersion`, `getSlot`, `getBlockHeight`, `getLatestBlockhash`, `getEpochInfo`, `getGenesisHash`, `getAccountInfo` on system program.

### 5.4 protocol registry seed

- 6 协议；`program_id_source` 必须标 `existing_artifact` / `official_doc_required` / `sdk_required` / `unknown`
- **不允许**凭记忆硬编码 program id 并标高置信
- 如果不确定 → 标 `unknown` 或 `needs_official_verification`

### 5.5 account discovery feasibility

- 小规模 smoke；**不**做大范围 scan
- 必须有 `dataSlice` / `memcmp` / `limit` 策略
- 如果 RPC reject → **停**并记录

## 6. 安全不变式（继承 + 本轮）

```text
can_run_probe_now                       = false
execution_allowed_now                   = false
tiny_canary_allowed                     = "no"
edge_proven                             = "no"
wallet_or_tx_touched                    = false
solana_wallet_or_keypair_touched        = false
transaction_sent                        = false
send_hard_disable_still_active          = true
v2_modified_by_this_task                = false
v2_line_count_unchanged                 = true
```

本阶段**不**改任何上述值。

## 7. 决定

继续 Stage C — Solana RPC readiness matrix。
