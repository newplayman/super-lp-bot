# RH-02aj：新增 V3 区间仓位的初始两腿推导（纯新文件，不接线）

## 背景（主脑与审计员已确认，不需要你重新验证）

shadow 回放的 HODL 基准目前用的是**虚拟常量** `1 token0 + 1 token1`
（`scripts/lp_rh_shadow_runner_v1_readonly.py:48-50`），在 token0≈2484 USD、
token1≈1 USD 的池子里约合 **2485 USD**，而 LP 仓位是 **1000 USD**。
两者规模差 2.485 倍，`net_pnl` 与 `hodl_delta` 在经济上不可比。

PRD `D04`（`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:69-70`）与 §12.2（同文件 :625-629）
明确要求 HODL 基准使用**头寸实际初始两腿数量**，并明确 50/50 只能作为额外对照。
`scripts/lp_rh_store_v1_readonly.py:98-104` 的 `rh_shadow_positions` 表
**已经预留**了 `initial_token0_raw`、`initial_token1_raw`、`tick_lower`、
`tick_upper`、`virtual_liquidity_raw` 五个列。

**本任务只做「算出两腿数量」这一件事，不接线到 shadow_runner。**
接线是下一个任务（RH-02ak），由主脑另派。

## 你要新建的文件（只有这两个）

1. `scripts/lp_rh_v3_inventory_v1_readonly.py`
2. `tests/test_lp_rh_v3_inventory_v1_readonly.py`

**不许改任何既有文件**——包括 `shadow_runner`、`pnl`、`store`、
`lp_v3_fee_share.py`、任何测试、任何 `.db`、`pool_meta.json`。
这一条是硬闸门：`git status --short` 里出现任何 ` M ` 开头的行就算失败。

## 要实现的函数

```python
def inventory_for_position(*, position_usd, entry_price, range_pct,
                           dec0, dec1, quote_usd_per_token1=None):
    """Return the two legs a v3 range position actually holds at open."""
```

标准 Uniswap V3 库存公式（价格在区间内时）：

```
sqrtP  = sqrt(entry_price)
sqrtPa = sqrt(entry_price * (1 - range_pct/100))
sqrtPb = sqrt(entry_price * (1 + range_pct/100))

amount0_human = L_human * (sqrtPb - sqrtP) / (sqrtP * sqrtPb)
amount1_human = L_human * (sqrtP - sqrtPa)
```

其中 `L_human` 用**人类单位**推导，再按 `10**dec0` / `10**dec1` 转成 raw。
`L_human` 由「两腿 USD 价值之和 == position_usd」这个约束定出：

```
value_usd = amount0_human * entry_price * quote + amount1_human * quote
求 L_human 使 value_usd == position_usd
```

因为两个 amount 都与 `L_human` 成正比，可以先令 `L_human = 1` 算出单位库存的
USD 价值 `unit_value`，再 `L_human = position_usd / unit_value`。

返回一个 dataclass 或 dict，至少含：

```
amount0_raw   (Decimal, 整数值)
amount1_raw   (Decimal, 整数值)
liquidity_raw (Decimal)
reconstructed_usd (Decimal)   # 两腿按 entry_price 折回的 USD 合计
```

### 边界与失败关闭

- `entry_price <= 0`、`position_usd <= 0`、`range_pct <= 0` → 抛
  `ValueError`，消息里点名是哪个参数。**不要返回 0 或默认值静默通过。**
- `quote_usd_per_token1` 为 None 时**抛 ValueError**，不要默认成 1。
  （PRD:651 明确写了 USDG 不许强制按 $1 估值，全局默认 1 正是已确认的缺陷之一。）
- 全部用 `Decimal` 运算。开方用 `Decimal.sqrt()`，**不要用 `math.sqrt`**。
- **不要在模块级调用 `getcontext().prec = N`**——那是本仓库明令禁止的全局精度污染。
  需要更高精度就用 `with localcontext() as ctx: ctx.prec = 60`。

## 验收标准（逐条，全部要过）

1. `reconstructed_usd` 与 `position_usd` 的相对误差 `< 1e-18`。
2. 两腿都为正：区间内开仓时 `amount0_raw > 0` 且 `amount1_raw > 0`。
3. **不是 1:1 raw 常量**：用 `dec0=18, dec1=6, entry_price=2484, range_pct=10,
   position_usd=1000, quote=1` 断言 `amount0_raw != amount1_raw`，
   且 `amount0_raw` 落在 `1e17 ~ 1e18` 量级、`amount1_raw` 落在 `1e8 ~ 1e9` 量级
   （这是主脑按公式手算的预期区间，若你算出来不在其中，**先怀疑自己的公式**，
   不要放宽断言区间来迁就结果）。
4. **不是 50/50，且值已由主脑独立算定**。同一组参数下，
   token0 腿的 USD 占比必须等于：

   ```
   0.4755795077845086
   ```

   断言写成相对容差 `1e-15`。**这个数是主脑用 Decimal 50 位精度独立算出的，
   不是从实现里抄的**；你若算出别的值，先怀疑自己的公式，
   不要改这个断言来迁就结果。

   同一组参数下另外三个已算定的期望值（同样用相对容差 `1e-15` 断言）：

   ```
   liquidity_raw     205043081922807.99205984882428818144653845292934
   amount0_raw       191457128737724882.53936834449842371736793257181
   amount1_raw       524420492.21549139177220903226591548605805549163
   ```

4b. **与既有实现交叉验证**：`scripts/lp_v3_fee_share.py` 的
   `position_liquidity_raw(1000.0, 2484.0, 10.0, 18, 6)` 返回
   `205043081922808.22`（float 实现）。断言你的 `liquidity_raw`
   与它的相对误差 `< 1e-9`。**只 import 它做对照，不许修改那个文件。**
   两条独立路径吻合是本任务最强的正确性证据。
5. 对称性：`range_pct` 越大，同样 `position_usd` 下 `liquidity_raw` 越小。
   用两个 range_pct（5 和 20）断言这个单调关系。
6. 精度不敏感：测试必须在**默认 28 位 Decimal 精度**下通过，
   不许 pin 精度、不许依赖任何模块的 import 副作用。
7. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_v3_inventory_v1_readonly.py -q -p no:cacheprovider`
   全绿，并把原样尾部输出贴进最终报告。
8. `git status --short` 输出里**只有两个 `??` 新文件**，没有任何 ` M ` 行。

## 纪律（违反即退回）

- **不要执行任何 git 命令**（不 add、不 commit、不 stash、不 checkout）。
- 单次 Write/Edit ≤ 150 行或 6000 字符，更大的分次写。
- 不要整读超过 300 行的文件，用 `sed -n 'a,bp'` 读片段。
- 不要重启任何 daemon / 录制器，不要动 crontab，不要发真实网络请求。
- 命令输出只贴尾部。

## 最终报告要写清

- 两个新文件各多少行；
- 验收标准 3 里 `amount0_raw` / `amount1_raw` 的实际值；
- 验收标准 4 里 token0 腿的 USD 占比实际值；
- pytest 原样尾部输出；
- `git status --short` 原样输出。
