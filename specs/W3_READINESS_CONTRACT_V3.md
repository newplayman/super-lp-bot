# W3 SPEC — 可消费的 readiness 与分层证据

**目标 SHA**: 18a8f39744af2d61d16737b7311d88cd88accea9 (W1+W2 完成后)
**owner-授权**: 已批 V3 taskpack

## 范围

只动：
- `scripts/lp_rh_paper_readiness_v1.py` (版本化 producer/consumer 契约)
- `tools/audit_repro/audit_repro.py` (添加 run_id 顶层字段 + mode 白名单固定为 AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS)
- `scripts/lp_rh_readiness_v1_readonly.py` (live_gate_status 真正采 rh_rpc_health)
- `tests/test_lp_rh_paper_readiness_v1.py` (新增 producer→consumer 契约测试 + 5 类门分离)
- `tests/test_audit_repro_*.py` (新增 run_id 绑定 + mode 白名单测试)
- `tests/test_lp_rh_readiness_v1_readonly.py` (新增 live_gate 用真实 rh_rpc_health 行)
- `scripts/lp_rh_provider_independence_v1.py` (新增 — 真实 DNS/IP/TLS/latency 探测)
- `tools/audit_repro/` 或同级新增版本化 schema 描述文件
- `specs/W3_READINESS_CONTRACT_V3.md` (本文件追加 patch log)

**不许动**：
- 六个冻结常量
- main 分支
- `internal/adapters/`

## 必须交付

### H1: 真实 producer/consumer 版本化 schema

新建 `reports/paper_closeout_v3_rev1/schemas/audit_repro_v1.json`:
```json
{
  "schema_version": "audit_repro/1",
  "required_top_level_fields": [
    "schema_version",
    "run_id",
    "head_sha",
    "mode",
    "tested_code_sha",
    "tested_config_sha",
    "scope",
    "started_at",
    "finished_at",
    "probes": [{"id": "R01..R08", "status": "PASS|FAIL|UNKNOWN", "evidence": {...}}],
    "counts": {"defects_reproduced": int, "probe_errors": int}
  ],
  "mode_whitelist": ["AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS"]
}
```

修改 `tools/audit_repro/audit_repro.py::main`:
- 输出顶层 `run_id` (UUID4)
- 输出顶层 `schema_version`
- 顶层 `mode` 仍在 source 字段下，但额外暴露顶层 alias
- 失败 mode 不在白名单时返回 exit code 2（producer 拒绝）

修改 `scripts/lp_rh_paper_readiness_v1.py::check_g2_audit_regression`:
- 验证 producer schema_version 匹配期望
- 验证 run_id 在外部绑定（运行前固定，不再从 producer 文件自取）
- 验证 mode ∈ mode_whitelist
- 验证 probes 全部存在 R01..R08
- 任一不满足 → 返回 BLOCKED_BY_SCHEMA_MISMATCH

### H2: 5 类门契约分离

修改 `scripts/lp_rh_paper_readiness_v1.py`:
- 新增 `GATE_DEFINITIONS` dict with 5 categories:
  - `ENGINEERING_GATE` — pytest pass, audit_repro pass, no new GH issues
  - `COLLECTION_START_GATE` — RPC healthy, no-send guard works, watcher can run
  - `STAGE_A_DATA_GATE` — ≥72h forward window with ≥99% valid key data
  - `PAPER_START_GATE` — engineering + StageA + paper config ready + owner approval
  - `PROFILE_GRADUATION_GATE` — CORE 14 complete days + full cost + sample-out + exit pressure
  - `LIVE_START_GATE` — CORE graduated + capital policy + dual path + fork/recovery + owner approval
- 每一类门独立 verdict + evidence，禁止交叉糊弄
- `PAPER_TECHNICALLY_READY = ENGINEERING_GATE pass AND STAGE_A_DATA_GATE pass` （不要求 owner approval，不要求 14 日毕业）
- `LIVE_TECHNICALLY_READY = PROFILE_GRADUATION_GATE pass` （不要求 owner approval）
- `LIVE_STARTED_BY_THIS_TASK = False`（硬写）

新增 `tests/test_lp_rh_paper_readiness_v1.py`:
- `test_5_gate_categories_isolated` — 每类门独立 PASS / FAIL
- `test_engineering_gate_requires_only_producer_evidence` — 不要求 72h
- `test_stage_a_gate_requires_72h_window` — 缺观测 → UNOBSERVED
- `test_paper_ready_does_not_require_owner_approval` — owner_authorized=False 但 paper_tech_ready=True
- `test_live_ready_does_not_require_owner_approval` — 同上
- `test_live_started_always_false_this_task` — 硬写 false

### H3: audit_repro R01–R08 探针验证

修改 `audit_repro` 输出，确保每个 R01..R08 探针都有 status + evidence。

新增 `tests/test_audit_repro_v3_probes_v1.py`:
- `test_all_eight_probes_present` — R01..R08 全部存在
- `test_probes_have_status_and_evidence` — 每探针 status ∈ {PASS, FAIL, UNKNOWN} + evidence 非空（status=PASS 时）
- `test_probe_errors_count_matches_unknown_count` — `counts.probe_errors == sum(p.status==UNKNOWN for p in probes)`
- `test_run_id_unique_per_invocation` — 两次运行 run_id 不同
- `test_head_sha_matches_bound_value` — 与外部 GITHUB_HEAD_SHA env 匹配

### H4: live_gate_status 接 rh_rpc_health

修改 `scripts/lp_rh_readiness_v1_readonly.py::live_gate_status`:
- 不再用字符串字面量 SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE
- 改为查询 `rh_rpc_health` 表的 `usable_provider_count`
- 当 `usable_provider_count >= 2` → not blocked
- 当 `usable_provider_count == 1` → emit SINGLE_PROVIDER_DEGRADED（warning，不阻塞）
- 当 `usable_provider_count == 0` → emit NO_PROVIDER_USABLE（阻塞）

新增 `tests/test_lp_rh_readiness_v1_readonly.py::TestLiveGateFromRpcHealth`:
- 模拟 2 provider rows → not blocked
- 模拟 1 provider → warning only
- 模拟 0 provider → blocked
- 字符串字面量 SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE 不再作为独立信号

### H5: provider independence 探测

新建 `scripts/lp_rh_provider_independence_v1.py::check_independence`:
- 接收 provider_a_url, provider_b_url
- DNS 解析 A, B → 收集 IP 集合
- 比较 IP 集合 → 同 IP 集合返回 `independent=False, reason=shared_backend`
- 不同 IP → 5 次小请求 sample，latency p50 差 >30% 返回 `independent=False, reason=same_latency_profile`
- 不同 IP + 正常 latency → 返回 `independent=True, reason=distinct`
- evidence dict 包含 IP 集合 / latency 分布 / request count

新增 `tests/test_lp_rh_provider_independence_v1.py`:
- `test_same_ip_returns_not_independent`
- `test_different_ip_returns_independent`
- `test_dns_failure_returns_indeterminate`

## 验收命令

```bash
# H1+H2+H3:
python -m pytest tests/test_lp_rh_paper_readiness_v1.py tests/test_audit_repro_v3_probes_v1.py -v --tb=short -p no:cacheprovider 2>&1 | tail -15

# H4:
python -m pytest tests/test_lp_rh_readiness_v1_readonly.py -v --tb=short -p no:cacheprovider 2>&1 | tail -10

# H5:
python -m pytest tests/test_lp_rh_provider_independence_v1.py -v --tb=short -p no:cacheprovider 2>&1 | tail -10

# End-to-end producer→consumer:
python tools/audit_repro/audit_repro.py --repo . --allow-other-head --json-out /tmp/w3_audit.json
python scripts/lp_rh_paper_readiness_v1.py --audit-json /tmp/w3_audit.json --expected-run-id "$RUN_ID" --json-out /tmp/w3_paper_ready.json

# Full regression:
python -m pytest tests/ -q --tb=line -p no:cacheprovider 2>&1 | tail -5
# Baseline ≤ 53 fail + W1/W2 net change
```

## 风险与边界

- 不连 RPC（independence 探测用 mock URL 或 localhost echo）
- 不放宽六个常量
- 不修改 runner 主体
- 不删 readiness gates，只增强契约
- provider_independence 不能 require 真实网络

## 输出要求

每 H 分块验证贴最后 10 行。最终 producer→consumer 验证贴完整 JSON 摘录（顶层 schema_version / run_id / mode / head_sha / probes 计数）。
