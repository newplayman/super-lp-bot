# RH-02x：让闸门消费区块时间戳——**这一包改变「什么情况下允许开仓」**

## 授权

用户 2026-09-09 明确批准：**「接，用区块时间戳作 CORE 桶依据」**。

前置 RH-02w 已把 `source_event_time` 加进 `rh_market_states` 并填上
（值来自 `good_block` 的区块时间戳，实测数据龄 1 秒）。

## 为什么区块时间戳对 CORE 桶是正确的新鲜度依据

当前 shadow 跑的是 `POOL_USDG_WETH`（`dec0=18` / `dec1=6`）——**CORE 桶**。
它的价格来自链上 `sqrtPriceX96`，**不引用任何外部或链上 oracle**。
对这样一个价格，「数据何时产生」就是**它所在区块的时间戳**，
所以区块时间戳既是 `api_generated_at` 也是 `oracle_updated_at` 的正确取值。

**★STOCK 桶不适用★**：股票代币的参考价来自 REST，必须走 RH-02L 的
`resolve_freshness`（`scripts/lp_rh_reference_freshness_v1_readonly.py`，已入库）。
**本包只处理 CORE 桶，代码里必须写明这一点。**

## 现场代码（已抽出，**不要再 grep**）

`scripts/lp_rh_shadow_runner_v1_readonly.py`，`load_samples_from_db`：
```
"SELECT asset_address, sample_time, chain_id, reference_mid, "
"multiplier_human, session, health_flags_json, reference_age_secs, "
"oracle_paused, source_payload_hash, reference_bid, reference_ask "
"FROM rh_market_states WHERE asset_address = ? ORDER BY sample_time LIMIT ?"
```
构造 sample 时的既有注释（**保留其精神**）：
```
# Columns the conjuncts need.  A missing column stays None so the
# conjunct that needs it fails closed and names itself.
```
闸门判定处：
```
flags = evaluate_health(
    oracle_paused=bool(sample.get("oracle_paused")),
    oracle_updated_at=sample.get("oracle_updated_at"),   # 该键从不存在 -> None
    api_generated_at=sample.get("source_event_time"),    # 该键从不存在 -> None
    now=now_dt, halt=..., corp_action_pending=...,
    sources_disagree=..., chain_degraded=...,
    oracle_heartbeat_secs=sample.get("oracle_heartbeat_secs"),
    api_stale_secs=age)
```
`evaluate_health` 的两个分支：`oracle_dt is None -> ORACLE_UNAVAILABLE`；
`api_dt is None -> API_STALE`。`allows_new_position` 是 `session=="RTH" and not flags`。

## 改动（只改一个文件）

`scripts/lp_rh_shadow_runner_v1_readonly.py`：
1. `load_samples_from_db` 的 SELECT **增加 `source_event_time`**，
   并放进 sample 字典（键名同列名）。**其余列的读取与顺序不得改动。**
2. 闸门判定处把 `oracle_updated_at` 改为取 `sample.get("source_event_time")`，
   并在**注释**里写明：CORE 桶的链上池价没有独立 oracle，
   区块时间戳即该价格的产生时间；**STOCK 桶须改走 `resolve_freshness`**。
   `api_generated_at` 保持取 `source_event_time`（改动后它才真正有值）。

## ★必须保持的 fail-closed 性质★

`source_event_time` 为 `None`（旧行、或当轮取不到区块）时，
两个 flag **必须照旧升起**，闸门照旧拒绝。**不得用 `sample_time` 或 `now` 顶替。**
本包让新鲜的数据能通过，**不得让缺失的数据也能通过**。

## 不许动
不改 `evaluate_health` / `allows_new_position` / `classify_session`
（`lp_rh_market_session_v1_readonly.py` 一个字都不许动）。
不改采集器、不改 `resolve_freshness`、不改表结构。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_wire_freshness_v1_readonly.py`（≤240 行，**≥16 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网**，用内存库 + 构造样本。必测：

- **★新鲜样本（`source_event_time` = now-3 秒）+ RTH 时刻 →
  `flags` 既不含 `API_STALE` 也不含 `ORACLE_UNAVAILABLE`，
  且 `market_and_chain_risk_pass is True`★**（本包的目的）
- **★`source_event_time is None` → 两个 flag 都在，
  `market_and_chain_risk_pass is False`★**（fail-closed，最重要的一条）
- **★`source_event_time` 比 now 早 10 分钟 → 出现 `ORACLE_STALE` 或
  `API_STALE`，且 `market_and_chain_risk_pass is False`★**
- 非 RTH 时刻（OVERNIGHT）+ 完全新鲜的数据 → 仍然 `False`
  （时段限制不得被本包绕过）。
- WEEKEND + 新鲜数据 → 仍然 `False`。
- `halt=True` + 新鲜数据 + RTH → 仍然 `False`（其他 flag 不得被吞掉）。
- `oracle_paused=True` + 新鲜数据 + RTH → 仍然 `False`。
- `sources_disagree=True` → 仍然 `False`。
- `load_samples_from_db` 返回的 sample 含 `source_event_time` 键。
- 旧行（该列为 NULL）读出来是 `None`，不抛异常。
- 回归：`reference_mid IS NULL` 的行仍被跳过并计数（既有行为）。
- 回归：sample 里 `reference_mid` 仍是 `Decimal`。
- 回归：`session` / `reference_age_secs` / `oracle_paused` /
  `source_payload_hash` 四键仍存在且取值不变（四条）。
- 回归：`data_complete_and_fresh` 合取项的判定不受影响
  （构造 `reference_mid=None` 与 `age` 超限各断言一次）。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_wire_freshness_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥16 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。

## 落地后必须做的事（写进 commit message）
本包生效需**重启 shadow daemon**。那次重启会**首次真正打开开仓闸门**，
性质与前两次（让数据修复生效）不同——**动手前须把当时状态贴给用户**。
