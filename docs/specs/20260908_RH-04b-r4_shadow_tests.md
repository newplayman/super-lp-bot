# RH-04b 第四轮：只补 Shadow Runner 的测试

`scripts/lp_rh_shadow_runner_v1_readonly.py` 已完整可导入（语法自检通过），但第三轮 worker 撞回合上限（81 turns）没写测试。**本轮只写测试文件，脚本一行不许改。**

## 真实签名（主脑已核实，直接用，不要再花回合调研）
```python
run_episode(conn, *, strategy_episode, samples, position_usd, horizon_hours,
            capital_usd, target_mode, now_fn) -> list[ShadowStep]
load_samples_from_db(conn, *, pool: str, limit: int) -> tuple[list[dict], int]   # (samples, skipped)
episode_summary(steps, *, load_skipped: int = 0) -> dict
class ShadowStep  # 见 scripts/lp_rh_shadow_runner_v1_readonly.py:44
```
先 `sed -n '44,58p' scripts/lp_rh_shadow_runner_v1_readonly.py` 读 `ShadowStep` 字段名，再写断言。

## 只新建一个文件
`tests/test_lp_rh_shadow_runner_v1_readonly.py`（≤250 行），全部 `tmp_path` 临时库 + 合成样本，**绝不碰 `reports/lp_rh/`（活库，正在跑 6 小时观测）**，不联网。≥12 个测试：

1. 端到端 5 样本 → 5 步，每步有 `primary_status`。
2. **T60**：全部不合格 → 合格步数 0，不抛异常，summary 计数正确。
3. **T32**：样本缺 `fee_apr_pct` → 该步 `INPUTS_UNAVAILABLE`，与 `COMPUTED_FAIL` 分开计数。
4. **T25**：`target_mode="LIVE_READINESS"` + 资本冲突 → 全部 `POLICY_BLOCKED`，预占未授予。
5. `SHADOW_SCENARIO` → 结果带 `simulated_policy_only=True`。
6. 预占只在第一个合格步授予。
7. NAV 连续性：`nav_end - nav_start - external_flow == net_pnl`（Decimal 精确）。
8. **T41**：episode 内多步 HODL 初始两腿数量恒定。
9. `load_samples_from_db` 对 `reference_mid IS NULL` 的行跳过并计入返回的 skipped，**不填 0**；`episode_summary(..., load_skipped=n)` 正确带出。
10. 每步各写 1 行 `rh_gate_decisions` 与 `rh_position_marks`；重复 `decision_id` 抛 `IntegrityError`。
11. 只读连接写入抛 `sqlite3.OperationalError`。
12. 跑完测试后活库行数不变（用 `reports/lp_rh/scanner.db` 跑前跑后计数，仅读不写）。

## 不许动
不改任何现有脚本（**含 shadow runner 本身**）与测试；不写活库；不联网；不碰 codex 正在写的文件。不要用 TaskCreate/TaskUpdate。**单次 Write ≤120 行，写完立刻 `ast.parse` 自检。**

## 验收
`pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿且 ≥12；全量 0 failed / 14 skipped；`git diff --stat` 为空。
