# RH-02cm — T37：价格出区间的那些步，不该计入手续费

## 背景

`scripts/lp_rh_in_range_v1_readonly.py`（PRD T37）实现完整、有测试、
**生产引用 0 次**。runner 的手续费累计：

```python
fee_usd = (tok0 * price + tok1) * quote
accrued += fee_usd          # 每一步都加，不问价格在不在区间内
```

集中流动性头寸只在价格落于 `[tick_lower, tick_upper)` 内才赚手续费。
价格越界期间全池的 `feeGrowthGlobal` 照涨，而这个头寸一分不赚——
照加就是高估。

主脑已实测（`reports/AUDIT_in_range_fraction_20260911.md`）：

```
判定窗口内 5038 个样本，in_range_fraction = 1.0000，出区间 0 次
=> 当前高估倍数 1.00x
```

**所以这不是在修一个正在发生的错误，是在补一个缺失的机制。**
价格一旦离开 ±10% 区间，现在的代码会继续记账。

## 设计：按步判断，不用 fraction 折算

`effective_fee_ev(full_range_fee_ev, in_range_fraction, concentration_multiplier)`
是给 **EV 预估**用的（乘一个平均占比）。本包做的是**实际累计**，
逐步判断更准确也更简单：某一步价格在区间外，那一步就不累加。

**不要引入 `concentration_multiplier`**——它需要按区间宽度与流动性分布
估算，模块明确拒绝估算它，本包也不估。逐步累计不需要它。

## 要做的事

改 `scripts/lp_rh_shadow_runner_v1_readonly.py`。

### 1. 开仓时算出区间边界

在库存解析那一步（`open_valid = True` 附近，已有 `entry_price`、
`range_pct_val`、`dec0_val`、`dec1_val`）：

```python
lo_price = entry_price * (1 - range_pct_val / 100)
hi_price = entry_price * (1 + range_pct_val / 100)
tick_lower = tick_from_price(lo_price, dec0=dec0_val, dec1=dec1_val)
tick_upper = tick_from_price(hi_price, dec0=dec0_val, dec1=dec1_val)
```

`tick_from_price` 从 `lp_rh_in_range_v1_readonly` 导入。
**注意两个 tick 的大小顺序**：价格与 tick 的方向取决于 token 排列，
用 `min()` / `max()` 规范化，不要假设 lower < upper。

### 2. 每步判断，决定是否累加

```python
step_tick = tick_from_price(price, dec0=..., dec1=...)
in_range = (tick_lo <= step_tick < tick_hi)     # 左闭右开，与模块一致
if in_range:
    accrued += fee_usd
else:
    out_of_range_steps += 1
```

**`price` 为 None 时**：既不累加也不计入 out_of_range——
缺数据不等于出区间（`in_range_fraction` 的 docstring 就是这么规定的，
本包必须保持一致）。单独计入 `skipped_no_price`。

### 3. 记录

- episode summary 加
  `in_range: {"in_range_steps", "out_of_range_steps", "skipped_no_price",
  "fraction", "tick_lower", "tick_upper"}`
  `fraction = in_range_steps / (in_range_steps + out_of_range_steps)`，
  分母为 0 时是 **None 不是 0**
- `rh_position_marks.unvalued_risk_json` 里每步加 `"in_range": true/false/null`
  （null = 无价格）
- daemon 日志行打印 `in_range=<fraction>`

## 关键：fraction 为 1.0 时行为必须逐字不变

当前生产数据 100% 在区间内。接线后**同一批样本算出的 `accrued`、`nav`、
`net_pnl`、`hodl_delta` 必须与接线前逐字相同**。

这一条由测试第 1 条钉死。今晚的 NAV 公式刚与独立参考实现对齐到 1e-26
（`9c59e2e`），任何偏移都不可接受。

## 不许动

- 不要改 `inventory_for_position`、`compute_nav`、`hodl_benchmark`、
  `net_pnl` 的任何公式。
- 不要改 `fee_usd` 的算法（`tok0 * price + tok1) * quote`），
  只改**要不要把它加进 accrued**。
- 不要引入 `concentration_multiplier`，不要调 `effective_fee_ev`。
- 不要改 NetCover 的 `fee_ev_usd`（那是预估路径，不在本包范围）。
- 不要碰 `scripts/lp_rh_shadow_daemon_v1_readonly.py`。
- 测试用内存库或 `tmp_path`；对生产库只读。
- **不要重启或 kill 任何进程**（采集器 2271374 / daemon 1789399 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

本会话已有**八次**「构造的输入进不去目标分支」，包括一次
`insert_row` 不 commit 导致对空表断言。逐条确认断言真的走到了目标分支。

1. **全部在区间内 → `accrued` / `nav` / `net_pnl` 与接线前逐字相同。**
   做法：构造一组价格都在区间内的样本，把结果与硬编码的期望值比对
   （期望值从当前实现跑一次取得，并在注释里写明它代表「接线前的行为」）。
   ——这条是整个包的安全保证。
2. 中间若干步价格跌破 `tick_lower` → 那些步不累加，
   `out_of_range_steps` 等于越界步数，`accrued` 小于全程在区间内的情形。
3. 价格涨过 `tick_upper` → 同样不累加（两侧都要测，不要只测一侧）。
4. `price` 为 None 的步 → 既不累加也不计入 `out_of_range_steps`，
   计入 `skipped_no_price`。**不要当成出区间**。
5. 全程出区间 → `accrued == 0`，`fraction == 0`，episode 不崩
   （PRD T37 的原话：全程 out-of-range 时 fee 为 0，不按全池 APR 分摊）。
6. 一个价格都没有 → `fraction is None`（**不是 0**）。
7. `rh_position_marks.unvalued_risk_json` 里逐步的 `in_range` 值与
   实际判断一致（抽查三步：区间内、区间外、无价格）。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥7 条。
2. 全量 `python3 -m pytest tests/ -q` 通过。
3. `grep -n "tick_from_price" scripts/lp_rh_shadow_runner_v1_readonly.py` 有生产调用。
4. `grep -n "effective_fee_ev\|concentration_multiplier" scripts/lp_rh_shadow_runner_v1_readonly.py`
   **无输出**（确认没引入未估算的放大倍数）。
5. `git status --short` 里只有
   `scripts/lp_rh_shadow_runner_v1_readonly.py` 和它的测试被改动。
