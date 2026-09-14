# OBSERVE_ONLY 决策规则（2026-09-14 RH 闭环）

## 1. 决策（owner-facing）

当前 `feat/prd-v2.1-m0-shadow` 分支上的 RH（Robinhood Chain V3 CORE）
观测管道在**只读观察模式**下运行。

- **任务起始模式** = `NONE`（未启动任何新进程）
- **现存只读长跑进程数** = 5
- **shadow / paper / live daemon 启动** = `false`
- **真实签名 / 广播 / 私钥导入 / 资金动用** = `false`
- **CORE_PAPER_ENGINEERING_GATE** = `FAIL`（参见 `reports/lp_rh/GRADUATION_VERDICT.json`）
- **CLAUDE.md freeze** = 未变更；本规则在 freeze 边界内运行

## 2. 决策依据（5 条 hard gate）

| # | Gate | 当前状态 | 证据 |
|---|------|---------|------|
| 1 | 真实 CORE terminal→ledger E2E 正控制 | **PASS** | `tests/test_lp_rh_terminal_to_ledger_e2e_v1_readonly.py::test_d1` —— NAV 1000→990, NetPnL=-10，3 行 gate_decisions / 3 行 position_marks / 1 行 reservation / 1 行 tx_intents 写入 ledger。5 个负控制（D2-D6）均 PASS。 |
| 2 | pytest 全量 | **PASS** | 5201 passed / 0 failed / 14 skipped（R3 整改完成 + 本轮 D 6 个新测试）。 |
| 3 | 5 个长跑 RH 进程在跑 | **PASS** | `reports/lp_rh/STAGE_A_REQUALIFICATION.json` —— collector / organic_recorder / premium_recorder / provider_health_recorder / shadow_daemon 全部存活，最新 tick 16:04–16:17 UTC（落在采集窗口内）。 |
| 4 | Audit-regression schema contract | **PASS** | workflow 加 `schema_version` / `run_id` / `head_sha` / `mode` / `github.sha` 五个必填字段（见 `tools/audit_repro/audit_repro.py` 改造 + `.github/workflows/audit-regression.yml` 同步）。 |
| 5 | CORE_PAPER_ENGINEERING_GATE | **FAIL**（已知） | GRADUATION_VERDICT.json 显示 Stage A `HOURS_COVERED_INSUFFICIENT` + `STAGE_A_SYNTHETIC_TESTS_FAILED`；Stage B `DAYS_COVERED_INSUFFICIENT` + `WEEKENDS_COVERED_INSUFFICIENT`；Live Gate `SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE` + `CAPITAL_POLICY_NOT_APPROVED`。 |

Gate 1–4 PASS 说明 CORE 终端到账本链路**形式正确**；Gate 5 FAIL 阻断
paper / live 启动。

## 3. OBSERVE_ONLY 允许的动作

| 动作 | 允许？ |
|------|--------|
| 读 `reports/lp_rh/scanner.db` 等只读 schema 查询 | ✅ |
| 重跑 pytest / audit_repro / preflight | ✅ |
| 解析 / 审计 `STAGE_A_REQUALIFICATION.json` 与 `GRADUATION_VERDICT.json` | ✅ |
| 提交只读 pipeline 的代码 + 测试（research: 前缀） | ✅ |
| 修改 `tools/audit_repro/audit_repro.py` schema 字段 | ✅ |
| 写 audit 报告（CN.md / .json）进 reports/ | ✅ |
| **触发** `_run_episode_persisted` 在测试内写 tmp db | ✅ |
| **写** `reports/lp_rh/scanner.db` | ⚠️ 仅 daemon 长跑进程持有写权限；测试只在 tmp_path |

## 4. OBSERVE_ONLY 阻断的动作

| 动作 | 阻断？ |
|------|--------|
| 启动新 collector / shadow / paper / live daemon | ❌ |
| `kill` / `systemctl restart` 5 个现存长跑进程 | ❌ |
| 修改 daemon 的 cfg / pool_meta / live_db 路径 | ❌ |
| 修改 ledger DB schema（`scanner.db` 表结构） | ❌ |
| 签名 / 广播 / 真实下单 / 私钥导入 | ❌ |
| 放宽 `live_allowed` / `tiny_live_authorized` 为 true | ❌ |
| 跳过 freeze / 修改 main / 绕过 CLAUDE.md | ❌ |
| 关停 GitHub Actions 的 `golangci-lint`（必须保留） | ❌ |
| 直接编辑 `reports/lp_rh/GRADUATION_VERDICT.json` 改判 PASS | ❌ |

## 5. 何时升级 / 降级

**升级到 PAPER 启动**：需要 owner 显式批准 + 5 条 gate 全 PASS。
- 5 条 gate 的 PASS 路径见 `BLOCKERS.csv`（债务分层）与
  `SCOPE_REQUEST_20260914_CN.md`（本期变更请求范围）。
- 不在 OBSERVE_ONLY 内自动跨过；任何 `paper_started=true` / `live_started=true`
  必须由 owner 在交接文档中显式签字。

**降级（owner 主动叫停）**：
- 改回纯 freeze：删除 STAGE_A_REQUALIFICATION.json 与本规则 → 回退到
  `20260531_124000` final freeze 状态。

## 6. 与 CLAUDE.md freeze 的关系

- CLAUDE.md（用户主指令）已规定：
  `edge_proven=no, tiny_canary_allowed=no, recommended=STOP_LP_RESEARCH_NOW`。
- 本决策**不**修改 CLAUDE.md；只在 freeze 边界内重新声明一个**子模式**
  （OBSERVE_ONLY），允许 read-only 数据采集 + audit pipeline 推进。
- 当 owner 显式签字 paper / live 时，再由 owner 在交接中提供 release。

## 7. 输出摘要

- `TASK_STARTED_MODE = NONE`
- `HOST_EXISTING_RH_READONLY_PROCESSES = 5`
  - collector (PID 2271374)
  - organic_recorder (PID 157737)
  - premium_recorder (PID 119849)
  - provider_health_recorder (PID 118592)
  - shadow_daemon (PID 2685886)
- `PAPER_STARTED = false`
- `LIVE_STARTED = false`
- `KEYS_CREATED = 0`
- `SIGNATURES = 0`
- `BROADCASTS = 0`
- `OBSERVE_ONLY_ACTIVE = true`
- `OBSERVE_ONLY_REQUIRES_EXPLICIT_OWNER_APPROVAL_TO_EXIT = true`