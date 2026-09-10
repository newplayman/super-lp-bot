# RH-02bz — 让 `decision_id` 能带上 episode（消除跨轮主键冲突的第一半）

## 背景（实测数字，不用重新验证）

`scripts/lp_rh_terminal_gate_v1_readonly.py`（约 L168）：

```python
candidate_key = str(record.get("candidate_key") or record.get("pool_key") or "unknown")
return GateDecision(
    decision_id=f"rh-terminal-{candidate_key}-{target_mode}",
    ...
```

`candidate_key` 形如 `0x52e6...71ca@2026-09-10T03:53:40.144738Z`（含 sample_time），
所以同一轮内不会自撞。但 daemon 每 15 分钟重跑一次、**样本窗口大量重叠**，
于是跨轮必然撞 `rh_gate_decisions` 的主键。

commit `330ab3e` 的实测：第二轮同样本重跑，`ledger_duplicate_rows=199`。
当前的应对是「撞了就 rollback、换临时库重跑整轮、只把新行拷回去」——
**正确但每次要算两遍**。根治办法是让 `decision_id` 带上 episode。

## 本包只做一半

改 `scripts/lp_rh_terminal_gate_v1_readonly.py`，让它**能**带 episode；
**不改 runner**（那是下一包，`_terminal_record` 要把 episode 放进 record）。
两包分开是因为 runner 正被另一条线改，并发会冲突。

### 做法：向后兼容的可选键

`evaluate_terminal_gate` 从 record 里多读一个可选键 `strategy_episode`：

```python
episode = record.get("strategy_episode")
if episode:
    decision_id = f"rh-terminal-{episode}-{candidate_key}-{target_mode}"
else:
    decision_id = f"rh-terminal-{candidate_key}-{target_mode}"   # 现状，一字不改
```

**record 里没有这个键时，decision_id 必须与现在逐字相同。**
这一点由测试钉死（见下面第 1 条）——否则本包会静默改变所有既有行为。

`episode` 值里若含 `-` 不需要转义（decision_id 只作主键，不做反解析），
但要 `str()` 并 `strip()`，空串按「没有」处理。

## 不许动

- **不要改 `GateDecision` 的其它字段**，不要动 `candidate_key` 的取法、
  `primary_status` / `terminal_bits` / `dominant_blocker` / `reasons` /
  `snapshot_ids` / `decided_at` / `simulated_policy_only` 的任何逻辑。
- **不要改 `scripts/lp_rh_shadow_runner_v1_readonly.py`**——另一条线正在改它，
  改了必然冲突。本包只准备能力，接线是下一包。
- 不要改 `CONJUNCT_ORDER` 或终闸十项的判定。
- 不要碰 `scripts/lp_rh_readiness_v1_readonly.py`、
  `scripts/lp_rh_pool_attestation_backfill_v1.py`（工作区有别的线的改动，
  那不是你改错了）。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（追加到 `tests/test_lp_rh_terminal_gate_v1_readonly.py`）

1. **record 里没有 `strategy_episode` → `decision_id` 与现状逐字相同**
   （断言等于字面量 `f"rh-terminal-{candidate_key}-{target_mode}"`）。
   **这条是本包最重要的一条：证明默认行为零改变。**
2. record 里有 `strategy_episode="ep-1"` → `decision_id` 以
   `rh-terminal-ep-1-` 开头，且仍以 `-{target_mode}` 结尾。
3. 同一个 `candidate_key`、两个不同 episode → 两个 `decision_id` **不相等**。
   ——这条是本包的目的：跨轮不再撞主键。
4. 同一个 episode、同一个 candidate_key → `decision_id` **相等**
   （幂等性没被破坏：同一轮内重复评估仍应得到同一个 id）。
5. `strategy_episode=""`（空串）→ 按「没有」处理，走现状分支。
6. `strategy_episode=None` → 同上。

每条 docstring 写清它防的是什么回归。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_terminal_gate_v1_readonly.py -q` 全绿，新增 ≥6 条。
2. **全量 `python3 -m pytest tests/ -q` 通过**——尤其
   `tests/test_lp_rh_shadow_runner_v1_readonly.py` 不得出现新失败
   （它有断言依赖 decision_id 的现状格式；没有 episode 时格式不变，
   所以本该全绿。若它挂了，说明你改动了默认分支）。
3. `git status --short` 里只有
   `scripts/lp_rh_terminal_gate_v1_readonly.py` 和
   `tests/test_lp_rh_terminal_gate_v1_readonly.py` 被改动。
