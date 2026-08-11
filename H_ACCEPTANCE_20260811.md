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
