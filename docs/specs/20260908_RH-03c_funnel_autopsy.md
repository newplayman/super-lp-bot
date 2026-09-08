# RH-03c：零候选解剖与摘除变异测试台（离线可测）

## 背景
PRD §8.4 要求每个候选归入唯一主状态并保留全部理由；§18.3 RH-INV-04 要求每道硬闸有摘除变异测试；用例 **T55**（每道新增硬闸单独被摘除时坏样本会被错误放行）、**T56**（旧 Base 模型同一快照新旧计算逐闸差异为 0）、**T59**（旧 terminal 字段无 writer → producer-map 验收 FAIL，不当经济证伪）、**T60**（0 合格池是正常可解释结果，不强制下单）。

已就位：`scripts/lp_rh_terminal_gate_v1_readonly.py`（`TERMINAL_CONJUNCTS` 十项、`evaluate_terminal_gate`、`mutation_witness_removed_gate`）、`lp_rh_netcover_inputs_v1_readonly.py`（`classify_zero_candidate`）、`lp_rh_store_v1_readonly.py`（`rh_gate_decisions` 表）。

## 只新建两个文件
1. `scripts/lp_rh_funnel_autopsy_v1_readonly.py`（≤300 行）
   - `autopsy(records, *, target_mode, now) -> dict`：对一批记录逐条跑终闸，产出
     `{"total", "by_primary_status": {五类计数}, "by_dominant_blocker": {闸名: 计数}, "closest_to_pass": [前3条及其唯一缺失闸], "no_producer_fields": [...], "decay": [{"gate":名, "survivors":n}]}`。
     `decay` 按 `TERMINAL_CONJUNCTS` 的书写顺序逐闸过滤，给出每闸之后还剩多少条——即漏斗衰减表。
   - `zero_candidate_explanation(summary) -> str`：**T60**。当 `by_primary_status["COMPUTED_PASS"] == 0` 时返回结构化解释，必须分别说明「已完成经济评估且不合格」「尚未能评估」「不支持」「政策阻挡」各多少条。**禁止输出"没有机会"这类结论**，只陈述分类。
   - `mutation_harness(records, *, target_mode, now) -> dict`：**T55**。对 `TERMINAL_CONJUNCTS` 每一项，构造把该闸强制置 True 的变异体，统计有多少条原本被拒的坏样本会被错误放行。返回 `{闸名: {"false_admits": n, "witness_detected": bool}}`。某闸 `false_admits == 0` 说明该闸从未独立起作用（可能被别的闸挡住），必须标 `witness_detected=False` 并在报告里单列——**PRD §8.5：若全部坏样本总被别的闸挡住，则不能证明新增闸已接线**。
   - `producer_map_check(records, required_fields) -> dict`：**T59**。统计每个必需字段有多少条记录里是缺失或 None，返回 `{字段: {"missing": n, "verdict": "NO_PRODUCER"|"OK"}}`；某字段在**全部**记录里都缺 → `NO_PRODUCER`。该结果**不得**被计入经济失败。
   - `main()`：`--records-json --target-mode --out`，不联网。
2. `tests/test_lp_rh_funnel_autopsy_v1_readonly.py`（≤300 行，≥16 测试）
   - T60：全部记录不合格 → `zero_candidate_explanation` 四类计数正确，且返回文本**不含**"无机会/no opportunity"字样（断言）。
   - T55：对十项逐一做变异，断言至少有闸的 `false_admits > 0`；对 `false_admits == 0` 的闸断言 `witness_detected is False`。
   - T59：构造一个字段在全部记录中都缺失 → `producer_map_check` 判 `NO_PRODUCER`，且该批记录的 `by_primary_status` 里它们计入 `INPUTS_UNAVAILABLE` 而**不是** `COMPUTED_FAIL`。
   - `decay` 表：构造 5 条记录使每闸各拒掉一部分，断言 survivors 单调不增且末项等于 `COMPUTED_PASS` 计数。
   - `closest_to_pass` 只返回**恰好缺一个闸**的记录。

## 不许动
不改任何现有文件；不联网；不写活库；不碰 `lp_rh_collector_v1_readonly.py`（生产运行中）、`lp_rh_exit_depth`/`lp_rh_shadow_runner`/`lp_rh_multiplier_reader`（其它 worker 正在写）。

## 验收
`pytest tests/test_lp_rh_funnel_autopsy_v1_readonly.py -q` 全绿；全量 0 failed / 14 skipped；`git diff --stat` 为空。
