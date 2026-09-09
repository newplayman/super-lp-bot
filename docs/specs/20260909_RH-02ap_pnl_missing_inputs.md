# RH-02ap：PnL 回放的四个输入缺失时静默当 0，外部入金会被记成利润

## 铁证（主脑已核实）

`scripts/lp_rh_pnl_v1_readonly.py:213-219`：

```python
external = Decimal(step.get("external_net_flow", "0"))
...
attr = attribution(
    nav_delta=nav_delta,
    fee_income=Decimal(step.get("fee_income", "0")),
    gas_paid=Decimal(step.get("gas_paid", "0")),
    price_move_effect=Decimal(step.get("price_move_effect", "0")),
)
```

四个 `.get(..., "0")` 都是**宽容默认值**。最危险的是第一个：
`net_pnl = nav - prev_nav - external`，若某一步忘了写 `external_net_flow`，
**一笔 $100 的外部入金会整笔变成 $100 的利润**。
PRD D03 明确规定「NAV ＋外部现金流为唯一实际 PnL」，
把外部现金流静默当 0 直接违反这条。

后三个的后果轻一些（归因分解失真而非总额失真），但同样是「缺数据」与
「确实为零」不可区分。

## 你要做的

区分「显式的零」与「根本没提供」：

- `external_net_flow` **缺失**（键不存在）→ 该步不可计算，
  `net_pnl` 返回 `None`，并在该步的输出里记明原因
  （用该模块既有的失败表达方式，先 `sed -n '190,240p'` 看它现在怎么表达不可用）。
  显式的 `"0"` / `0` / `Decimal(0)` 仍然合法，照常计算。
- `fee_income` / `gas_paid` / `price_move_effect` 缺失 → 归因结果标记为
  不可对账（该模块已有 `reconciled` 概念，让它为 `False` 并点名缺哪个键），
  **但不要因此让整步失败**——它们只影响分解，不影响总额。
- **不要抛异常**，这是回放路径，要能继续处理后续步。

## 不许动

`scripts/lp_rh_shadow_runner_v1_readonly.py`（两条线在改它）、
`scripts/lp_rh_v3_inventory_v1_readonly.py`、任何 recorder / daemon、任何 `.db`。
`tests/test_lp_rh_pnl_v1_readonly.py`（若存在）**只允许新增测试**。

## 验收标准

1. step 里**没有** `external_net_flow` 键 → 该步 `net_pnl is None`，
   且原因里出现 `external_net_flow`。
2. step 里 `external_net_flow="0"` → 正常计算，**行为与修改前完全一致**
   （这条是防回归）。
3. 构造：价格不变、LP 本金不变、钱包因外部入金增加 $100，
   且 step **省略** `external_net_flow` → 断言不再输出 `net_pnl=+100`。
4. 缺 `fee_income` → 该步仍有 `net_pnl` 数值，但归因标记为不可对账且点名该键。
5. `/root/lp-bot/.venv/bin/python -m pytest tests/ -k pnl -q -p no:cacheprovider`
   全绿，原有测试全部仍在。

## 交付格式（只读沙箱，写不了文件）

最后一条消息只包含被改文件的完整内容，标记独占一行：

```
===FILE:scripts/lp_rh_pnl_v1_readonly.py===
===FILE:tests/test_lp_rh_pnl_v1_readonly.py===
===END===
```

若 `tests/test_lp_rh_pnl_v1_readonly.py` 不存在，先 `ls tests/ | grep pnl`
找到实际的测试文件名，用那个真实路径作标记。
动笔前先跑一遍复现输入确认缺陷存在。
