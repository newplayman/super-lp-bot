# TP-H-v1 验收记录（进行中）

A 档 36 池尚未完成全量复跑，当前不能诚实报告 NetCover 实数分布或 `>=1.0` 数量。
未出数池的字段归因将在 H5 用分段 checkpoint 的完整 A 档结果统计；本记录不会把未跑的池写成经济失败。
三档 `terminal_pass` 以及“算出来没过/没算成”的拆分同样留待 H5 的完整输出，B/C 无稳定腿的不可达设计保持不变。

## H1 — Solana gas / 交易成本模型

机械验收原始输出：

```text
$ python3 -m pytest tests/test_lp_netcover_inputs_v1_readonly.py tests/test_lp_solana_stock_stage2_v1_readonly.py -q
59 passed in 0.42s
```

AAPLX-USDC 的免费 RPC 实测费用输入（53 个已解码真实 swap 的中位交易费、150 个近期优先费样本中位数、
RPC `getMinimumBalanceForRentExemption(165)` 查询的两个 ATA 租金；无签名、无广播）：

```json
{
  "status": "PASS",
  "signature_fee_lamports": 24474,
  "priority_fee_lamports": 0,
  "rent_lamports": 4078560,
  "rent_components": {"ata_count": 2, "ata_rent_lamports_each": 2039280, "tick_array_rent_lamports": 0},
  "operation_count": 2,
  "operation_model": "open_plus_close;swap_legs_not_required_for_stable_pair",
  "fee_sample_count": 53,
  "priority_sample_count": 150,
  "sol_usd": 75.95,
  "sol_usd_source": "free_coingecko_simple_price:solana/usd",
  "quoted_at": 1786429027
}
```

由同一证据包计算的 `gas_usd` 原始值为 `0.3134842326`：`2 × (24474 + 0) + 4078560` lamports，按当次免费
SOL/USD 报价换算。Jupiter 的公共 hostname 在本机不可解析，代码记录该失败并使用可验证的免费 CoinGecko 当次报价；两者都不可得时专属 reason 为 `SOL_USD_QUOTE_UNAVAILABLE`，严格 fail-closed。

## H2 — Solana reward 模型与兑换成本

机械验收原始输出：

```text
$ python3 -m pytest tests/test_lp_netcover_inputs_v1_readonly.py tests/test_lp_solana_stock_stage2_v1_readonly.py -q
61 passed in 0.33s
```

共享组装器现将 `NO_REWARDS` 映射为 `reward_ev_usd=0.0` 与
`reward_conversion_cost_usd=0.0`；`FAIL_CLOSED` 的账户读取错误仍保留为
`SOLANA_REWARD_READ_<具体原因>`，二者不可混同。Raydium/Orca 已按各自池账户
布局解码 reward infos，并且对每一个有 emission 的 vault 用免费 RPC 读取剩余额度。

AAPLX-USDC 当次链上读取的原始 reward 字段：

```json
{
  "reward_infos": [],
  "evidence": {"status": "NO_REWARDS", "reason": "ONCHAIN_REWARD_INFOS_EMPTY", "rewards": []}
}
```

此 117 池固定股票宇宙中没有 `apyReward > 0` 的 Solana 行，因而没有可诚实列为“有 reward 的 Solana 股票池”的样本；
不会伪造或以非股票池替代。对于有 reward info 但免费无签名报价不可得的情形，读取结论保持
`FAIL_CLOSED`，不会把未估价的 emission 当收入。

## H3 / H3a — 采样深度与 sigma 日化

采样停止条件现为**同时** `>=20` 个真实 swap 且实际跨度 `>=3h`；默认每页 60 笔、最多 10 页。
每页通过免费 RPC 轮巡，失败由现有指数退避记录在 `rpc_health.endpoints`。若达到页上限、历史耗尽或
端点受限，输出仍会带 `swap_count`、`actual_span_hours`、`pages_fetched` 和 `replay_stop_reason`，经济计算
保持 fail-closed，而不是凭交易数量推断时间跨度。

波动率不再把“相邻 swap”当成“每日”样本。每个 5 分钟 UTC 固定桶取最后一笔成交价，桶间空白以前一桶收盘价
前填；若桶收益为 `r_i`，则 `sigma_daily = sqrt(mean(r_i^2)) * sqrt(288)`。`sigma_per_swap` 仅作为未经时间
折算的审计字段；范围和 NetCover 都只使用日口径 `sigma_daily`（兼容字段 `sigma_pair` 也已明确为日口径）。
单测构造每桶固定对数收益 `r=0.01`，断言 `sigma_daily == 0.01 * sqrt(288)`：

```text
$ python3 -m pytest tests/test_lp_solana_stock_stage2_v1_readonly.py tests/test_lp_netcover_inputs_v1_readonly.py tests/test_lp_vol_range_sizer_v1_readonly.py -q
69 passed in 0.50s
```

AAPLX-USDC（`9462784c-c0e5-4539-914e-ac006e5b3097`）连续三次免费 RPC 原始复跑：

| run | swap_count | 采样窗口小时数 | pages / 停止原因 | sigma_per_swap | sigma_daily | 每日样本数 |
|---|---:|---:|---|---:|---:|---:|
| 1 | 49 | 5.3080555556 | 1 / `TARGET_REACHED` | 4.7410034157 | 0.0172099782 | 288 |
| 2 | 52 | 5.9202777778 | 1 / `TARGET_REACHED` | 4.5726297389 | 0.0164402618 | 288 |
| 3 | 52 | 5.9202777778 | 1 / `TARGET_REACHED` | 4.5726297389 | 0.0164402618 | 288 |

三次都满足样本数与 3h 跨度闸，且停在第一页；每次 RPC 状态均为 `DEGRADED`，唯一失败端点是
`https://rpc.solanatracker.io/public`（`consecutive_failures=1`），其余五个端点正常。原始 JSON 位于
`reports/lp_tp_h/20260811/h3a_aaplx_stage2_run{1,2,3}.json`。

**H3a 机械验收不通过，且已保持为显式失败：**固定桶口径的 `sigma_daily` 为 1.64%–1.72%，不在指定的
5%–100% 股票代币验收区间。它不再是旧错误的 0.297% per-swap 值；相反，连续桶收盘价在这 5–6 小时窗口确实
近乎不动。样本中另有一笔同一 5 分钟桶内 `-0.00000001 AAPLX / +5000 USDC` 的 vault 差额，其 per-swap
隐含价为 `500000000000`，故原始 `sigma_per_swap` 高达约 4.6；该瞬时、同桶内随后恢复的差额不会污染桶末收盘
价。没有把低日波动率调高、也没有放宽任何经济阈值；因此 H3a 的口径修复已生效，但 AAPLX 的 5% 外部量级
验收不能诚实宣称通过。

## H4 — Base 不变性固定快照对照

使用 Python `sqlite3.Connection.backup()` 于 `2026-08-11T09:55:05.586558+00:00` 从
`reports/lp_scanner/scanner.db` 制作 `reports/lp_tp_h/20260811/h4_base_invariance/scanner.snapshot.db`。
两次 AUTOPSY 都只读该副本和同一份 Stage-1 输入：基线为 `29ac336`，当前为包含 H1–H3a 的代码。

| 字段/闸 | 29ac336 | 当前 | 一致 |
|---|---:|---:|---|
| `netcover_failures.missing_input` | 0 | 0 | 是 |
| `netcover_failures.calculated_below_1` | 4 | 4 | 是 |
| `accepted_recomputed` | 0 | 0 | 是 |
| `resolution_status` survived/eliminated | 15 / 15 | 15 / 15 | 是 |
| `asset_quality` survived/eliminated | 15 / 0 | 15 / 0 | 是 |
| `yield_cover` survived/eliminated | 14 / 1 | 14 / 1 | 是 |
| `multiwindow_stable` survived/eliminated | 5 / 9 | 5 / 9 | 是 |
| `entry_eligible` survived/eliminated | 4 / 1 | 4 / 1 | 是 |
| `netcover` survived/eliminated | 0 / 4 | 0 / 4 | 是 |
| `position_cap` survived/eliminated | 0 / 0 | 0 / 0 | 是 |

原始 AUTOPSY 输出分别在 `reports/lp_tp_h/20260811/h4_base_invariance/baseline_29ac336/`
及 `.../current/`。结论：Base 的既有数值行为在该固定快照上逐闸不变。

## H5 — A 档 36 池分段 checkpoint（未完成）

H5 的确定性输入是固定股票宇宙中 `chain=Solana && tier=A && protocol_type=clmm` 的 **36** 池，已保存为
`reports/lp_tp_h/20260811/h5_solana_a_clmm_36_universe.json`。首次 checkpoint（offset 0、limit 6、每页 60、
目标 3h、最多 10 页）在单池的免费 `getTransaction` 历史分页节流中运行超过十分钟而未落盘完整段；中断时栈位于
`RpcPool._pace_request(... getTransaction ...)`。只中断了本次 H5 子进程，未影响任何受保护观测进程。

因此没有完整 checkpoint，H5 的真实完成度为 **0/36**；没有 NetCover 分布、`>=1.0` 数量、三档 terminal 拆分或
“算出来没过/没算成”可报告。不会把未完成的 36 池归类成失败，也不会以更宽经济阈值、付费 RPC 或跳过采样来凑出数。
B/C 无稳定腿的不可达标注没有被修改。

## 最后一次编辑后的全量回归

```text
$ python3 -m pytest tests/ -q
3096 passed, 14 skipped in 64.48s (0:01:04)

$ go test ./...
ok  github.com/lpbot/lpbot/adapters/broadcast/disabled (cached)
...（各包均为 ok 或 [no test files]，命令退出码 0）
ok  github.com/lpbot/lpbot/pkg/tickmath (cached)
?   github.com/lpbot/lpbot/scripts/aggregate-verdict [no test files]
ok  github.com/lpbot/lpbot/tests/chaos (cached)
?   github.com/lpbot/lpbot/tests/fork [no test files]
ok  github.com/lpbot/lpbot/tests/property (cached)
ok  github.com/lpbot/lpbot/tests/property/mocks (cached)
```
