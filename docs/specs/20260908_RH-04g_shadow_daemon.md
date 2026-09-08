# RH-04g：常驻 Shadow 守护（Stage B 的时钟）

## 背景

RH-04f 之后（提交 `8680856`），shadow 闭环在实盘数据上已能跑到
`COMPUTED_FAIL`——经济学全部算出来了，只剩一个具名阻塞
`market_and_chain_risk_pass`（`session=POSTMARKET`、`ORACLE_UNAVAILABLE`）。

`lp_rh_shadow_runner_v1_readonly` 目前是**批量重放工具**，跑一次退出。
Stage B 要求 **≥14 天连续 Shadow 且必须覆盖一个周末**，需要一个常驻守护。

**明确预期**：在「无链上 oracle」这一政策问题解决前，
`eligible_steps` 会长期为 0。**这不是白跑**——守护会持续记录
「哪一项在拦、在什么时段拦、拦了多久」，那本身就是 Stage B 要的观测数据，
而且它证明流水线能连续运行并给出一致判定。政策一旦拍板，同一个守护立刻产出合格步。

## 只写三个文件

1. `scripts/lp_rh_shadow_daemon_v1_readonly.py`（≤280 行）
   **复用 `scripts.lp_rh_shadow_runner_v1_readonly` 的
   `run_episode` / `load_samples_from_db` / `episode_summary`，不要重写它们。**

   - 自己的库 `reports/lp_rh/shadow.db`（**独立文件**，不碰另外四个库）。WAL。两张表：
     - `rh_shadow_episodes`：`episode_id, started_at, ended_at, pool, target_mode,
       position_usd, capital_usd, horizon_hours, n_samples, eligible_steps,
       first_eligible_at, status_counts_json, conjunct_failure_counts_json,
       skipped_at_load, steps_without_nav, nav_start, nav_end, net_pnl,
       hodl_delta, pool_meta_hash, error`，主键 `episode_id`。
     - `rh_shadow_blockers`：`episode_id, conjunct, fail_count, sample_session`，
       主键 `(episode_id, conjunct, sample_session)`。**按时段分组统计**，
       这样能看出「RTH 时是否只剩 oracle 一项在拦」。
     金额用 TEXT（Decimal 字符串）。缺值 NULL，**绝不写 0**。
   - 每轮：从活库读最近 `--samples` 个样本 → `run_episode` → 汇总落库。
     **活库只读打开**，Shadow 的写入走独立的临时 store（`run_episode` 已如此设计）。
   - `--pool-meta-json` 必填；读进来后算 `sha256` 存 `pool_meta_hash`，
     便于日后判断某段观测用的是哪份池证据。
   - `main()`：`--db --pool --samples --period-secs 900 --pool-meta-json
     --position-usd --capital-usd --horizon-hours --pid-file --once`。
     循环 deadline **从本轮起点算**。`SIGTERM`/`SIGINT` 优雅退出并删 pid 文件。
     单轮异常**不得中断守护**：记进 `error` 列，继续下一轮。

2. `tests/test_lp_rh_shadow_daemon_v1_readonly.py`（≤260 行，**≥14 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   **内存 SQLite + 合成样本，不许联网、不许写 `reports/`。** 必测：
   - 一轮写入恰好一行 `rh_shadow_episodes`。
   - `conjunct_failure_counts_json` 能被 `json.loads` 还原成 dict 且键是合取项名。
   - 阻塞项按时段分组：构造 RTH 与 POSTMARKET 两批样本，
     断言 `rh_shadow_blockers` 里两个 `sample_session` 各有行。
   - `eligible_steps == 0` 时 `first_eligible_at is None`（**`is None`，不是空串**）。
   - 有合格步时 `first_eligible_at` 是该步的 `sample_time`。
   - `run_episode` 抛异常 → 该轮 `error` 非空，**且守护不退出**（用 `--once` 验证返回 0）。
   - `pool_meta_hash` 对同一份 meta 稳定、对不同 meta 不同。
   - 金额列往返为 `Decimal` 不丢精度。
   - `nav_start`/`net_pnl` 在无 NAV 时为 `NULL`（**`is None` 断言**）。
   - 同一 `episode_id` 写两次只有一行。
   - `--once` 返回 0 且**不在 `reports/` 下建库**（`--db` 指向 `tmp_path`）。
   - 活库以只读方式打开：传一个只读连接，断言未抛异常且活库未被写入
     （比对 mtime 前后一致）。
   - deadline 从本轮起点算：注入假 `sleep_fn` 与假时钟，断言两轮起点间隔等于
     `period_secs`，而不是「上一轮结束 + period」。

3. `scripts/lp_rh_shadow_watchdog.sh`
   照抄 `scripts/lp_rh_premium_watchdog.sh`（**按行增长判活**），改成
   `shadow.db` / `rh_shadow_episodes` / `shadow_daemon.pid`，
   时间列用 `started_at`（**先 grep 确认列名再写**），
   `STALL_SECS=2400`，`MAX_RESTARTS=50`。**不要装 cron，主脑来装。**

## 不许动
不改 `lp_rh_shadow_runner_v1_readonly.py` 与其他脚本。不写另外四个库。
不联网。不碰任何签名/广播路径。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**先落盘骨架再逐步填充**，不要攒到最后一次性写。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
ls -la scripts/lp_rh_shadow_watchdog.sh reports/lp_rh/
```
定向 ≥14 全绿；全量 0 failed / 14 skipped；看门狗存在且可执行；
`reports/lp_rh/` 下**未新增 shadow.db**。三条命令尾部原样贴出。
