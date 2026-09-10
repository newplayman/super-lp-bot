# RH-02cc — 补齐 mark 的四个空字段 + 把 episode 接进 decision_id

两件事都在 `scripts/lp_rh_shadow_runner_v1_readonly.py`，一起做，避免两包争同一文件。

## 事实（主脑已在生产库上核实，不用重新调研）

### A. `rh_position_marks` 四个列 2378 行全空

```
price_snapshot_id      非空    0/2378
reference_nav          非空 2328/2378
liquidation_nav        非空    0/2378
accrued_fee            非空 2328/2378
unvalued_risk_json     非空 2378/2378
derived_block_hash     非空    0/2378
derived_block_number   非空    0/2378
```

写入处（约 L758）直接把三个写死成 `None`，第四、五个列根本没出现在 dict 里：

```python
insert_row(conn, "rh_position_marks", {
    "position_id": f"rh-shadow-{strategy_episode}",
    "mark_time": sample_time if sample_time is not None else now_fn(),
    "price_snapshot_id": None, "reference_nav": nav, "liquidation_nav": None,
    "accrued_fee": accrued if nav is not None else None,
    "unvalued_risk_json": json.dumps(risk_data, sort_keys=True),
})
```

PRD Stage B 的「实际全成本退出 / 最差日 / 不确定性」都要按区块和价格快照回溯
这些 mark，全空就回溯不了（依据 `reports/AUDIT_shadow_ledger_writer_gap_20260910.md`）。

### B. `decision_id` 仍不含 episode

commit `b15ff05` 让 `evaluate_terminal_gate` **能**读 `record["strategy_episode"]`，
但 `_terminal_record()`（约 L90-112）没有把它放进 record，所以能力没生效。

后果实测：daemon 每轮重读重叠样本，跨轮撞 `rh_gate_decisions` 主键，
走 rollback + scratch 重跑路径，**每轮把整个 episode 算两遍**：

```
round 1  ledger_duplicate_rows=137
round 2  ledger_duplicate_rows=140
round 3  ledger_duplicate_rows=184
```

## 要做的事

### 1. `price_snapshot_id` / `derived_block_hash` / `derived_block_number`

三者都从**当前 sample** 取，样本里已有同名字段
（`rh_market_states` 的列：`source_payload_hash`、`derived_block_hash`、
`derived_block_number`）：

```python
"price_snapshot_id":    sample.get("source_payload_hash"),
"derived_block_hash":   sample.get("derived_block_hash"),
"derived_block_number": sample.get("derived_block_number"),
```

**取不到就写 `None`**（保持现状），不要编造、不要用池地址或 mark_time 顶替。
`price_snapshot_id` 与 `rh_economic_evaluations.snapshot_id` 用的是同一个
`source_payload_hash`，这样两张表能按快照 join——这正是本节的目的。

### 2. `liquidation_nav`

**本包不计算它**，但要把「为什么是 None」记下来。

`reference_nav` 是按参考价估的 NAV；`liquidation_nav` 是按**实际退出深度**
折算后的 NAV，需要 `exit_depth_for_size` 的结果。runner 在
`position_and_exit_depth_pass` 那里算过 `depth`（搜 `exit_depth_for_size`），
但那是**开仓准入判定**，不是逐步的退出估值，两者不能混用。

所以：在 `unvalued_risk_json` 里加一个键说明它为何缺失，例如

```python
risk_data["liquidation_nav_reason"] = "NOT_COMPUTED:EXIT_DEPTH_PER_STEP_NOT_WIRED"
```

**不要为了填上这一列而拿准入判定的 depth 顶替**——那会让一个未实现的
估值看起来像已实现，正是本仓库 27 例「静默假绿」的形状。

### 3. `_terminal_record` 传 episode

`_terminal_record` 现在的签名（L90）没有 episode。加一个关键字参数：

```python
def _terminal_record(sample, gated, step_index, *, pool_meta=None,
                     capital_usd=None, position_usd=None, now=None,
                     conjunct_reasons=None, strategy_episode=None) -> dict:
```

并在 `rec["candidate_key"] = ...` 附近加：

```python
if strategy_episode:
    rec["strategy_episode"] = strategy_episode
```

调用处（搜 `_terminal_record(` 在主循环里那一处）传入 `strategy_episode=strategy_episode`。

**`strategy_episode` 为空/None 时不要放进 record**，这样 `decision_id`
退回旧格式——`b15ff05` 的第一条测试钉的就是这个向后兼容。

## 不许动

- 不要改 NAV / HODL / fee / inventory 的任何计算。
- 不要改 `evaluate_terminal_gate`（`scripts/lp_rh_terminal_gate_v1_readonly.py`）
  ——它已经在 `b15ff05` 里改好了，本包只是把数据喂给它。
- 不要改其它四个 writer 的字段。
- 不要碰 `scripts/lp_rh_shadow_daemon_v1_readonly.py`、
  `scripts/lp_rh_collector_v1_readonly.py`。
- **不要真的写 `reports/lp_rh/scanner.db`**；测试用内存库或 `tmp_path`。
- **不要重启或 kill 任何进程**（采集器 1168725 / daemon 1221417 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## `rh_position_marks` 真实列（照抄，本会话已有五个 worker 猜错 schema）

```
NOT NULL: position_id, mark_time
全部    : position_id, mark_time, price_snapshot_id, reference_nav,
          liquidation_nav, accrued_fee, unvalued_risk_json,
          derived_block_hash, derived_block_number
```

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

1. 样本带 `source_payload_hash` / `derived_block_hash` / `derived_block_number`
   → mark 行的对应三列**等于样本里的值**（逐字）。
2. 样本缺这三个字段 → 三列都是 `None`，episode 不崩。
3. mark 的 `price_snapshot_id` 与同一步 `rh_economic_evaluations.snapshot_id`
   **相等** —— 证明两表可按快照 join。
4. `unvalued_risk_json` 里含 `liquidation_nav_reason`，
   且 `liquidation_nav` 仍是 `None`。
5. `_terminal_record(..., strategy_episode="ep-x")` → 返回的 record 含
   `strategy_episode == "ep-x"`。
6. `_terminal_record(...)` 不传该参数 → record **不含** `strategy_episode` 键。
7. 端到端：同一批样本跑**两个不同 episode** →
   `rh_gate_decisions` 行数是两倍（decision_id 因 episode 不同而不冲突），
   且无重复 decision_id。
   ——这条是 B 的核心证据：跨轮不再撞主键。
8. 既有行为零回归：该文件现有测试全绿。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥7 条。
2. 全量 `python3 -m pytest tests/ -q` 通过。
3. `grep -n '"liquidation_nav": None' scripts/lp_rh_shadow_runner_v1_readonly.py`
   仍有输出（这一列**故意**保持 None），且附近能看到 `liquidation_nav_reason`。
4. `git status --short` 里只有
   `scripts/lp_rh_shadow_runner_v1_readonly.py` 和
   `tests/test_lp_rh_shadow_runner_v1_readonly.py` 被改动。
