# RH-02ak：给 v3_inventory 增加「仓位按当前价重估」函数

## 为什么需要它（主脑实测，第三层缺陷）

`scripts/lp_rh_shadow_runner_v1_readonly.py` 的 NAV 把 LP 本金当**常数**：

```python
nav = compute_nav(wallet=capital_usd - position_usd,
                  lp_principal=position_usd,       # ← 恒 1000，从不重估
                  accrued_fees=accrued, ...)
```

于是 NAV 的**唯一变动项是只增不减的手续费**，`net_pnl` 结构性恒正，
**shadow 永远不会报告亏损**。实测真实 50 分钟窗口：被忽略的仓位价值变化是
**-2.245 USD，是同期手续费(0.0277)的 81 倍**。修好手续费量纲（RH-02ai）
也救不了这一层——那只是把 27.49 改成 0.0277，符号仍然恒正。

本包只做**纯函数**，不接线到 shadow_runner（接线是 RH-02al，主脑另派）。

## 你要交付的（两个文件的完整新版）

1. `scripts/lp_rh_v3_inventory_v1_readonly.py` —— **在现有内容基础上增加一个函数**
2. `tests/test_lp_rh_v3_inventory_v1_readonly.py` —— **在现有测试基础上增加新测试**

**硬约束：现有的 `inventory_for_position`、`V3Inventory`、
以及现有的 8 个测试函数，一行都不许改。** 只允许新增。
（它们刚通过主脑的独立验收并已入库 commit `3ad02ec`，改动等于推翻已验收产物。）

## 要实现的函数

```python
def position_value_at(*, price, liquidity_human, entry_price, range_pct,
                      quote_usd_per_token1):
    """Mark a v3 range position to market at `price`."""
```

标准 v3 库存公式，**两腿数量随价格变化——这正是无常损失的来源**：

```
sqrtPa = sqrt(entry_price * (1 - range_pct/100))
sqrtPb = sqrt(entry_price * (1 + range_pct/100))
sqrtP  = sqrt(price)

price <= lower:   a0 = L*(sqrtPb-sqrtPa)/(sqrtPa*sqrtPb),  a1 = 0        # 全 token0
price >= upper:   a0 = 0,                                  a1 = L*(sqrtPb-sqrtPa)  # 全 token1
区间内:            a0 = L*(sqrtPb-sqrtP)/(sqrtP*sqrtPb),     a1 = L*(sqrtP-sqrtPa)

value_usd = a0 * price * quote + a1 * quote
```

返回至少含 `value_usd`、`amount0_human`、`amount1_human` 的结构
（沿用现有 `V3Inventory` 的风格，新建一个 frozen dataclass 也可以）。

## 主脑已独立算定的锚点（照这些写断言，相对容差 `1e-25`）

参数：`entry_price=2484`、`range_pct=10`、`position_usd=1000`、
`dec0=18`、`dec1=6`、`quote=1`，由 `inventory_for_position` 得
`liquidity_human = 205.04308192280799205984882428818144653845292934029`。

| price | value_usd | amount0_human | amount1_human |
|---|---|---|---|
| 2484（=entry） | `1000` **精确** | `0.19145712873772488253936834449842371736793257180588` | `524.42049221549139177220903226591548605805549163421` |
| 2474.055679 | `998.05506101569517744962307444767141901132021256836` | `0.19971692330763781371243527892716317242894531930221` | `503.94427271402638035922849969797434490383182136826` |
| 2235.6（=下界） | `925.53051912632391929181381822363713956594958075681` | `0.41399647482837892256746010834837946840487993413706` | `0` |
| 2732.4（=上界） | `1023.2124879882894863806499472872990837981715472935` | `0` | `1023.2124879882894863806499472872990837981715472935` |
| 1000（远低于下界） | `413.99647482837892256746010834837946840487993413706` | `0.41399647482837892256746010834837946840487993413706` | `0` |
| 5000（远高于上界） | `1023.2124879882894863806499472872990837981715472935` | `0` | `1023.2124879882894863806499472872990837981715472935` |

**这些值是主脑用 50 位精度独立算出的，不是从任何实现里抄的。**
你若算出别的值，先怀疑自己的公式，不要改断言迁就结果。

## 验收标准

1. 上表六行全部断言通过（`price == entry` 那行必须**精确等于 `position_usd`**，
   这是「开仓瞬间仓位市值等于投入本金」的自洽性，相对误差 `< 1e-40`）。
2. **出界后 token 数量冻结**：断言 `price=1000` 与 `price=2235.6`（下界）的
   `amount0_human` **完全相等**；`price=5000` 与 `price=2732.4`（上界）的
   `amount1_human` **完全相等**。这是 v3 的定义性质。
3. **无常损失方向**：构造同一个价格变动，断言
   `position_value_at(P1) - position_value_at(P0)`
   **劣于**「固定两腿按同样价格重估」的变化
   （即 v3 仓位相对 hodl 有非正的价格暴露差）。用上表 2484 → 2474.055679 这组，
   主脑算出的差值是 **-0.0400036836926775543** 量级，容差 `1e-15`。
4. 失败关闭：`quote_usd_per_token1=None`、`price<=0`、`liquidity_human<=0`、
   `range_pct<=0` 一律抛 `ValueError` 且消息里点名是哪个参数。
5. 不许有模块级 `getcontext().prec = N`，一律 `localcontext()`。
   测试要断言导入前后全局精度都是 28（现有测试已有这个模式，照抄）。
6. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_v3_inventory_v1_readonly.py -q -p no:cacheprovider`
   全绿，且**原有 8 个测试全部仍在、仍绿**。

## 交付格式（你在只读沙箱里，写不了文件）

最后一条消息里只包含两个文件的**完整内容**，用下面的标记分隔，
标记独占一行、一字不差：

```
===FILE:scripts/lp_rh_v3_inventory_v1_readonly.py===
（完整内容，不要用 markdown 代码围栏包裹）
===FILE:tests/test_lp_rh_v3_inventory_v1_readonly.py===
（完整内容，不要用 markdown 代码围栏包裹）
===END===
```

动笔前先用 python（`python3 -c` 或 heredoc，不写文件）把你的公式实际算一遍，
确认与上表六行一致。若不一致，**在文件内容之前先用文字说明分歧**，不要擅自改断言。
