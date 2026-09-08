# RH-05h：`exit_depth` 的三个语义缺陷修复（缺失、拼错、耗尽必须可区分）

## 背景

`scripts/lp_rh_exit_depth_v1_readonly.py` 的**计算本身是正确的**（今日两次实盘验证：
WETH/USDG 池与 SPY 两池，冲击随规模单调、量级合理）。缺陷全在**状态语义**上：
三种完全不同的情况被压成同一个 `INPUTS_UNAVAILABLE: EXIT_QUOTE`。

三个缺陷都由主脑今日亲跑撞出，证据见
`reports/rh_pivot/20260907T124500Z/RH-05-research/SPY_EXIT_DEPTH_RECHECK_20260908.md`
与 `EXIT_DEPTH_LIVE_20260908.md` §2。

| # | 现状 | 为什么错 |
|---|---|---|
| 1 | `_state_factors` 缺 decimals 默认 `0`、缺价格默认 `Decimal(1)` | 静默把 $50,000 当成 50,000 wei，返回「深度为零」。**不抛异常、只在部分输入上给错答案。** |
| 2 | `**pool_state` 收下任何拼错的键，内部 `KeyError` 被吞成 `INPUTS_UNAVAILABLE` | 调用方分不清「我把 `current_tick` 写成了 `tick`」和「链上真没数据」。主脑为此白跑三轮。 |
| 3 | `liquidity_exhausted` 返回 `INPUTS_UNAVAILABLE` | 「池子吃不下这个量」是**算出来的答案**（PRD 语义属 `COMPUTED_FAIL`），不是输入缺失。fail-closed 下动作相同、无资金风险，但审计链分不清两者。 |

## 改哪些文件

只改 `scripts/lp_rh_exit_depth_v1_readonly.py`，只补
`tests/test_lp_rh_exit_depth_v1_readonly.py`。**不得动任何其他文件。**

### 1. 必需键显式校验
在 `exit_depth_for_size` 与 `measured_exit_depth_cap` 里，进入计算前先检查
`REQUIRED_POOL_KEYS = ("sqrt_price_x96","current_tick","tick_spacing","fee_pips","liquidity")`。
缺任何一个 → 返回
`{"max_exit_usd": None, "impact_at_size_bps": None, "sufficient": False,
  "reason": "INPUTS_UNAVAILABLE: MISSING_KEYS", "missing_keys": [按字母序的列表]}`。
**`missing_keys` 必须列出具体键名**，这正是拼错时能立刻看出问题的东西。

### 2. 精度与价格不再有宽容默认
`_state_factors` 缺 `token0_decimals`/`token1_decimals`（或旧名 `decimals0`/`decimals1`），
或既无 `input_price_usd` 也无对应侧的 `token0_price_usd`/`token1_price_usd` 时，
**返回 `None` 而不是 `(1, 0)`**，上层据此返回
`reason = "INPUTS_UNAVAILABLE: PRICE_OR_DECIMALS"`。
**禁止保留 `Decimal(1)` 与 `0` 作为兜底。**

### 3. 流动性耗尽是 COMPUTED_FAIL
`liquidity_exhausted` 为真时返回
`{"max_exit_usd": <二分搜索得到的可退出上限，可为 Decimal(0)>,
  "impact_at_size_bps": <对应冲击，可为 None>,
  "sufficient": False, "reason": "COMPUTED_FAIL: LIQUIDITY_EXHAUSTED"}`。
注意：此处 `max_exit_usd` 为 0 是**算出来的 0**（池子真的吃不下），与
`INPUTS_UNAVAILABLE` 的 `None` 语义不同，不得混用。

## 不许动

- **一条现有测试都不许改、不许删、不许加 skip/xfail。** 现有 29 条必须原样全绿。
  若某条现有测试因本次语义变更而失败，**停下来在最终报告里写明是哪一条、为什么**，
  不要改它——那意味着 spec 与既有契约冲突，需要主脑裁决。
- 不改任何计算逻辑（`simulate_exit_swap`、tick 数学、二分搜索）。本包**只改状态与校验**。
- 不改六个受保护常量。不联网。

## 新增测试（追加进现有测试文件，**≥12 条**）

- 少传 `current_tick` → `reason` 含 `MISSING_KEYS` 且 `missing_keys == ["current_tick"]`。
- 同时少传 `fee_pips` 与 `liquidity` → `missing_keys == ["fee_pips","liquidity"]`（有序）。
- 拼错成 `tick=...`（而非 `current_tick`）→ 仍报 `MISSING_KEYS` 且列出 `current_tick`。
  **这条直接复现主脑今日白跑三轮的场景。**
- 缺 `token0_decimals` → `reason` 含 `PRICE_OR_DECIMALS`，且 `max_exit_usd is None`
  （**断言 `is None`，不是 0**）。
- 缺一切价格来源 → 同上。
- 传全 `input_price_usd` 但缺 decimals → 仍报 `PRICE_OR_DECIMALS`（价格不能替代精度）。
- 构造一个极浅的 tick 集合使流动性耗尽 → `reason == "COMPUTED_FAIL: LIQUIDITY_EXHAUSTED"`，
  且 `max_exit_usd is not None`（是算出来的数，可能为 0）。
- 同一场景断言 `sufficient is False`。
- 正常充足场景仍返回 `EXIT_DEPTH_OK` 且 `max_exit_usd == position`（回归保护）。
- 正常不足但未耗尽场景仍返回 `EXIT_DEPTH_INSUFFICIENT`（回归保护）。
- `tick_data` 为空列表 → 仍是 `INPUTS_UNAVAILABLE`（现有行为不变）。
- 三种 `INPUTS_UNAVAILABLE` / `COMPUTED_FAIL` 的 `reason` 字符串两两不相等。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_exit_depth_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向测试 ≥41 全绿（原 29 + 新增 ≥12）；全量 0 failed / 14 skipped。
`git diff --stat` 只含上述两个文件。单次写 ≤120 行，写完 `ast.parse` 自检。
把两条命令的原样尾部输出贴出来。
