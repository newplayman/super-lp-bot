# TP-F-v1 验收记录（运行中）

最终三项结论将在 F7 完成后，以本次任务的实际重跑结果补写于此。

## F1 — Base/EVM CLMM 生产路径回归修复

机械验收命令：

```text
$ python3 -m pytest tests/test_lp_scanner_daemon_v1_readonly.py tests/test_lp_netcover_inputs_v1_readonly.py tests/test_lp_netcover_amm_dispatch_v1_readonly.py -q
........................................................................ [ 69%]
...............................                                          [100%]
103 passed in 4.65s
```

生产路径最小完整 Base 记录（未手工设置 `protocol_type`）内联验收：

```text
$ python3 - <<'PY' ... PY
None
```

## F2 — C 档总敞口累加

机械验收命令：

```text
$ python3 -m pytest tests/test_lp_stock_tier_acceptance_v1_readonly.py -q
...                                                                      [100%]
3 passed in 0.04s
```

组合级回归用例 `test_c_batch_accumulates_passed_exposure_and_rejects_fifth_candidate`
断言同批五个完整 C 候选的前四个通过，第五个 `passed is False`，且
`failures` 包含 `7_budget_caps`。

## F3 — vetted_menu 每轮 cycle 导出

机械验收命令：

```text
$ python3 -m pytest tests/test_lp_scanner_daemon_v1_readonly.py -q
...............................................                          [100%]
47 passed in 2.39s
```

cycle 级回归用例 `test_cycle_exports_empty_vetted_menu_with_valid_json_schema`
运行一轮 `--once`，断言输出文件存在、可解析为 JSON list，且零候选时内容为 `[]`。

## F4 — Solana CLMM 经济回放

机械验收（新增/既有 stage2 单测）：

```text
$ python3 -m pytest tests/test_lp_solana_stock_stage2_v1_readonly.py -q
.........                                                                [100%]
9 passed in 0.09s
```

分段原始 stage2 输出合并校验（每段使用免费 RPC 轮巡、`--replay-limit 3`，无签名、无广播）：

```text
{"economics_reasons": {"ACTIVE_LIQUIDITY_USD_ANCHOR_UNAVAILABLE": 23, "None": 5, "PASS": 23, "RAW_SWAP_PRICE_PATH_INSUFFICIENT": 10}, "legacy_reason_count": 0, "stage2_pass_count": 0, "tier_counts": {"A": {"stage2_pass": 0, "total": 36}, "B": {"stage2_pass": 0, "total": 9}, "C": {"stage2_pass": 0, "total": 15}}, "universe_count": 61}
65 reports/lp_tp_f/20260810/stage2_clmm_f4_table.md
```

当前输入快照实际筛出 61 个 Solana CLMM 记录（其中 A/B/C 为 60 个；与任务书的 59 个不一致，未删除任何记录凑数）。旧裸原因
`CLMM_RANGE_AND_RAW_SWAP_REPLAY_REQUIRED` 计数为 0；逐池 NetCover/拒绝原因表见
`reports/lp_tp_f/20260810/stage2_clmm_f4_table.md`。

SPYX-SSX 同窗口回放验收：

```text
{"reference_fee_apr_pct": 2717.146, "relative_deviation_pct": 4.359088030887411, "spxy_ssx_fee_apr_pct": 2598.703213932264, "within_5pct": true}
```

## F5 — C 档退出、卖出模拟与滑点证据

配对单测：

```text
$ python3 -m pytest tests/test_lp_solana_stock_stage2_v1_readonly.py tests/test_lp_solana_tier_c_risk_evidence_v1_readonly.py -q
.............                                                            [100%]
13 passed in 0.13s
```

`tier_c_risk` 重跑（免费 RPC 索引不可用时保留原有 fail-closed）：

```text
$ python3 scripts/lp_solana_tier_c_risk_evidence_v1_readonly.py ... --fail-closed-rpc-reason 'F5 free RPC indexed holder data unavailable; no substitute used'
{"pool_count": 15, "pass_count": 0}
```

逐池字段完整性校验：

```text
{'tier_c_count': 15, 'missing_fields': 0, 'bare_fail_closed': 0}
```

未能构造可由协议官方 quote builder 提供的无签名 sell 交易包时，卖出模拟保持
`FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE`；没有签名、广播或生成私钥。
