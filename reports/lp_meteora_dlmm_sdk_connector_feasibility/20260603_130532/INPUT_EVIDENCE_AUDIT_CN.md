# Input Evidence Audit — LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1

- stage: `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1`
- run_id: `20260603_130532`
- branch: `feat/supabase-postgres-deployment`
- head before: `4099b13` (research: fix solana registry sdk api path 20260603_102657 — V2)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/FINAL_VERDICT.json` | status=WARN; sdk_source_discovery_ran=true; discovery_path_decided=true; smoke_ran=true (partial); recommended=LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/ONEPAGE_CN.md` | 总览; 5 sourced; 4 verified; 1 not_found (CPMM); 1 deferred (Lifinity) | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/METEORA_DLMM_SDK_API_SOURCE_DISCOVERY_CN.md` | 6 sources verified (SDK package, DLMM class, getLbPairs, DLMM.create, swapQuote example, lock_info example); 1 unknown (dlmm-api.meteora.ag 404) | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/meteora_dlmm_sdk_api_source_discovery.json` | structured source results | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/METEORA_DLMM_READONLY_DISCOVERY_PATH_DECISION_CN.md` | 3 paths: public_rpc_gpa (not_feasible), paid_rpc_gpa (recommended), official_sdk_api (partial) | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/meteora_dlmm_readonly_discovery_path_decision.json` | structured decision | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/METEORA_DLMM_MINIMAL_READONLY_SMOKE_CN.md` | pool 5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF readable; owner=DLMM program; data_len=904 | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/meteora_dlmm_minimal_readonly_smoke.json` | structured; smoke_success=true (partial) | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/SOLANA_PROGRAM_ID_REGISTRY_V3_CN.md` | registry v3: 4 verified + 1 not_found + 1 deferred | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/solana_program_id_registry_v3.json` | structured registry v3 | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/solana_rpc_registry_fix_v2_next_stage_decision.json` | recommended=LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT | OK |

## 2. 关键事实（继承 V2）

```text
previous_stage                          = LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2
previous_status                         = WARN
previous_run_id                         = 20260603_102657
previous_commit                         = 4099b13
oficial_program_id_count                = 5
verified_program_count                  = 4
not_found_count                         = 1 (Raydium CPMM)
deferred_count                          = 1 (Lifinity)
meteora_dlmm_sdk_api_source_discovery_ran = true
meteora_dlmm_discovery_path_decided     = true (paid_rpc_gpa recommended; official_sdk_api fallback)
meteora_dlmm_minimal_smoke_ran          = true
meteora_dlmm_minimal_smoke_success      = true (partial: known-pool read verified; struct decode needs full SDK)
meteora_dlmm_pool_smoke_address         = 5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF
meteora_dlmm_pool_owner                 = LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo (= Meteora DLMM program)
meteora_dlmm_pool_data_len              = 904 bytes (matches LbPair struct)
public_rpc_gpa_blocked                  = true (V1 0/4)
dlmm_api_meteora_ag_rest                = 404 on all paths
can_run_probe_now                       = false
solana_wallet_or_keypair_touched        = false
tiny_canary_allowed                     = "no"
edge_proven                             = "no"
v2_line_count_unchanged                 = true (992)
```

## 3. V2 阻断与 V3 必须解决

| 阻断 | V2 状态 | V3 目标 |
|---|---|---|
| SDK 实际 install + struct decode 未做 | V2 smoke 用 stdlib-only Python 替代 | V3 实际 `npm install` 在 `/tmp` 隔离; 用 full SDK decode 已知 pool |
| Quote smoke 未做 | V2 仅 decode path; quote 未实测 | V3 跑 SDK `swapQuote` (read-only) on known pool |
| Connector schema 未设计 | V2 没有 connector schema | V3 设计 6 张 read-only research-only 表 |
| Discovery strategy 决策 | V2 推荐 paid_rpc_gpa | V3 进一步决策 known_pool_feed vs paid_rpc_gpa vs blocked |

## 4. V3 目标 (来自 operator prompt)

1. **隔离 SDK 环境审计** — `npm view` / `npm pack` / `npm install @meteora-ag/dlmm` 到 `/tmp/lpbot_meteora_dlmm_sdk_probe_${RUN_ID}` (不污染 repo root)
2. **Known-pool feed freeze** — V2 smoke pool + 官方 SDK example pools (来源明确)
3. **SDK known-pool read-only smoke** — 实际运行 `DLMM.create` + helpers, 提取 active_bin / bin_step / fee / token mints / reserves
4. **SDK quote smoke (read-only only)** — 10U/20U quote simulation; 不构造 tx; 不签名
5. **Connector schema v1** — 6 张 research-only 表
6. **Discovery strategy decision** — 3 路径比较; 推荐 known_pool_feed_sdk_decode
7. **Next-stage decision** — `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1` 或继续 fix_repeat

## 5. 严格只读不变式（继承 + 本轮）

```text
can_run_probe_now                       = false
execution_allowed_now                   = false
transaction_sent                        = false
wallet_or_tx_touched                    = false
solana_wallet_or_keypair_touched        = false
tiny_canary_allowed                     = "no"
edge_proven                             = "no"
manual_approval_required                = true
send_hard_disable_still_active          = true
v2_modified_by_this_task                = false
v2_line_count_unchanged                 = true
```

本轮**不**改任何上述值；不读 keypair；不签名；不发 tx；不开 LP；不 swap；不 bridge；不 probe；不启动 live/canary/paper；不写 production positions；不修改 EVM executor v2；不释放 v2 hard-disable。

## 6. 允许范围（来自 operator prompt）

* npm view / npm pack / isolated npm install 到 /tmp
* node read-only SDK script
* Solana public RPC read-only call (getAccountInfo, getMultipleAccounts)
* SDK decode account
* SDK read active bin
* SDK read fee info
* SDK read bin step
* SDK quote simulation if no tx/signing
* SDK examples inspection
* known pool feed JSON/CSV
* reports / scripts / tests

## 7. 严格禁止

* 不读取 Solana 私钥
* 不读取 seed phrase
* 不读取 keypair json
* 不读取 wallet adapter
* 不创建 signer
* 不构造可发送 transaction
* 不调用 sendTransaction
* 不调用 swap / open_lp / close_lp / collect_fee
* 不桥接
* 不自动换币
* 不启动 live / canary / paper
* 不写 production positions
* 不覆盖 shadow 表
* 不修改 EVM executor 执行路径
* 不释放 EVM executor hard-disable
* 不安装 wallet / keypair 适配器依赖
* 不调用任何 wallet adapter execution path

## 8. 决定

进入 Stage C — 隔离 SDK 环境审计 (npm view/pack/install 在 /tmp)。
