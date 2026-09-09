# RH-02aa：shadow 一直在回放库里最早的一小时，从未看过新数据

## 实测证据（2026-09-09 13:3x UTC，RTH 已开盘）

```
库中样本 7500 条，跨度 2026-09-08T05:15:14Z .. 2026-09-09T13:35:36Z

load_samples_from_db(limit=200) 实际返回：
  第一条  2026-09-08T05:15:14Z   session=UNKNOWN
  最后条  2026-09-08T06:12:26Z   session=UNKNOWN
  分布    {'UNKNOWN': 199}

库里最新 200 条的分布： {'RTH': 23, 'PREMARKET': 177}
含 source_event_time 的行： 642（全部在最新那批）
```

**shadow daemon 自启动以来一直在回放 2026-09-08 早上 5:15–6:12 那一小时**，
且那批行是今日修复**之前**写的：`session` 恒为 `UNKNOWN`、`source_event_time` 恒为 `NULL`。

## 根因

`scripts/lp_rh_shadow_runner_v1_readonly.py` 的 `load_samples_from_db`：
```
"FROM rh_market_states WHERE asset_address = ? ORDER BY sample_time LIMIT ?"
```
**`ORDER BY sample_time` 是升序，`LIMIT` 因此取的是最早的 N 条**，
而不是最近的 N 条。样本积累越多，回放的窗口离现在越远。

后果：
- `eligible_steps` 恒为 0，与闸门是否修好无关；
- RH-02w／RH-02x 写入并接线的 `source_event_time` **永远读不到**（那批老行是 NULL）；
- blocker 里的 `sample_session` 永远是那一小时的时段，与当前时段无关。

## 改动（只改一个函数）

把取数改为**最近 N 条，再按时间升序回放**：
```
SELECT ... FROM (
    SELECT <同样的列> FROM rh_market_states
    WHERE asset_address = ?
    ORDER BY sample_time DESC LIMIT ?
) ORDER BY sample_time
```
- **列的选择与顺序、解包顺序、sample 字典的键，一律保持不变**
  （RH-02x 刚加过 `source_event_time`，不要动它）。
- 回放顺序**必须仍是时间升序**：`run_episode` 逐样本推进，
  第 i 步不得引用后续样本（PRD T36 已有断言，不能破坏）。
- `reference_mid IS NULL` 的跳过与计数行为不变。

## 不许动
不改 `run_episode`、不改 `compute_conjuncts`、不改任何闸门、不改表结构。
不改 daemon 的 `--samples` 语义（仍是「回放多少条」）。
不联网。单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_replay_recent_v1_readonly.py`（≤240 行，**≥14 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网**，用内存库插入已知时间序列。必测：

- **★插入 500 条（sample_time 递增），`limit=200` 返回的是**最后** 200 条，
  第一条等于第 301 条的时间★**（复现本缺陷）
- **★返回顺序仍是**时间升序**（逐对断言 `t[i] <= t[i+1]`）★**
- 样本总数少于 limit 时全部返回，且仍升序。
- 样本数恰等于 limit 时全部返回。
- `limit=1` 返回**最新**那条（不是最早那条）。
- 只取指定 `asset_address` 的行（插入两个 pool，断言不串）。
- `reference_mid IS NULL` 的行被跳过并计入 skipped（回归）。
- 跳过的行不占 limit 名额时的行为与原实现一致（按现有语义断言，
  **若与现有实现冲突，停下来报告，不要改实现迁就测试**）。
- sample 字典包含 `source_event_time` 键且取自该列（回归 RH-02x）。
- sample 的 `reference_mid` 仍是 `Decimal`（回归）。
- `session`／`reference_age_secs`／`oracle_paused`／`source_payload_hash`
  四键仍存在且取值正确（四条回归）。
- 新旧行混合时（前 300 条 `source_event_time` 为 NULL、后 200 条有值），
  `limit=200` 返回的**全部带值**——**这正是本缺陷让 shadow 读不到新数据的那一点**。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_replay_recent_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。
**不要执行任何 git 命令，尤其不要 commit——入库是主脑裁决后的动作。**
