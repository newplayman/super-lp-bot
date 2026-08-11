# TP-G-v1 验收记录（进行中）

## G1 — 跨链 CLMM 组装器可达性

机械验收原始输出：

```text
$ python3 -m pytest tests/test_lp_funnel_autopsy_v1_readonly.py tests/test_lp_netcover_inputs_v1_readonly.py tests/test_lp_solana_stock_stage2_v1_readonly.py -q
............................................................             [100%]
60 passed in 0.38s
```

新增 Solana 受控记录使用链上账户标记
`measured:pool.sqrt_price_x64` / `measured:pool.liquidity` 与共享的 Solana
USDC mint，断言 `fee_ev_usd`、`position_cap_usd` 均非空；将出处改成
`caller:claimed_pool_state` 后 `fee_ev_usd is None`。Base 原有 token 集及
slot0/liquidity 分支未变，未知/缺失链仍返回空稳定腿集合（fail-closed）。

Base 不变性通过。为了锁定持续 scanner 的准确同一批次，解剖器新增只读
`--scanner-as-of`；本次使用可信基线中记录的
`2026-08-11T03:33:45.804864+00:00`，原始比较输出：

```text
$ python3 scripts/lp_funnel_autopsy_v1_readonly.py ... --scanner-as-of 2026-08-11T03:33:45.804864+00:00 ...
autopsy terminal=30 accepted=0 independent=200
{"netcover_failures": {"baseline": {"missing_input": 0, "calculated_below_1": 2}, "rerun": {"missing_input": 0, "calculated_below_1": 2}, "identical": true}, "decay": {"identical": true}}
```

完整 `python3 -m pytest tests/ -q` 和 `go test ./...` 会在最后一次编辑后重新执行并粘贴完整原始输出；不引用此处以前的回归结果。
