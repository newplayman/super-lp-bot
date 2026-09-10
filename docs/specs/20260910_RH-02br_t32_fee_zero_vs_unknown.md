# RH-02br — T32：把「合法的 fee=0」与「fee 未知」钉死在测试里

## 背景

PRD §20 的 60 个 T 用例里，**T32 是唯一一条「已实现但没有测试」**
（依据 `reports/AUDIT_prd_full_reconciliation_20260910.md`）。

T32 要求（PRD L1024）：**未知 fee 与合法 fee=0 必须区分**。

代码在 `scripts/lp_rh_netcover_inputs_v1_readonly.py:82-88`：

```python
fee_apr_pct = _to_float(evidence.get("fee_apr_pct"))
if fee_apr_pct is None:
    fee_ev_usd = None
    missing.append(("fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE"))
else:
    fee_ev_usd = pos * fee_apr_pct / 100.0 * horizon_hours / 8760.0
```

**实现是对的**，主脑已实测 `_to_float` 的行为：

```
_to_float(0)         -> 0.0      _to_float('')        -> None
_to_float(0.0)       -> 0.0      _to_float(None)      -> None
_to_float('0')       -> 0.0      _to_float('null')    -> None
_to_float('0.0')     -> 0.0      _to_float('unknown') -> None
```

现有测试只覆盖了 `fee_apr_pct=None`
（`tests/test_lp_rh_netcover_inputs_v1_readonly.py:110`），
**合法的 0 这一半从来没有测试钉住**。

这正是本仓库「静默假绿」最容易复发的地方：哪天有人给 `_to_float` 加一个
`if not value: return None` 的「防御性」写法，合法的 0 就会被当成未知，
而所有现存测试仍然全绿。

## 唯一任务：补测试

只改 `tests/test_lp_rh_netcover_inputs_v1_readonly.py`，追加以下测试。
复用该文件里已有的 `_evidence(...)` 辅助函数和 `_has_missing(...)` 断言助手。

1. `fee_apr_pct=0`（int 零）→ `fee_ev_usd == 0.0`，
   且 `missing` 里**不含** `fee_apr_pct`。
2. `fee_apr_pct=0.0`（float 零）→ 同上。
3. `fee_apr_pct="0"`（字符串零）→ 同上。
4. `fee_apr_pct="0.0"` → 同上。
5. `fee_apr_pct=None` → `fee_ev_usd is None`，
   `missing` 里**含** `("fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")`。
   （这条已存在，不用重复写；引用它即可）
6. `fee_apr_pct=""`（空串）→ 与 `None` 同样处理（未知，进 missing）。
7. `fee_apr_pct="unknown"` → 同样进 missing。
8. **一条并列断言**：把 `fee_apr_pct=0` 与 `fee_apr_pct=None` 两次调用的结果
   放在同一个测试里比较，断言
   `out_zero["fee_ev_usd"] == 0.0` 而 `out_none["fee_ev_usd"] is None`，
   且两者的 `missing` 一个不含、一个含。
   ——**这条是 T32 的直接体现**，测试名里带上 `t32`，
   docstring 引用 `PRD L1024`。

每条测试的 docstring 写清它防的是什么回归。

## 不许动

- **不要改 `scripts/lp_rh_netcover_inputs_v1_readonly.py`**——实现是对的，
  本包只补测试。改了实现反而可能引入回归。
- 不要改 `scripts/lp_netcover_engine_v1_readonly.py`。
- 不要改该测试文件里**已有的**任何测试，只追加。
- 不要碰 `scripts/lp_rh_shadow_runner_v1_readonly.py`、
  `scripts/lp_rh_shadow_daemon_v1_readonly.py`、
  `scripts/lp_rh_readiness_v1_readonly.py`（三条线正在改它们）。
- 不要动任何 `.db`。
- **不要执行任何 git 命令**（不要 add / commit / checkout / stash）。
- 单次 Write/Edit ≤150 行或 6000 字符。
- 不要整读大文件；`sed -n '1,40p'` 看该测试文件的 import 与 `_evidence` 助手，
  `sed -n '100,120p'` 看现有的 missing 那条测试怎么写的，照着风格来。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_netcover_inputs_v1_readonly.py -q` 全绿，
   新增测试 ≥ 6 条。
2. `grep -n "t32" tests/test_lp_rh_netcover_inputs_v1_readonly.py` 能看到
   那条并列断言的测试名。
3. **回归证明**：临时在 `_to_float` 开头插一行 `if not value: return None`
   （模拟未来有人加「防御性」写法），跑测试**必须有失败**；
   然后把这行删掉恢复原状，再跑必须全绿。
   把这两次的输出尾部贴进你的总结里。
   ——**改完必须恢复原文件**，`git status` 里不能有
   `scripts/lp_rh_netcover_inputs_v1_readonly.py` 的改动。
4. `git status --short` 里只有
   `tests/test_lp_rh_netcover_inputs_v1_readonly.py` 被改动。
