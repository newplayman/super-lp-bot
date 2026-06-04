# Stage B — 输入证据审计 (Input Evidence Audit)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`
- branch: `feat/supabase-postgres-deployment`
- HEAD: `44954ba research: smoke long horizon readonly collector 20260604_081432`

## 0. 目的

在补 9 项 readiness 之前, 把上一阶段 smoke_v1 + final freeze + 5 个 protocol verdict
read-back 验证, 锁存 boundary 字段 / 5 个真实 pool_address / 上一阶段遗漏的 readiness
缺口 / 硬禁止项. 这是只读 audit, 不修改任何 collector 脚本.

## 1. 必读清单与 read-back 状态

| # | 必读文件 | 路径 | 状态 | 关键字段确认 |
|---|---|---|---|---|
| 1 | smoke_v1 FINAL_VERDICT | `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/FINAL_VERDICT.json` | ✅ read | status=WARN, smoke_mode_ran=true, schema_validation_pass=true, long_run_ready=false, recommended_next_stage=LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT |
| 2 | smoke_v1 smoke_result | `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/collector_smoke_result.json` | ✅ read | exit_code=0, source_adapter_status 4 stub, placeholder_only=true |
| 3 | smoke_v1 health | `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/collector_health_and_failure_mode.json` | ✅ read | long_run_readiness=0/9, current_blocker 5 项 |
| 4 | final freeze FINAL_VERDICT | `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json` | ✅ read | research_freeze_complete=true, 5 protocols frozen |
| 5 | meteora DLMM verdict | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/FINAL_VERDICT.json` | ✅ read | best_pool=`CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa` |
| 6 | orca whirlpool verdict | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/FINAL_VERDICT.json` | ✅ read | best_pool=`C9U2Ksk6KKWvLEeo5yUQ7Xu46X7NzeBJtd9PBfuXaUSM` |
| 7 | raydium CLMM verdict | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/FINAL_VERDICT.json` | ✅ read | best_pool=`3nMFwZXwY1s1M5s8vYAHqd4wGs4iSxXE4LRoUMMYqEgF` |
| 8 | raydium CPMM verdict | `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/FINAL_VERDICT.json` | ✅ read | best_pool=`vs6XUbGcVWG75Gv81qvDMBxkQ67Kr2eLrFNDTrCxxwk` |
| 9 | solana stable verdict | `reports/lp_solana_stable_pool_research/20260604_044118/FINAL_VERDICT.json` | ✅ read | best_pool=`AiMZS5U3JMvpdvsr1KeaMiS354Z1DeSg5XjA4yYRxtFf` |

## 2. 5 个真实 pool_address (本任务 replay 样本)

| protocol | pool_address | 用途 |
|---|---|---|
| meteora_dlmm | `CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa` | local_artifact_replay_adapter real_data |
| orca_whirlpool | `C9U2Ksk6KKWvLEeo5yUQ7Xu46X7NzeBJtd9PBfuXaUSM` | local_artifact_replay_adapter real_data |
| raydium_clmm | `3nMFwZXwY1s1M5s8vYAHqd4wGs4iSxXE4LRoUMMYqEgF` | local_artifact_replay_adapter real_data |
| raydium_cpmm | `vs6XUbGcVWG75Gv81qvDMBxkQ67Kr2eLrFNDTrCxxwk` | local_artifact_replay_adapter real_data |
| solana_stable | `AiMZS5U3JMvpdvsr1KeaMiS354Z1DeSg5XjA4yYRxtFf` | local_artifact_replay_adapter real_data |

每个 pool 配 1 个 program_id (per final freeze verdict):
- meteora_dlmm → `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`
- orca_whirlpool → `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`
- raydium_clmm → `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`
- raydium_cpmm → `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`
- solana_stable → `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` (Orca LST)

## 3. 9 项 readiness 缺口 (待本任务补完)

per `collector_health_and_failure_mode.json` smoke_v1:

- [ ] source_adapter_implemented
- [ ] classifier_implemented
- [ ] rate_limit_retry_backoff_implemented
- [ ] abort_condition_implemented
- [ ] sqlite_enabled
- [ ] paid_rpc_indexer_integrated (本任务仍不需要, 留待 7D_RUN)
- [ ] error_rate_monitor_implemented
- [ ] cron_systemd_configured (本任务仍不需要, 留待 7D_RUN)
- [ ] manual_approval_recorded (本任务仍不需要, 留待 7D_RUN)

本任务目标: 补前 6 项 (source adapter + classifier + retry/backoff + abort +
sqlite + error rate monitor). 留 paid_rpc / cron / manual_approval 三项给后续 7D_RUN_REQUEST_V1.

## 4. boundary 字段 (locked, 不动)

- [x] `can_run_probe_now = false` (locked)
- [x] `tiny_canary_allowed = "no"` (locked)
- [x] `edge_proven = "no"` (locked)
- [x] `send_hard_disable_still_active = true` (locked)
- [x] `wallet_or_tx_touched = false`
- [x] `transaction_sent = false`
- [x] `long_run_started = false` (本任务不启动 7d run)
- [x] `global_lp_rejected = false` (口径)

## 5. hard-disable 字段 (本任务全程不破)

- [x] 不跑 7d / 14d / 30d
- [x] 不启动长期 daemon
- [x] 不接钱包 / 签名 / 发交易 / approve / mint / add/remove liquidity / collect / swap / bridge
- [x] 不 probe / canary / live / paper
- [x] 不写 production positions
- [x] 不覆盖 shadow 原始表
- [x] `can_run_probe_now` 必须保持 false
- [x] `tiny_canary_allowed` 必须保持 no

## 6. 本任务输出 (lock from input)

- INPUT_EVIDENCE_AUDIT_CN.md / .json
- FIX_REPEAT_PLAN_CN.md / .json (Stage C)
- RETRY_BACKOFF_UTILS_IMPL_CN.md / .json (Stage D)
- LOCAL_ARTIFACT_REPLAY_ADAPTER_IMPL_CN.md / .json (Stage E)
- PUBLIC_API_AND_SOLANA_RPC_ADAPTERS_IMPL_CN.md / .json (Stage F)
- REGIME_CLASSIFIER_IMPL_CN.md / .json (Stage G)
- SQLITE_STORAGE_IMPL_CN.md / .json (Stage H)
- REAL_DATA_SMOKE_RUNNER_IMPL_CN.md / .json (Stage I)
- REAL_DATA_SMOKE_RESULT_CN.md / .json (Stage J)
- FINAL_VERDICT.json
- ONEPAGE_CN.md
- ARTIFACT_INDEX.md
- 1 个新脚本: `scripts/lp_long_horizon_readonly_real_data_smoke_v1.py`
- 4 个新 lib (under `scripts/lp_long_horizon/`):
  - `__init__.py`
  - `adapters/local_artifact_replay.py`
  - `adapters/public_api_coingecko.py`
  - `adapters/solana_rpc_readonly.py`
  - `utils/retry.py`
  - `utils/abort.py`
  - `classify/market_regime.py`
  - `storage/research_store.py`
- 1 个新 pytest: `tests/test_lp_long_horizon_readonly_collector_fix_repeat_v1.py`

## 7. 不在本任务范围 (read 不写)

- 任何 7d / 14d / 30d 实际 run (留待 7D_RUN_REQUEST_V1)
- 任何 paid RPC / paid indexer (留待 7D_RUN_REQUEST_V1)
- 任何 cron / systemd / long-running process
- 任何 manual approval 流程实装 (留待 7D_RUN_REQUEST_V1)
- 任何 actual fee accrual 抓取 (R1 阶段, 需 user tokenId)
- 任何 protocol 重新连接 (5 connector 已 verify, 复用即可)
- 任何 heuristic 改动
- 任何 production 写

## 8. 结论

输入证据 read-back 通过. 5 个真实 pool_address 锁定. 9 项 readiness 缺口
确认 (本任务目标: 补 6 项, 留 3 项). 硬禁止项明确. Stage B 通过.
进入 Stage C (FIX_REPEAT 实施计划).
