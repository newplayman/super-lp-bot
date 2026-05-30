# Fixed Horizon Input Artifact Audit

- source_dir: `reports/materializer_semantics/20260530_143120`
- input_exists:
  - `FINAL_VERDICT.json`: yes
  - `MATERIALIZER_SEMANTICS_DECISION_CN.md`: yes
  - `MATERIALIZER_V3_PROOF_QUALITY_CN.md`: yes
  - `materializer_v3_proof_quality.csv`: yes
  - `V2_VS_V3_COVERAGE_COMPARISON_CN.md`: yes
  - `v2_vs_v3_coverage_comparison.csv`: yes
  - `MATERIALIZER_V3_RESEARCH_MATERIALIZATION_CN.md`: yes
  - `materializer_v3_research_materialization_counts.csv`: yes
- missing_inputs: none
- enough_to_freeze_proof_policy: yes
- enough_to_hard_judge_edge: no
- note:
  - 输入已经足够冻结 canonical proof policy。
  - 输入不构成新的 edge 证明，只能支持 policy freeze 和 OOS accumulation 计划。
