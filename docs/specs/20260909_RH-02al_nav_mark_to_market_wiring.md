# RH-02al：把仓位市价重估与真实两腿接进 run_episode（三层修复的收口）

## 前置（必须先确认，不满足就停下报告）

```bash
git log --oneline -6 | grep -c 'rh-02aj\|rh-02ak'     # 应为 2
grep -c 'position_value_at' scripts/lp_rh_v3_inventory_v1_readonly.py   # 应 >0
```

本包依赖 `scripts/lp_rh_v3_inventory_v1_readonly.py` 已提供的两个函数：
`inventory_for_position(...)` 与 `position_value_at(...)`。
它们已通过主脑独立验收（与独立实现吻合到 1e-50），**直接 import 复用，不要重写**。

## 三层缺陷，前两层已修，本包修第三层并把前两层接起来

| 层 | 现状 |
|---|---|
| 1 手续费量纲 | RH-02ai 已修（用 `L_pos` 而非 `position_usd`） |
| 2 HODL 基准是虚拟 lot | 本包接线：改用 `inventory_for_position` 的真实两腿 |
| 3 **NAV 从不市价重估** | 本包修：`lp_principal` 恒 1000 → 按当前价重估 |

第三层的危害：NAV 的唯一变动项是只增不减的手续费，
**`net_pnl` 结构性恒正，shadow 在数学上不可能报告亏损**。
实测真实 50 分钟窗口，被忽略的仓位价值变化是同期手续费的 **81 倍**。

## 要改的语义（主脑裁决，照此实现）

在 `run_episode` 里：

1. **建仓时刻**：第一个「有 `reference_mid` 的步」即开仓步。
   用**那一步的 `reference_mid`** 作 `entry_price`
   （不要用 `pool_meta.input_price_usd`——那是静态值，会让 `nav_start != capital_usd`）。
   `range_pct` 取自 `pool_meta`。调 `inventory_for_position` 得到
   `amount0_human` / `amount1_human` / `liquidity_human`，**全程缓存不再重算**。
2. **每一步**：
   ```
   lp_value = position_value_at(price=该步 reference_mid, liquidity_human=缓存的 L,
                                entry_price=开仓价, range_pct=..., quote_usd_per_token1=quote)
   nav = compute_nav(wallet=capital_usd - position_usd,
                     lp_principal=lp_value.value_usd,      # ← 市价，不再是常数
                     accrued_fees=accrued, verified_rewards=0, liabilities=0)
   hodl = amount0_human * price * quote + amount1_human * quote   # 两腿固定，只重估
   ```
   **不要再用 `VIRTUAL_INITIAL_TOKEN0_RAW` / `VIRTUAL_INITIAL_TOKEN1_RAW`**。
   这两个常量在本包之后应无引用（留着定义无妨，但不能再被 `run_episode` 用到）。
3. **窗口对齐**：`episode_summary` 现在分别取
   `[s.nav for s in steps if s.nav is not None]` 与
   `[s.hodl_value for s in steps if s.hodl_value is not None]` 的首尾——
   **两个序列的可用步集合不同**（NAV 要 fee_growth 两列非空，HODL 只要 price 非空），
   所以两个数比的不是同一段时间。改成：
   - 先求两者**都可用**的步集合；
   - `net_pnl` 与 `hodl_delta` 都在这个交集的首尾上算；
   - 交集不足 2 步时两者都返回 `None`，并在 episode 行里记明原因，
     **不要各自退回自己的首尾**。
4. **失败关闭**：`pool_meta` 缺 `range_pct`、开仓步没有 `reference_mid`、
   或 `quote_usd_per_token1` 不可得时 → 该 episode 的 nav/hodl 全为 `None`，
   不要用默认值硬算。

## 不许动

`scripts/lp_rh_v3_inventory_v1_readonly.py`（已验收入库，只 import）、
`scripts/lp_rh_pnl_v1_readonly.py`、任何 recorder / daemon、任何 `.db`、`pool_meta.json`。
`load_samples_from_db` 里读 `health_flags_json` 的部分**另有一条线在改**，不要碰。

## 验收标准（性质断言，逐条）

1. **开仓自洽**：合成样本回放，断言第一步
   `lp_value == position_usd` **精确**（相对误差 `< 1e-40`）、
   `hodl == position_usd` 精确、`nav == capital_usd` 精确。
   这三条同时成立是本包正确的最强信号。
2. **net_pnl 可以为负**：构造一组价格下跌的合成样本，
   断言 `net_pnl < 0`。**这条是本包存在的理由**——
   修改前它在数学上不可能为负。
3. **窗口对齐**：构造一组样本，其中某一步有 `reference_mid` 但
   `fee_growth_global_0/1` 为 `None`（真实数据里确实存在这种步），
   断言 `hodl_delta` 与 `net_pnl` 的起止时刻相同；
   把这两个时刻也写进 episode 行或在测试里显式取出比较。
4. **真实数据 sanity**：用真实 DB 跑一次（`load_samples_from_db`，limit=200），
   断言隐含年化 `= net_pnl / position_usd * 365*24*3600 / 窗口秒数 * 100`
   落在 `[-500, 500]` 区间内。修改前这个数是 **29076**，
   量纲错误会立刻撞破这个上界。把实际算出的数贴进报告。
5. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py tests/test_lp_rh_first_step_accrual_v1_readonly.py -q -p no:cacheprovider`
   全绿。若 `first_step_accrual` 里有测试因本包语义变更而失效
   （它们断言的是「NAV = capital + 手续费」这个旧口径），
   **允许更新那些数值断言**，但不许删测试、不许放宽成恒真，
   且必须在报告里逐条说明改了哪条、为什么。

## 纪律

- **不要执行任何 git 命令**。
- 单次 Write/Edit ≤ 150 行或 6000 字符。
- 不要整读 >300 行的文件，用 `sed -n 'a,bp'`。
- 不要重启 daemon / 录制器，不要动 crontab，不要发真实网络请求。
- 命令输出只贴尾部。

## 报告要写清

- 第 1 条三个精确等式的实际相对误差；
- 第 2 条构造的价格路径与算出的 `net_pnl`；
- 第 4 条真实数据的隐含年化实际值；
- 若改了 `first_step_accrual` 的断言，逐条列出改动理由。

---

## 补充：若 RH-02ai 尚未落地，本包一并做第 1 层

先跑这条判断：

```bash
grep -n 'accrued +=' scripts/lp_rh_shadow_runner_v1_readonly.py
```

- 若看到 `accrued += position_usd * (d0 + d1) / FEE_GROWTH_SCALE`
  → **RH-02ai 没落地，第 1 层的量纲错误还在，本包一并修**；
- 若已经是按 liquidity 算的形式 → RH-02ai 已落地，跳过本节。

### 第 1 层的正确公式（主脑已实测自洽，照此实现）

```
L_pos   = inventory_for_position(...).liquidity_raw      # 复用 RH-02aj 的模块
tok0    = L_pos * d0 / 2**128 / 10**dec0                 # token0 人类单位
tok1    = L_pos * d1 / 2**128 / 10**dec1                 # token1 人类单位
accrued += tok0 * price_t1_per_t0 * quote + tok1 * quote
```

其中 `d0`/`d1` 是相邻两次 `feeGrowthGlobal` 读数之差，
`price_t1_per_t0` 用该步的 `reference_mid`。

**首步语义不变**（RH-02af 已确立）：没有前一次读数时增量未知，
`accrued` 不变（首步加 0），只记录读数。**不要回退这条。**

**`L_pos` 与本包第 1 节算 hodl 两腿用的是同一次 `inventory_for_position` 调用结果**，
不要算两遍，也不要一处用 Decimal 版、另一处用 `lp_v3_fee_share` 的 float 版。

### 实测对照（用于验收标准 4）

真实 2985 秒窗口下：
```
错误公式  27.2489 USD   隐含年化 29076%
正确公式   0.0266 USD   隐含年化 28.15%
pool_meta.fee_apr_pct 独立估算        27.34%
```
你算出来的隐含年化应落在 `[10, 60]` 区间。若是四位数，说明还在用 USD 名义值乘 feeGrowth。
