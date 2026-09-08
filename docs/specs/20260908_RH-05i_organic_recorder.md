# RH-05i：有机成交量长窗口录制器（把 17 分钟快照变成跨昼夜序列）

## 背景

`ORGANIC_VOLUME_LIVE_20260908.md` 实测 `organic_fraction = 0.9177`，并据此让资金政策
结论成立。但该报告第 5 节自己写明**最弱的一环**：

> 17 分钟的窗口。一个 17 分钟切片不能代表 30 天。这段时间恰逢美股交易时段，
> 隔夜与周末的成交量结构完全未观测。

本包把它变成序列。**墙钟约束**：越晚上线，跨昼夜样本越少。

## 关键实测事实（已核实，直接用，不要另猜）

- 出块间隔 **0.102 s/块**；15 分钟 ≈ 8,800 块。
- 提供方能力（`PROVIDER_MATRIX_20260908.md` 更正 3）：
  | 端点 | 状态保留 | 10k 块 getLogs |
  |---|---|---|
  | `https://rpc.ordofi.network` | 51 小时 | **稳定，首选** |
  | `https://rpc.mainnet.chain.robinhood.com` | 10.4 分钟 | 不稳定，仅作备选 |
  | `https://robinhood-rpc.publicnode.com` | 无 | **全部 403，不要用** |
- ordofi 偶发 `{'code': -32005, 'message': 'the network is busy'}`，需退避重试。
- CORE 种子池 `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`。

## 只写三个文件

1. `scripts/lp_rh_organic_recorder_v1_readonly.py`（≤300 行）
   **复用已有模块，不要重写它们**：
   `scripts.lp_rh_swap_logs_v1_readonly` 的 `fetch_swaps` / `to_organic_events`，
   `scripts.lp_rh_organic_volume_v1_readonly` 的
   `participant_concentration` / `round_trip_volume` / `organic_volume_estimate`。

   - 自己的库 `reports/lp_rh/organic.db`（**独立文件**，绝不碰 `scanner.db` 与 `premium.db`，
     那两个各有单写者）。WAL。表 `rh_organic_windows`：
     `window_start_block, window_end_block, sample_time, provider, n_events,
      n_unique_senders, top1_share, top5_share, hhi, round_trip_share,
      total_volume, round_trip_volume, concentration_excess_volume,
      organic_fraction, coverage_frac, fetch_status, estimate_status, error`
     主键 `(window_start_block, window_end_block)`。金额/比率存 **TEXT（Decimal 字符串）**。
     **缺值一律 NULL，绝不写 0。**
   - `next_window(conn, head, *, span_blocks, max_lookback_blocks) -> tuple[int,int] | None`
     从库里最后一个 `window_end_block` 接着往前推进；库为空时取 `head - span_blocks`。
     若距上次窗口的间隔超过 `max_lookback_blocks`（提供方保留深度，默认 1,700,000，
     略小于实测的 1,800,100 留余量），**跳到 `head - span_blocks` 并把这次跳过记入
     `error` 字段**，不要去请求已被裁剪掉的区块。
   - `record_window(conn, pool, lo, hi, call_fn, provider) -> dict`
     跑一次抓取 + 三个指标，写一行。`fetch_status` 非 `COMPLETE` 时
     `estimate_status` 与 `organic_fraction` 照样按实际拿到的事件计算并如实标注，
     **但 `coverage_frac` 必须原样带上**，让读者知道这一行基于多少覆盖率。
   - `main()`：`--db --pool --provider-url --span-blocks 8800 --period-secs 900
     --max-lookback-blocks 1700000 --pid-file --once`。
     循环的 **deadline 从本轮起点算**，不是结束点（采集器周期漂移的教训）。
     `SIGTERM`/`SIGINT` 优雅退出并删 pid 文件。
     provider 报 `-32005` / 429 / 5xx 时退避 `8/24/72` 秒重试，仍失败则该窗口记
     `fetch_status="INPUTS_UNAVAILABLE"` 并**继续下一轮**，不得整体退出。

2. `tests/test_lp_rh_organic_recorder_v1_readonly.py`（≤280 行，**≥16 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   全部用**内存 SQLite + 注入的假 `call_fn`**，**不许联网、不许写 `reports/` 下任何文件**。必测：
   - 空库时 `next_window` 返回 `(head - span, head)`。
   - 库里已有一行时，下一个窗口紧接其 `window_end_block`，**不重叠**。
   - 间隔超过 `max_lookback_blocks` 时跳到 `head - span`，且返回的行 `error` 非空。
   - 写入后再读出，`organic_fraction` 是 `Decimal` 且与直接调用 `organic_volume_estimate` 一致。
   - 同一 `(lo,hi)` 写两次只有一行（主键去重）。
   - `call_fn` 全失败 → 该行 `fetch_status == "INPUTS_UNAVAILABLE"`、
     `organic_fraction is None`（**用 `is None` 断言，不是 0**）、`coverage_frac is None`。
   - 部分区间失败 → `fetch_status == "PARTIAL"`，`coverage_frac` 是 0~1 之间的 `Decimal`，
     且 `organic_fraction` **仍然算出来**（不是 None）。
   - 事件数低于 `min_events` → `estimate_status == "INSUFFICIENT_SAMPLES"` 且
     `organic_fraction is None`，但 `n_events` 照样写入。
   - 所有 Decimal 列往返（写入→读出→`Decimal(...)`）不丢精度。
   - `--once` 只跑一轮就返回 0。

3. `scripts/lp_rh_organic_watchdog.sh`
   照抄 `scripts/lp_rh_premium_watchdog.sh` 的结构（**按行增长判活，不是按进程存在**），
   改成 `organic.db` / `rh_organic_windows` / `organic_recorder.pid`，
   `STALL_SECS=2400`（周期 900 秒，容三轮），`MAX_RESTARTS=50`。**不要装 cron，我来装。**

## 不许动
不改任何现有脚本或测试。不写 `reports/lp_rh/scanner.db`、`premium.db`。不联网（测试）。
单次 Write/Edit ≤150 行或 6000 字符，更大的文件分次写；写完对每个 .py 跑 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_organic_recorder_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥16 全绿；全量 0 failed / 14 skipped。`git diff --stat` 只含本包三个新文件。
跑完 `ls -la reports/lp_rh/` 确认**没有新建任何库文件**（测试只用内存库）。把三条命令的尾部原样贴出来。
