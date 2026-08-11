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

## G3 — 失败原因归因顺序

机械验收原始输出：

```text
$ python3 -m pytest tests/test_lp_solana_stock_stage2_v1_readonly.py -q
............                                                             [100%]
12 passed in 0.11s
```

stage2 现在逐一检查真正的合取失败项：链上身份、经济、swap 数、经济价格完整性、
最后才是 NetCover。回归用例中 economics/replay 都是 `PASS` 而 NetCover 是
`NETCOVER_INPUT_MISSING:gas_usd`，最终 reason 恰为该 NetCover 原因，且不含
`FAIL_CLOSED:PASS`。

## G4 — 假阴性自检与证据生产者覆盖

机械验收原始输出：

```text
$ python3 -m pytest tests/test_lp_stock_tier_acceptance_v1_readonly.py -q
.......                                                                  [100%]
7 passed in 0.12s
```

受控端到端元测试通过真实 `build_acceptance → evaluate_c_gate` 路径，把 C 档终闸
消费的七个 gate 全部产出为 true，并断言全部数值证据非空；没有 mock 被测 policy。
报告的 A/B/C `tier_counts` 现在额外列出
`0_because_computed_and_failed` 与 `0_because_inputs_unavailable`；每档
`terminal_pass + 两类零原因 = universe`，因此零通过不再与“根本没算成”同值。
