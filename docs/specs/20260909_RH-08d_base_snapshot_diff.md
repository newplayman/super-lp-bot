# RH-08d：旧 Base 快照逐闸差分（T56）——证明改动没有悄悄改变判定

## 审计发现

T56 取证：**全仓找不到「旧 Base 模型在同一 SQLite 快照上新旧计算逐闸比对」的实现**。
`旧Base模型` / `旧Base` / `Base模型` 在 `scripts/` 与 `tests/` 中零命中。

用例期望：同一份冻结的 SQLite 快照，**用新旧两套计算跑一遍，逐闸给出差异**。
PRD 的要求是「旧 Base 固定快照可复现」，即**改闸门不得改变对历史数据的判定**，
改变了必须能被看见。

**为什么现在特别需要它**：2026-09-08 夜至 09-09 凌晨这一段，闸门周边改动密集
（netcover 输入、终闸合取项接线、溢价 regime、分辨率闸、gas、储备、空区间）。
**没有这道护栏，就无法证明这些改动没有意外改变对既有数据的结论。**

## 只写两个文件

1. `scripts/lp_rh_snapshot_diff_v1_readonly.py`（≤260 行）

   - `freeze_snapshot(src_db, dst_path) -> dict`
     用 sqlite3 的 `backup()` 把活库一致性快照到 `dst_path`（**源库只读打开**）。
     返回 `{"rows": {表名: 行数}, "sha256", "frozen_at"}`。
     **绝不 VACUUM、绝不修改源库。**
   - `replay_gates(snapshot_db, *, pool, samples, position_usd, capital_usd,
     horizon_hours, pool_meta) -> list[dict]`
     在快照上跑 `lp_rh_shadow_runner_v1_readonly.run_episode`，
     返回每一步的 `{"step_index","sample_time","primary_status","dominant_blocker",
     "terminal_bits"}`。**只读快照，Shadow 写入走临时 store。**
   - `diff_replays(baseline, current) -> dict`
     逐步逐闸比对两次重放：返回
     `{"n_steps","identical","changed_steps":[{"step_index","field","from","to"}],
       "changed_count","status_transitions":{"旧->新": 次数}}`。
     - 步数不一致 → `{"error": "STEP_COUNT_MISMATCH", ...}`，**不要强行对齐**。
     - 完全一致 → `identical is True`，`changed_steps` 为空。
   - `save_baseline(replay, path)` / `load_baseline(path)`
     基线存 JSON，**含 `git_head` 与 `frozen_at`**，让读者知道这份基线是哪个版本产生的。
   - `main()`：`--snapshot --baseline --out [--save-baseline]`。
     **无基线时不报错**，输出 `{"status":"NO_BASELINE","hint":"..."}` 并提示如何生成。

2. `tests/test_lp_rh_snapshot_diff_v1_readonly.py`（≤240 行，**≥14 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   **内存/临时库，不许联网、不许写 `reports/`。** 必测：
   - `freeze_snapshot` 后源库**未被修改**（比对源库 mtime 与行数）。
   - 快照行数与源库一致（逐表断言）。
   - 同一份数据重放两次 → `diff_replays` 的 `identical is True`。
   - 人为改动一步的 `primary_status` → `changed_count == 1`，
     `changed_steps[0]["field"] == "primary_status"`，且 `from`/`to` 正确。
   - 改动 `dominant_blocker` → 同样被检出。
   - 一步里两个字段都变 → `changed_count == 2`（**逐字段计数，不是逐步**）。
   - 步数不一致 → 返回 `STEP_COUNT_MISMATCH`，**不抛异常、不截断对齐**。
   - `status_transitions` 统计正确：三步从 `COMPUTED_FAIL` 变 `INPUTS_UNAVAILABLE`
     → `{"COMPUTED_FAIL->INPUTS_UNAVAILABLE": 3}`。
   - `save_baseline` / `load_baseline` 往返一致，且基线里含 `git_head` 与 `frozen_at`。
   - 无基线时 `main` 返回 0 且输出 `status == "NO_BASELINE"`（**不抛异常**）。
   - `replay_gates` 不写快照库：调用前后快照文件 mtime 不变。
   - 空快照（0 行样本）→ `replay_gates` 返回 `[]`，`diff_replays([], [])` 的
     `identical is True`（**空与空相同，不是错误**）。

## 不许动
不改任何现有脚本。不写 `reports/lp_rh/` 下的活库。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_snapshot_diff_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
