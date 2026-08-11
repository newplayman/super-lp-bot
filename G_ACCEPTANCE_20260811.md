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

## G2 — 采样深度与退化区间防护

机械验收原始输出：

```text
$ python3 -m pytest tests/test_lp_solana_stock_stage2_v1_readonly.py tests/test_lp_netcover_inputs_v1_readonly.py -q
........................................................                 [100%]
56 passed in 0.27s
```

`--replay-limit` 的默认值现为 60。sigma 仅接受至少 20 笔具有时间戳的真实
swap、且首尾至少相隔 1 小时；不足时返回例如
`SIGMA_SAMPLE_INSUFFICIENT:n=3,span=0.3h`，不产生 range 或 FeeEV 输入。另有
`recommend_range_pct < 0.1%` 的 fail-closed 检查，原因带计算出的区间值。

对 AAPLX-USDC (`9462784c-c0e5-4539-914e-ac006e5b3097`) 的免费 RPC 只读
60 条签名轮巡原始输出：

```text
{"universe_count": 1, "stage2_pass_count": 0, "tier_counts": {"A": {"total": 1, "stage2_pass": 0}, "B": {"total": 0, "stage2_pass": 0}, "C": {"total": 0, "stage2_pass": 0}}}
{"swap_count": 50, "sigma_pair": 0.024013010166132644, "range_pct": 7.623894375558334, "fee_ev_usd": 0.009182465753424658, "netcover": null, "economics_reason": "PASS", "netcover_reason": "NETCOVER_INPUT_MISSING:reward_ev_usd,gas_usd,reward_conversion_cost_usd", "rpc_health": {"state": "NORMAL", "total_endpoints": 6, "impaired_endpoints": 0, "cooling_endpoints": 0, "max_consecutive_failures": 0}}
```

这里 `netcover=null` 是原始结果：Solana 尚没有历史 gas / reward 转换成本证据，
所以终闸保持 fail-closed；未用任何替代或付费服务填补。
