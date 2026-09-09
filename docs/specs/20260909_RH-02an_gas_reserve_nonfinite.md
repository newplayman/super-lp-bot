# RH-02an：gas 储备闸门接受 Infinity 余额

## 铁证（主脑已核实）

`scripts/lp_rh_gas_reserve_v1_readonly.py:44-57,100-137`：
`_to_decimal` 接受 `Decimal("Infinity")`，reserve gate 没有有限性校验。

复现：`native_balance_wei=Infinity` → 返回 `pass=True, reason="OK",
available_usd=Infinity`，而实际所需仅 `$1.05`。
**无异常、无失败状态，数字"正常"地通过了一个资金安全闸门。**

`Infinity` 不是假想输入：`Decimal(str(x))` 在 `x` 为 `float('inf')`、
`"Infinity"`、`"1e999"`（溢出）时都会产出它，而 RPC 返回值经过若干次
除法/换算后完全可能变成 `Infinity` 或 `NaN`。

## 你要做的

在该模块**所有对外函数的入口**加有限性与符号校验：

- 任何金额/价格/gas 量参数：必须 `is_finite()`，否则失败关闭；
- `NaN` 同样必须被拦（`Decimal("NaN").is_finite()` 为 False，一并覆盖）；
- 余额、价格必须 `>= 0`（价格 `> 0`）；
- 失败时返回该模块**既有风格**的失败结构
  （先 `sed -n '90,140p'` 看它现在怎么表达失败，照抄那个形状，
  reason 用 `INPUTS_UNAVAILABLE: <哪个参数>`），**不要抛异常**，
  也不要返回 `pass=True`。

## 不许动

`scripts/lp_rh_readiness_v1_readonly.py`（另一条线正在改它）、
任何其它 `scripts/`、任何 `.db`。
`tests/test_lp_rh_gas_reserve_v1_readonly.py` **只允许新增测试**。

## 验收标准

1. `native_balance_wei=Decimal("Infinity")` → `pass is False`，
   reason 含 `INPUTS_UNAVAILABLE`。
2. `NaN` 同样阻断。
3. 负余额、价格 `<= 0` 同样阻断。
4. **正常输入行为不变**：用该模块既有测试里的正常用例，
   断言修改前后返回值完全一致（这条是防回归，必须有）。
5. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_gas_reserve_v1_readonly.py -q -p no:cacheprovider`
   全绿，原有测试全部仍在。

## 交付格式

同上，两个文件完整内容：

```
===FILE:scripts/lp_rh_gas_reserve_v1_readonly.py===
===FILE:tests/test_lp_rh_gas_reserve_v1_readonly.py===
===END===
```
