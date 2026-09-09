# RH-02af：首步把池的全部历史手续费当成了这一步的收益

## 实测（2026-09-09 16:48 UTC，NAV 首次算出）

```
episode 4806-0  n=199 eligible=198 steps_without_nav=31
nav_start = 143047.5359756284883369817912...
nav_end   = 143089.7749421933741150305319...
net_pnl   = 42.2389665648857780487407...
capital_usd = 10000   position_usd = 1000
```
**NAV 比本金高出 13 倍。** 算术对得上：
```
fg0 / 2^128        = 133.0897
× position 1000    = 133089.69
+ capital 10000    ≈ 143090     ← 与实测 nav_start 吻合
```

## 根因

`scripts/lp_rh_shadow_runner_v1_readonly.py`：
```
d0 = Decimal(str(fg0)) - (prev_fg0 or Decimal(0))
d1 = Decimal(str(fg1)) - (prev_fg1 or Decimal(0))
accrued += position_usd * (d0 + d1) / FEE_GROWTH_SCALE
prev_fg0, prev_fg1 = Decimal(str(fg0)), Decimal(str(fg1))
```
`prev_fg0` 初值为 `None`，`or Decimal(0)` 使**首步的 `d0` 等于
`feeGrowthGlobal` 的全部累计值**——那是池自创建以来所有 LP 赚到的手续费，
不是这一步的增量。

`feeGrowthGlobal` 是**单调累计量**，只有相邻两次读数之差才是增量。
**没有前值时，增量是「未知」，不是「等于全部」。**

后果：`nav_start` 与 `nav_end` 都虚高约 133090；
`net_pnl`（两者之差）侥幸正确，因为污染项相同而抵消；
但 `hodl_delta` 的对比、任何 NAV 绝对值判断、以及跨 episode 比较全部失真。

## 改动（只改这一处）

首次拿到 `fg0`/`fg1` 时**只记录不累加**：
- `prev_fg0 is None` 或 `prev_fg1 is None` → 把当前值存进 `prev_fg0/prev_fg1`，
  **`accrued` 不变**（该步 `accrued` 增量为 0）。
- 之后各步照旧算差值。
- **该步的 `nav` 仍应算出**（`accrued` 为 0 是合法值，
  首步 NAV 就等于 `wallet + lp_principal`），
  **不要因此把首步变成 `nav=None`**——那会与「没有 fg 数据」混淆。
- `or Decimal(0)` 这个写法一并去掉：**用 `is None` 显式判断**。
  `Decimal(0)` 是合法的 feeGrowth 读数（新池），`or` 会把它误判为「没有前值」。

## 不许动
不改 `FEE_GROWTH_SCALE`、不改 `compute_nav`、不改取样器、不改采集器。
不改 `steps_without_nav` 的语义（它数的是 `nav is None` 的步数）。
不联网。单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**不要执行任何 git 命令，尤其不要 commit。**

## 新增测试 `tests/test_lp_rh_first_step_accrual_v1_readonly.py`（≤240 行，**≥12 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。** 必测：

- **★两条样本，fg 从 `X` 增到 `X+Δ`（`X` 取实测量级 4.5e40）：
  首步 `accrued` 增量为 0，NAV 等于 `capital`（本例 10000），
  **不含 133089 那一坨**★**
- **★第二步的 `accrued` 只反映 `Δ`：断言
  `nav_2 - nav_1 == position_usd * Δ_total / 2**128`（精确相等，用 `Decimal`）★**
- **★首步 NAV 不为 `None`★**（`accrued=0` 是合法值，不得与「无数据」混淆）
- **★`fg0` 读数恰为 `Decimal(0)`（新池）时，仍被视为「有前值」，
  第二步差值从 0 起算，而不是被 `or` 当成没有前值★**
- 三条样本递增 → `accrued` 单调不减。
- `fg` 中途出现 `None`（链降级）→ 该步无 NAV，且**不污染** `prev_fg`
  （下一条有值的样本相对于最后一个有效前值算差，断言差值正确）。
- 回归：`steps_without_nav` 仍只数 `nav is None` 的步数。
- 回归：`net_pnl` 仍是 `nav_end - nav_start`。
- 回归：`hodl_delta` 计算不受影响。
- 大数精度：`Δ` 取 1，断言 `accrued` 增量与 `Decimal(1000) / Decimal(2)**128`
  **在默认 28 位精度下相等**（即 `abs(a - b) <= abs(b) * Decimal("1e-25")`）。
  **★不要断言「乘回去精确等于 1000」——`1000/2**128` 在 28 位精度下本就不可精确表示，
  那个等式数学上无解★**（主脑上一版 spec 在此写错，worker 因此卡住 10 分钟，
  已改正；不要试图用 `getcontext().prec` 提高精度来硬凑，保持默认上下文）。
- fg 递减（异常，理论上不该发生）→ **只断言不抛异常且 `nav` 仍可得**，
  并在测试 docstring 里写明观察到的实际行为。
  **不要为此改动源码**；若认为源码行为不合理，停下来报告。
- 端到端：`run_episode` 跑 3 条带 fg 的样本，`nav_start` 落在
  `capital ± position` 量级内（不是 143047）。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_first_step_accrual_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥12 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。
