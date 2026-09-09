# RH-02g：重组回滚（T11 的后半句）——前置条件已就绪

## 背景

T11 判 FAIL 的理由是「标记有、回滚无」。追查发现根因是**六个派生表没有区块溯源，
回滚此前根本写不出来**。`RH-02f`（提交 `95222e0`）已补上
`derived_block_hash` / `derived_block_number` 两列与只读定位函数
`rows_derived_from_block`，并明确区分「无受影响行」与「未记录溯源」。

**本包实现回滚本身。**

## 设计原则（先读完再动手）

1. **不删除任何行。** 重组不是「这些数据从未存在」，而是「这些数据基于一条被放弃的链」。
   删掉就失去了审计线索。**用标记而不是删除。**
2. **无溯源的表不得被当作「未受影响」。** `rows_derived_from_block` 已把这类表放进
   `tables_without_provenance`；回滚遇到它们必须**显式报告为不可判定**，
   而不是跳过。
3. **回滚必须幂等。** 同一个 block_hash 回滚两次，结果与一次相同。

## 只写两个文件

1. `scripts/lp_rh_reorg_rollback_v1_readonly.py`（≤240 行）
   复用 `scripts.lp_rh_store_v1_readonly` 的 `rows_derived_from_block`，**不要重写**。

   - 六个派生表各加一列 `invalidated_by_block TEXT`（幂等 `ALTER TABLE`，
     沿用 `_ensure_columns` 模式，**不改主键、不 DROP**）。
     `NULL` = 有效；非空 = 被该 block_hash 的重组作废。
   - `plan_rollback(conn, *, orphaned_block_hash) -> dict`
     **只查不改**。返回
     `{"orphaned_block_hash", "affected": {表名: [主键元组]},
       "affected_total": int, "tables_without_provenance": [...],
       "undecidable": bool}`。
     `undecidable` 在 `tables_without_provenance` 非空时为 `True`——
     **有表说不清，整个回滚的完整性就说不清**，调用方必须看见这一点。
   - `apply_rollback(conn, *, orphaned_block_hash, plan=None) -> dict`
     把受影响行的 `invalidated_by_block` 置为该 hash。返回
     `{"marked": {表名: 行数}, "marked_total", "already_marked", "undecidable"}`。
     - **幂等**：已标记的行不重复计入 `marked`，计入 `already_marked`。
     - **绝不 DELETE**。
     - `undecidable` 为 `True` 时**仍然执行标记**（能标的先标），
       但结果里保留该标志，让调用方知道覆盖不完整。
   - `active_rows_only(table) -> str`
     返回一个 SQL 片段 `f"{table} WHERE invalidated_by_block IS NULL"`，
     供下游查询排除已作废行。docstring 写明：**下游若不用它，就会读到已作废的数据**。
   - `main()`：`--db --orphaned-block-hash --dry-run/--apply --out`。
     **默认 `--dry-run`**；`--apply` 必须显式给出。

2. `tests/test_lp_rh_reorg_rollback_v1_readonly.py`（≤240 行，**≥14 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   **内存 SQLite，不许联网、不许写 `reports/`。** 必测：
   - 三行来自 `0xaaa`、两行来自 `0xbbb` → `plan_rollback("0xaaa")` 的
     `affected_total == 3`。
   - `apply_rollback` 后那三行 `invalidated_by_block == "0xaaa"`，
     另两行**仍为 NULL**。
   - **幂等**：连续 `apply_rollback` 两次，第二次 `marked_total == 0`、
     `already_marked == 3`，且数据库状态不变。
   - **绝不删除**：回滚前后各表 `COUNT(*)` 完全相同（六表逐一断言）。
   - 某表有行但溯源全 NULL → `plan_rollback` 的 `undecidable is True`
     且该表名在 `tables_without_provenance` 里。
   - `undecidable` 为 `True` 时 `apply_rollback` **仍标记能标的行**，
     且返回的 `undecidable` 仍为 `True`。
   - 全部有溯源时 `undecidable is False`。
   - `active_rows_only("rh_gate_decisions")` 生成的 SQL 能正确排除已作废行
     （实际执行一次查询断言行数）。
   - `--dry-run` 是默认：调用 `main` 不传 `--apply` 时**数据库未被修改**
     （比对修改前后的行内容）。
   - `--apply` 才真正修改。
   - 幂等 `_ensure_columns`：连续两次不报错，且主键未变。
   - 回滚一个不存在的 block_hash → `affected_total == 0`，不抛异常，
     `marked_total == 0`。

## 不许动
不改 `lp_rh_store_v1_readonly.py` 的既有函数（只新增列由本模块的
`_ensure_columns` 负责）。**不要把 `active_rows_only` 强制接进任何现有查询**——
接入是下一包，需先让用户看到影响面。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_reorg_rollback_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
