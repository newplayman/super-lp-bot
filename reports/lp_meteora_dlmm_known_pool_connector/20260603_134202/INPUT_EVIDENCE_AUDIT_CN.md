# Input Evidence Audit — LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1

- stage: `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`
- run_id: `20260603_134202`
- branch: `feat/supabase-postgres-deployment`
- head before: `fa4e5e4` (research: test meteora dlmm sdk connector feasibility 20260603_130532 — V3)

## 1. 上游 inputs 一览

| 路径 | 关键字段 | 状态 |
|---|---|---|
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/FINAL_VERDICT.json` | status=WARN; sdk_install_or_pack_success=true; known_pool_feed_ready=true; known_pool_smoke_success=true; quote_smoke_success=false; connector_schema_ready=true; recommended_next_stage=LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1 | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/ONEPAGE_CN.md` | 一页总览 | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/METEORA_DLMM_SDK_PACKAGE_AUDIT_CN.md` | SDK @meteora-ag/dlmm@1.9.10; install in /tmp isolated | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/meteora_dlmm_sdk_package_audit.json` | structured SDK audit | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/METEORA_DLMM_KNOWN_POOL_FEED_CN.md` | 2 pools from official SDK examples; 1 skipped (3W2HKgUa not on mainnet) | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/meteora_dlmm_known_pool_feed.json` | structured feed; 2/2 selected, 1 skipped | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/METEORA_DLMM_SDK_KNOWN_POOL_SMOKE_CN.md` | 2/2 pools full LbPair decode via SDK | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/meteora_dlmm_sdk_known_pool_smoke.json` | structured smoke results; per-pool fields | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/METEORA_DLMM_SDK_QUOTE_SMOKE_CN.md` | 0/4 quote; root cause = getBinArrayForSwap 403/410 | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/meteora_dlmm_sdk_quote_smoke.json` | structured quote results | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/METEORA_DLMM_KNOWN_POOL_CONNECTOR_SCHEMA_CN.md` | 6 tables design; 14/14 field coverage | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/meteora_dlmm_known_pool_connector_schema.json` | structured schema | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/METEORA_DLMM_DISCOVERY_STRATEGY_DECISION_CN.md` | 3 paths; known_pool_feed_sdk_decode selected for Phase 2A | OK |
| `reports/lp_meteora_dlmm_sdk_connector_feasibility/20260603_130532/meteora_dlmm_discovery_strategy_decision.json` | structured strategy decision | OK |
| `reports/lp_solana_rpc_registry_fix_v2/20260603_102657/FINAL_VERDICT.json` | upstream V2 final | OK |

## 2. 关键事实（继承 V3）

```text
previous_stage                          = LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1
previous_status                         = WARN
previous_run_id                         = 20260603_130532
previous_commit                         = fa4e5e4
sdk_package_audit_ran                   = true
sdk_install_or_pack_success             = true
sdk_version_resolved                    = 1.9.10
sdk_install_dir                         = /tmp/lpbot_meteora_dlmm_sdk_probe_20260603_130532
sdk_repo_root_touched                   = false
sdk_wallet_adapter_imported             = false
sdk_keypair_instantiated                = false
known_pool_feed_ready                   = true
known_pool_feed_size                    = 2
known_pool_smoke_ran                    = true
known_pool_smoke_success                = true
known_pool_smoke_pools                  = 2/2 full LbPair decode
quote_smoke_ran                         = true
quote_smoke_success                     = false
quote_smoke_blocker                     = bin_arrays_403_public_rpc
quote_smoke_root_cause                  = getBinArrayForSwap 403 on publicnode / 410 on mainnet-beta
connector_schema_ready                  = true
connector_schema_tables_count           = 6
recommended_near_term_path              = known_pool_feed_sdk_decode
recommended_next_stage                  = LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1
can_run_probe_now                       = false
solana_wallet_or_keypair_touched        = false
tiny_canary_allowed                     = "no"
edge_proven                             = "no"
v2_line_count_unchanged                 = true (992)
```

## 3. V3 阻断与 V4 必须实现

| 阻断 | V3 状态 | V4 目标 |
|---|---|---|
| Connector script 复用 | V3 smoke 是 single-use script | V4 写可复用的 connector script (`lp_meteora_dlmm_known_pool_connector_v1_readonly.js`) with `--mode snapshot/quote-smoke/all` |
| pool_snapshot 表 | V3 验证 SDK decode works | V4 固化 known-pool universe → 跑 script → 输出 CSV/JSON/MD |
| fee_snapshot 表 | V3 验证 base/max 可用 | V4 跑 script → 提取 + 输出 CSV/JSON/MD |
| bin_liquidity 表 | V3 blocked (public RPC 403) | V4 尝试 + honest blocker 记录 (不伪造) |
| quote_snapshot 表 | V3 0/4 (depends on bin arrays) | V4 尝试 + honest blocker 记录 |
| readiness matrix | V3 设计 6 表状态 | V4 输出 readiness matrix; 评估 connector_ready/quote_ready/ev_ready |

## 4. V4 目标 (来自 operator prompt)

1. **Stage C** — 写可复用 connector script (read-only strict); 支持 `--mode snapshot/quote-smoke/all`
2. **Stage D** — 固化 known_pool_universe (2 pools from V3 feed, 完整地址从 V3 JSON 读取)
3. **Stage E** — pool_snapshot 表: 2/2 pools SDK decode
4. **Stage F** — fee_snapshot 表: 2/2 pools fee 提取
5. **Stage G** — bin_liquidity 表: 尝试 + 记录 blocker
6. **Stage H** — quote_snapshot 表: 尝试 10U/20U + 记录 blocker
7. **Stage I** — readiness matrix: 6 表状态
8. **Stage J** — next-stage decision
9. **Stage K** — final verdict
10. **Stage L** — tests + safety scan
11. **Stage M** — git publish

## 5. Known pool feed (full addresses from V3 artifact, NOT 手写)

| pool_address | source_file | selected |
|---|---|---|
| `5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF` | `swap_quote.ts` (V3 verified on mainnet) | ✅ |
| `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` | `fetch_lb_pair_lock_info.ts` (V3 verified on mainnet) | ✅ |

注: 第 3 个候选 (`3W2HKgUa96Z69zzG3LK1g8KdcRAWzAttiLiHfYnKuPw5` from `example.ts`) 在 V3 中**已 skipped** (not on mainnet); V4 仍维持 skip.

## 6. 严格只读不变式（继承 + 本轮）

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

本轮**不**改任何上述值；不读 keypair；不签名；不发 tx；不开 LP；不 swap；不 bridge；不 probe；不启动 live/canary/paper；不写 production positions；不修改 EVM executor v2；不释放 v2 hard-disable；不在 repo root 安装任何 npm package。

## 7. 决定

进入 Stage C — 写 connector script (read-only strict, isolated /tmp install).
