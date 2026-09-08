# RH-08b：毕业就绪度面板（离线可测）

## 背景
PRD §17.1 要求首页回答六问，§21 定义 Stage A/B/C/D 的毕业门槛。当前真实状态（主脑实测）：Stage A 正向观测已跑 6+ 小时 / 72 小时门槛，样本 1292 条；终闸十项中依赖外部证据的部分刚具备可满足条件；`usable_provider_count=1` 使 LIVE 闸保持 BLOCKED。

已就位可 import：`lp_rh_daily_report_v1_readonly`（`answer_six_questions`、`evidence_freshness_table`）、`lp_rh_funnel_autopsy_v1_readonly`、`lp_rh_terminal_gate_v1_readonly`（`TERMINAL_CONJUNCTS`）、`lp_rh_store_v1_readonly`（`budget_status`、`open_store`）。

## 只新建两个文件
1. `scripts/lp_rh_readiness_v1_readonly.py`（≤280 行）
   - `STAGE_A_MIN_HOURS = 72`、`STAGE_A_MIN_COVERAGE = Decimal("0.99")`、`STAGE_B_MIN_DAYS = 14`、`STAGE_B_MIN_WEEKENDS = 1`、`STAGE_C_MIN_DAYS = 30`（PRD §21）。
   - `stage_a_status(*, first_sample, last_sample, expected_interval_secs, actual_samples) -> dict`：
     返回 `{"hours_covered", "hours_required", "coverage_ratio", "expected_samples", "actual_samples", "gaps", "passed": bool, "blockers": [...]}`。
     **覆盖率分母必须是「计划应观测的窗口」**（`hours_covered * 3600 / interval`），**不得删掉坏窗口后报 100%**（PRD §21.1）。`coverage_ratio < 0.99` → 进 `blockers`。
   - `stage_b_status(*, days_covered, weekends_covered, unexplained_ledger_diffs, invariant_violations, missed_risk_events) -> dict`：任一非零 → `passed=False`。**跑满 14 天不自动 PASS**（PRD §21.2）。
   - `live_gate_status(*, usable_provider_count, capital_policy_approved, signatures, broadcasts, keys_created) -> dict`：`usable_provider_count < 2` → `blockers` 含 `SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE`（PRD §8.3）；`capital_policy_approved is False` → 含 `CAPITAL_POLICY_CONFLICT`；签名/广播/密钥任一非 0 → 含 `UNAUTHORIZED_ACTION_DETECTED`。**永远返回 `live_allowed=False` 除非全部为空**。
   - `render_dashboard(state) -> str`：Markdown，含六问、四阶段进度条、终闸十项当前值、证据新鲜度表、预算用量。**任一数据缺失显示 `NOT_MEASURED`，不得显示 0 或猜测值**。
   - `graduation_verdict(stage_a, stage_b, live_gate) -> dict`：返回 `{"verdict": "PASS"|"WARN"|"FAIL", "next_allowed_task", "explicitly_not_authorized": [...]}`。**只要 live_gate 有 blocker，`verdict` 不得为 PASS。**
   - `main()`：`--db`（只读打开活库）`--out READINESS_DASHBOARD.md`。不联网、不写活库。
2. `tests/test_lp_rh_readiness_v1_readonly.py`（≤250 行，≥16 测试）
   - Stage A 覆盖率分母正确：观测 10 小时、间隔 15 秒 → 应有 2400 样本；实际 1200 → `coverage_ratio == 0.5`，`passed False`。**断言分母不是实际样本数。**
   - 观测 72 小时但覆盖率 0.98 → 仍 `passed False`（两个条件都要满足）。
   - Stage B 跑满 14 天但 `invariant_violations=1` → `passed False`（不自动 PASS）。
   - `live_gate_status(usable_provider_count=1, ...)` → `live_allowed False` 且 blocker 含 `SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE`。
   - 签名数为 1 → blocker 含 `UNAUTHORIZED_ACTION_DETECTED`。
   - 全部干净且 provider≥2 且政策已批 → `live_allowed True`。
   - `graduation_verdict`：live_gate 有任一 blocker → verdict 不为 `PASS`（参数化遍历三种 blocker）。
   - `render_dashboard`：某字段为 None → 输出含 `NOT_MEASURED`，**不含** `0` 作为该字段的值。
   - 用真实数值回归：Stage A 6 小时 / 72 小时 → `passed False`，`hours_required=72`。

## 不许动
不改任何现有文件；不联网；不写活库；不碰 `lp_rh_collector_v1_readonly.py`（生产运行中）与其它 worker 正在写的文件。不要用 TaskCreate/TaskUpdate。单次 Write ≤120 行，写完 `ast.parse` 自检。

## 验收
`pytest tests/test_lp_rh_readiness_v1_readonly.py -q` 全绿且 ≥16；全量 0 failed / 14 skipped；`git diff --stat` 为空。
