# RH-02e：区分「oracle 不存在」与「oracle 陈旧」，并修一处崩溃

## 两个实测问题

证据见 `reports/rh_pivot/20260907T124500Z/RH-05-research/SESSION_CLOSE_LIVE_20260908.md`。

### 问题 1：缺失被当成陈旧，STOCK 因此永远开不了仓

`evaluate_health` 在 `oracle_updated_at is None` 时置 `ORACLE_STALE`。
但**本链的股票代币根本不引用链上价格源**（已实测），该值恒为 `None`，
于是 `allows_new_position` 在 RTH 也恒为 `False`。

「不存在」与「陈旧」是两回事：前者是结构性的、要靠政策决定处置，
后者是暂时性的、等一会儿就好。压成一个 flag 之后读者无法分辨。

### 问题 2：`stale_reason` 崩溃

```
TypeError: '>' not supported between instances of 'NoneType' and 'int'
```
`scripts/lp_rh_market_session_v1_readonly.py` 的 `stale_reason` 第 173 行附近，
`oracle_age_secs` 为 `None` 时直接比较。可达路径：
`scripts/lp_rh_stock_reference_v1_readonly.py:125`（T23）。

## 改哪些文件

只改 `scripts/lp_rh_market_session_v1_readonly.py`，
测试追加进 `tests/test_lp_rh_market_session_v1_readonly.py`。
**现有测试一条不许改、不许删**；若某条因本次变更失败，停下来写明是哪条、为什么。

### 1. 新增 `ORACLE_UNAVAILABLE`

- `HEALTH_FLAGS` 元组里加入 `"ORACLE_UNAVAILABLE"`（放在 `ORACLE_STALE` 之前，保持有序输出）。
- `evaluate_health`：
  - `oracle_updated_at is None` → 置 `ORACLE_UNAVAILABLE`，**不再置 `ORACLE_STALE`**。
  - `oracle_updated_at` 有值但超过 `oracle_heartbeat_secs` → 仍置 `ORACLE_STALE`。
  - 两者**互斥**，不得同时出现。
- `allows_new_position` 的语义**不变**：任何 flag 都阻止开仓。
  **`ORACLE_UNAVAILABLE` 仍然阻止开仓**——本包只让理由变准确，不放宽闸门。

### 2. `stale_reason` 不再崩溃

`oracle_age_secs is None` → 返回 `"ORACLE_UNAVAILABLE"`（新增的第四个返回值），
**在 `session != "RTH"` 的判断之前**还是之后由你决定，但必须写清理由：
建议放在最前面，因为「没有 oracle」与时段无关。
其余三个返回值 `EXPECTED_SESSION_CLOSED` / `STALE_WHILE_EXPECTED_LIVE` / `FRESH` **不变**。

`heartbeat_secs` 为 `None` 时同样不得崩溃 → 也返回 `"ORACLE_UNAVAILABLE"`。

## 新增测试（**≥10 条**）

- `evaluate_health(oracle_updated_at=None, ...)` → flags 含 `ORACLE_UNAVAILABLE`
  且**不含** `ORACLE_STALE`。
- `evaluate_health` 有 oracle 但陈旧 → 含 `ORACLE_STALE` 且**不含** `ORACLE_UNAVAILABLE`。
- 两个 flag 在任何输入组合下**不同时出现**（构造 4 种组合各断言一次，或写成参数化）。
- RTH + 无 oracle → `allows_new_position` 仍为 `False`（**本包不放宽闸门**，回归保护）。
- RTH + 有新鲜 oracle + 无其他 flag → 仍为 `True`（证明闸门非恒 False）。
- `stale_reason("RTH", None, 3600) == "ORACLE_UNAVAILABLE"`（**不抛异常**）。
- `stale_reason("RTH", 100, None) == "ORACLE_UNAVAILABLE"`（**不抛异常**）。
- `stale_reason("POSTMARKET", None, 3600) == "ORACLE_UNAVAILABLE"`
  （无 oracle 与时段无关）。
- 原有三个返回值逐一回归断言（`RTH/7200/3600`、`PREMARKET/7200/3600`、`RTH/100/3600`）。
- `HEALTH_FLAGS` 里 `ORACLE_UNAVAILABLE` 存在，且 `evaluate_health` 返回的 flags
  **全部**是 `HEALTH_FLAGS` 的成员（防止拼写漂移）。
- `lp_rh_stock_reference_v1_readonly` 的转调路径传 `None` 不再崩溃（一条集成测试）。

## 不许动
不改其他脚本（`lp_rh_stock_reference` 只做转调，不用改）。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**不要顺手放宽 `allows_new_position`**——STOCK 能不能开仓是用户的政策决定，不是本包的。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_market_session_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向全绿且新增 ≥10；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
