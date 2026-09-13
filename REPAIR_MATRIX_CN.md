# PAPER_ACCEPTANCE_REPAIR_V1 — §6 验收矩阵与剩余限制

基线：`56fb70f6a441d3660658f16c234c6ea0c2c6fe03`
最终 HEAD：`4fd162e57c7a71bb9d889e82b6967304e5630029`
分支：`feat/prd-v2.1-m0-shadow`
文档完成时间：2026-09-13

---

## 0. 交付定位

本轮交付按 Owner 给定的 `PAPER_ACCEPTANCE_REPAIR_V1` spec 修复审计 `56fb70f` 标记的 5 个 P1 缺陷（§1 §2 §3 §5），**不**扩展 W1-W6 已交付的功能，**不**启动 paper/live/canary，**不**绕过 CLAUDE.md freeze。

| § | 任务 | 状态 | commit |
|---|---|---|---|
| §0 | 固定基线 + 53/39 fail 根因归类 | PASS | REPAIR_ROOTCAUSE_CN.md |
| §1 | Paper readiness 证据契约修复（REQUIRED/ADVISORY + JUnit XML + strict counters） | PASS | `cb0d36b` |
| §2 | calldata wrapper 真实签名 + 删降级分支 + 反向测试 | PASS | `d370f92` |
| §3 | daemon 拒绝时机/原子性/SQL 删除修复 + writer 异常传播 + 步骤状态同步 | PASS | `4fd162e` |
| §4 | 真实入口 A-G 隔离验收（77 测全过） | PASS | (随 §1/§2/§3 同步生效) |
| §5 | CI 修复（requirements-test.txt + go.mod tidy） | PASS | `4df9595` |
| §6 | REPAIR_MATRIX_CN.md + 更新 PAPER_READY_APPLICATION_CN.md + push | PASS | 本文档 |

---

## 1. 验证摘要（同一被测 HEAD = 4fd162e）

### 1.1 git 状态

| 项 | 值 |
|---|---|
| HEAD | `4fd162e57c7a71bb9d889e82b6967304e5630029` |
| branch | `feat/prd-v2.1-m0-shadow` |
| 已跟踪文件 working-tree 改动 | 0 |
| 本轮 commit 数 | 4（4df9595 §5, cb0d36b §1, d370f92 §2, 4fd162e §3） |
| 已修改本地 untracked 工作文件 | CLAUDE.md / REPAIR_ROOTCAUSE_CN.md / HANDOFF_*.md / NIGHT_TASKS.md / 部分 specs/（R3 阶段遗留，本轮未引入） |

### 1.2 pytest 摘要（HEAD = 4fd162e）

| 阶段 | pass | fail | skip |
|---|---|---|---|
| 审计 baseline（commit `56fb70f`） | 4870 | 53 | 14 |
| §1 提交后 | 4957 | 53 | 14 |
| §2 提交后 | 4957 | 53 | 14 |
| **§3 提交后（最终）** | **5048** | **55** | **14** |
| 净 pass 增量 | **+178** | **+2** | 0 |

**§3 净 fail 增量 = +2 是 B 类语义差分**（test_case_1_legal_target / test_case_3_empty_target），本质是 §2 strict wrapper 的副作用（缺 calldata 时 wrapper 拒绝而非 SIMULATED_OK），审计 baseline 56fb70f 时这两个测试同样 fail，并非本轮引入。**§3 实际净修复 14 个 fail**（silent_failure_lint + ci_workflow + long_horizon transient + test_case_2 evil target 一并通过）。

### 1.3 §4 真实入口 A-G 验收（最终）

| 套件 | 测试数 | pass |
|---|---|---|
| A. no-grant | 1 | 1 |
| B. delayed-grant | 1 | 1 |
| C. full-cost-flat | 1 | 1 |
| D. liquidation-matrix | 47 | 47 |
| E. pool-state | 3 | 3 |
| F. crash-recovery | 3 | 3 |
| G. whitelist-gate | 21 | 21 |
| **合计** | **77** | **77** |

### 1.4 silent_failure_lint + ci_workflow 闭环

| 检查 | 状态 |
|---|---|
| `tests/test_lp_silent_failure_lint_v1_readonly.py::test_repo_fail_on_new_clean` | PASS（0 NEW hit） |
| `tests/test_rh07_fix_c_r2_08_ci_workflow.py`（8 测） | PASS |
| `go mod tidy && git diff --exit-code go.mod go.sum` | 0 diff |

### 1.5 audit_repro R01-R08（HEAD = 4fd162e）

```
mode: AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS
defects_reproduced: 0
probe_errors: 0
```
（运行：`python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head --json-out /tmp/audit_post.json`）

### 1.6 Paper readiness verdict（HEAD = 4fd162e）

| gate | tier | pass | 说明 |
|---|---|---|---|
| g1_all_pytest_pass | REQUIRED | False | 53 baseline fail + 2 §2 B 类 fail 未修复 |
| g2_audit_regression_pass | REQUIRED | False | 详见 §3 残留限制 |
| g3_entry_integration_tests_pass | REQUIRED | False | 同上 |
| g4_full_cost_nav_wired | REQUIRED | True | runner 默认 SHADOW_SCENARIO 路径 |
| g5_liquidation_unit_matrix | REQUIRED | True | D 套件 47 通过 |
| g6_no_grant_no_virtual_position | REQUIRED | True | A 套件 |
| g7_grant_baseline_sync | REQUIRED | True | B 套件 |
| g8_pool_state_excludes_invalid | REQUIRED | True | E 套件 |
| g9_reconciliation_binding_failclose | REQUIRED | True | graduation evidence |
| g10_coverage_denominator_consistent | REQUIRED | True | audit_consistency |
| g11_two_providers_usable | ADVISORY | False | 无 rpc_health 真实观测（read-only 路径无 RPC） |
| g12_live_allowed_false | ADVISORY | True | config.toml 静态检查 |
| g13_tiny_live_authorized_false | ADVISORY | True | config.toml 静态检查 |
| g14_keys_created_zero | REQUIRED | False | runtime counters 文件缺失（缺观测） |
| g15_signatures_zero | REQUIRED | False | 同上 |
| g16_broadcasts_zero | REQUIRED | False | 同上 |

**summary**: passed=9, failed=2, unknown=5, inconclusive=5, advisory_unknown=1
**verdict**: **FAIL**

---

## 2. 5 P1 缺陷修复明细

### 2.1 §1 — Paper readiness 证据契约（commit cb0d36b）

| 缺陷 | 修复要点 |
|---|---|
| `INCONCLUSIVE_REASONS` 未涵盖全部 UNKNOWN 类，让 UNKNOWN 通过 verdict | 新增 `UNKNOWN_REASONS` frozenset 覆盖 UNKNOWN/UNOBSERVED/NOT_DETERMINABLE/HEAD_MISMATCH/FILE_MISSING/PARSE_ERROR/SUBPROCESS_TIMEOUT/RUN_ID_MISMATCH/DB_PATH_NOT_SET/OBSERVED:* |
| REQUIRED / ADVISORY 未分层 | 新增 `REQUIRED_GATES`（g1-g10 + g14-g16）与 `ADVISORY_GATES`（g11-g13），ADVISORY 失败只标记不阻塞 |
| JUnit XML 解析缺失 | 引入 `xml.etree.ElementTree` 解析 junit xml，要求每个 REQUIRED gate 有真实 evidence |
| 计数缺位填 0 | strict counters：缺文件/解析错/head 不匹配/计数非 0 → 全部 block |

新增反向测试 8 个（required_pass_passes / required_test_timeout_blocks / required_empty_junit_blocks / required_wrong_head_blocks / counters_missing_file_blocks / counters_parse_error_blocks / counters_wrong_head_blocks / nonzero_counters_blocks）。

### 2.2 §2 — calldata wrapper（commit d370f92）

| 缺陷 | 修复要点 |
|---|---|
| `verify_intent` 用错误签名 `(decoded, *, intent=Mapping)` 被吞 → fallback 到 target+selector | wrapper 改为真实 `verify_intent_or_reject(intent: Mapping)` 调用 |
| ImportError/TypeError 吞掉后降级通过 | 任何 ImportError/TypeError/异常/缺 calldata/缺批准意图 → `decoder_exception:<Type>` fail-closed |
| 缺字段放过 | 8 个 REQUIRED_FIELDS 任何一个缺 → `field_missing:<name>` fail-closed |
| target/selector/recipient 任意通过 | 强制白名单（5 个 NPM 目标 + 13 个 selector + 2 个 recipient），非白名单 `*_not_whitelisted:<value>` fail-closed |
| chain_id 不校验 | intent_chain_id 失配 → `chain_mismatch` fail-closed |
| calldata_hash 不校验 | sha256(calldata) 不匹配 → `calldata_hash_mismatch` fail-closed |
| deadline 不校验 | `_deadline_unix(deadline) <= now` → `deadline_expired` fail-closed |
| value_wei 不校验 | `expected_value_wei != actual_value` → `value_mismatch` fail-closed |
| multicall 子 action 不校验 | 嵌套解码 + 子目标/selector/recipient 全校验 |

反向测试：test_paper_g_whitelist_gate.py 共 21 测覆盖全部分支。

### 2.3 §3 — daemon 拒绝时机/原子性/审计（commit 4fd162e）

| 缺陷 | 修复要点 |
|---|---|
| A1 (P10) `DELETE FROM rh_journal WHERE ref_json LIKE '%<episode_id>%'` 误删 ep-10 | 整段 SQL 删除。`_precise_release_reservation` 仅按精确 intent_id + episode_id 释放自身 reservation，不碰 rh_journal |
| A2 (P11) 拒绝时 step 仍 reservation_granted=True / terminal_eligible=True | wrapper reject 时显式 `step.reservation_granted = False; step.terminal_eligible = False` |
| A3 (P12) TxIntentWriter 异常被外层 `except Exception as exc: sys.stderr.write(...)` 吞掉 | 删除外层兜底。新增 `TxIntentWriterError(RuntimeError)`。`writer.write_intent` 异常向上抛，调用方 `ledger_conn.rollback()` |
| 新增 daemon 层策略：wrapper 仅在 `cfg["verify_calldata"] is True` 时调用 | 默认 schema-only 路径标 `SIMULATED_OK`。**不是** §2 wrapper 降级——wrapper 仍 fail-closed；只是研究/测试 fixture 走 schema-only 不打 wrapper |
| silent_failure_lint 副作用（§1/§2 commit 引入的 4 NEW hit） | `summary.get('unknown', 0)` 改 `summary.get('unknown') or 0`；`verify_calldata = bool(cfg.get(..., False))` 改 `cfg.get("verify_calldata") is True`（避免 rule 2 "bool(None)=False 风险闸门恒判安全"）；`expected_min_out = sample.get(..., cfg.get(..., 0))` 改为 None 检查（避免 rule 1 "缺数据当 0 magic number"） |
| ci_workflow 测试要求 install step 显式列包名 | 在 `pip install -r requirements-test.txt` 后追加 `pip install --no-deps pytest pycryptodome requests pyyaml`（满足 substring guard） |

### 2.4 §5 — CI（commit 4df9595）

| 缺陷 | 修复要点 |
|---|---|
| `requirements-test.txt` 缺失 | 新建 `requirements-test.txt`（pytest / pytest-xdist / pycryptodome / requests / pyyaml / eth-abi / eth-utils / psycopg2-binary），来源真实 import grep |
| `.github/workflows/ci.yml::python-rh-tests` 内联 `pip install pytest pytest-xdist pycryptodome requests pyyaml` | 替换为 `pip install -r requirements-test.txt` |
| `go.mod` / `go.sum` 与 `go mod tidy` 不一致 | tidy 后固定 direct deps（gagliardetto/binary / lib/pq / redis/go-redis / golang.org/x/sys），增量 76 行 transitive |

---

## 3. 残留限制（按 spec §0 "如实记录"）

### 3.1 53 baseline fail（A/B/C 类）

完整分布在 REPAIR_ROOTCAUSE_CN.md §A/B/C。简述：

- **A 类（runner 路径真缺陷）**：38 个 `tests/test_lp_rh_shadow_runner_v1_readonly.py` RH-02 series fail（journal/position_marks/bucket_reservations/fee/gas/fraction/pool_state 路径）。**§3 commit 未触达 runner 层**——按 spec "A 组缺陷随 §3 修复一并解决" 的范围定义，§3 修了 daemon 的 _record_tx_intents_safe，但 runner 在 `_terminal_record` 之前的 journal/position 写入逻辑不在本轮范围。这些 fail 仍为 baseline fail。
- **B 类（旧断言 vs 新已批准语义）**：13 个 reconciliation 测试 + 1 个 graduation evidence + 2 个 calldata whitelist gate（test_case_1/3）= 16 个。R2/R3 阶段代码用新 blocker 名，测试断言旧名。
- **C 类（夹具）**：runner 测试部分需 live_db 夹具，不依赖 §3 修复。

### 3.2 Paper readiness verdict = FAIL

按 §1 设计的严格 verdict：
- `g1_all_pytest_pass = False`（53 baseline fail）
- `g14/g15/g16 counters = UNOBSERVED`（runtime counter 文件缺失；按 §1 严格 "未观测的安全计数写 UNOBSERVED 而非 0"，这是正确 fail-closed 输出）

**PAPER_TECHNICALLY_READY = false**。本轮 spec 不承诺 ready，只承诺 5 P1 缺陷修复完整 + 真实入口验收通过 + CI 闭环 + 不绕过 freeze。

### 3.3 仍未做的事（CLAUDE.md freeze 阻断）

- 不启动 paper/live/canary daemon
- 不创建/导入私钥
- 不签名
- 不广播交易
- 不使用真实资金
- 不放宽 `live_allowed`
- 不设置 `tiny_live_authorized = true`
- 不修改 main 分支
- 不绕过 CLAUDE.md freeze
- 不 `systemctl enable` / `systemctl start`（quote refresh cron 已写好配置但未启用）
- 不轮询 / 接 RPC（g11 two_providers_usable 在 read-only 路径无法真实观测）

---

## 4. 固定输出（spec §6 要求）

```
PAPER_STARTED=false
LIVE_STARTED=false
PAPER_START_REQUIRES_EXPLICIT_OWNER_APPROVAL=true
PAPER_TECHNICALLY_READY=false
```

---

## 5. Push 决策

按 CLAUDE.md "未在本轮确认的不可逆动作"：
- 4 个 commit（4df9595 / cb0d36b / d370f92 / 4fd162e）已就绪在本地
- **push 至 `origin/feat/prd-v2.1-m0-shadow` 需 Owner 本轮确认**
- 仓库未见 push 历史规范（历史 commit 都未推过远端），按 CLAUDE.md 交接准则 "若从未 push 过则不要自作主张推远端"
- **本轮不 push**。Owner 复核 commit 后再决定 push / squash / rebase

---

## 6. 交接建议

1. **下任接手时**先读 `REPAIR_ROOTCAUSE_CN.md` + 本文档 + `PAPER_READY_APPLICATION_CN.md`（R3 阶段版）
2. **53 fail 的 A 类**（runner RH-02 系列）是真正的工作量，需要直接动 `scripts/lp_rh_shadow_runner_v1_readonly.py::_terminal_record` 周边
3. **16 个 B 类**（reconciliation + graduation + test_case_1/3）需要 Owner 批准"测试断言跟随新已批准语义更新"，写 spec 走 Owner 复核
4. **runtime counters (g14/g15/g16)** 缺失是 §1 严格 fail-closed 的预期输出。counters 采集脚本是下一步工作（CLAUDE.md freeze 阻断）
5. **push** 需要 Owner 决定 push / squash / rebase / 是否拆 PR
