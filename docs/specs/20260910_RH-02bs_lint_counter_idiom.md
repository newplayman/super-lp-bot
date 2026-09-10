# RH-02bs — 让扫描器认识「计数自增」惯用法，别再把它当宽容默认值

## 背景（主脑已实测，数据在这里，不用重新统计）

`scripts/lp_silent_failure_lint_v1_readonly.py` 的规则1 抓「宽容默认值」
（`d.get(k, <默认值>)`，键缺失时不报错、悄悄用默认值继续算）。
这条规则是有效的——本仓库 27 例「静默假绿」里多例源于此。

但它对一个**语义上完全正确**的 Python 惯用法误报：

```python
counts[name] = counts.get(name, 0) + 1
by_day[t.date()] = by_day.get(t.date(), 0) + 1
status_counts[s.primary_status] = status_counts.get(s.primary_status, 0) + 1
```

这里的 `0` 是**唯一正确语义**（「还没数到过 = 零次」），不是宽容默认。

实测（HEAD `e8859fd`，全仓 249 条 rule1）：

| 模式 | 条数 | 占比 |
|---|---:|---:|
| 其它（真正的宽容默认值） | 219 | 88.0% |
| **计数自增 `.get(k, 0) + N`** | **24** | **9.6%** |
| 空容器默认 `.get(k, [])` / `.get(k, {})` | 6 | 2.4% |

更关键的是**新代码的信噪比**：今晚新增的 8 条 rule1/rule5 命中里，
**7 条是这个计数惯用法**。也就是说 `--fail-on-new` 这道防复发闸门
正在被自己的误报淹没——真出现新缺陷时会淹没在噪音里。

## 唯一任务：给规则1 加一条**精确**的排除

只改 `scripts/lp_silent_failure_lint_v1_readonly.py`。

### 排除条件（AST 层面，必须全部满足）

命中的 `X.get(k, 0)` 调用，**其直接父节点是一个 `ast.BinOp`**，且：

1. 运算符是 `ast.Add` 或 `ast.Sub`
2. 该 `.get(...)` 调用是这个 BinOp 的**左操作数**
3. `.get()` 的第二个参数是**字面量 `0`**（`ast.Constant` 且 `value == 0`
   且**不是** `True`/`False`——`isinstance(v, bool)` 要排除）
4. BinOp 的右操作数是一个**数值字面量**（`ast.Constant`，`int` 或 `float`，
   同样排除 bool）

四条全中才排除。**任何一条不满足都照常报告。**

反例（这些**必须仍然被报告**）：

```python
total = counts.get(k, 0) + other_dict.get(k, 0)   # 右操作数不是字面量
x = state.get("balance", 0) - fee                  # 右操作数是变量
y = cfg.get("retries", 3) + 1                      # 默认值不是 0
z = 1 + counts.get(k, 0)                           # .get 在右侧
w = cp.get("usdc_balance_raw", 0) < 10 * 10**6     # 父节点是 Compare 不是 BinOp
v = int(state.get("pool_count", 0) or 0)           # 父节点是 BoolOp
```

**这一条是本包的重点**：`cp.get("usdc_balance_raw", 0) < ...` 这种
「余额缺失当成 0 去比较」正是规则1 要抓的真缺陷，绝不能被误排除。

### 实现要求

- 排除逻辑写成一个独立的小函数，例如
  `def _is_counter_increment(call_node, parent) -> bool`，便于单测。
- 需要拿到父节点。若现有 visitor 没有父节点信息，用
  `for parent in ast.walk(tree): for child in ast.iter_child_nodes(parent): child._lint_parent = parent`
  这样的一次性标注，**不要改动 visitor 的整体结构**。
- 被排除的命中**不要静默丢弃**：在结果里加计数
  `excluded_counter_idiom: <int>`，`--json` 输出和终端摘要都要显示。
  我们要知道排除了多少条，而不是让它们凭空消失。

## 不许动

- **不要改规则 2/3/4/5 的任何逻辑。**
- 不要改 `fingerprint_snippet()`、身份定义 `(file, rule, fingerprint)`、
  基线读写格式（`version=2`）。
- **不要执行 `--write-baseline`**，不要修改
  `reports/silent_failure_lint_baseline.json`——基线更新是主脑在所有 worker
  收工后统一做的动作，现在写会把别人的半成品固化进去。
- 不要碰 `scripts/lp_rh_shadow_runner_v1_readonly.py`、
  `scripts/lp_rh_readiness_v1_readonly.py`、
  `scripts/lp_rh_shadow_daemon_v1_readonly.py`（三条线正在改它们）。
- **不要执行任何 git 命令**（不要 add / commit / checkout / stash）。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（追加到 `tests/test_lp_silent_failure_lint_v1_readonly.py`）

用 `--stdin` 或直接调内部扫描函数喂**源码字符串**，不要扫真实文件。

**应当被排除（不再报 rule1）：**
1. `counts[k] = counts.get(k, 0) + 1`
2. `by_day[d] = by_day.get(d, 0) + 1`
3. `x = c.get(k, 0) - 1`
4. `x = c.get(k, 0) + 2.5`

**必须仍然报告 rule1（每条单独一个断言）：**
5. `total = a.get(k, 0) + b.get(k, 0)`（右操作数不是字面量）
6. `x = state.get("balance", 0) - fee`（右操作数是变量）
7. `y = cfg.get("retries", 3) + 1`（默认值不是 0）
8. `z = 1 + counts.get(k, 0)`（`.get` 在右侧）
9. `w = cp.get("usdc_balance_raw", 0) < 10 * 10**6`（父节点是 Compare）
10. `v = int(state.get("pool_count", 0) or 0)`（父节点是 BoolOp）
11. `u = flags.get(k, False) + 1`（默认值是 bool，不是数值 0）

**计数正确性：**
12. 喂一段含 2 条计数惯用法 + 1 条真命中的源码 →
    报告 1 条 rule1，且 `excluded_counter_idiom == 2`。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_silent_failure_lint_v1_readonly.py -q` 全绿，
   新增 ≥12 条。
2. 全仓扫描 `python3 scripts/lp_silent_failure_lint_v1_readonly.py --json`：
   rule1 条数从 **249** 降到约 **225**（249 − 24），
   且 `excluded_counter_idiom` 约等于 24。
   **数字不必精确，但降幅必须落在 20~28 之间**——降太多说明排除条件过宽。
3. **反向证明**：确认下面这条**仍然出现**在扫描结果里
   （它是真缺陷，绝不能被排除）：
   ```
   scripts/lp_base_10u_probe_readiness_monitor_v1.py:163
   cp.get("usdc_balance_raw", 0) < 10 * 10**6
   ```
   用 `--path scripts/lp_base_10u_probe_readiness_monitor_v1.py` 单独扫这个文件验证，
   把输出贴进总结。
4. `reports/silent_failure_lint_baseline.json` **未被修改**
   （`git status --short` 里不能有它）。
5. `git status --short` 里只有
   `scripts/lp_silent_failure_lint_v1_readonly.py` 和
   `tests/test_lp_silent_failure_lint_v1_readonly.py` 被改动。
