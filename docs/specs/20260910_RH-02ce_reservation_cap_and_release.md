# RH-02ce — 资金占用上限在 rollback 路径上失效 + reservation 从不释放

## 缺陷一：cap 检查在空库上做（正在生产上发生）

生产实测（`reports/lp_rh/scanner.db`）：

```
rh_bucket_reservations 里 7 条 PENDING，全部 released_at IS NULL
合计 amount_usd = 7000
CORE bucket_active_cap(capital=10000) = 4250
=> 超限 65%，而每一轮仍然 granted
```

在 ledger 上直接算：`reserved_total=7000, cap=4250, room=-2750`，
`try_reserve(1000)` **必然被拒**。但它没被拒，因为判定根本不在 ledger 上做。

因果链（`scripts/lp_rh_shadow_daemon_v1_readonly.py` 的 `_run_episode_persisted`）：

```
rh_economic_evaluations 的 PK 是六元组，不含 episode
  -> daemon 每轮重读重叠样本，跨轮撞该表主键
  -> 整轮 rollback
  -> 在【全新的 scratch 库】上重跑 run_episode
  -> scratch 里 rh_bucket_reservations 是空的，reserved_total=0，room=4250
  -> granted
  -> _copy_new_rows 把这条 reservation 搬进 ledger
```

**bucket active cap 是 PRD §16.3 的风控核心之一，在这条路径上形同虚设。**
任何「读账本历史再做判定」的逻辑都有同样的问题，reservation 是目前唯一一个。

## 缺陷二：reservation 从不释放

`release()` 与 `set_status()` 在 `scripts/lp_rh_bucket_ledger_v1_readonly.py`
里存在，`grep -rn` 全仓库**没有任何生产调用**，只有测试在调。
每个 episode 开一条 PENDING，永不释放，于是无限累积。

Shadow 是反事实模拟：**一轮 episode 结束，那笔虚拟占用就该释放**，
否则修好缺陷一之后，第 5 轮就再也开不了仓（4250 / 1000 = 4.25）。

两个缺陷必须一起修，只修一个都会立刻暴露另一个。

## 要做的事

### 1. scratch 重跑前同步 reservation 状态

`_run_episode_persisted` 在 `migrate(scratch_conn)` 之后、`run_episode` 之前，
把 ledger 的 `rh_bucket_reservations` **整表复制**到 scratch。

这样 scratch 上的 `reserved_total` 与 ledger 一致，cap 检查恢复效力。

- 列名用 `PRAGMA table_info` 动态取，**不要手写**（本会话已有五个 worker 猜错 schema）
- ledger 里没有该表或为空 → 复制 0 行，不报错
- 复制是**只读 ledger、只写 scratch**，不得反向写

在返回的 stats 里加 `reservations_synced: <int>`，daemon 日志行打印出来——
**同步了多少条必须可见**，否则下次失效时同样无声无息。

### 2. episode 结束时释放本轮的 reservation

`run_episode` 正常结束时（`scripts/lp_rh_shadow_runner_v1_readonly.py`），
对本轮 granted 的那条 intent 调用 `release()`。

- intent_id 就是 `try_reserve` 用的那个（搜 `intent_id=f"rh-shadow-{strategy_episode}-{i}"`）
- `reason` 用 `"SHADOW_EPISODE_COMPLETE"`
- `now` 用 episode 最后一步的时间；取不到用 `now_fn()`
- **只在本轮真的 granted 过才释放**（复用已有的 `position_open` / granted 标志，
  不要新增状态变量）
- `release()` 返回 False（找不到该 intent）时**不要静默忽略**，
  在 step reasons 或返回值里留痕

**不要在 except 里释放**：episode 异常中断时，那笔占用应当留下来供人排查，
这与「异常时保留证据」一致。

### 3. 不许动

- 不要改 `bucket_active_cap` 的公式、`RESERVED_STATUSES`、
  `reserved_total` 的 SQL 语义。
- 不要改 `try_reserve` 的 SAVEPOINT 逻辑（`a2f2625` 刚修，正在生效）。
- 不要改 `rh_economic_evaluations` 的主键或表结构
  （消除跨轮冲突是另一个方向，本包不做）。
- **不要清理生产库里已有的 7 条超限 reservation** —— 那是主脑与用户的决定。
- **不要真的写 `reports/lp_rh/scanner.db`**；测试一律用 `tmp_path`。
- **不要重启或 kill 任何进程**（采集器 1168725 / daemon 1569118 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试

### `tests/test_lp_rh_shadow_daemon_v1_readonly.py`

1. ledger 已有 4 条 PENDING × 1000（合计 4000，逼近 cap 4250）→
   走 rollback 路径重跑 → scratch 里 `reserved_total == 4000` →
   本轮 `try_reserve(1000)` **被拒**（room 只剩 250）。
   ——**这条是缺陷一的核心证据**：修复前它会 granted。
2. ledger 为空 → 同步 0 条，本轮正常 granted。
3. stats 里 `reservations_synced` 等于 ledger 里的实际条数。

### `tests/test_lp_rh_shadow_runner_v1_readonly.py`

4. 有 granted 步的 episode 正常结束 → 该 intent 的 `status` / `released_at`
   反映已释放（按 `release()` 的实际语义断言，先读它的实现确认写的是哪个字段）。
5. 无 granted 步的 episode → 不调用 release，`rh_bucket_reservations` 仍为 0 行。
6. 连跑两个 episode（各自 granted 并释放）→ 第二轮的 `reserved_total`
   **不包含**第一轮已释放的那条，两轮都能 granted。
   ——**这条是缺陷二的核心证据**：不释放的话第二轮 room 会少 1000。
7. `release()` 返回 False 时留痕（构造一个 intent 不存在的场景）。

每条 docstring 写清它防的是什么回归。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py tests/test_lp_rh_shadow_runner_v1_readonly.py -q`
   全绿，新增 ≥7 条。
2. 全量 `python3 -m pytest tests/ -q` 通过。
3. `grep -n "reservations_synced" scripts/lp_rh_shadow_daemon_v1_readonly.py` 有输出。
4. `grep -n "release(" scripts/lp_rh_shadow_runner_v1_readonly.py` 有生产调用。
5. `git status --short` 里只有那三个文件（daemon / runner 及其测试）被改动，
   `reports/lp_rh/scanner.db` **未被修改**。
