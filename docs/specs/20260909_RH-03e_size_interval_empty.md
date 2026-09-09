# RH-03e：`q_min > q_max` 时的空区间分类（T31）

## 审计发现

T31 取证：`q_min` / `q_max` **只作为 SQLite 列存在**
（`scripts/lp_rh_store_v1_readonly.py` 第 85 行的建表列、第 143 行的字段集合），
**没有任何模块从它们算经济可行区间，也没有处理 `q_min > q_max`**。

用例期望：「经济可行区间为空，合法 0 配置」——即这是一个**正常可解释的结果**，
不是错误，也不是 `INPUTS_UNAVAILABLE`。PRD 的状态名是 `SIZE_INTERVAL_EMPTY`。

**为什么要区分**：区间为空说明「这个池在任何仓位下都不划算」，是一个**算出来的结论**；
把它混进 `INPUTS_UNAVAILABLE` 会让人以为是数据缺失，从而去补数据而不是换池子。

## 只写两个文件

1. `scripts/lp_rh_size_interval_v1_readonly.py`（≤200 行）
   - `size_interval(*, q_min, q_max) -> dict`
     返回 `{"status", "q_min", "q_max", "width", "reason"}`：
     - 任一为 `None` → `status="INPUTS_UNAVAILABLE"`，`width is None`（**不是 0**）。
     - `q_min > q_max` → `status="SIZE_INTERVAL_EMPTY"`，`width` 为
       `q_max - q_min`（**负数，如实给出**），`reason` 说明两个边界的值。
     - `q_min == q_max` → `status="SIZE_INTERVAL_POINT"`，`width == 0`。
       **这是合法的：恰好只有一个可行仓位。**
     - `q_min < q_max` → `status="COMPUTED"`，`width > 0`。
   - `is_actionable(interval) -> bool`
     只有 `COMPUTED` 与 `SIZE_INTERVAL_POINT` 为 `True`。
     `SIZE_INTERVAL_EMPTY` 与 `INPUTS_UNAVAILABLE` 均为 `False`——
     **但两者的含义不同，调用方应读 `status` 而不是只看这个布尔**，docstring 写明。
   - `clamp_to_interval(size, interval) -> Optional[Decimal]`
     把一个仓位夹进区间；区间为空或输入缺失 → `None`（**不是夹到边界**）。
   - `main()`：`--q-min --q-max --out`，纯离线。

2. `tests/test_lp_rh_size_interval_v1_readonly.py`（≤180 行，**≥12 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。必测：
   - `q_min=60, q_max=40` → `SIZE_INTERVAL_EMPTY`，`width == -20`。
     **这条是 T31 的场景。**
   - `q_min=40, q_max=60` → `COMPUTED`，`width == 20`，`is_actionable` 为 `True`。
   - `q_min == q_max == 50` → `SIZE_INTERVAL_POINT`，`width == 0`，
     `is_actionable` 为 `True`（**单点可行不是空**）。
   - `q_min=None` → `INPUTS_UNAVAILABLE` 且 `width is None`（**`is None` 断言**）。
   - `q_max=None` → 同上。
   - **空区间与缺输入的 `status` 不相等**（一条专门的断言，防止两者被合并）。
   - `is_actionable`：四种 status 各断言一次。
   - `clamp_to_interval(50, 空区间)` → `None`（**不是 40 也不是 60**）。
   - `clamp_to_interval(30, [40,60])` → `40`；`clamp_to_interval(80, [40,60])` → `60`；
     `clamp_to_interval(50, [40,60])` → `50`。
   - 所有数值是 `Decimal` 不是 float。

## 不许动
**不要接进 netcover 或终闸**——接入是下一包。不改其他脚本。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_size_interval_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥12 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
