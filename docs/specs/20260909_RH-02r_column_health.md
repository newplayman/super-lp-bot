# RH-02r：列健康哨兵——把「表有行但列是空的」变成可自动发现的

## 为什么要这个

2026-09-09 一天之内，同一形状的缺陷出现了三次，每次都是主脑手工敲 SQL 才发现的：

| 实例 | 表面现象 | 实际 |
|---|---|---|
| `rh_assets` | 采集器退出码 0、`errors: []` | 194 条全被静默跳过，0 行 |
| `rh_assets` 六列 | 194 行写进去了 | `symbol_display` 等 6 列全 NULL |
| `rh_market_states` | 6131 行、覆盖率 96.18% | 14 列里 6 列全 NULL、`session` 恒为 `"UNKNOWN"` |

**没有一个会让测试变红，也没有一个会让覆盖率下降。**
覆盖率只算时间维度上有没有样本，从不检查样本里有多少列是空的。

## 只新建一个实质文件 + 其测试

### 1. `scripts/lp_rh_column_health_v1_readonly.py`（≤260 行，只读，不联网）

**只读**：除了 `SELECT` 与 `PRAGMA` 之外不得执行任何 SQL。

- `column_stats(conn, table) -> list[dict]`
  每列一条：`{"column","null_count","distinct_count","sample"}`。
  `sample` 取第一个非 NULL 值（截断到 60 字符），没有则 `None`。
- `classify_column(stat, *, total_rows) -> str`
  - `total_rows == 0` → `"NO_ROWS"`（**不得除以零**，也不得判成 EMPTY——
    空表和有行但列空是两回事）。
  - `null_count == total_rows` → `"EMPTY"`
  - `null_count == 0 and distinct_count == 1` → `"CONSTANT"`
  - 其余 → `"POPULATED"`
- `scan_database(conn, *, prefix="rh_") -> dict`
  扫所有 `sqlite_master` 里 `type='table'` 且名字以 `prefix` 开头的表。
  返回 `{"tables": {name: {"total_rows", "columns": [...]}},
  "summary": {"empty_columns": [...], "constant_columns": [...]}}`，
  两个列表里的元素是 `"<表>.<列>"` 字符串，**排序稳定**。
- `format_report(scan) -> str` 人类可读表格，每列一行，标出分类。
- `main()`：`--db --prefix --json --fail-on-empty`。
  **`--fail-on-empty` 给出时，若存在任何 `EMPTY` 列则返回退出码 1**，
  否则恒返回 0（供 cron/看门狗使用）。不给该标志时**永远返回 0**。

### 2. `tests/test_lp_rh_column_health_v1_readonly.py`（≤240 行，**≥16 测试**）

顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网**，全部用内存 SQLite 自建的小表。必测：

- 一列全 NULL、表有 3 行 → `"EMPTY"`。
- 一列全部相同且无 NULL → `"CONSTANT"`（复现 `session` 恒为 `"UNKNOWN"`）。
- 一列取值各不相同 → `"POPULATED"`。
- 一列部分 NULL 部分有值 → `"POPULATED"`（**不是 EMPTY**）。
- **★`total_rows == 0` 的表 → 每列 `"NO_ROWS"`，且全程不抛
  `ZeroDivisionError`★**（空表与「有行但列空」必须区分）。
- 单行表：该行有值的列是 `CONSTANT`，为 NULL 的列是 `EMPTY`。
- `scan_database` 只扫 `prefix` 开头的表（建一张 `other_x` 表，断言不出现在结果里）。
- `prefix` 传 `""` 时扫全部表。
- `summary.empty_columns` 的元素形如 `"表名.列名"` 且**已排序**。
- `summary.constant_columns` 同上。
- 没有任何空列时两个列表都是 `[]`（不是 `None`）。
- `column_stats` 的 `sample` 取第一个非 NULL 值；全 NULL 时为 `None`。
- `sample` 超长时被截断到 60 字符。
- **★只读性：跑完 `scan_database` 后，表的行数与内容完全不变★**
  （建表塞数据 → 记录全表快照 → 扫描 → 断言快照相等）。
- `main` 不带 `--fail-on-empty` 时，即使有空列也返回 **0**。
- `main` 带 `--fail-on-empty` 且有空列时返回 **1**。
- `main` 带 `--fail-on-empty` 但无空列时返回 **0**。

## 不许动
不改任何现有脚本、任何现有测试、任何表结构。不写任何数据。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_column_health_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥16 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。
