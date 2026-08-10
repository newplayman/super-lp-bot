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
