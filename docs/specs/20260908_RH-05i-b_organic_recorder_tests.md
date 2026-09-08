# RH-05i-b：只补有机成交量录制器的**测试与看门狗**（脚本已存在，不要重写）

## 背景

RH-05i 的第一轮 worker 已经写出
`scripts/lp_rh_organic_recorder_v1_readonly.py`（300 行，13 个函数，`ast.parse` 通过），
但在写测试时卡住，跑了 2.2 小时、93 轮仍未收敛，已被主脑终止。
**这与 RH-01b 是同一失败模式**（一包塞了脚本+测试+看门狗，worker 写完脚本后卡死），
当初拆成 RH-01c 只补测试，21 分钟完成。本包照此办理。

## 绝对不要做的事

**不要重写、不要重构 `scripts/lp_rh_organic_recorder_v1_readonly.py`。**
它已经存在且语法正确。只有当某个测试暴露出真实缺陷时才最小化修改它，
并在最终报告里写明改了哪一行、为什么。

## 已存在的接口（照此写测试，不要猜）

```
SCHEMA                                    # 建表 SQL 常量
next_window(conn, head, *, span_blocks, max_lookback_blocks) -> tuple|None
record_window(conn, pool, lo, hi, call_fn, provider) -> dict
make_backoff_call_fn(base, sleep_fn=time.sleep)
make_head_fn(rpc_url)
main(argv=None, *, call_fn=None, head_fn=None) -> int
_last_end_block(conn) / _is_transient(exc) / _sleep_until(started, period_secs)
```

先 `sed -n '1,60p'` 与 `grep -n 'def ' ` 读一遍实际签名与返回字段，**以源码为准**；
若下面的验收项与源码实际行为冲突，**停下来在报告里写明冲突点**，不要改源码去迁就测试。

## 只写两个文件

1. `tests/test_lp_rh_organic_recorder_v1_readonly.py`（≤280 行，**≥16 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   **全部用内存 SQLite（`sqlite3.connect(":memory:")` + `conn.executescript(mod.SCHEMA)`）
   与注入的假 `call_fn`。不许联网。不许在 `reports/` 下建任何文件。**

   必测：
   - 空库时 `next_window` 返回 `(head - span, head)`。
   - 库里已有一行时，下一个窗口紧接其 `window_end_block`，**区间不重叠**。
   - 间隔超过 `max_lookback_blocks` → 跳到 `head - span`（不去请求已被裁剪的区块）。
   - `record_window` 写入后读回，`organic_fraction` 是 `Decimal` 且与直接调用
     `lp_rh_organic_volume_v1_readonly.organic_volume_estimate` 的结果一致。
   - 同一 `(window_start_block, window_end_block)` 写两次只有一行（主键去重）。
   - `call_fn` **全部失败** → 该行 `fetch_status == "INPUTS_UNAVAILABLE"`、
     `organic_fraction is None`、`coverage_frac is None`
     （**三处都用 `is None` 断言，不是 0**）。
   - **部分区间失败** → `fetch_status == "PARTIAL"`，`coverage_frac` 是 0~1 的 `Decimal`，
     且 `organic_fraction` **仍然算得出来**（不是 None）。
   - 事件数低于 `min_events` → `estimate_status == "INSUFFICIENT_SAMPLES"`、
     `organic_fraction is None`，但 `n_events` 照写。
   - `_is_transient`：对 `-32005 network is busy`、HTTP 429、HTTP 503 返回 True；
     对 `ValueError("bad params")` 返回 False。
   - `make_backoff_call_fn`：注入假 `sleep_fn` 记录调用，
     前两次抛瞬时错、第三次成功 → 总共 sleep 两次且**退避递增**。
   - `make_backoff_call_fn` 遇到**非瞬时**错误 → 立即抛出，**不重试**（断言 sleep 次数为 0）。
   - 所有 `Decimal` 列往返（写入→读出→`Decimal(...)`）不丢精度。
   - `main(..., call_fn=假, head_fn=假)` 加 `--once` 只跑一轮返回 0，
     且**不在 `reports/` 下建库**（用 `--db` 指向 `tmp_path`）。
   - `--once` 跑完后 `rh_organic_windows` 恰好多一行。

2. `scripts/lp_rh_organic_watchdog.sh`
   照抄 `scripts/lp_rh_premium_watchdog.sh` 的结构（**按行增长判活，不是按进程存在**），
   改成：`DB=reports/lp_rh/organic.db`、表 `rh_organic_windows`、
   `PIDF=reports/lp_rh/organic_recorder.pid`、`LOG=reports/lp_rh/organic_recorder.log`、
   `WLOG=reports/lp_rh/organic_watchdog.log`、`STATE=reports/lp_rh/organic_watchdog_state.json`、
   `STALL_SECS=2400`、`MAX_RESTARTS=50`，重启命令指向
   `scripts/lp_rh_organic_recorder_v1_readonly.py --db "$DB" --period-secs 900 --pid-file "$PIDF"`。
   `chmod +x`。**不要装 cron，主脑来装。**
   注意 `rh_organic_windows` 的时间列名是 `sample_time`（与 premium 看门狗一致）；
   **先 `grep` 确认列名再写**，不要照抄错。

## 硬约束
不改任何其他文件。测试不联网、不写 `reports/`。
单次 Write/Edit ≤150 行或 6000 字符，更大的分次写；写完 `ast.parse` 自检。
**若 30 分钟内没写出测试文件，先把已完成的部分落盘再继续。**

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_organic_recorder_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
ls -la scripts/lp_rh_organic_watchdog.sh reports/lp_rh/
```
定向 ≥16 全绿；全量 0 failed / 14 skipped；看门狗存在且可执行；
`reports/lp_rh/` 下**未新增 organic.db**（测试只用内存库与 tmp_path）。三条命令尾部原样贴出。
