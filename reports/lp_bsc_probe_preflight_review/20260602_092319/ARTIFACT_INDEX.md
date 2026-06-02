# Artifact Index — `20260602_092319`

Stage: `LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`
Status: **PASS**
recommended_next_stage: `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`

## 报告文件

| 文件 | 用途 |
|---|---|
| `FINAL_VERDICT.json` | 顶层 verdict |
| `ONEPAGE_CN.md` | 单页总览 |
| `INPUT_EVIDENCE_AUDIT_CN.md` / `input_evidence_audit.json` | Phase B — 9 份上游输入逐项确认 |
| `BSC_PROBE_CANDIDATE_REVIEW_CN.md` / `bsc_probe_candidate_review.json` | Phase C — 候选池 12 维就绪 + 6 个 downside risk + EV 矩阵 |
| `BSC_10_20U_PROBE_RISK_LIMITS_CN.md` / `bsc_10_20u_probe_risk_limits.json` | Phase D — 资金 / 时间 / 10 个 stop / approval 政策 / 10 个 pre-mint 硬门禁 |
| `BSC_PROBE_REQUIRED_TELEMETRY_CN.md` / `bsc_probe_required_telemetry.json` | Phase E — entry / hold / exit telemetry + 4 个 DB schema 提案（仅 proposal，未创建表） |
| `BSC_PROBE_DRY_RUN_BUILDER_SPEC_CN.md` / `bsc_probe_dry_run_builder_spec.json` | Phase F — dry-run builder I/O + 允许/禁止操作 + safety gates + manual approval checkpoint |
| `BSC_10_20U_PROBE_APPROVAL_PACKET_CN.md` / `bsc_10_20u_probe_approval_packet.json` | Phase G — 给您审批的完整 packet |

## 上游引用

源：`reports/lp_bsc_fee_velocity_recovery_probe_preflight/20260602_060633/`
源 status：`PASS`
源 recommended_next_stage：`LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1`（即本阶段）

## 工具脚本

本阶段**不**引入新的执行脚本（preflight review 只是审查 + 写文档）。
下一阶段 `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1` 才会新增 `scripts/lp_bsc_10_20u_probe_dry_run_builder_v1_readonly.py`。

## 测试

`tests/test_lp_bsc_probe_preflight_review_v1_readonly.py` — Phase I 添加，校验本审查包的形状与安全断言。
