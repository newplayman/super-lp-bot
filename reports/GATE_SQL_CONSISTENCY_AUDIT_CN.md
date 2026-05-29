# Gate SQL Consistency Audit

- canonical source: `shadow_outcome_labels_repaired_terminal_v1`
- compared reports:
  - `TERMINAL_INCLUSIVE_RESIDUAL_AUDIT_CN.md`
  - `COHORT_PNL_PROOF_CN.md`
  - `TERMINAL_EXIT_PNL_AUDIT_CN.md`
  - `GATE_CONCLUSION_CN.md`

## Canonical Cross-check

| Horizon | residual strict-valid | cohort combined_strict_valid | terminal audited count | terminal audited coverage % | gate_report_status |
| --- | ---: | ---: | ---: | ---: | --- |
| 6h | 24256 | 24256 | 5655 | 99.507302 | CONSISTENT |
| 24h | 22480 | 22480 | 14019 | 99.800669 | CONSISTENT |

## Conclusion

- 这次已修正两类 report SQL bug：`repaired_v2` 非去重 join，以及 terminal auditability 过宽口径。
- 如果后续 gate 指标再次偏离 `6h=5655/5683`、`24h=14019/14047` 这组 terminal 审计事实，应直接判 `gate_report_status = INCONSISTENT`。
