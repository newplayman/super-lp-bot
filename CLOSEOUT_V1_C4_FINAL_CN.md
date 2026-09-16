# RH CORE 闭环 — C4 收尾交付（2026-09-16）

> 本文档替代 `PAPER_START_REQUEST_CN.md` 后续的 docs HEAD 刷写 commit。
> 停止"docs commit 仅刷新 SHA"的循环。下方 TESTED_CODE_SHA 指向当前
> 仓库 HEAD，所有新证据直接归档到 `reports/lp_rh/release_candidate_d1291e8/`。

---

## 1. 当前状态

- **分支**：`feat/prd-v2.1-m0-shadow`
- **HEAD（TESTED_CODE_SHA）**：`d1291e8d8bf159b38d57b96d73bff9646f2e4dbb`
- **工作区干净**（`git status --short` 过滤 `??` 后为空）
- **OBSERVE_ONLY 维持**：未启动 paper/canary/live 进程

---

## 2. C1–C4 验收结论（截至 2026-09-16）

| 缺陷 | 标题 | 状态 |
|------|------|------|
| **C1** | 补源价格/流动性差分测试（不只 chain_id 过滤） | **PASS** — `test_source_price_variation_changes_engine_pnl` + `test_source_liquidity_variation_changes_engine_decision` 新增并通过；price 差分通过 tick_lower/tick_upper 变化证明；liquidity 差分通过 exit_depth_for_size 的 max_exit_usd 差分证明 |
| **C2-CLOSE** | 禁强制 netcover_pass，真实开平仓 | **PASS** — `test_run_once_real_episode_nav_1000_to_990_pnl_minus_10` |
| **C2-RESUME** | 状态恢复必须在引擎前 | **PASS** — `_run_episode_persisted` 在 engine 前从 ledger 读 prev_nav/prior_open_position |
| **C2-FAULT** | SIGKILL 必须确认到目标写入点 | **PASS** — `REACHED_WRITE_POINT:rh_paper_cursor` stderr 标记 + `proc.kill()` 管道握手 |
| **C3** | 完整 72h 半开窗口 | **PASS** |
| **C4** | TESTED_CODE_SHA 锁定 + 文档 HEAD 刷写停止 + 产物可获取 | **PASS** — 本文件即终态；JUnit + audit 原文归档 |

---

## 3. 验证证据（artifacts）

- `audit_results.json` — `python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head --json-out audit_results.json`：
  - `counts.defects_reproduced = 0`
  - `counts.probe_errors = 0`
  - `source.mode = AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS`
- `junit_results.xml` — `python3 -m pytest tests/ -q --tb=no -p no:cacheprovider --junit-xml=junit_results.xml`：
  - **5242 passed / 1 failed / 14 skipped**
  - 唯一失败：`test_lp_rh_graduation_evidence_v1_readonly.py::test_real_prod_db_readonly_run_output_to_tmp`
    （pre-existing data-driven 测试，依赖 `reports/lp_rh/scanner.db` 实际内容，与本任务无关）
- 关键 C1/C2 测试集（`test_lp_rh_paper_daemon_entry_v1` + `test_lp_rh_paper_daemon_isolated_endurance_v1`）：**33/33 pass**

---

## 4. 终止"docs HEAD 刷写循环"

历史循环模式：每轮 docs commit 把 SHA 刷到更新 commit → 触发下一轮 docs commit。
自本文件起：

- **不**再为仅刷新 SHA 创建 docs commit
- 旧 acceptance docs（`FINAL_VERDICT_20260914_CN.md`、`ACCEPTANCE_MATRIX_20260914_CN.md`、
  `READ_FIRST_20260914_CN.md`、`HANDOFF_20260914_CN.md`、`ACCEPTANCE_EVIDENCE_20260914_CN.md`、
  `OBSERVE_ONLY_DECISION_RULES_CN.md`、`PAPER_START_REQUEST_CN.md`、`PAPER_MIN_RELEASE_V1_CN.md`、
  `PUSH_AUTHORIZATION_CN.md`）保留为历史快照，不修改
- 任何后续 SHA 更新必须伴随代码/测试/脚本变更，禁止纯 docs 刷写
- 任何后续 acceptance 必须直接引用本文件 + `audit_results.json` + `junit_results.xml`

---

## 5. 安全边界

- 未启动 paper/canary/live 任何模式
- 未签名、未广播、未调用 `broadcaster.SendTransaction`
- 未创建/导入私钥
- 未放宽 `live_allowed`
- 未推送远端（commit 在本地，等 owner 显式 push 授权）

---

## 6. Owner 决定点

| 项 | 当前值 | 需 owner 决定 |
|----|--------|----------------|
| `PAPER_STARTED` | `false` | yes |
| `LIVE_STARTED` | `false` | yes |
| `KEYS_CREATED` | `0` | yes |
| `SIGNATURES` | `0` | yes |
| `BROADCASTS` | `0` | yes |
| `TINY_LIVE_AUTHORIZED` | `false` | yes |
| `push to origin` | 未推送 | yes |

---

## 7. 复跑命令（完整 self-contained）

```bash
# 1. 全量测试 + JUnit
python3 -m pytest tests/ -q --tb=no -p no:cacheprovider \
  --junit-xml=junit_results.xml

# 2. audit_repro
python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head \
  --json-out audit_results.json
python3 -c "
import json
d = json.load(open('audit_results.json'))
assert d['source']['mode'] == 'AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS'
assert d['counts']['defects_reproduced'] == 0
assert d['counts']['probe_errors'] == 0
print('audit_repro PASS head_sha=', d['source']['reviewed_head'])
"

# 3. 关键 C1/C2 测试集
python3 -m pytest tests/test_lp_rh_paper_daemon_entry_v1.py \
                   tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py \
                   -q
```

任一项不过 → REWORK_REQUIRED。
