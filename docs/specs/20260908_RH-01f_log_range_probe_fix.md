# RH-01f：修提供方探针的两处测量缺陷

## 背景

证据见 `reports/rh_pivot/20260907T124500Z/RH-05-research/PROVIDER_LOG_RANGE_20260908.md`。
`log_range_10k` 四家 0/5，但其中两家是**我的探针问错了**：

- ordefi 被 **10 秒超时**误杀，实测该查询需 41.5 秒（且成功返回 20,897 条）。
- robinhood 撞上 `-32000: logs matched by query exceeds limit of 10000`——
  这个池 10,000 块里有 8,600–20,900 条 Swap，**窗口装不装得下取决于池子多活跃，
  不取决于提供方多强**，布尔量测不出它想测的东西。

## 改哪些文件

只改 `scripts/lp_rh_provider_health_recorder_v1_readonly.py`，
测试追加进 `tests/test_lp_rh_provider_health_recorder_v1_readonly.py`。
**现有 32 条测试一条不许改、不许删**；若某条因本次变更失败，停下来写明是哪条、为什么。

### 1. 超时按能力分级

现在全局 `timeout=10`（第 355 行）。改为按能力查表：

```python
TIMEOUT_BY_PROBE = {          # 秒
    "head": 10, "chain_id": 10, "block_hash_consistency": 10,
    "eth_call": 10, "gas_estimate": 10, "error_structure": 10,
    "historical_read": 20,
    "log_range_1k": 30, "log_range_max_span": 90,
}
```
缺省 10 秒。**超时值必须能被测试读到并断言**（即做成模块级常量，不要写死在调用处）。

### 2. `log_range_10k` 布尔量 → `log_range_max_span` 整数

- 从 `CAPABILITIES` 里**移除** `log_range_10k`，**加入** `log_range_max_span`。
- 探测方式：沿阶梯 `LOG_RANGE_LADDER = (500, 2000, 5000, 10000)` 从小到大试，
  记录**最后一个成功的跨度**；第一次失败即停止（不必试更大的）。
- `ok` 的判据：**至少 500 跨度成功**（即该提供方支持带区间的日志查询）。
  一个都不成功 → `ok = 0`，`result_digest` 为 `None`。
- 把测得的整数写进新列 `max_span`（`rh_provider_capability` 加一列 `max_span INTEGER`，
  其余能力该列为 `NULL`）。**`NULL` 表示未测，不是 0。**
- **不要把 `log_range_max_span` 加进 `CONSENSUS_METHODS`**：各家上限本就不同，
  拿它比对会把正常的能力差异误报成 `SOURCE_DISAGREEMENT`。
  （`CONSENSUS_METHODS` 保持 `["chain_id", "block_hash_consistency", "eth_call"]` 不变。）

## 新增测试（**≥10 条**）

- `TIMEOUT_BY_PROBE` 里 `log_range_max_span` 的值 ≥ 60（断言具体值），
  简单调用为 10。
- 假 `call_fn` 对跨度 >5000 抛错、≤5000 成功 → `max_span == 5000`，`ok == 1`。
- 假 `call_fn` 对所有跨度都抛错 → `ok == 0`，`max_span is None`
  （**`is None` 断言，不是 0**）。
- 假 `call_fn` 全部成功 → `max_span == 10000`。
- 阶梯是从小到大且**首次失败即停**：注入计数器，断言 500 失败时只调用了 1 次。
- 非 `log_range_max_span` 的能力，其 `max_span` 列为 `NULL`。
- `CAPABILITIES` 里已无 `log_range_10k`、已有 `log_range_max_span`。
- `CONSENSUS_METHODS` **仍然**是那三项，且**不含** `log_range_max_span`，
  也**不含** `eth_blockNumber`（回归保护，两条各一个断言）。
- 现有的「错链提供方被排除」与「链头各异不报分歧」两条行为不变（各补一条回归断言）。

## 不许动
不改其他脚本。测试不联网、不写 `reports/`。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**注意**：`SCHEMA` 加列后，已存在的 `reports/lp_rh/provider_health.db` 需要
`ALTER TABLE` 才能兼容——请在 `SCHEMA` 之外加一个幂等的
`_ensure_columns(conn)`，用 `PRAGMA table_info` 检查后再 `ALTER TABLE ... ADD COLUMN`，
**不要 DROP 或重建表**（那会丢掉已采集的数据）。为此另加 2 条测试：
旧表结构能被就地升级、升级后重复调用不报错。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_provider_health_recorder_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥44 全绿（原 32 + 新增 ≥12）；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
