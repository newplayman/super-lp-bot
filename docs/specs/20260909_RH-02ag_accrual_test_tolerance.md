# RH-02ag：RH-02af 的实现是对的，是测试的比较方式不成立

## 现状

`scripts/lp_rh_shadow_runner_v1_readonly.py` 的首步累计修复**已正确落地**：
```
if prev_fg0 is not None and prev_fg1 is not None:
    d0 = cur0 - prev_fg0
    d1 = cur1 - prev_fg1
    accrued += position_usd * (d0 + d1) / FEE_GROWTH_SCALE
prev_fg0, prev_fg1 = cur0, cur1
```
实证：首步 `nav == Decimal('10000')`，正好等于 `capital_usd`，
修复前的 `nav_start = 143047.53`（含 133089 历史累计污染）已消除。

**但 `tests/test_lp_rh_first_step_accrual_v1_readonly.py` 有 5 条测试红着**，
原因不在实现。

## 根因：量级悬殊相减，尾数必然丢失

`nav = 10000 + 2.9387358770557187699218413430556141945466638919302188E-35`。
Decimal 默认 28 位有效数字，这个加法本身就吸收掉了小数的尾部；
再 `nav_2 - nav_1` 取回来，只能得到前 40 位一致、末尾有差的值：
```
实际  Decimal('2.9387358770557187699218413430556141945467E-35')
期望  Decimal('2.9387358770557187699218413430556141945466638919302188037718792656960431486368179E-35')
```
**测试拿它与「直接算出的完整小数」比 `==`，数学上不可能成立。**
（这与主脑上一版 spec 要求「乘回去精确等于 1000」是同一类错误，
**都是主脑写 spec 时没考虑 Decimal 上下文精度**。）

## 只改测试文件，一行实现都不许动

`tests/test_lp_rh_first_step_accrual_v1_readonly.py`：
把所有「NAV 差值 == 期望增量」的**精确相等**断言，改为**相对误差**断言：
```
assert abs(actual - expected) <= abs(expected) * Decimal("1e-25")
```
涉及（以实际报错为准，不限于）：
`test_second_step_accrued_reflects_only_delta`、
`test_net_pnl_is_nav_end_minus_nav_start`、
`test_fg_zero_reading_treated_as_previous`、
`test_large_number_precision_delta_one`、以及第三步增量那条。

**必须保留的断言强度（不得借机放宽）**：
- **★首步 `nav` 仍须**精确等于** `capital_usd`（`== Decimal("10000")`）★**
  ——这是本次修复的核心，是精确值，不许改成近似。
- **★首步 `accrued` 增量为 0★**（精确）。
- **★`nav` 不得接近 143047 那个量级★**：断言 `nav < capital_usd * 2`。
- 单调性、`None` 处理、`fg` 递减不抛异常等断言**保持原样**。

## 不许动
**不改 `scripts/` 下任何文件**——实现已正确。
不改 `FEE_GROWTH_SCALE`、不调 `getcontext().prec`。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**不要执行任何 git 命令，尤其不要 commit。**

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_first_step_accrual_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向全绿；全量 **0 failed / 14 skipped**（现有 4411 passed 基线之上只增不减）。
两条命令尾部原样贴出。
