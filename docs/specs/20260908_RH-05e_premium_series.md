# RH-05e：参考价溢价**时间序列**（把单点快照升级成分布）

## 背景与经济动机

`RH05_EVIDENCE_COMPLETE.md` 自列的未闭合缺口之一：**溢价目前只有单点快照，不是序列**。
RH 链上的股票代币相对真实股价存在溢价/折价。单点快照无法区分两种性质完全不同的情形：

- **均值回复型**：溢价反复穿越零轴。做市商每次回复都被**单向成交**，这是真实 LVR 损耗，必须从费收里扣。
- **持久偏移型**：溢价长期停在某一侧（套利通道受限）。此时 LP 只是持有一份被重定价的库存，损耗**不重复发生**。

两者对 NetCover 的影响方向相反，因此 PRD §10.1 的费收折算必须知道处于哪种状态。本包只做**离线纯函数**：主脑负责跑实盘录制并喂样本。

## 只写两个文件（写到 `/tmp/codex_out/RH-05e/` 下同名子目录）

1. `scripts/lp_rh_premium_series_v1_readonly.py`（≤300 行）
   全部金额/比率用 `Decimal`。缺输入返回 `None`，**绝不用 0 代替缺失**。不联网、不写库、不 import 任何签名/广播模块。

   - `premium_bps(chain_price, reference_price) -> Optional[Decimal]`
     `(chain/ref - 1) * 10000`。任一为 `None`/`<=0` → `None`。
   - `series_stats(samples, *, min_samples=30) -> dict`
     `samples` 为 `[{"sample_time": iso8601_str, "chain_price": .., "reference_price": ..}]`，按时间升序。返回：
     `{"n_total","n_usable","n_skipped","status","mean_bps","median_bps","stdev_bps","p05_bps","p95_bps","max_abs_bps","zero_crossings","sign_stability","persistence_frac","half_life_secs"}`
     - 任一价格为 `None` 的样本 **跳过并计入 `n_skipped`**，不当作溢价 0。
     - `status`：`n_usable == 0` → `"INPUTS_UNAVAILABLE"`；`0 < n_usable < min_samples` → `"INSUFFICIENT_SAMPLES"`（此时**除计数外所有统计量为 `None`**）；否则 `"COMPUTED"`。
     - `sign_stability` = 众数符号样本数 / `n_usable`（零值归入正号）。
     - `persistence_frac` = `|premium| > persistence_threshold_bps`（默认 `Decimal("10")`，形参可覆盖）的样本占比。
     - `half_life_secs`：对 `premium_t` 与 `premium_{t-1}` 做 AR(1) 最小二乘估 `rho`（无截距）；`0 < rho < 1` 时 `-ln(2)/ln(rho) × 中位采样间隔秒`，否则 `None`。**`rho >= 1`（发散）或 `rho <= 0`（振荡）都必须返回 `None`，不许夹逼成有限值。**
   - `premium_regime(stats) -> str`
     `MEAN_REVERTING` / `PERSISTENT_OFFSET` / `UNSTABLE` / `INSUFFICIENT_SAMPLES` / `INPUTS_UNAVAILABLE`。
     判定：status 非 COMPUTED 直接透传；`sign_stability >= 0.9 且 zero_crossings <= n_usable*0.02` → `PERSISTENT_OFFSET`；`zero_crossings >= n_usable*0.1 且 half_life_secs is not None` → `MEAN_REVERTING`；其余 `UNSTABLE`。
   - `lvr_haircut_frac(stats, regime) -> Optional[Decimal]`
     只有 `MEAN_REVERTING` 才产生折损：返回 `min(1, stdev_bps / 10000 × Decimal("0.5"))`（`LVR_COEFFICIENT_MODEL=0.50`，**该常量不得改数值**）。`PERSISTENT_OFFSET` → `Decimal(0)`（不重复扣）。其余 regime → `None`（**不是 0**：未知不等于无损）。
   - `main()`：`--samples-json --out`，纯离线。

2. `tests/test_lp_rh_premium_series_v1_readonly.py`（≤280 行，**≥18 个测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。必测：
   - `premium_bps` 正/负/零；参考价为 `None` 或 0 → `None`。
   - 合成**均值回复**序列（正弦穿零 120 点）→ `MEAN_REVERTING` 且 `half_life_secs is not None`。
   - 合成**持久偏移**序列（恒 +80bps 加微噪 120 点）→ `PERSISTENT_OFFSET`，`zero_crossings == 0`，`sign_stability == 1`。
   - 合成**随机游走发散**序列 → `half_life_secs is None`（断言不是某个大数）。
   - `n_usable = 29 < min_samples=30` → `status == "INSUFFICIENT_SAMPLES"` 且 `mean_bps is None`。
   - 全部样本价格为 `None` → `INPUTS_UNAVAILABLE`，`n_skipped == n_total`。
   - **缺数据不得被当成溢价 0**：100 个样本其中 40 个 `reference_price=None`、60 个恒 +50bps → `n_usable==60`、`n_skipped==40`、`mean_bps == Decimal("50")`（不是 30）。**这条是本包的核心陷阱。**
   - `lvr_haircut_frac`：`PERSISTENT_OFFSET` → `Decimal(0)`；`UNSTABLE` → `None`（用 `is None` 断言，不能是 0）。
   - 系数核对：源码中 `0.50` 出现处即 `LVR_COEFFICIENT_MODEL`，测试 grep 断言文件里不含 `0.25`/`0.75` 等改写。
   - 时间乱序输入不崩溃（内部排序或明确拒绝，二选一并测之）。

## 硬约束
不读、不改 `/opt/lpbot` 下任何文件（spec 除外，只读）。单次写 ≤120 行，超了分次。写完 `python -c "import ast,sys;ast.parse(open(p).read())"` 自检两个文件。

## 验收
```
cd /tmp/codex_out/RH-05e && PYTHONPATH=/opt/lpbot/lp-bot-v3-origin-check:/tmp/codex_out/RH-05e \
  /root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
必须真跑通、全绿、≥18 passed。把最后 15 行原样贴出来。
