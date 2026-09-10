# RH-02bu-2 — 把虚拟开仓落进 `rh_shadow_positions`（重派：上一轮 spec 结构没交代清楚）

## 上一轮为什么没做出来（不是 worker 的错）

RH-02bu 的 worker 跑了 18 分钟、50 个 turn、**零 Write**。它在找一个
「开仓时可用的 `initial_token0_raw`」——而那东西在开仓点上**根本不存在**。
主脑的 spec 没说清 runner 的结构。本轮把结构直接给出，不要再自己摸索。

## runner 里的两个事件是分开的（关键）

```python
# 事件 A：reservation 获批 —— 约 L550
granted = False
if eligible and not position_open:
    res = try_reserve(conn, intent_id=f"rh-shadow-{strategy_episode}-{i}", ...)
    granted = bool(res.get("granted"))
    if granted:
        position_open = True

# ...中间还有几十行...

# 事件 B：库存解析 —— 约 L589-628，整个 episode 只跑一次
if not open_resolved and price is not None and price > 0:
    open_resolved = True
    ...
    inv = inventory_for_position(position_usd=p_usd, entry_price=price,
                                 range_pct=r_pct, dec0=d0, dec1=d1,
                                 quote_usd_per_token1=step_quote_val)
    amount0_human = inv.amount0_human
    amount1_human = inv.amount1_human
    liquidity_human = inv.liquidity_raw / scale
    l_pos = inv.liquidity_raw
    open_valid = True
```

**A 在源码里靠前，B 在后**，而且两者通常落在**不同的迭代**上：
B 只要有价格就在第 1 步完成，A 要等终闸放行（只在纽约 RTH 时段可能发生）。
所以在 A 那一行是拿不到 `inv` 的——这就是上一轮卡住的原因。

`V3Inventory` 的字段（`scripts/lp_rh_v3_inventory_v1_readonly.py:8-15`，照抄）：

```python
amount0_raw, amount1_raw, liquidity_raw, reconstructed_usd,
amount0_human, amount1_human
```

`amount0_raw` / `amount1_raw` / `liquidity_raw` **正是表要的三个 `_raw` 字段**，
已经是链上原始量纲，**不需要再乘 10**decimals**。

## 做法：循环末尾写，用一个标志

1. 在循环外（`position_open` 那些变量旁边）加
   `position_row_written = False` 和 `pending_position_open_at = None`。
2. 事件 A 里 `if granted:` 分支中，除了 `position_open = True`，
   再加 `pending_position_open_at = decision_now`。
   **不要在这里写库**。
3. 在**循环体的最末尾**（`steps.append(ShadowStep(...))` 之前或之后都行，
   但必须在事件 B 的 inventory 块之后）：

```python
if (pending_position_open_at is not None and not position_row_written
        and open_valid and inv_cached is not None):
    pool_key = <见下>
    if pool_key:
        insert_row(conn, "rh_shadow_positions", {...})
        position_row_written = True
    else:
        step_reasons.append("SHADOW_POSITION_NOT_RECORDED:NO_POOL_KEY")
```

`inv_cached`：事件 B 里 `inv` 是局部变量，出了那个 `if` 就没了。
在循环外加一个 `inv_cached = None`，事件 B 里 `open_valid = True` 之后
加一行 `inv_cached = inv`。**不要重算 inventory**——重算一次就多一个
可能与 NAV/HODL 不一致的数字来源。

## 字段映射

| 列 | 值 |
|---|---|
| `strategy_episode` | 函数参数 `strategy_episode` |
| `position_id` | `f"rh-shadow-{strategy_episode}"`（**去 `rh_position_marks` 的 insert 处抄，必须一致**） |
| `pool_key` | `pool_meta.get("pool_address") or pool_meta.get("pool_key") or sample.get("asset_address")`；三个都拿不到就**不写行** |
| `profile` | `"CORE"` |
| `bucket` | `"CORE"`（与 `try_reserve(bucket="CORE")` 一致） |
| `initial_token0_raw` | `str(inv_cached.amount0_raw)` |
| `initial_token1_raw` | `str(inv_cached.amount1_raw)` |
| `virtual_liquidity_raw` | `str(inv_cached.liquidity_raw)` |
| `tick_lower` / `tick_upper` | `None`（`V3Inventory` 里没有；**不要自己从 range_pct 反推**） |
| `opened_at` | `pending_position_open_at`（获批那一步的时刻） |
| `closed_at` | `None`（本包不做平仓） |

**语义说明，写进代码注释**：数量取自库存解析步（episode 的建仓假设，
HODL 基准用的也是它），`opened_at` 取自 reservation 获批步。两者可能不同步，
这是当前经济模型的既有形态，本包只如实记录，不改模型。

`_raw` 是 Decimal，可能带小数（如 `191457128737724882.5`）。
`str()` 直接存，**不要 int() 截断**——截断会让它与 NAV 用的值对不上。

## 三条硬性语义

1. 拿不到 `pool_key` 就**不写这一行**（NOT NULL），并在 step reasons 里记原因。
   **绝不用空串或占位符顶替。**
2. 每个 episode 至多一行（`position_row_written` 保证）。
3. **不要捕获 `sqlite3.IntegrityError`**——跨轮重跑的主键冲突交给 daemon 层
   （`_run_episode_persisted`，commit `330ab3e`），与 `rh_economic_evaluations` 一致。

## 不许动

- 不要改 NAV / HODL / fee 计算，不要改 `inventory_for_position`。
- 不要改已有三个 writer（gate_decisions / position_marks / economic_evaluations）的字段。
- 不要碰 `scripts/lp_rh_shadow_daemon_v1_readonly.py`、
  `scripts/lp_rh_readiness_v1_readonly.py`、
  `scripts/lp_silent_failure_lint_v1_readonly.py`。
- **不要真的写 `reports/lp_rh/scanner.db`**；测试用内存库或 `tmp_path`。
- **不要重启或 kill 任何 daemon 进程。**
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。
- **不要再花轮次去"先搞清楚 X"**——上面已经把结构、字段名、变量名全给了。
  读一遍 `sed -n '540,700p' scripts/lp_rh_shadow_runner_v1_readonly.py` 就够，
  然后直接动手。

## 表结构（已核实，照抄）

```
rh_shadow_positions
  NOT NULL: strategy_episode, position_id, pool_key, profile, bucket, opened_at
  全部    : strategy_episode, position_id, pool_key, profile, bucket,
            initial_token0_raw, initial_token1_raw, tick_lower, tick_upper,
            virtual_liquidity_raw, opened_at, closed_at
  PK      : (strategy_episode, position_id)
```

`insert_row()` 会**静默丢弃**表里没有的列名——本会话已有三个 worker 猜错
schema，只在很久之后以 NOT NULL 失败的形式露头。照抄上面的列名。

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

复用该文件已有的 fixture 与 episode helper（`grep -n "def test_.*episode" ` 找样板）。

1. 一个**有 granted 步**的 episode → `rh_shadow_positions` 恰好 **1 行**。
   注意样本的 `now` 要落在纽约 RTH 内，否则 `market_and_chain_risk_pass`
   会拦掉所有步（参考已有测试怎么设时间）。
2. 承 1：该行 `position_id` 与 `rh_position_marks` 的 `position_id` **相等**。
3. 承 1：`initial_token0_raw` / `initial_token1_raw` / `virtual_liquidity_raw`
   三者都不是 None、不是 `"0"`，且与该 episode 的 `inv.amount0_raw` 等**逐字相等**。
4. **没有任何 granted 步**的 episode → `rh_shadow_positions` **0 行**
   （其它三张表照常有行）。
5. 多个 eligible 步 → 仍然只有 **1 行**。
6. `pool_meta` 与 sample 都没有池标识时 → **不写行**，episode 不崩，
   step reasons 里能找到 `NO_POOL_KEY`。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥6 条。
2. `grep -n "rh_shadow_positions" scripts/lp_rh_shadow_runner_v1_readonly.py`
   能看到 `insert_row` 调用。
3. `grep -n "IntegrityError" scripts/lp_rh_shadow_runner_v1_readonly.py` **无输出**。
4. 全量 `python3 -m pytest tests/ -q` 通过。
5. `git status --short` 里只有
   `scripts/lp_rh_shadow_runner_v1_readonly.py` 和
   `tests/test_lp_rh_shadow_runner_v1_readonly.py` 被改动
   （`scripts/lp_silent_failure_lint_v1_readonly.py` 已有的改动是另一条线的，
   不要碰它，也不要因为它存在而以为自己改错了）。
