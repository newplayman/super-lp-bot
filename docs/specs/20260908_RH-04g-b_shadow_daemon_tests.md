# RH-04g-b：只补 Shadow 守护的**测试与看门狗**（脚本已存在）

## 背景

RH-04g 的 worker 已写出 `scripts/lp_rh_shadow_daemon_v1_readonly.py`
（280 行，`ast.parse` 通过，可导入），然后在 182 轮撞上 `error_max_turns`。

**这是本项目第三次同款失败**：RH-05i、RH-04f、RH-04g 三个「脚本+测试+看门狗」
三文件包，全部在写完脚本后耗尽预算；而 RH-05i-b 拆成「只补测试与看门狗」后一次通过。
**本包照此办理。**

## 绝对不要做的事

**不要重写、不要重构 `scripts/lp_rh_shadow_daemon_v1_readonly.py`。**
它已存在且能导入。只有当某个测试暴露真实缺陷时才最小化修改，
并在报告里写明改了哪一行、为什么。

## 已存在的接口（以源码为准，先 `grep -n '^def '` 确认）

```
DEFAULT_SHADOW_DB / LIVE_DB / DEFAULT_PERIOD_SECS / TARGET_MODE
_EPISODES_DDL / _BLOCKERS_DDL
open_shadow_store(db_path)          open_live_store(live_db_path)
pool_meta_hash_of(meta_text)        blocker_rows_from_steps(steps, samples)
persist_episode(conn, *, episode_id, started_at, ended_at, pool, target_mode, ...)
run_one_round(cfg, *, shadow_conn, episode_id, started_at, now_fn)
run_round_safe(cfg, *, shadow_conn, episode_id, now_fn)
run_daemon(cfg, *, shadow_conn, period_secs, now_fn, sleep_fn, stop_event)
main(argv=None)
```

若下列验收项与源码实际行为冲突，**停下来在报告里写明冲突点**，不要改源码迁就测试。

## 只写两个文件

1. `tests/test_lp_rh_shadow_daemon_v1_readonly.py`（≤260 行，**≥14 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   **内存 SQLite（`open_shadow_store(":memory:")` 或直接建表）+ 合成样本。
   不许联网、不许写 `reports/` 下任何文件。** 必测：
   - 一轮写入恰好一行 episodes。
   - 同一 `episode_id` 写两次只有一行（主键去重）。
   - `conjunct_failure_counts_json` 能 `json.loads` 还原成 dict。
   - `blocker_rows_from_steps` 按时段分组：构造两种 session 的样本，
     断言两个 `sample_session` 各有行。
   - `eligible_steps == 0` 时 `first_eligible_at is None`（**`is None`，不是空串**）。
   - 有合格步时 `first_eligible_at` 等于该步的 `sample_time`。
   - `run_round_safe`：内部抛异常 → 该轮 `error` 列非空，**函数不向上抛**。
   - `pool_meta_hash_of` 对同一文本稳定、对不同文本不同、对 `None` 返回 `None`
     （**若源码行为不同，如实记录，不要改源码**）。
   - 金额列往返为 `Decimal` 不丢精度（`_money_text` 的往返）。
   - 无 NAV 时 `nav_start` / `net_pnl` 为 `NULL`（**`is None` 断言**）。
   - `run_daemon`：注入假 `sleep_fn` 与 `stop_event`，跑 2 轮后停止，
     断言 episodes 恰好 2 行、`sleep_fn` 被调用 1 次。
   - `run_daemon` 的 deadline **从本轮起点算**：注入可控 `now_fn`，
     断言传给 `sleep_fn` 的秒数 = `period_secs − 本轮耗时`，而不是恒等于 `period_secs`。
   - `open_live_store` 以只读方式打开：对一个真实文件调用后尝试写入应失败
     （或断言连接的 `uri`/`mode=ro`，以源码实现为准）。
   - `main(["--once", "--db", str(tmp_path/"s.db"), ...])` 返回 0，
     且**不在 `reports/` 下建库**。

2. `scripts/lp_rh_shadow_watchdog.sh`
   照抄 `scripts/lp_rh_premium_watchdog.sh` 的结构（**按行增长判活，不是按进程存在**），
   改成 `DB=reports/lp_rh/shadow.db`、表 `rh_shadow_episodes`、
   `PIDF=reports/lp_rh/shadow_daemon.pid`、`LOG=reports/lp_rh/shadow_daemon.log`、
   `WLOG=reports/lp_rh/shadow_watchdog.log`、
   `STATE=reports/lp_rh/shadow_watchdog_state.json`、
   `STALL_SECS=2400`、`MAX_RESTARTS=50`。
   **时间列先 `grep -n started_at scripts/lp_rh_shadow_daemon_v1_readonly.py` 确认再写。**
   `chmod +x`。**不要装 cron，主脑来装。**

## 硬约束
不改任何其他文件。测试不联网、不写 `reports/`。
单次 Write/Edit ≤150 行或 6000 字符，更大的分次写；写完 `ast.parse` 自检。
**若 30 分钟内未写出测试文件，先把已完成部分落盘再继续。**

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
ls -la scripts/lp_rh_shadow_watchdog.sh reports/lp_rh/
```
定向 ≥14 全绿；全量 0 failed / 14 skipped；看门狗存在且可执行；
`reports/lp_rh/` 下**未新增 shadow.db**。三条命令尾部原样贴出。
