# RH-05l：有机录制器丢窗口且追不上链

## 实测的两个缺陷

守护跑了 6.3 小时、25 个窗口，主脑核查发现：

### 缺陷 1：抓取失败的窗口被**永久跳过**

8 个窗口 `fetch_status=INPUTS_UNAVAILABLE`、`n_events=0`、**`error` 列为空**。
而下一个窗口从失败窗口的 `window_end_block + 1` 继续：

```
19:39:47  57937732–57946532  0 事件  INPUTS_UNAVAILABLE  error 为空
19:54:47  57946533–57955333  0 事件  ← 直接跳过了失败区间，永不重试
```

**后果：8 × 8800 = 70,400 块的链上历史永久缺失于有机成交量记录**，
且没有任何地方记下这些区间失败过、为什么失败。
Stage B 要跑 14 天，按这个比例会丢掉约三分之一的观测。

### 缺陷 2：窗口推进追不上链

`--span-blocks 8800` 配 `--period-secs 900`，而实测出块 0.102 s/块，
**900 秒实际流逝约 8,824 块**。每轮欠 24 块，叠加失败窗口的耗时，
当前已落后链头 **18,805 块（32 分钟）**，且只会越拉越大。

## 改哪些文件

只改 `scripts/lp_rh_organic_recorder_v1_readonly.py`，
测试追加进 `tests/test_lp_rh_organic_recorder_v1_readonly.py`。
**现有 18 条测试一条不许改、不许删。**

### 1. 失败区间进重试队列，不再跳过

新增表（幂等建表，`CREATE TABLE IF NOT EXISTS`）
`rh_organic_pending`：`window_start_block, window_end_block, first_failed_at,
attempts, last_error`，主键 `(window_start_block, window_end_block)`。

- `record_window` 的 `fetch_status` 为 `INPUTS_UNAVAILABLE` 或 `PARTIAL` 时，
  把该区间写进 `rh_organic_pending`（`attempts` 递增，`last_error` 记原因）。
- `next_window` 每轮**优先返回 `rh_organic_pending` 里 `attempts` 最少的区间**；
  没有待重试项时才推进到新窗口。
- 重试成功后从 `rh_organic_pending` 删除该行。
- `attempts >= max_attempts`（默认 5）时**不再重试但保留该行**，
  并把 `last_error` 保留——**永久缺失必须留下痕迹，不能静默消失**。

### 2. `error` 列必须写入失败原因

`fetch_status` 非 `COMPLETE` 时，`rh_organic_windows.error` 必须非空，
内容取 `fetch_swaps` 返回的 `failed_ranges` 摘要或异常文本。
**现在它是空的，等于失败了却不说为什么。**

### 3. span 必须覆盖周期

新增 `required_span_blocks(period_secs, block_time_secs=0.102, margin=1.15) -> int`。
`main()` 启动时若 `--span-blocks` 小于该值，**打印警告并自动改用该值**
（不要静默沿用，也不要拒绝启动）。900 秒 → 约 10,147 块。

## 新增测试（**≥12 条**）

- 抓取失败 → 该区间出现在 `rh_organic_pending`，`attempts == 1`，
  `last_error` 非空。
- 下一轮 `next_window` **返回那个待重试区间**，而不是新窗口。
- 重试成功 → 该行从 `rh_organic_pending` 消失，且 `rh_organic_windows`
  对应行的 `fetch_status == "COMPLETE"`。
- 连续失败 5 次后 `attempts == 5`，第 6 轮 `next_window` **不再返回它**
  （改推进新窗口），但该行**仍在表里**（痕迹保留）。
- `fetch_status` 非 COMPLETE 时 `error` 列非空（两种状态各一条）。
- `fetch_status == COMPLETE` 时 `error is None`。
- `required_span_blocks(900)` 在 10,000–10,400 之间。
- `required_span_blocks(300)` 约为其三分之一（线性）。
- `main` 传 `--span-blocks 8800 --period-secs 900` → 实际使用的 span
  **大于 8800**（断言写入库的窗口跨度）。
- 待重试区间与新窗口**不重叠**（构造两者共存的场景断言）。
- `rh_organic_pending` 幂等建表：连续两次 migrate 不报错。
- 同一区间失败两次只有一行，`attempts == 2`。

## 不许动
不改其他脚本。不联网（测试）。既有 `organic.db` 需就地兼容：
新表用 `CREATE TABLE IF NOT EXISTS`，**不要 DROP 或重建 `rh_organic_windows`**。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_organic_recorder_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥30 全绿（原 18 + 新增 ≥12）；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
