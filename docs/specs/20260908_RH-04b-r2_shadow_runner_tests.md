# RH-04b 第二轮：补 Shadow Runner 的配对测试

第一轮 worker 写出了 `scripts/lp_rh_shadow_runner_v1_readonly.py`（150 行）但**没有测试文件**（工具调用报错中断）。本轮只补测试，**不许改脚本一行**。

先 `grep -n 'def ' scripts/lp_rh_shadow_runner_v1_readonly.py` 读真实签名再写断言，不要猜。

## 只新建一个文件
`tests/test_lp_rh_shadow_runner_v1_readonly.py`（≤250 行），全部 `tmp_path` 临时库 + 合成样本，**绝不碰 `reports/lp_rh/`（活库，正在积累 72h 观测）**，不联网。至少 12 个测试：

1. 端到端：5 个合成样本跑完，返回 5 步，每步有 `primary_status`。
2. **T60 零候选是合法结果**：全部样本 netcover 不足 → 合格步数 0 且**不抛异常**，summary 的 `COMPUTED_FAIL` 计数正确。
3. **T32 缺输入不当经济失败**：样本缺 `fee_apr_pct` → 该步 `INPUTS_UNAVAILABLE`，与 `COMPUTED_FAIL` 分开计数。
4. **T25 政策阻挡**：`target_mode="LIVE_READINESS"` + 资本冲突 → 所有步 `POLICY_BLOCKED`，预占全部未授予。
5. `SHADOW_SCENARIO` 的结果带 `simulated_policy_only=True`。
6. **预占只发生一次**：连续多步合格时只有第一步授予预占。
7. **NAV 连续性**：`nav_end - nav_start - external_flow == net_pnl`（Decimal 精确）。
8. **T41 HODL 基准不被重置**：episode 内多步的初始两腿数量恒定。
9. 样本缺 `reference_mid` → 跳过并在 summary 计数，**不填 0**。
10. 每步各写 1 行 `rh_gate_decisions` 与 `rh_position_marks`；重复 `decision_id` 抛 `IntegrityError`。
11. 活库以只读打开：用 `mode=ro` 连接尝试写入抛 `sqlite3.OperationalError`。
12. 跑完测试后活库行数不变（跑前跑后计数相同）。

## 不许动
不改任何现有脚本（**含 `lp_rh_shadow_runner_v1_readonly.py` 本身**）与测试；不写活库；不联网；不碰 codex 正在写的 `lp_rh_exit_depth`/`lp_rh_funnel_autopsy`/`lp_rh_meme_audit`/`lp_rh_markout`。不要用 TaskCreate/TaskUpdate。

## 验收
`pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿且 ≥12 个；全量 0 failed / 14 skipped；`git diff --stat` 为空。
