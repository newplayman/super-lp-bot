# RH-02u：`source_event_time` 列存在、数据在手边，6490 行全空

## 实测现状

`rh_source_snapshots` 共 6490 行：
```
source              = 'rh_rpc:pool_state'
fetch_time          = '2026-09-09T09:21:55.234859Z'   （有值：抓取时刻）
source_event_time   = None                             （全空：数据源事件时间）
```

采集器写入处把它写死成 `None`：
```
insert_row(conn, "rh_source_snapshots", {
    "source": "rh_rpc:pool_state", "payload_hash": payload_hash,
    "source_event_time": None, "fetch_time": now,      # <== 写死
    "schema_kind": "JSON_RPC_V1", "raw_ref": None,
    "quality": "OK" if not errors else "PARTIAL",
})
```

而 `collect_round` **同一函数内、该 insert 之前**已经算出了 `block_timestamp`
（`_hex_to_int(blk_age.get("timestamp"))`，正是用来算 `reference_age_secs` 的）。
**数据在手边，没写进去**——与 `derived_block_hash`、`session` 同一形状，今天第三次。

`fetch_time`（我们何时抓的）与 `source_event_time`（数据源何时产生的）是两个不同的量，
后者才是新鲜度的真实依据。

## ★本包不改变开仓条件★

`shadow_runner` 只读 `rh_market_states`，**不读这张表**。
因此填这一列不影响 `evaluate_health` / `allows_new_position`，
不触及「什么情况下允许开仓」。**让 shadow 消费它是另一个包，须用户授权，不在本包范围。**

## 只改一个文件 + 其测试

### `scripts/lp_rh_collector_v1_readonly.py`
`source_event_time` ← `block_timestamp` 转 **UTC RFC3339**。

- 格式用 `datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`
  （已验证可通过 `store.assert_utc_rfc3339`；`block_timestamp` 是整数秒，无需微秒）。
- **`block_timestamp` 为 `None` 时写 `None`**（当前轮取不到区块时）——
  **绝不用 `now` 顶替、绝不用 0**。「不知道数据多新」与「数据是此刻的」是相反的两件事，
  用 `fetch_time` 顶替会把陈旧数据伪装成新鲜数据。
- `fetch_time` 保持现状（仍是 `now`），**语义不得与 `source_event_time` 混同**。
- 若 insert 需要在 `block_timestamp` 计算之后进行，可调整同一函数内的语句顺序，
  但**不得改变任何其他列的取值**，也不得改变 `sqlite3.IntegrityError` 的幂等兜底行为。

## 不许动
不改 `rh_market_states` 的任何列（那一步改变开仓条件，须用户授权）。
不改 `fetch_time` / `quality` / `schema_kind` / `payload_hash` 的既有语义。
不改 `lp_rh_store_v1_readonly.py`、不改表结构。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_source_event_time_v1_readonly.py`（≤240 行，**≥14 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网**，用假 `rpc_fn` + 临时 SQLite。必测：

- **★假 `rpc_fn` 返回区块 `timestamp = 0x64`（100 秒）→ 写入的
  `source_event_time == "1970-01-01T00:01:40Z"`★**（精确值，不是"非空"）
- **★`block_timestamp` 取不到（区块请求失败）→ `source_event_time is None`，
  且**断言它不等于 `fetch_time`**★**（不得用 now 顶替）
- 写入值能通过 `store.assert_utc_rfc3339`（直接调该函数断言不抛）。
- 写入值以 `"Z"` 结尾且**不含** `"+00:00"`。
- 同一轮里 `fetch_time` 与 `source_event_time` **是两个不同的值**
  （构造区块时间戳明显早于 now，断言二者不等）。
- `fetch_time` 仍为 RFC3339 且非空（回归）。
- 大时间戳（如 `0x67000000`）正确换算，不溢出。
- 时间戳为 `0` → 写 `"1970-01-01T00:00:00Z"`（**不是 `None`**：0 是合法纪元时刻，
  与"取不到"必须可区分）。
- 幂等：同一 payload 重复写触发 `IntegrityError` 时仍被吞掉，不抛（回归）。
- `quality` 在有 error 时仍为 `"PARTIAL"`、无 error 时为 `"OK"`（回归，两条）。
- `schema_kind` 仍为 `"JSON_RPC_V1"`、`raw_ref` 仍为 `None`（回归，两条）。
- **`rh_market_states` 的所有列取值不受本包影响**：同一轮写入后，
  断言 `session` / `derived_block_hash` / `reference_age_secs` 与 RH-02p 后的行为一致
  （证明没有越界改动）。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_source_event_time_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 **0 failed / 14 skipped**（现有 4215 passed 一条都不许退）。
两条命令尾部原样贴出。
