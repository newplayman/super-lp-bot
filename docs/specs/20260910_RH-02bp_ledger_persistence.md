# RH-02bp — 让 Shadow 的账本记录不再蒸发（**默认行为一字不改**）

## 缺陷（已由 codex 定位 + 主脑核实，不要重新调研）

`scripts/lp_rh_shadow_daemon_v1_readonly.py` 的 `run_one_round()`（L227-239）：

```python
with tempfile.TemporaryDirectory() as scratch_dir:
    scratch_conn = open_store(Path(scratch_dir) / "scratch.db")
    migrate(scratch_conn)
    try:
        steps = run_episode(scratch_conn, ...)
        scratch_conn.commit()
    finally:
        scratch_conn.close()
```

`run_episode()` **确实**每步都写这三张表：

- `rh_gate_decisions` — `scripts/lp_rh_shadow_runner_v1_readonly.py:659-667`
- `rh_position_marks` — `scripts/lp_rh_shadow_runner_v1_readonly.py:672-678`
- `rh_bucket_reservations` — `scripts/lp_rh_shadow_runner_v1_readonly.py:527-536`（首次 eligible 时）

但目标是**每轮新建又销毁的临时库**，`with` 块一退出，整轮记录全部蒸发。

实测后果：daemon 跑了 **113 个 episode、4,487 步通过终闸**，
而 `reports/lp_rh/scanner.db` 里这三张表 **0 行**。
只有 `shadow.db` 留下 episode 汇总（`eligible_steps` 这样的一个总数）。

Stage B 要求的 14 天证据（零账差、零漏闸、逐日 NAV、HODL、最差日）
全部依赖这些逐步记录——**这 14 天从来没开始计时过**。

## 本包只做一件事：给 daemon 加一个可选的持久账本库

**默认行为必须一字不变**：不给新参数时，仍然用临时 scratch、仍然销毁。
只有显式给了 `--ledger-db <path>` 才持久化。

这样代码就绪但不生效，是完全可逆的——切换与否是主脑与用户的决定，不是本包的。

### 改 `scripts/lp_rh_shadow_daemon_v1_readonly.py`

1. **CLI 新增** `--ledger-db <path>`（默认 `None`），存进 `cfg["ledger_db"]`。
   帮助文本写明：「持久化每步 gate/mark/reservation 记录到该库；
   不给则沿用每轮临时库（记录不保留）」。

2. `run_one_round()` 改成：

```python
ledger_db = cfg.get("ledger_db")
if ledger_db:
    ledger_conn = open_store(Path(ledger_db))
    migrate(ledger_conn)
    try:
        steps = run_episode(ledger_conn, strategy_episode=episode_id, ...)
        ledger_conn.commit()
    finally:
        ledger_conn.close()
else:
    # 原有分支，一字不改
    with tempfile.TemporaryDirectory() as scratch_dir:
        ...
```

**两个分支传给 `run_episode()` 的参数必须完全一致**，只有 connection 不同。
可以把这段抽成一个小函数避免重复，但不要顺手改 `run_episode` 的签名。

3. **幂等性**：持久库上重复的 `decision_id` 会撞主键。
   `rh_gate_decisions` 的 decision id 不含 episode
   （`scripts/lp_rh_terminal_gate_v1_readonly.py:167-179`），
   而 daemon 每 15 分钟重跑一次、样本窗口**大量重叠**，所以必然重复。

   本包的处理：**捕获这一类主键冲突并计数，不要让整轮崩掉，也不要静默吞掉。**
   在 `run_one_round` 返回的 summary 里加一个字段
   `ledger_duplicate_rows`（整数；未启用持久化时为 `None`）。
   记录到 `rh_shadow_episodes` 需要加列的话，**本包不加列**——
   只把它放进 summary dict 并在 daemon 的日志行里打印出来。

   **不要用 `INSERT OR IGNORE` 掩盖它**：我们需要知道有多少行是重复的，
   这个数字本身是下一个包（决定 decision_id 该怎么带 episode）的输入。

4. `--ledger-db` 指向的路径不可写 / `open_store` 失败时：
   **不要静默退回 scratch 分支**（那是典型的静默假绿），
   而是让异常传播出去、这一轮明确失败并在日志里写清原因。

## 不许动

- **不要改 `scripts/lp_rh_shadow_runner_v1_readonly.py`**——它写得是对的，
  问题在 daemon 给它的 connection。
- 不要改 `scripts/lp_rh_readiness_v1_readonly.py` 或它的测试
  （另一条线正在改，会冲突）。
- 不要改 `scripts/lp_rh_terminal_gate_v1_readonly.py` 的 decision id 生成
  （那是下一个包的事，本包只统计冲突次数）。
- **不要真的去写 `reports/lp_rh/scanner.db`**。测试一律用 `tmp_path` 下的临时库。
- **不要重启、不要 kill 任何正在跑的 daemon 进程**（PID 939215 在跑生产）。
- **不要执行任何 git 命令**（不要 add / commit / checkout / stash）。
- 单次 Write/Edit ≤150 行或 6000 字符。
- 不要整读大文件；用 `grep -n` 定位、`sed -n 'X,Yp'` 读片段。

## 测试（追加到 `tests/test_lp_rh_shadow_daemon_v1_readonly.py`；没有就新建）

全部用 `tmp_path` 下的临时库，不碰 `reports/`。

1. **不给 `--ledger-db` 时行为不变**：跑一轮后，
   进程结束时没有任何新的持久文件被创建（除 daemon 自有的 shadow.db），
   且 summary 里 `ledger_duplicate_rows is None`。
   ——这条保证默认路径零回归。
2. 给了 `--ledger-db <tmp>` 后跑一轮：该文件存在，
   `rh_gate_decisions` 行数 **> 0**，`rh_position_marks` 行数 **> 0**。
   ——这条是本包核心证据。
3. 承 2：同一批样本**再跑一轮**，`ledger_duplicate_rows > 0`，
   且第一轮写进去的行**没有被覆盖或删除**（行数不减少）。
4. `--ledger-db` 指向一个不可写的路径（如 `tmp_path/nonexistent_dir/x.db`
   且父目录不存在）→ 这一轮抛异常或明确返回失败，
   **不会**悄悄退回临时库。
5. 两个分支传给 `run_episode` 的关键参数一致
   （用 monkeypatch 捕获调用参数，比对除 connection 外的每一个 kwarg）。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py -q` 全绿，新增 ≥5 条。
2. `grep -n "ledger_db" scripts/lp_rh_shadow_daemon_v1_readonly.py` 能看到
   CLI 参数、cfg 存取、`run_one_round` 里的分支三处。
3. `grep -n "INSERT OR IGNORE\|except.*pass" scripts/lp_rh_shadow_daemon_v1_readonly.py`
   **不得出现新增的吞异常写法**。
4. 全量 `python3 -m pytest tests/ -q` 通过。
5. `git status --short` 里只有
   `scripts/lp_rh_shadow_daemon_v1_readonly.py` 和
   `tests/test_lp_rh_shadow_daemon_v1_readonly.py` 被改动
   （其它文件的既有改动状态不能被你改变）。
