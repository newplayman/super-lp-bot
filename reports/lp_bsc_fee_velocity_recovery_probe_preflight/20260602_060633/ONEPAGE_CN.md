# 单页总览（recovery pipeline）

```text
stage                              = LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1
run_id                             = 20260602_060633
status                             = PASS

old_run_finalized                  = True
old_runner_stopped_by_this_task    = True

rpc_capability_matrix_ran          = True
usable_bsc_rpc_count               = 1

smoke_1pool_24h_ran                = True
smoke_1pool_24h_pass               = True

short_backfill_ran                 = True
fee_ready_pool_count               = 7
decoded_swap_log_count             = 273563

economics_preview_ran              = True
positive_proxy_count_realistic     = 0
near_break_even_count              = 394
best_pool                          = 0x172fcd41e0913e95784454622d1c3724f546f849
best_pair                          = USDT/WBNB
best_fee_tier                      = 100
best_notional                      = 20
best_hold_window                   = 15m
best_net_ev_proxy_usd              = -0.015560

probe_preflight_design_ready       = True
can_run_probe_now                  = False
manual_approval_required_for_probe = True
edge_proven                        = no
actual_fee_ready                   = False
token_id_available                 = False
wallet_or_tx_touched               = False
tiny_canary_allowed                = no

recommended_next_stage             = LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1
```

## 严格禁区（本轮已遵守）

```text
不发交易            no tx
不启动 live         no live
不启动 paper        no paper
不运行 canary       no canary
不执行 probe        no probe
不读私钥/wallet     no wallet
不创建 signer       no signer
不调用 swap/mint/burn/collect/approve/increaseLiquidity/decreaseLiquidity
不写 production positions
不覆盖 shadow 表
不重启 lpbot-shadow / lpbot-live
tiny_canary_allowed = no
can_run_probe_now   = false
edge_proven         = no
```
