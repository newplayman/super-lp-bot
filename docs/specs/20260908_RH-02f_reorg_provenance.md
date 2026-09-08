# RH-02f：派生值缺少区块溯源，导致重组回滚**不可能实现**（T11）

## 审计发现

T11 要求「同高度不同 hash → 标记分歧／重组；**回滚受影响派生值**」，
PRD §813 另有「逐块事件保留 block hash；发生 reorg 时回滚受影响派生结果并重新评估，
**不能只按 block number 去重**」。

主脑逐表核查 `scripts/lp_rh_store_v1_readonly.py` 建出的真实 schema：

### 已经做对的（不要动）

- `rh_pool_events` 主键 `(chain_id, block_hash, tx_hash, log_index)`
  ——**按 block_hash 去重，不是 block_number**。PRD §813 后半句已满足。
- `rh_contract_attestations` 主键含 `block_hash`。
- `rh_tx_receipts` 已有 `reorg_detected` 列。

### 缺的东西

**六个派生值表全都没有回溯到区块的溯源列**：

| 表 | 溯源列 |
|---|---|
| `rh_gate_decisions` | 无 |
| `rh_economic_evaluations` | 无 |
| `rh_position_marks` | 无 |
| `rh_market_states` | 无 |
| `rh_bucket_reservations` | 无 |
| `rh_reconciliation_runs` | 无 |

而 `scripts/lp_rh_netcover_inputs_v1_readonly.py` 的第 60、140 行
**已经算出了 `rh_evidence_block_hash`**，只是没人存。

**结论：回滚不是「尚未实现」，是「以当前 schema 不可能实现」——
重组发生时无法定位哪些派生行来自被孤立的区块。**
本包只补溯源，让回滚成为可能；回滚本身另立一包。

## 改哪些文件

只改 `scripts/lp_rh_store_v1_readonly.py`，测试追加进
`tests/test_lp_rh_store_v1_readonly.py`。**现有测试一条不许改、不许删。**

### 1. 六个派生表各加两列

`derived_block_hash TEXT` 与 `derived_block_number INTEGER`，**均可为 NULL**。
`NULL` 表示「该行未记录溯源」，**不是「来自区块 0」**——这个区别必须在
docstring 里写明，并有测试断言。

**不要改任何主键**（改主键会让已采集的行失效）。用幂等的
`_ensure_columns(conn)`：`PRAGMA table_info` 检查后再 `ALTER TABLE ... ADD COLUMN`，
**绝不 DROP 或重建表**。`migrate()` 里调用它，使既有库就地升级。

### 2. 提供一个定位函数（只查不改）

```python
def rows_derived_from_block(conn, *, block_hash) -> dict:
    """Which derived rows came from this block.  Read-only: locates, never deletes.

    Returns {table_name: [primary key tuples]} for the six derived tables.
    A table whose derived_block_hash is NULL for every row contributes an empty
    list, which means 'no provenance recorded', not 'nothing was affected'.
    """
```
返回值里必须能区分「该表没有受影响的行」与「该表根本没记溯源」：
前者 `[]`，后者在结果里另附 `tables_without_provenance` 列表。

**本包不实现删除或回滚。** 定位与处置分开，处置需要在知道影响面之后再设计。

## 新增测试（**≥10 条**）

- 六个表各断言新增了两列（一个参数化测试即可，但要覆盖全部六个表）。
- `_ensure_columns` 幂等：连续调用两次不报错。
- 旧库（无新列）就地升级后**原有行不丢**（先插数据再升级再计数）。
- 主键未被改动：升级前后 `PRAGMA table_info` 的 pk 列完全一致（六个表各断言）。
- `derived_block_hash` 为 `NULL` 的行：`rows_derived_from_block` **不把它算成命中**。
- 三行来自 `0xaaa`、两行来自 `0xbbb` → 查 `0xaaa` 只返回那三行的主键。
- 查一个不存在的 block_hash → 每个表返回 `[]`，**不抛异常**。
- 某表全为 `NULL` → 该表出现在 `tables_without_provenance` 里，
  且其 `[]` 不被误读成「无影响」（断言两个字段同时存在）。
- `rh_pool_events` 的主键**仍然含 block_hash**（回归保护，防止有人顺手改成 block_number）。
- 函数不执行任何写操作：传只读连接调用不抛异常。

## 不许动
不改其他脚本。不实现回滚/删除。不改任何主键。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_store_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向全绿且新增 ≥10；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
