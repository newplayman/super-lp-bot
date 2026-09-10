# RH-02bu — 把虚拟开仓落进 `rh_shadow_positions`

## 背景

commit `330ab3e` 让 daemon 能把每步记录持久化（`--ledger-db`），
`rh_gate_decisions` / `rh_position_marks` / `rh_economic_evaluations`
三张表已经在写。实测一轮 200 个样本各落 200 行。

但 `rh_shadow_positions` **仍然 0 行——它根本没有 writer**。
runner 只在内存里维护 `position_open` 布尔量
（`scripts/lp_rh_shadow_runner_v1_readonly.py`，搜 `position_open`）。

后果（依据 `reports/AUDIT_shadow_ledger_writer_gap_20260910.md`）：
PRD Stage B 要求的 **HODL 对比**必须用「实际的初始两腿数量」
（PRD §D04，L625-629：不得按 50/50 假设）。没有这张表，
就无法证明某个 episode 开仓时到底持有多少 token0 / token1，
最差日、持仓生命周期、资产不变量也都缺原始依据。

## 唯一任务：首次开仓成功时写一行

### 写入时机

runner 主循环里，`try_reserve` 返回 `granted` 为真、
`position_open` 由 False 变 True 的**那一步**（每个 episode 至多一次）。
搜 `granted = bool(res.get("granted"))` 定位。

### 表结构（已核实，照抄）

```sql
CREATE TABLE rh_shadow_positions (
    strategy_episode TEXT NOT NULL,
    position_id TEXT NOT NULL,
    pool_key TEXT NOT NULL,
    profile TEXT NOT NULL,
    bucket TEXT NOT NULL,
    initial_token0_raw TEXT,
    initial_token1_raw TEXT,
    tick_lower INTEGER,
    tick_upper INTEGER,
    virtual_liquidity_raw TEXT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    PRIMARY KEY (strategy_episode, position_id)
)
```

### 字段来源

- `strategy_episode` ← 函数参数 `strategy_episode`
- `position_id` ← `f"rh-shadow-{strategy_episode}"`
  （**必须与 `rh_position_marks` 写入时用的 position_id 完全一致**，
  否则两张表对不上；去 `insert_row(conn, "rh_position_marks", ...)` 那里抄）
- `pool_key` ← `pool_meta` 里的池标识；没有现成键就用
  `sample.get("asset_address")`。**取不到就不要编**，见下面的 fail-close。
- `profile` ← `"CORE"`（当前只跑 CORE 池），`bucket` ← `"CORE"`
  （与 `try_reserve(bucket="CORE")` 一致）
- `opened_at` ← 该步的 `decision_now`（与同步写入的 gate 行 `decided_at` 一致）
- `closed_at` ← `None`（本包不做平仓，episode 结束不等于平仓）
- `initial_token0_raw` / `initial_token1_raw` / `virtual_liquidity_raw`
  ← 来自 `inventory_for_position(...)` 的返回值。

  **先确认它到底返回什么**，不要猜：
  ```bash
  grep -n "def inventory_for_position" -A 30 scripts/lp_rh_v3_inventory_v1_readonly.py
  grep -n "class V3Inventory" -A 15 scripts/lp_rh_v3_inventory_v1_readonly.py
  grep -n "inventory_for_position\|amount0_human\|amount1_human" scripts/lp_rh_shadow_runner_v1_readonly.py | head
  ```
  runner 主循环里已经算过 inventory（HODL 用的就是它），**直接复用那个结果，
  不要重算**——重算一次就多一个可能与 NAV 不一致的数字来源。

  注意 `_raw` 后缀：存的是**链上原始整数**（字符串形式），
  不是除过 decimals 的人类可读值。如果手上只有 human 值，
  乘回 `10 ** dec0` / `10 ** dec1`，并用 `str()` 存整数字符串。
- `tick_lower` / `tick_upper` ← 若 inventory 结果里有就用；
  **没有就存 `None`**，不要自己从 range_pct 反推一个出来。

### 三条硬性语义

1. **拿不到 `pool_key` 就不写这一行**（它是 NOT NULL），
   并在该步的 reasons 里记一条原因。**绝不用空串或占位符顶替。**
2. **每个 episode 至多写一行。** 用已有的 `position_open` 标志保证，
   不要引入新的状态变量。
3. **不要捕获 `sqlite3.IntegrityError`。** 跨轮重跑的主键冲突要交给
   daemon 层处理（`_run_episode_persisted`，commit `330ab3e`），
   与 `rh_economic_evaluations` 的做法保持一致。

## 不许动

- 不要改 NAV / HODL / fee 的任何计算，也不要改 `inventory_for_position`
  ——今晚刚与独立参考实现对齐到 1e-26。
- 不要改 `rh_gate_decisions` / `rh_position_marks` / `rh_economic_evaluations`
  三个已有 writer 的任何字段。
- 不要改 `scripts/lp_rh_shadow_daemon_v1_readonly.py`。
- 不要改 `scripts/lp_rh_readiness_v1_readonly.py`（另一条线刚改完，待验收）。
- 不要改 `scripts/lp_silent_failure_lint_v1_readonly.py`（另一条线正在改）。
- **不要真的写 `reports/lp_rh/scanner.db`**；测试用内存库或 `tmp_path`。
- **不要重启、不要 kill 任何 daemon 进程。**
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。
- 不要整读这个 900+ 行的文件；`grep -n` 定位后 `sed -n` 读片段。

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

复用该文件已有的 fixture 风格（`_conj_meta()` / `_conj()` / episode 相关 helper）。

1. 跑一个**有 eligible step** 的 episode → `rh_shadow_positions` 恰好 **1 行**。
   （构造样本时注意：非 RTH 时段会被 `market_and_chain_risk_pass` 拦掉，
   `now` 要落在纽约 RTH 内，参考已有测试怎么设 `now=`。）
2. 承 1：该行的 `position_id` 与 `rh_position_marks` 里的 `position_id` **相等**。
   ——这条保证两表能 join。
3. 承 1：`initial_token0_raw` 与 `initial_token1_raw` **都不是 None、都不是 "0"**，
   且与该步 inventory 的值一致（乘过 decimals 的整数字符串）。
4. 跑一个**全程没有 eligible step** 的 episode → `rh_shadow_positions` **0 行**。
5. 多个 eligible step 的 episode → 仍然只有 **1 行**（不重复开仓）。
6. `pool_key` 取不到时 → **不写行**，且 episode 不崩、其它表照常写。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥6 条。
2. `grep -n "rh_shadow_positions" scripts/lp_rh_shadow_runner_v1_readonly.py`
   能看到 `insert_row` 调用。
3. `grep -n "IntegrityError" scripts/lp_rh_shadow_runner_v1_readonly.py` **无输出**。
4. 全量 `python3 -m pytest tests/ -q` 通过。
5. `git status --short` 里只有
   `scripts/lp_rh_shadow_runner_v1_readonly.py` 和
   `tests/test_lp_rh_shadow_runner_v1_readonly.py` 被改动。
