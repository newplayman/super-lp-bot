# RH-02w：`rh_market_states` 加 `source_event_time` 列并填上（不改开仓条件）

## 背景

`shadow_runner` 读 `sample.get("source_event_time")` 与
`sample.get("oracle_updated_at")`，而 `rh_market_states` **两列都不存在**，
`dict.get` 对不存在的键返回 `None` 且不报错，于是 `evaluate_health` 无条件加上
`API_STALE` 与 `ORACLE_UNAVAILABLE` 两个 flag。实测：

```
真实样本 flags = ['API_STALE', 'ORACLE_UNAVAILABLE']
allows_new_position 是 session=="RTH" and not flags —— 任一 flag 都拦死
```

数据一直都在：`collect_round` 手里有 `block_timestamp`（用来算 `reference_age_secs`），
RH-02u 已把它写进 `rh_source_snapshots.source_event_time`，实测新行
`source_event_time='2026-09-09T10:00:16Z'` / `fetch_time='…10:00:17.42Z'`，数据龄 1 秒。

**本包只加列并填上，不改 `shadow_runner`、不改 `evaluate_health`——
开仓条件一个字都不变。** 让闸门消费它是下一包（用户已授权，但单独做才可验）。

## 现场代码（已抽出，**不要再 grep**）

`scripts/lp_rh_store_v1_readonly.py` 的 schema 定义：
```
("rh_market_states", ("asset_address", "sample_time"), [
    "asset_address TEXT NOT NULL", "sample_time TEXT NOT NULL",
    "chain_id INTEGER NOT NULL", "source_payload_hash TEXT",
    "session TEXT NOT NULL", "health_flags_json TEXT NOT NULL",
    "reference_bid TEXT", "reference_ask TEXT", "reference_mid TEXT",
    "reference_age_secs INTEGER", "multiplier_human TEXT",
    "oracle_paused INTEGER",
    "derived_block_hash TEXT", "derived_block_number INTEGER"]),
```
同文件已有 `_ensure_columns(conn)`：对 `DERIVED_TABLES` 逐个
`PRAGMA table_info` 再 `ALTER TABLE ... ADD COLUMN`，**幂等、从不重建表**。
`rh_market_states` 是 `DERIVED_TABLES` 成员。

`scripts/lp_rh_collector_v1_readonly.py` 已在写入 `rh_source_snapshots` 时
把 `block_timestamp` 转成 RFC3339（RH-02u 落地），**复用同一个转换，不要重写**。

## 改动

### A. `scripts/lp_rh_store_v1_readonly.py`
1. 在上面那个列清单**末尾**追加 `"source_event_time TEXT"`（新库直接带上）。
2. 让 `_ensure_columns` 也幂等地给**已存在的** `rh_market_states` 补这一列
   （现有库有 6600+ 行，必须 `ALTER TABLE ADD COLUMN`，**不得重建表**）。
   已有行的该列为 `NULL`——那是正确的，表示"当时没记录"。

### B. `scripts/lp_rh_collector_v1_readonly.py`
写 `rh_market_states` 时带上 `source_event_time`，**与同一轮写进
`rh_source_snapshots` 的值完全相同**（同一个变量，不要各算一次）。
`block_timestamp` 为 `None` 时写 `None`——**绝不用 `now` / `sample_time` 顶替**。

## 不许动
不改 `shadow_runner`、不改 `evaluate_health` / `allows_new_position`、
不改 `oracle_updated_at`（本包不加这一列）。
不改 `rh_source_snapshots` 的写入（RH-02u 已验收）。
不重建任何表。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_market_states_event_time_v1_readonly.py`（≤240 行，**≥14 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。** 必测：

- 新建库 `migrate` 后，`PRAGMA table_info(rh_market_states)` 含 `source_event_time`。
- **★对一个「旧」库（先建不带该列的表并插入 2 行）跑 `migrate`：
  列被加上、**原有 2 行仍在**、且它们的该列为 `NULL`★**（不得重建表丢数据）
- `migrate` 连跑两次不报错（幂等）。
- 假 `rpc_fn` 给区块 `timestamp=0x64` → 写入的
  `rh_market_states.source_event_time == "1970-01-01T00:01:40Z"`（精确值）。
- **★同一轮里 `rh_market_states.source_event_time` 与
  `rh_source_snapshots.source_event_time` **完全相等**★**（同一个值，不是各算一次）
- `block_timestamp` 取不到 → 该列为 `None`，**且断言它不等于 `sample_time`**
  （不得用 now 顶替）。
- `timestamp=0` → `"1970-01-01T00:00:00Z"`（0 与"取不到"可区分）。
- 写入值通过 `store.assert_utc_rfc3339`。
- 回归：`session` / `derived_block_hash` / `derived_block_number` /
  `reference_age_secs` / `reference_mid` 五列行为与 RH-02p、RH-02u 后一致（五条）。
- 回归：`rh_market_states` 的主键仍是 `(asset_address, sample_time)`，
  重复写同一 `sample_time` 不产生第二行。
- **本包不得引入 `oracle_updated_at` 列**：断言 `PRAGMA table_info` 里**没有**它。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_market_states_event_time_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 **0 failed / 14 skipped**（现有 4245 passed 一条都不许退）。
两条命令尾部原样贴出。
