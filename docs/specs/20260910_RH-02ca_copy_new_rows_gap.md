# RH-02ca — 账本 rollback 路径漏了三张表（正在生产上丢数据）

## 缺陷（主脑已在生产库上确认，不要重新调研）

`scripts/lp_rh_shadow_daemon_v1_readonly.py` 的 `_copy_new_rows()` 只搬三张表：

```
rh_gate_decisions        （按 existing_decision_ids 去重）
rh_position_marks        （无条件 INSERT，不去重）
rh_bucket_reservations
```

**缺 `rh_economic_evaluations`、`rh_shadow_positions`、`rh_journal`。**

原因是时序：`_copy_new_rows` 随 commit `330ab3e` 落地，
而这三张表的 writer 是之后才加的（`330ab3e` 的 bq、`f1ab502` 的 bu、`4af0aba` 的 by），
搬运函数没跟上。

`_run_episode_persisted` 的流程是：直接写 ledger → 撞主键 → **整轮 rollback** →
用 scratch 重跑 → `_copy_new_rows` 把新行搬回去。
所以**凡是不在 `_copy_new_rows` 里的表，从第二轮起就永远不再增长**。

生产实测（daemon 已切到 `--ledger-db scanner.db`，跑了两轮）：

```
rh_gate_decisions        241   （241 个不同 decision_id，去重生效）
rh_position_marks        378   （只有 241 个不同 mark_time -> 137 个时刻重复记录）
rh_economic_evaluations  181   （= 第一轮的量；第二轮一条都没进来）
rh_shadow_positions        0   （当前 OVERNIGHT 无 granted step，但一旦有也会丢）
rh_journal                 0   （同上）

两个 episode: ...064033-0 写了 181 marks, ...065533-1 写了 197 marks
```

后果有两层：
1. **economic / positions / journal 从第二轮起停止积累** —— Stage B 的全成本、
   HODL、账差证据都断了
2. **marks 重复** —— 同一时刻多行 NAV，逐日序列和最差日统计会被污染

## 要做的事

只改 `scripts/lp_rh_shadow_daemon_v1_readonly.py`。

### 1. `_copy_new_rows` 补齐三张表

按各表主键去重，**不要用 `INSERT OR IGNORE`**（那会掩盖搬了多少、漏了多少）。
先查 ledger 里已有的主键集合，再逐行判断。

各表主键（已核实，照抄）：

```
rh_economic_evaluations  PK (candidate_key, snapshot_id, model_version,
                             policy_version, horizon_hours, position_usd)
rh_shadow_positions      PK (strategy_episode, position_id)
rh_journal               PK (event_id)
rh_position_marks        PK (position_id, mark_time)
rh_gate_decisions        PK (decision_id)
rh_bucket_reservations   PK (intent_id)
```

列名用 `PRAGMA table_info(<表>)` 动态取，**不要手写列清单**——
本会话已有四个 worker 手写列名出错。取到列名后用
`INSERT INTO t (<cols>) VALUES (<?,...>)` 拼。

### 2. `rh_position_marks` 也要去重

现在它无条件 INSERT。改成与其它表一致：按 `(position_id, mark_time)` 判重。

（注：`position_id` 含 episode，所以跨轮本不该撞；重复来自
**同一轮内 rollback 后重跑**，scratch 里的行与 ledger 里第一次写进去的行
主键相同却没被拦住。去重后这一类重复消失。）

### 3. 返回搬运统计

`_copy_new_rows` 改为返回 dict：

```python
{"rh_gate_decisions": {"copied": n, "skipped_existing": n}, ...}
```

`_run_episode_persisted` 把它并进返回值，`run_one_round` 放进 summary，
daemon 日志行里打印总计，形如：

```
[rh-shadow-daemon] rh-shadow-...: ledger_duplicate_rows=199 copied={gate:60, marks:60, econ:60, ...}
```

**不要因此改 `rh_shadow_episodes` 的表结构**（不加列）。

### 4. 防复发：一条元测试

新增一条测试，从 runner 源码里提取所有 `insert_row(conn, "rh_xxx"` 的表名，
与 `_copy_new_rows` 实际处理的表名集合比对，**两者必须相等**。

实现思路（用正则扫源码即可，不要 import runner 后反射）：

```python
import re, pathlib
src = pathlib.Path("scripts/lp_rh_shadow_runner_v1_readonly.py").read_text()
written = set(re.findall(r'insert_row\(\s*conn\s*,\s*"(rh_\w+)"', src))
# book_journal_event 走的是 rh_journal，单独加上
written.add("rh_journal")
```

`_copy_new_rows` 处理的表名请做成模块级常量
`_LEDGER_TABLES = (...)`，测试直接 import 它来比对。

**这条测试是本包最重要的产出**：它保证下次再加 writer 时，
如果忘了同步搬运函数，测试会红。

## 不许动

- 不要改 `run_episode` 或 `scripts/lp_rh_shadow_runner_v1_readonly.py` 的任何逻辑。
- 不要改 `_run_episode_persisted` 的整体策略（先直写、撞了 rollback、
  scratch 重跑、搬新行）——只补它搬运的表和统计。
- 不要改 `rh_shadow_episodes` 的表结构。
- 不要用 `INSERT OR IGNORE` 或 `except sqlite3.IntegrityError: pass`。
- **不要真的写 `reports/lp_rh/scanner.db`**；测试一律用 `tmp_path`。
- **不要重启或 kill 任何 daemon / collector 进程**（PID 1192666 / 1168725 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（追加到 `tests/test_lp_rh_shadow_daemon_v1_readonly.py`）

用 `tmp_path`，不碰 `reports/`。

1. **元测试**（见上）：runner 写入的表名集合 == `_LEDGER_TABLES`。
2. 同一批样本连跑两轮 → `rh_economic_evaluations` 的行数**大于第一轮**
   （第二轮的新样本进来了），且**没有重复的主键六元组**。
   ——这条直接对应生产上观察到的 181 卡住不动。
3. 同一批样本连跑两轮 → `rh_position_marks` 里
   `count(*) == count(distinct (position_id, mark_time))`。
   ——这条对应 378 行只有 241 个不同 mark_time。
4. 两轮之后 `rh_gate_decisions` 行数 == 不同 decision_id 数（现状不得回归）。
5. `_copy_new_rows` 的返回统计里，每张表的 `copied + skipped_existing`
   等于 scratch 里该表的行数。
6. 有 granted step 的两轮 → `rh_shadow_positions` 每个 episode 恰好 1 行，
   `rh_journal` 每个 episode 恰好 2 行，第二轮不丢。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py -q` 全绿，新增 ≥6 条。
2. 全量 `python3 -m pytest tests/ -q` 通过。
3. `grep -n "INSERT OR IGNORE" scripts/lp_rh_shadow_daemon_v1_readonly.py` **无输出**。
4. `git status --short` 里只有
   `scripts/lp_rh_shadow_daemon_v1_readonly.py` 和
   `tests/test_lp_rh_shadow_daemon_v1_readonly.py` 被改动
   （`reports/lp_rh/pool_meta.json` 有主脑的未提交改动，不要碰）。
