# RH-02ac：闸门通了但 NAV 算不出——采集器没采 feeGrowthGlobal

## 实测现状（2026-09-09 15:1x UTC，RTH 开盘中）

RH-02aa／RH-02ab 落地后，shadow 首次产生合格步：
```
episode rh-shadow-20260909150846-0
  status_counts     {"COMPUTED_PASS": 198, "COMPUTED_FAIL": 1}
  conjunct_failures 各 1（唯一失败者是那条 CHAIN_DEGRADED 样本，正确拦住）
  ★steps_without_nav = 199★   nav_start / nav_end / net_pnl 全为 None
```

**199 步全部没有 NAV。** 根因在 `run_episode`：
```
fg0, fg1 = sample.get("fee_growth_global_0"), sample.get("fee_growth_global_1")
nav = None
if fg0 is not None and fg1 is not None:
    ...
    nav = compute_nav(...)
```
而 `rh_market_states` 的 15 个列里**没有这两列**，`dict.get` 返回 `None` 且不报错。
**与 `source_event_time` 是同一形状的缺陷，今天第三次。**

后果：shadow 能判定「可以开仓」，但**算不出任何收益**。
PRD §21.2 的 Stage B 门槛要求全成本净收益证据，没有 NAV 就无从谈起。

## 实测过的选择器（主脑对本池实调，直接用）

```
feeGrowthGlobal0X128()  0xf3058399  -> 45250119888616697086558471479183978286028
feeGrowthGlobal1X128()  0x46141319  -> 83497510076664027119448656548640
```

## ★uint256 必须存 decimal TEXT★

`45250119888616697086558471479183978286028` ≈ 4.5e40，
而 SQLite `INTEGER` 上限约 9.2e18（2^63−1）。
**用 INTEGER 列会静默溢出/失真；用 float 更糟。**
必须与 `rh_assets.multiplier_raw` 同规矩：**列类型 TEXT，全程不经 `int` 之外的转换，
存的是十进制字符串**。`run_episode` 里已有 `Decimal(str(fg0))`，与 TEXT 天然兼容。

## 改动

### A. `scripts/lp_rh_store_v1_readonly.py`
在 `rh_market_states` 列清单末尾追加
`"fee_growth_global_0 TEXT"`、`"fee_growth_global_1 TEXT"`，
并让既有的幂等加列逻辑（`_ensure_columns`，RH-02w 刚扩展过）也补这两列
——现有 7700+ 行必须 `ALTER TABLE ADD COLUMN` 保留，**不得重建表**。
同时把这两列加入 `_DECIMAL_TEXT_COLUMNS["rh_market_states"]`（若该表已有条目则追加）。

### B. `scripts/lp_rh_collector_v1_readonly.py`
每轮用现有 `rpc_fn` 调上述两个选择器（`eth_call` + `latest`），
把结果按 **uint256 十进制字符串**写入两列。
- 返回值不是 `0x` 开头、长度不足、或调用出错 → 该列写 `None`，
  **绝不写 0**（`0` 是合法的 feeGrowth 初值，与「没问到」必须可区分）。
- 与现有 `derived_block_hash` 等同轮写入，不新增额外轮次。

## 不许动
不改 `run_episode` 的 NAV 计算逻辑（它已经正确，只是拿不到输入）。
不改 `compute_nav` / `net_pnl` / `hodl_benchmark`。
不改 `reference_bid`／`reference_ask`／`multiplier_human`／`oracle_paused`。
不重建任何表。不联网（测试用假 `rpc_fn`）。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**不要执行任何 git 命令，尤其不要 commit。**

## 新增测试 `tests/test_lp_rh_fee_growth_v1_readonly.py`（≤240 行，**≥14 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。** 必测：

- **★写入实测值 `45250119888616697086558471479183978286028` 后读回，
  **逐字符相等**且类型为 `str`★**（uint256 不得失真）
- **★`Decimal(读回值) == Decimal(原值)`，且断言该值 > 2**63（证明超出 INTEGER 范围）★**
- `feeGrowthGlobal0X128` 调用出错 → 该列 `None`，**不是 0**。
- 返回 `0x0…0`（真值 0）→ 写 `"0"`，**键有值**（0 与「没问到」可区分，两条断言）。
- 返回非 `0x` 开头／长度不足 → `None`。
- 一个成功一个失败 → 各自独立（成功那列有值，失败那列 `None`）。
- **★旧库迁移：先建不含两列的表并插 2 行，`migrate` 后列被加上、
  原有 2 行仍在、其值为 `None`★**（不得重建表）
- `migrate` 幂等：连跑两次不报错。
- 回归：`derived_block_hash`／`session`／`source_event_time`／`reference_mid`
  四列行为不变（四条）。
- 端到端：构造带两列的样本喂给 `run_episode`，断言 `steps_without_nav` 减少
  且 `nav` 非 `None`（**证明这正是 NAV 缺失的原因**）。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_fee_growth_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。
