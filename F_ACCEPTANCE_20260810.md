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
