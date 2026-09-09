# RH-02as：空的证据对象被当成「已验证」

## 铁证（主脑已核实）

`scripts/lp_rh_meme_audit_v1_readonly.py:121-122`：

```python
if isinstance(value, Mapping):
    available = value.get("available", value.get("verified", True))
    return (available is True), None
```

传 `holder_concentration_evidence={}` 时：
`{}.get("available", {}.get("verified", True))` → 内层先求值得 `True`
→ `available = True` → **返回通过**。

**一个空的证据对象等于「已验证」。** 持仓集中度完全未知，
其余安全事实又都通过时，`admission_check` 返回 `(True, [])`——
把一个从未验证过的代币判为可接纳。

同一个函数上面几行的处理是对的：`value is None` → `UNKNOWN_...`。
**只有 Mapping 分支把「空」和「已验证」混为一谈。**

## 你要做的

Mapping 分支改成：**必须存在显式的布尔**才算数。

- `value` 含 `available` 或 `verified` 且其值是 `True` → 通过
- 含且值是 `False` → 不通过（这是明确的「验证过，不合格」）
- **两个键都不存在**（含空字典 `{}`）→ 返回
  `(None, "UNKNOWN_HOLDER_CONCENTRATION_EVIDENCE")`，与 `value is None` 同样处置
- 键存在但值不是 bool（字符串 `"true"`、数字 1 等）→ 同样返回 UNKNOWN，
  不要做真值转换

**顺带检查同文件其它证据判定函数**（`grep -n 'def _.*_evidence_result' scripts/lp_rh_meme_audit_v1_readonly.py`）
有没有同一个 `, True)` 兜底模式，有就一并修，没有就在报告里写明查过哪几个。

## 不许动

任何其它 `scripts/`（多条线在改别的文件）、任何 `.db`。
该模块的测试文件**只允许新增测试**（先 `ls tests/ | grep -i meme` 确认真实文件名）。

## 验收标准

1. `holder_concentration_evidence={}` → `admission_check` **不再返回 `(True, [])``，
   理由里出现 `UNKNOWN_HOLDER_CONCENTRATION_EVIDENCE`。
2. `{"available": True}` → 通过（**防回归**，这条必须有）。
3. `{"available": False}` → 不通过。
4. `{"verified": True}` → 通过（保留既有的二选一语义）。
5. `{"available": "true"}`（字符串）→ UNKNOWN，不得当成 True。
6. `{"other_key": 1}`（有内容但无相关键）→ UNKNOWN。
7. `/root/lp-bot/.venv/bin/python -m pytest tests/ -k meme -q -p no:cacheprovider`
   全绿，原有测试全部仍在。

## 交付格式（只读沙箱）

```
===FILE:scripts/lp_rh_meme_audit_v1_readonly.py===
===FILE:<该模块真实的测试文件路径>===
===END===
```

标记独占一行、一字不差，内容不要用代码围栏包裹。
动笔前先跑一遍复现输入确认缺陷存在，把实际返回值写进说明。
