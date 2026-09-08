# RH-08a：每日决策报告生成器（离线可测）

## 背景
PRD §17.3 规定 `DAILY_DECISION.md` 必含：证据日期／完整性、已算与未算数量、三个最接近通过的候选及真正 blocker、100U 当前政策下是否有可行仓位、所有费用与风险成本、无交易是否为合理选择、必须处理的基础设施缺口。**明令禁止只输出「accepted=0、测试全绿」，禁止用旧 paper runner 的历史虚拟盈亏为 RH 宣传收益。** §17.1 要求首页能回答六个问题。

已就位可直接 import：`lp_rh_funnel_autopsy_v1_readonly`（`autopsy`、`zero_candidate_explanation`、`producer_map_check`）、`lp_rh_terminal_gate_v1_readonly`（`TERMINAL_CONJUNCTS`）、`lp_rh_store_v1_readonly`（`budget_status`、`open_store`）。

## 只新建两个文件
1. `scripts/lp_rh_daily_report_v1_readonly.py`（≤300 行）
   - `build_report(*, run_id, as_of, autopsy_summary, coverage, capital_policy, cost_breakdown, infra_gaps, evidence_freshness) -> str`：生成 Markdown。**必须包含七个固定小节**，缺任一节抛 `ValueError("MISSING_SECTION:<name>")`：
     `证据日期与完整性 / 已算与未算 / 最接近通过的三个候选 / 100U 政策下可行性 / 全部费用与风险成本 / 无交易是否合理 / 基础设施缺口`
   - `answer_six_questions(state) -> dict`：PRD §17.1 的六问，每问返回 `{"answer": str, "evidence": str}`。**任一问缺证据 → `answer` 必须写明 `NOT_MEASURED`，不得编造。**
   - `forbid_paper_pnl(text) -> None`：扫描报告文本，若出现 `paper_runner` 历史盈亏字样（`paper` 与数字金额同现）抛 `ValueError("PAPER_PNL_CITED_FOR_RH")`（PRD §17.3 明令）。
   - `assert_not_bare_accepted_zero(report: str, summary: Mapping) -> None`：若 `COMPUTED_PASS == 0` 且报告中**不含**四类拆分计数 → 抛 `ValueError("BARE_ACCEPTED_ZERO")`。
   - `evidence_freshness_table(sources) -> str`：每个数据源列 `source / fetched_at / source_event_time / age_secs / quality`；`source_event_time` 为 None → 标 `SERVER_TIME_UNKNOWN`（PRD §8.1：拉取时间不能替代服务器时间）。
   - `main()`：`--state-json --out DAILY_DECISION.md`，不联网、不写活库。
2. `tests/test_lp_rh_daily_report_v1_readonly.py`（≤250 行，≥16 测试）
   - 七个小节缺任一 → `MISSING_SECTION:<name>`（参数化遍历七节）。
   - `COMPUTED_PASS=0` 且报告只写 "accepted=0" → `BARE_ACCEPTED_ZERO`；带四类拆分 → 通过。
   - 报告中出现 `paper runner 净值 $1,769` 字样 → `PAPER_PNL_CITED_FOR_RH`。
   - 六问中某问无证据 → `answer` 含 `NOT_MEASURED`，且**不含**编造数字。
   - `evidence_freshness_table`：`source_event_time=None` → 输出含 `SERVER_TIME_UNKNOWN`。
   - 正常输入 → 生成的 Markdown 含全部七节标题且非空。

## 不许动
同 RH-07a。不要用 TaskCreate/TaskUpdate。

## 验收
`pytest tests/test_lp_rh_daily_report_v1_readonly.py -q` 全绿且 ≥16；全量 0 failed / 14 skipped；`git diff --stat` 为空。
