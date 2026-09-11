# RH-02cn — 按有机成交量折减手续费（PRD §10.3）

## 背景（已实测，见 `reports/AUDIT_organic_fraction_20260911.md`）

`reports/lp_rh/organic.db` 的 `rh_organic_windows` 有 195 行，
`lp_rh_organic_recorder_v1_readonly.py` 每 15 分钟写一条。
**`runner` 对 `organic` 的引用是 0。**

192 个 `estimate_status = COMPUTED` 的窗口：

```
organic_fraction  min 0.7419   p50 0.9026   max 0.9728   avg 0.8975
coverage_frac     全部 = 1.0000（窗口内事件全取到，不是抽样）
=> fee 按 raw 计，平均高估 11.42%，最差窗口 34.79%
```

手续费来自 `feeGrowthGlobal` 增量，那计入**每一笔**成交，
包括往返套利与集中地址的非有机部分。PRD §10.3 要求区分 raw 与 organic。

这是本轮第三个 fee 高估源，也是**当前唯一仍在生效**的那个
（量纲错误已修 `12efd38`；in-range 已接 `d458c64`，当前 fraction 1.0）。

## 要做的事

改 `scripts/lp_rh_shadow_runner_v1_readonly.py`。

### 1. 整轮加载一次窗口表

在 `run_episode` 开头（与 RH-02cg 取 gas 观测、RH-02ck 取 gas 储备同一处），
从 `organic.db` 读**全部** `rh_organic_windows` 到内存列表。
新增参数 `organic_db_path`，默认 `reports/lp_rh/organic.db`。

**不要每步查库**——一轮 200 步会变成 200 次查询。

### 2. 每步按时间取窗口

按该步的 `sample_time`，取**最接近且不晚于它**的窗口。

- **不要用最新窗口套全程**：一轮跨 50 分钟，会横跨三四个窗口，
  有机占比在窗口之间是变动的（实测 0.74 ~ 0.97）
- 取不到（所有窗口都晚于该步）→ 见下面的 fail-close

### 3. 三条 fail-close（本包的核心）

| 情况 | 行为 |
|---|---|
| 取不到窗口 | **不折减**，标记 `ORGANIC_UNAVAILABLE:NO_WINDOW` |
| `estimate_status != "COMPUTED"` | **不折减**，标记 `ORGANIC_UNAVAILABLE:<status>` |
| `coverage_frac < 1` | **不折减**，标记 `ORGANIC_UNAVAILABLE:PARTIAL_COVERAGE` |
| `organic_fraction` 为 None 或不在 (0, 1] | **不折减**，标记 `ORGANIC_UNAVAILABLE:INVALID_FRACTION` |

**「不折减」意味着用原始 fee，并且把这一步标出来。**

**绝不默认 `organic_fraction = 1.0`。** 把「测不出有机占比」当成
「全都是有机的」，正是本仓库 27 例「静默假绿」的形状——数字照出、
量级正常、结论偏高。标记与不折减必须同时发生，只做一半等于没做。

### 4. 折减与留痕

```python
fee_usd_raw = (tok0 * price + tok1) * quote      # 现有算法，不改
fee_usd = fee_usd_raw * organic_fraction          # 折减后
accrued += fee_usd                                # 只在 in_range 时（RH-02cm 已有）
```

**两个数都要留**：
- `rh_position_marks.unvalued_risk_json` 每步加
  `{"fee_usd_raw":..., "fee_usd_organic":..., "organic_fraction":...|null,
    "organic_status": "OK"|"ORGANIC_UNAVAILABLE:..."}`
- episode summary 加 `organic`：
  `{"steps_discounted", "steps_not_discounted", "fraction_min",
    "fraction_max", "fraction_avg", "accrued_raw", "accrued_organic"}`
  分母为 0 时各统计量是 **None 不是 0**
- daemon 日志行打印 `organic=<steps_discounted>/<total>`

保留 raw 是为了能回溯两者差异——**修正幅度本身是要被审计的证据**。

## 不许动

- 不要改 `fee_usd_raw` 的算法、`compute_nav`、`hodl_benchmark`、`net_pnl`。
- 不要改 RH-02cm 的 in-range 判断逻辑（两者叠加：先判 in_range，再乘 organic）。
- 不要改 NetCover 的 `fee_ev_usd`（那是预估路径，不在本包）。
- 不要改 `organic.db` 的任何内容，只读（`mode=ro`）。
- 不要碰 `scripts/lp_rh_shadow_daemon_v1_readonly.py` 的逻辑，
  **除了**把 `organic` 统计加进日志行那一处（与 RH-02cm 的 `in_range` 同样处理）。
- 测试用 `tmp_path` 造 organic 库；**不要读生产 organic.db**。
- **不要重启或 kill 任何进程**（采集器 2271374 / daemon 1789399 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## `rh_organic_windows` 真实列（照抄）

```
window_start_block, window_end_block, sample_time, provider, n_events,
n_unique_senders, top1_share, top5_share, hhi, round_trip_share,
total_volume, round_trip_volume, concentration_excess_volume,
organic_fraction, coverage_frac, fetch_status, estimate_status, error
```

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

本会话已有**九次**「构造的输入进不去目标分支」，最近一次是
`_open_sample(price=...)` 落到了没人读的 `s["price"]` 键上
（runner 读 `reference_mid`）。逐条确认断言真的走到了目标分支。

1. 窗口 `organic_fraction = 0.9`、`COMPUTED`、`coverage_frac = 1` →
   `accrued` 恰好是不折减时的 **0.9 倍**（用两次 run_episode 对比，
   或直接断言 `accrued_organic == accrued_raw * Decimal("0.9")`）。
2. 无窗口 → **不折减**，`accrued_organic == accrued_raw`，
   该步 `organic_status` 为 `ORGANIC_UNAVAILABLE:NO_WINDOW`。
3. `estimate_status = "INPUTS_UNAVAILABLE"` → 不折减并标记。
4. `coverage_frac = 0.5` → 不折减并标记 `PARTIAL_COVERAGE`。
5. `organic_fraction = None` / `0` / `1.5` → 三种都不折减并标记
   `INVALID_FRACTION`（**注意 0 也要拒绝**：零有机占比意味着零手续费，
   那是结论不是输入，不能静默乘上去）。
6. 三个窗口时间不同、该 episode 的步跨越它们 →
   每步用的是各自**不晚于自己**的那个窗口，不是最新的那个。
7. 与 in-range 叠加：一步在区间外 → 不累加（organic 不影响这个判断）；
   一步在区间内且有窗口 → 累加折减后的值。
8. `fraction_min` / `fraction_max` / `fraction_avg` 在全部步都没窗口时
   都是 **None 不是 0**。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥8 条。
2. 全量 `python3 -m pytest tests/ -q` 通过。
3. `grep -n "organic" scripts/lp_rh_shadow_runner_v1_readonly.py` 有生产调用。
4. `grep -n "organic_fraction.*1\.0\|organic_fraction, 1" scripts/lp_rh_shadow_runner_v1_readonly.py`
   **不得出现把 1.0 当默认值的写法**。
5. `git status --short` 里只有 runner、daemon（仅日志行）及测试被改动。
