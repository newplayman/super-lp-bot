# RH-02ah：三个模块导入时改全局 Decimal 精度，污染整个进程

## 实测

```
scripts/lp_rh_exit_depth_v1_readonly.py:18        getcontext().prec = 80
scripts/lp_rh_organic_recorder_v1_readonly.py:56  getcontext().prec = 60
scripts/lp_rh_premium_recorder_v1_readonly.py:35  getcontext().prec = 60

导入前 prec = 28   导入 organic_recorder 后 prec = 60
```
**这是模块级副作用**：任何 `import` 了它们的代码，Decimal 行为被静默改变。

症状：`tests/test_lp_rh_first_step_accrual_v1_readonly.py`
**单独跑 12 passed，全量跑 5 failed**——它是第一批依赖默认 28 位精度的测试，
于是第一个踩到。**将来任何新写的 Decimal 测试都会随机变红。**

## 改法：局部提精度，不动全局

三处 `getcontext().prec = N` 全部删除，改为在**真正需要高精度的计算处**
用 `decimal.localcontext()`：
```
from decimal import localcontext
with localcontext() as ctx:
    ctx.prec = 80          # 或 60，与原值一致
    ... 该函数内的高精度计算 ...
```
- **每个模块原来的精度值必须保持**（80 / 60 / 60），不要统一。
- 作用域**只包住真正需要的计算**，不要把整个函数体或整个模块包进去。
- **不得改任何计算逻辑、不得改任何数值**——只改精度作用域。

## ★这是有回归风险的改动，必须逐一验证★

**14 个测试文件**涉及这三个模块。落地后：
- 全量必须 **0 failed**；
- **且原本依赖高精度的断言不得退化**——若某测试原来在 prec=80 下通过、
  改后因精度不足而失败，**说明 localcontext 没包住该计算路径，
  要扩大作用域，不要降低断言**。
- 若发现某处确实需要跨函数保持高精度而 `localcontext` 无法覆盖，
  **停下来报告，不要退回改全局**。

## 不许动
不改任何计算公式与常量。不改测试断言的强度。
不改 `lp_rh_shadow_runner`、不改 `lp_rh_store`。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**不要执行任何 git 命令，尤其不要 commit。**

## 新增测试 `tests/test_lp_rh_decimal_context_isolation_v1_readonly.py`（≤200 行，**≥8 测试**）
- **★导入这三个模块后，`getcontext().prec` 仍为 28★**（三条，各一个模块）
- **★调用各模块的高精度函数后，`getcontext().prec` 仍为 28★**（三条）
- 高精度计算结果与改动前一致（各取一个已知输入输出对，断言数值不变）。
- 端到端：先导入这三个模块，再跑
  `tests/test_lp_rh_first_step_accrual_v1_readonly.py` 里那条
  `test_large_number_precision_delta_one` 的等价断言，**必须通过**。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_decimal_context_isolation_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥8 全绿；全量 **0 failed / 14 skipped**（现有 4418 passed 基线之上只增不减，
且那 5 个 first_step_accrual 的失败必须消失）。两条命令尾部原样贴出。
