# RH-02ai：shadow 手续费累计存在量纲错误，收益虚高 1022 倍

## 硬证据（主脑已实测，不需要你重新推导）

`scripts/lp_rh_shadow_runner_v1_readonly.py:372` 现行公式：

```python
accrued += position_usd * (d0 + d1) / FEE_GROWTH_SCALE
```

用真实链上数据（池 `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`，
`reports/lp_rh/scanner.db` 最近 200 条 `rh_market_states`，窗口 2985 秒）实测：

| 口径 | 窗口内手续费 | 隐含年化 |
|---|---|---|
| 现行公式 | **27.2489 USD** | **29076 %** |
| 正确公式 | **0.0266 USD** | **28.15 %** |
| 扫描器独立估算 `pool_meta.fee_apr_pct` | — | **27.34 %** |

正确公式与扫描器独立路径吻合到 3% 以内；现行公式虚高 **1022 倍**。

## 三条根因

1. **量纲错**：`feeGrowthGlobal` 的单位是「每单位 liquidity 的 token 数」(Q128 定点)，
   要乘的是仓位的 **liquidity `L_pos`**，不是仓位的 **USD 名义值**。
2. **异币种直接相加**：`d0 + d1` 把 token0（18 位小数）与 token1（6 位小数）
   两种不同代币的原始整数直接相加，量纲无意义，且被 18 位那边完全主导。
3. **缺价格换算**：两条腿都要先按各自 decimals 化成人类单位，
   再各自换算成 USD 才能相加。

## 正确公式（已实测自洽，照此实现）

```
L_pos   = position_liquidity_raw(position_usd, entry_price, range_pct, dec0, dec1)
tok0    = L_pos * d0 / 2**128 / 10**dec0        # token0 人类单位
tok1    = L_pos * d1 / 2**128 / 10**dec1        # token1 人类单位
fee_usd = tok0 * price_t1_per_t0 * quote_usd_per_token1 + tok1 * quote_usd_per_token1
accrued += fee_usd
```

- `position_liquidity_raw` **直接从 `scripts/lp_v3_fee_share.py` import 复用**，
  不要重写、不要修改那个文件（它已被修正过，注释里写明了 raw 缩放因子的由来）。
  它返回 float，转成 `Decimal(str(...))` 后再参与 Decimal 运算。
- `entry_price`、`range_pct`、`dec0`、`dec1` 从 `pool_meta` 取
  （键名分别是 `input_price_usd`、`range_pct`、`dec0`、`dec1`，实测均存在）。
- `price_t1_per_t0` 用该步样本的 `reference_mid`（代码里已有局部变量 `price`）。
- `quote_usd_per_token1` 复用现有局部变量 `quote`（默认 `Decimal("1")`）。
- `L_pos` 只在第一步算一次并缓存：仓位开出后 liquidity 不随价格变化。

## 失败关闭（必须遵守，这是本仓库的既定风格）

`pool_meta` 缺少 `input_price_usd` / `range_pct` / `dec0` / `dec1` 任一键，
或 `position_liquidity_raw` 返回 0，或该步 `price` 为 None 时：
**该步 `nav` 必须是 `None`**，不得用默认值静默算出一个数。
不要引入新的模块级默认常量来"兜底"。

## 你要改的文件（只有这两个）

1. `scripts/lp_rh_shadow_runner_v1_readonly.py` —— 只改 `run_episode` 里
   第 356–380 行附近的 accrual/NAV 块，以及为缓存 `L_pos` 所必需的局部变量初始化。
   **不要动**该文件的任何其它函数、不要动 gate/conjunct 逻辑、不要动 SQL。
2. 新建 `tests/test_lp_rh_fee_accrual_dimensional_v1_readonly.py`。

**不许改**：`scripts/lp_v3_fee_share.py`、`scripts/lp_rh_pnl_v1_readonly.py`、
任何 recorder / daemon 脚本、任何既有测试文件、任何 `.db`、`pool_meta.json`。

## 验收标准（逐条，全部要过）

1. 新测试用**构造的合成样本**（不要连真实 DB）覆盖：
   a. 两步之间 `feeGrowthGlobal` 增量给定时，`accrued` 等于上面公式的手算值；
   b. 首步 `accrued` 仍为 0（RH-02af 已确立的语义，不得回退）；
   c. `pool_meta` 缺 `range_pct` 时该步 `nav is None`；
   d. 中途出现一条 `fee_growth_global_0/1` 为 None 的样本后再恢复，
      `prev_fg` 不被重置，恢复后的增量是跨越该 gap 的真实差值（回归锁）。
2. **量纲回归锁**：断言在同一组输入下，
   `旧公式结果 / 新公式结果 > 100`（防止有人改回按 USD 乘）。
3. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_fee_accrual_dimensional_v1_readonly.py tests/test_lp_rh_shadow_runner_v1_readonly.py tests/test_lp_rh_first_step_accrual_v1_readonly.py -q -p no:cacheprovider`
   全绿（`first_step_accrual` 目前可能有既存红，若红请在最终报告里**原样贴出**失败名，
   不要为了让它绿而改那个测试文件）。
4. 全量 `/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider | tail -5`
   相对基线不新增 failed（基线：约 4418 passed / 5 failed，5 个红是已知的
   Decimal 全局精度污染，另一路在修，与本任务无关）。

## 纪律（违反即退回）

- **不要执行任何 git 命令**（不 add、不 commit、不 stash、不 checkout）。
- 单次 Write/Edit ≤ 150 行或 6000 字符，更大的改动分次写。
- 不要整读超过 300 行的文件，用 `sed -n 'a,bp'` 读片段。
- 命令输出只贴尾部。
- 不要重启任何 daemon / 录制器，不要动 crontab。
- 不要写任何真实网络请求。

## 最终报告要写清

- 改了哪几行；
- 第 2 条量纲回归锁实际算出的倍数；
- 三条 pytest 命令的原样尾部输出。

---

## 补充（主脑 19:30 追加，覆盖上文冲突处）

### 1. 授权你修改一个既有测试文件

`tests/test_lp_rh_first_step_accrual_v1_readonly.py` 里有 7 条测试断言了
**基于旧公式算出的具体数值**。公式修正后这些数值必然改变，
所以**授权你修改这一个文件**，规则：

- 只允许更新数值期望与容差写法，**不允许删除任何测试函数**、
  **不允许把断言放宽成恒真**（例如 `assert nav is not None` 顶替数值断言）；
- 期望值必须由**新公式手算/独立复算**得出，不许把实际输出抄回去当期望
  （抄回去等于没有断言）；
- 大数相减导致尾数丢失时，用**相对容差**：
  `assert abs(actual - expected) <= abs(expected) * Decimal("1e-25")`，
  不要写精确相等 `==`（这在 Decimal 默认 28 位精度下数学上不成立，
  前一轮已经有 worker 在这个坑里空转了 80 分钟）。

除这一个文件外，其它既有测试文件仍然不许改。

### 2. 全量测试当前不是稳定基线

另一条线（RH-02ah）**此刻正在并发修改**
`scripts/lp_rh_exit_depth_v1_readonly.py`、
`scripts/lp_rh_organic_recorder_v1_readonly.py`、
`scripts/lp_rh_premium_recorder_v1_readonly.py`
的全局 Decimal 精度污染。因此：

- 上文验收标准第 4 条（全量不新增 failed）**降级为「贴出结果供主脑判读」**，
  不作为你的通过闸门；
- **不要去修**上述三个文件或它们的测试，看到它们红就在报告里注明"属 RH-02ah 范围"；
- 你的硬闸门是验收标准 1、2、3 三条。

### 3. 你的断言要对全局精度不敏感

正因为上面那条并发修改，**不要在测试里读取或依赖 `getcontext().prec` 的具体值**，
也**不要**用 `getcontext().prec = N` 去 pin 精度（那是把污染合法化，已被明令禁止）。
一律用相对容差断言。

---

## 补充二（主脑 19:35 追加，这条能帮你少兜一大圈）

主脑刚查清那 5–7 条红的**真正根因**，与你的任务直接相关：

`tests/test_lp_rh_first_step_accrual_v1_readonly.py` 里的合成样本用
`d0=7, d1=3` 这种**极小的 feeGrowth 增量**。在旧公式下：

```
增量 = 1000 * (7+3) / 2**128 ≈ 2.9e-35
nav  = 10000 + 2.9e-35
```

`10000 + 2.9e-35` 在 Decimal 默认 28 位精度下**尾数被整个吸收**，
`nav_2 - nav_1` 取回来是 0 或严重截断值。
这些测试此前之所以"单独跑 12 passed"，**是因为 `lp_rh_exit_depth` 模块
在 import 时把全局精度改成了 80 位**——它们是**靠污染才绿的**。
RH-02ah 正在清除那个污染，清完后它们必然红。

**你的新公式天然解决这个问题**：`L_pos` 约 2e14，比 `position_usd`(1e3) 大 11 个数量级，
同样的 feeGrowth 增量下费用从 1e-35 量级变成 1e-4 量级（实测：50 分钟窗口 0.0266 USD），
在 28 位精度下**完全可见**。

因此你改那个测试文件时：

1. **合成样本的 feeGrowth 增量要用真实量级**。参考实测值：
   窗口 2985 秒内 `Δfg0 = 9365277615024075401537929281665916457`、
   `Δfg1 = 21451527583324632536589703137`（这是真实链上数据，可直接用作 fixture）。
   不要再用 `d0=7, d1=3` 这种在任何合理精度下都不可见的增量。
2. 改完后这些测试必须在**默认 28 位精度**下绿（不许靠任何模块的污染，
   也不许自己 pin 精度）。可以用
   `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_first_step_accrual_v1_readonly.py -q -p no:cacheprovider`
   单独跑来验证——**但要先确认 RH-02ah 是否已落地**，
   若 `git diff --stat` 显示 `lp_rh_exit_depth_v1_readonly.py` 仍有未提交改动，
   说明那条线还在跑，此时单独跑的结果不稳定，在报告里注明即可。
3. 如果某条测试的语义在新公式下不再成立
   （例如 `test_large_number_precision_delta_one` 断言"Δ_total=1 时增量等于 1000/2**128"，
   这是**旧公式的性质**），把它改写成新公式下的等价性质，
   并在测试 docstring 里写清"为什么这么改"。**不要删除它。**
