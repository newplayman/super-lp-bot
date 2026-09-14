# CI_EVIDENCE_20260914_CN.md

## 1. 本地 audit_repro（commit 4da8bc0）

```
schema_version = audit_repro/1
run_id         = 430264c0-a72b-4d68-944e-2f0cec24c508
head_sha       = 4da8bc0d68b4d052b49bd0d2281198dcdb1e5944
mode           = AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS
scope          = AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS
defects_reproduced = 0
probe_errors       = 0
github             = null  (本地无 GITHUB_SHA)
```
原文：`reports/lp_rh/audit_repro_20260914.json`

## 2. workflow YAML 解析正确性

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/audit-regression.yml')); print('audit-regression.yml OK')"
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml OK')"
```
两文件均解析无误（直接执行确认）。

## 3. 任务 B — schema contract 字段已落

`tools/audit_repro/audit_repro.py:495-519` 注入顶层：
- `schema_version`
- `run_id`（uuid）
- `head_sha`
- `mode`
- `github.sha`（由 `GITHUB_SHA` / `GITHUB_HEAD_SHA` env 注入；本地为 null）

workflow `audit-regression.yml` 已用 heredoc 传 `GITHUB_HEAD_SHA`。

## 4. Python 测试本地

```
5201 passed, 14 skipped in 64.85s (0:01:04)
```
详细原文：`reports/lp_rh/pytest_summary_20260914.txt`

## 5. GitHub Actions（owner 验收后填写）

owner 在推送后目视最终 HEAD 的 Actions：

| Workflow | Job | Expected | Actual (owner to fill) |
|----------|-----|----------|-----------------------|
| ci.yml | golangci-lint | PASS | _ |
| ci.yml | go-test | PASS | _ |
| ci.yml | go-build (4 modes) | PASS | _ |
| ci.yml | python-rh-tests | PASS (5201/0/14) | _ |
| audit-regression.yml | audit-repro | PASS (defects=0, probe_errors=0) | _ |
| audit-regression.yml | schema contract check | PASS (5 fields present) | _ |

## 6. 已知 CI 风险

- pytest 在 CI 上可能受 race condition（shadow_daemon 写 ledger 时并发读）
  影响 → 已通过 tmp_path 隔离 + daemon 不在 CI 跑来缓解
- GitHub-hosted runner 的 sqlite version 可能与本地不一致 → 已固化
  `sqlite` 版本到 schema_version 字段
- GITHUB_SHA vs GITHUB_HEAD_SHA：CI 用 HEAD_SHA（与 PR 触发兼容）