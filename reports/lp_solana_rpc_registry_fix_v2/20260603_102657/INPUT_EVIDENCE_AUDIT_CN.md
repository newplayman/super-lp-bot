# Input Evidence Audit — LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2`
- run_id: `20260603_102657`
- branch: `feat/supabase-postgres-deployment`
- head before: `2ca2ab6` (research: fix solana program registry 20260603_093136 — V1)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_solana_rpc_registry_fix/20260603_093136/FINAL_VERDICT.json` | status=WARN, verified=4, oficial=5/6, gpa=0/4, recommended=LP_SOLANA_RPC_REGISTRY_FIX_REPEAT | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/ONEPAGE_CN.md` | 总览; 5 sourced; 4 verified; 0/4 GPA | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/SOLANA_PROGRAM_ID_OFFICIAL_SOURCE_DISCOVERY_CN.md` | 5/6 sourced via WebFetch + curl github raw | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_official_source_discovery.json` | structured source results | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/SOLANA_PROGRAM_ID_REGISTRY_V2_CN.md` | registry v2: 5 official + 1 unknown | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_registry_v2.json` | structured registry v2 | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/SOLANA_PROGRAM_ID_ONCHAIN_VERIFICATION_V2_CN.md` | 4 verified + 1 not_found + 1 skipped | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_onchain_verification_v2.json` | structured verification | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/SOLANA_GPA_SMOKE_V2_CN.md` | 0/4 GPA on public RPC; timeouts / -32010 / 429 | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_gpa_smoke_v2.json` | structured GPA results | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/METEORA_DLMM_REGISTRY_READINESS_V2_CN.md` | 4/5 sub-conditions; only GPA blocked | OK |
| `reports/lp_solana_rpc_registry_fix/20260603_093136/meteora_dlmm_registry_readiness_v2.json` | structured readiness | OK |
| `reports/lp_solana_readonly_rpc_registry/20260603_084054/FINAL_VERDICT.json` | upstream RPC readiness | OK |
| `reports/lp_solana_connector_design/20260603_080347/FINAL_VERDICT.json` | upstream connector design | OK |

## 2. 关键事实（继承 V1）

```text
previous_stage                      = LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1
previous_status                    = WARN
previous_run_id                    = 20260603_093136
previous_commit                    = 2ca2ab6
oficial_source_discovery_ran       = true
oficial_program_id_count           = 5  (Meteora DLMM, DAMM v2, Orca, Raydium CLMM, Raydium CPMM)
unknown_count                      = 1  (Lifinity)
verified_program_count             = 4  (Meteora DLMM, DAMM v2, Orca, Raydium CLMM)
not_found                          = 1  (Raydium CPMM; cp-swap declare_id! not on mainnet)
gpa_smoke_attempted_count          = 4
gpa_smoke_success_count            = 0  (timeout / -32010 / 429 on public RPC)
meteora_dlmm_registry_ready_v2     = false
orca_registry_ready                = false
damm_v2_registry_ready             = false
raydium_registry_ready             = false
lifinity_registry_ready            = false
primary_endpoint_id                = public_publicnode-110e5a18
primary_avg_latency_ms             = 314.54
v2_line_count_unchanged            = true (992)
can_run_probe_now                  = false
solana_wallet_or_keypair_touched   = false
tiny_canary_allowed                = "no"
edge_proven                        = "no"
send_hard_disable_still_active     = true
```

## 3. V1 阻断与 V2 必须解决

| 阻断 | V1 状态 | V2 目标 |
|---|---|---|
| Raydium CPMM pid `CPMMoo8L...` not on mainnet | not_found | 拉 `raydium-amm-v3` 真 pid 或 docs |
| Lifinity pid unknown | unknown | 若仍无官方源则显式 deferred |
| Meteora DLMM GPA 在 public RPC timeout | Q3=no | 评估 SDK/API 替代路径 + 跑 minimal smoke |
| SDK/API paths designed but not wired | Q4=partial | 本轮 wire Meteora SDK 或 DLMM API |
| Connector stage risk (combine pid+SDK+paid RPC) | not selected | SDK/API 路径可让 connector 不再依赖 paid RPC |

## 4. V2 目标 (来自 operator prompt)

1. **Meteora DLMM SDK/API 路径评估** — 寻找官方 SDK package / GitHub repo / docs / API endpoint / examples
2. **3 条 path 比较** — public_rpc_gpa / paid_rpc_gpa / official_sdk_api
3. **minimal read-only smoke** — 仅当 C/D 找到 path 时；目标: 1 个 Meteora DLMM pool/pair metadata
4. **Raydium CPMM 真 mainnet pid** — `raydium-amm-v3` 仓库或 Raydium 官方 docs
5. **Lifinity deferred** — 仍无 source 则标记 deferred，不阻塞 P0/P1
6. **Registry v3 + 下一阶段决策**

## 5. 严格只读不变式（继承 + 本轮）

```text
can_run_probe_now                  = false
execution_allowed_now              = false
transaction_sent                   = false
wallet_or_tx_touched                = false
solana_wallet_or_keypair_touched   = false
tiny_canary_allowed                = "no"
edge_proven                        = "no"
manual_approval_required           = true
send_hard_disable_still_active     = true
v2_modified_by_this_task           = false
v2_line_count_unchanged            = true
```

本轮**不**改任何上述值；不读 keypair；不签名；不发 tx；不开 LP；不 swap；不 bridge；不 probe；不启动 live/canary/paper。

## 6. 允许范围（来自 operator prompt）

* WebFetch 官方 docs / 官方 GitHub
* curl 官方 raw source
* npm package metadata / package source
* Solana read-only RPC (getAccountInfo, getProgramAccounts bounded, getMultipleAccounts)
* 官方 API read-only endpoint
* SDK import inspection only
* read-only pool discovery
* 生成 registry / connector feasibility reports
* 测试

## 7. 决定

进入 Stage C — Meteora DLMM 官方 SDK / API source discovery。
