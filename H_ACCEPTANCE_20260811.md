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

## H3 — 采样深度加固（未完成，未提交）

首轮免费 RPC 原始输出（每页 60、目标 3h、验收临时上限 3 页）：

```json
{"swap_count": 169, "actual_span_hours": 1.2205555555555556, "pages_fetched": 3, "replay_stop_reason": "PAGINATION_LIMIT_REACHED", "transactions_checked": 180}
```

对应结论为 `FAIL_CLOSED:SIGMA_SAMPLE_INSUFFICIENT:n=100,span=1.2h`。这证明旧的 60 笔边界采样并不稳定；
新代码会继续翻页到默认最多 10 页，但本轮尚未完成三次都达到 3h 的验收；H3 与 H5 仍不宣称完成。

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
