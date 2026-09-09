# RH-02p：采集器手里有区块 hash 却不写溯源列——回滚因此没有对象

## 实测现状（主脑 2026-09-09 取证，6131 行全量统计）

```
derived_block_hash     NULL=6131/6131   <== 全空
derived_block_number   NULL=6131/6131   <== 全空
session                distinct=1       <== 恒为 "UNKNOWN"
multiplier_human       NULL=6131/6131   （需 REST，本包不处理）
reference_bid / ask    NULL=6131/6131   （需 REST，本包不处理）
oracle_paused          NULL=6131/6131   （需链上 paused() 调用，本包不处理）
```

`derived_block_hash` 是**溯源列**：`scripts/lp_rh_reorg_rollback_v1_readonly.py`
的 `plan_rollback` / `apply_rollback` 靠它定位受被弃链影响的派生行。
它全空，意味着整条重组回滚链（含刚落地的 RH-02k）**在真实数据上没有任何回滚对象**——
逻辑正确，作用于空集。

**数据本来就在手边**，只是没写进 `insert_row`。

## 现场代码（`scripts/lp_rh_collector_v1_readonly.py`，已抽出，**不要再 grep**）

`collect_round` 内已有：
```
blk, err, ms = rpc_fn("eth_getBlockByNumber", ["latest", False])        # L166
good_block = block_number if block_number is not None else last_good_block   # L205
blk_age, err_age, _ = rpc_fn("eth_getBlockByNumber", [hex(good_block), False])  # L213-214
if ...:
    block_timestamp = _hex_to_int(blk_age.get("timestamp"))             # L217
```
写入处（L262-273）：
```
insert_row(conn, "rh_market_states", {
    "asset_address": POOL, "sample_time": now,
    "chain_id": CHAIN_ID, "source_payload_hash": payload_hash,
    "session": "UNKNOWN",
    "health_flags_json": json.dumps(sorted(flags)),
    "reference_bid": None, "reference_ask": None,
    "reference_mid": price_text,
    "reference_age_secs": reference_age_secs,
    "multiplier_human": None, "oracle_paused": None,
})
```
**`derived_block_hash` 与 `derived_block_number` 根本不在这个字典里。**

## 只改一个文件 + 其测试

### A. 写入溯源列
- `derived_block_number` ← `good_block`。
- `derived_block_hash` ← **`good_block` 对应区块的 hash**，即 `blk_age.get("hash")`
  （**不是 `blk` 的 hash**——`good_block` 可能是上一轮的 `last_good_block`，
  两者会不一致，写错等于把行归给错误的区块）。
- 取不到时写 `None`，**不要填空串、不要退而用 `latest` 的 hash**。
  为此把 `blk_age` 的 hash 与 timestamp 一并保留到写入处
  （现有代码只留了 `block_timestamp`）。

### B. 真实时段分类
```
from scripts.lp_rh_market_session_v1_readonly import classify_session
```
`session` ← `classify_session(<sample_time 的 aware datetime>, calendar=None)[0]`。
该函数返回 `(session, dict)`，取第 0 位。解析不出时间时保持 `"UNKNOWN"`
（**函数对 `None` 输入的既有行为不要改**）。

## 不许动
不改 `reference_bid` / `reference_ask` / `multiplier_human`（需要 REST，
采集器按设计只读链上，改这个是设计变更，留给用户决定）。
不改 `oracle_paused`（需额外链上调用）。
不改 `lp_rh_market_session_v1_readonly.py`、不改回滚模块、不改表结构。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_collector_provenance_v1_readonly.py`（≤240 行，**≥14 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网**：用假 `rpc_fn` 与内存/临时 SQLite。必测：

- **★正常路径：写入后 `derived_block_hash` 等于假 `rpc_fn` 为 `good_block`
  返回的那个 hash，`derived_block_number` 等于 `good_block`★**
- **★`good_block` 回落到 `last_good_block` 时（当轮取不到新块），
  写入的 hash 必须是 `last_good_block` 那个区块的 hash，
  不得是 `latest` 的 hash★**（构造两者不同的假响应，断言取的是前者）
- 取 `good_block` 区块失败（`rpc_fn` 抛错或返回 err）→ `derived_block_hash is None`，
  **不是空串、不是 latest 的 hash**；且该行其余列仍正常写入。
- 区块对象缺 `hash` 键 → `None`。
- `good_block` 为 `None`（首轮且无历史）→ 两列均 `None`，不抛异常。
- `session` 在 RTH 时刻（美东工作日 10:00）写入 `"RTH"`。
- `session` 在美东工作日 02:00 写入 `"OVERNIGHT"`。
- `session` 在周六写入 `"WEEKEND"`。
- `session` 在美东工作日 05:00 写入 `"PREMARKET"`。
- 时间戳不可解析 → `session == "UNKNOWN"`（保持既有兜底）。
- 写入的 `session` 取值必属于 `lp_rh_market_session_v1_readonly.SESSIONS`。
- 回归：`reference_mid` / `reference_age_secs` / `source_payload_hash` /
  `health_flags_json` 四列的既有行为**不变**（各断言一次）。
- 回归：`reference_bid` / `reference_ask` / `multiplier_human` / `oracle_paused`
  仍为 `None`（本包不动它们，防止误改）。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_collector_provenance_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。

## 注意（写进 commit message，不要写进代码注释）
本修复**只影响新写入的行**。已有 6131 行的溯源列不可追回——
与覆盖率的历史亏空一样，属于永久缺失。
修复后**必须重启采集器**才生效（正在跑的是旧代码）。
