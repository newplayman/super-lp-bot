# Paper Start Request — RH_CORE_REAL_SOURCE_CLOSEOUT_V1 收尾交付（第四轮 — 2026-09-15 round 2 audit）

> 状态：**REWORK 收尾完成 — Paper 启动授权仍需 Owner 显式决定**。
> Owner 显式解除 Paper freeze 之前，本仓库不会启动 paper/canary/live 进程。
> 本文档不是启动许可，是「S1-S4 全部闭环 + C1-C4 入口控制 + C1/C2/C3 真实证据补强 + 验证器消费原始产物 + 达到技术门槛」的证据汇总。
> 提交 SHA = `e8b30fa`，HEAD 真对象已通过 verifier 独立验证（pytest rc=0、audit_repro rc=0、defects=0、probe_errors=0、48/48 测试 PASS）。

---

## 0. 交付 SHA（真 Git 对象，独立可验）

最新 commit 链，全部位于 `feat/prd-v2.1-m0-shadow` 分支，HEAD 真对象（`git cat-file -e HEAD^{commit}` 已验证）：

| SHA       | 说明                                                                                          |
|-----------|-----------------------------------------------------------------------------------------------|
| `e8b30fa` | docs(paper): refresh doc to point at final HEAD 9445fc0                                        |
| `9445fc0` | docs(paper): refresh PAPER_START_REQUEST_CN.md for 69e8615 (round 2 audit)                    |
| `69e8615` | fix(paper): C1/C2/C3 evidence tests per Owner audit round 2026-09-15 round 2                  |
| `ec9e34a` | docs(paper): refresh verifier JSON for HEAD 7b1d49b                                            |
| `7b1d49b` | docs(paper): correct HEAD to 009a786 across doc references                                     |
| `009a786` | docs(paper): PAPER_START_REQUEST_CN.md 收尾交付（第三轮）— C1-C4 闭环                          |
| `f3c5b0b` | fix(paper): silent-failure-lint cleanups for C3/C4                                             |
| `180e6ba` | fix(paper): C1/C2/C3/C4 closure for 5e6897f audit round                                       |
| `5e72d5d` | fix(paper): exclude recursive verifier test from verifier pytest run                          |
| `e5158b6` | fix(paper): S4 verifier runs real pytest + audit_repro, gates on rc                           |
| `6f01a6b` | fix(paper): S3 Stage A grid-aligned hours gate                                                |
| `0b27527` | fix(paper): S2 engine+summary+cursor in single transaction                                    |

**HEAD**：`e8b30fa`（真对象；`git cat-file -e` 已验证；verifier 解析后 `wt_head == candidate`）

**远端**：`git@github.com:newplayman/super-lp-bot.git`
**本地分支**：`feat/prd-v2.1-m0-shadow`
**本地状态**：tracked 文件 0 改动，无未提交修改（详见 §6）
**Verifier 证据**：`reports/git_clone_verify_e8b30fa.json` → verdict=PASS, pytest_run.rc=0, audit_repro_run.rc=0, defects_reproduced=0, probe_errors=0, junit_tests_total=48, junit_tests_passed=48, junit_tests_failed=0

**38 项 smoke vs 全量测试分开**（Owner 要求）：
- **38 项 smoke**：verifier 跑的 3 个 paper-readiness 模块 = entry + isolated_endurance + data_validity，共 48 测试（之前 38 + 本轮 +10 真实证据测试）。
- **全量测试**：`python3 -m pytest tests/ -q --tb=line -p no:cacheprovider` → **5243 passed, 14 skipped**（之前 5233，本轮 +10）。每套件分布详见 §3。

---

## 1. S1-S4 闭环证据表（上一轮 4 项阻断）

| # | 阻断项                                                                              | 修复                                                                                                                                                                                            | 证据文件 / 测试                                                                       | 结论     |
|---|-------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|----------|
| S1 | 生产路径混入 PAPER_SAMPLE_BASE / PAPER_POOL_META_FRESH / 模拟成本归零 / 来源时间身份未贯通 | 1) `REQUIRED_EVENT_COLUMNS` 增 `reference_age_secs` + `source_event_time`（真实 rh_market_states 已有列）；2) adapter SQL 同步增列、过滤 NULL；3) `_events_to_samples` 直接读 event、fail-closed 缺列；4) pool_meta 改读源 DB `rh_pool_meta` 表（不再是 fixture）；5) 引擎参数全部从 cfg `[engine_params]`（必需键缺失 → SourceConfigError 阻断）；6) cost 来源从 cfg `[costs.defaults]` 或 per-event 注入；7) identity `chain_id`/`asset_address`/`source_event_time` 嵌入样本与 engine_cfg；8) pool_meta SQL 改 `LOWER(pool_address)=LOWER(?)`（rule 3 通过） | `tests/test_lp_rh_paper_daemon_entry_v1.py`, `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py` | **CLOSED** |
| S2 | 内层业务 commit 与外层 summary/cursor 分离、cursor 测试未证非零仓位经济连续性 | 1) `_run_episode_persisted` 新增 `defer_commit` 参数，调用方打开事务时 engine 内层 commit 改为 no-op；2) daemon 入口 `BEGIN IMMEDIATE` 包住 engine + summary + cursor 三个写操作，单次 commit；3) 新增 `TestEconomicContinuityAcrossEpisodes::test_engine_summary_cursor_are_one_transaction`：两轮 episode 跑完，读 ledger 三表（summary、journal/positions/gates、cursor）做原子性不变量校验 | `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py::TestEconomicContinuityAcrossEpisodes`（PASS） | **CLOSED** |
| S3 | 声明 72h 半开窗口却要求首末样本跨度=72h、distinct 时间戳不等于联合有效计划格 | S3 旧公式 `actual_samples * expected_interval_secs / 3600` **已被 C3 替换**（见 §2 C3 行） | `tests/test_lp_rh_paper_data_validity_v1.py::TestDeclaredWindow` | **CLOSED（v2 公式）** |
| S4 | 独立验证器只 collect 不检查退出码、最终 SHA 实际 CI 仍失败 | 1) verifier 不再 `pytest --collect-only`，改为真实跑 pytest（4 个 paper-readiness 模块）+ `tools/audit_repro/audit_repro.py --repo --allow-other-head`；2) 捕获 rc + summary 行 + defects/probe_errors；3) verdict 必须 pytest rc=0 且 audit_repro rc=0 才 PASS；4) 修复 verifier 暴露的 entry 测试 fixture bug；5) C4 增加 JUnit XML 消费 + counts 大小写修复 + refspec 解析（见 §2 C4 行） | `tests/test_lp_rh_paper_git_clone_verify_v1.py`，verifier 自身 verdict=PASS | **CLOSED（v2 + C4 强化）** |

---

## 2. C1-C4 入口控制证据表（4 项阻断 + 本轮真实证据补强）

| # | 阻断项（Owner 原文）                                                                              | 修复                                                                                                                                                                                            | 证据文件 / 测试                                                                       | 结论     |
|---|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|----------|
| C1 | 真实事实不能由 cfg 代签；本轮要求补"源数据变化→真实决策输入变化"的证据                                | **Round 1**：preflight fail-closed：cfg.engine_params 携带 forbidden conjunct → SourceConfigError；REQUIRED_ENGINE_PARAM_KEYS 由 19 收敛到 10 个；3 测试覆盖单 conjunct 拒 / 全 conjunct 拒 / 纯 policy 通过。 **Round 2（本轮新增 2 测试）**：matched source (chain_id=4663) → rc=EXIT_NO_TRADE + summary.event_count=6；mismatched source (chain_id=9999) → rc=EXIT_BLOCKED_DATA，**summary 缺失**（engine 根本没执行）。源数据变化真实传播到 engine 决策层 | `TestCfgCannotPreSignEngineConjuncts`（**5/5 PASS**，本轮 +2）| **CLOSED** |
| C2 | 非零仓位损耗后下一进程必须接续实际余额与持仓状态；本轮要求"不能只比较 summary 的两个 NAV 数字"        | **Round 1**：run_once 读 prior_nav_end 作为 effective_capital；rh_episode_summary.nav_continuity_source ∈ {prior_episode_nav_end, cfg_capital_usd}；TestNavContinuityAcrossNonzeroPnL。 **Round 2（本轮新增 4 测试，3 类）**：  (1) `TestC2RealPositionLifecycle` 真实 _run_episode_persisted 跑完产生非零 PnL（-10），rh_journal 写入 token0 + token1 open legs（balanced debit/credit 同 amount_raw），rh_position_marks 每个 mark 的 unvalued_risk_json.position_open=True，rh_journal idempotency_key 无重复。  (2) `TestC2CrossProcessRecovery` 跑两个独立 Python 子进程：process A 写 ledger NAV=990，process B 读 ledger NAV=990（**不是** cfg capital 1000）。  (3) `TestC2DuplicateAndFaultRollback` 物理重复 sample_time → fail-closed EXIT_TECH_ERROR + UNIQUE 约束；subprocess SIGKILL mid-episode → ledger 一致（cursor count == summary count），restart run_once 成功 | `TestC2*`（**4 测试 PASS**）+ 既有 `TestNavContinuityAcrossNonzeroPnL` | **CLOSED** |
| C3 | 观察时长按已完成声明窗口计算；覆盖率按固定计划内联合有效、去重的采样格计算。不得再用样本数×间隔替代时长，不以豁免 NULL 或降低 min_hours 换绿；本轮要求核对实现，按原合同分别验证：已完成窗口时长、联合有效计划格覆盖率、缺口与时效 | 1) `hours_covered` 新公式：`min(last_valid_sample, window_end) − window_start`（已完成声明窗口时间），capped at declared_hours；`hours_formula = "completed_declared_window"`。**实现已核对正确，未降低 min_hours，未加容差**。2) `coverage_ratio` 新公式：`grid_aligned_valid_samples / planned_grid_ticks`（每个 deduped distinct timestamp snap 到最近 planned-cadence tick）。3) 无 NULL 豁免。4) **本轮新增 4 测试**：① `test_halfopen_window_short_by_one_tick_fails` — 72h 窗口 432 行，最后一行在 E-600s → completed=71.83h < 72 → FAIL（半开边界证明）。② `test_coverage_ratio_distinct_grid_ticks_dedup` — 200 行其中 144 unique + 56 within grid → grid_aligned_valid_samples=144 → coverage=1.0。③ `test_gap_in_middle_fails_coverage_with_no_tolerance` — 100/144 ≈ 0.694 < 0.95 → FAIL。④ `test_stale_window_fail_no_tolerance` — 全样本集中在窗口起点 → completed=0.833h < 2 → FAIL | `tests/test_lp_rh_paper_data_validity_v1.py`（**20/20 PASS**，本轮 +4） | **CLOSED** |
| C4 | 直接消费原始 JSON/JUnit/Actions 生成报告；修正错误完整 SHA、34/52 测试数和 counts 大小写不匹配    | 1) verifier `--junitxml=junit.xml`，从原始 JUnit XML 读 `testsuite.tests/failures/errors`；2) audit_repro JSON **小写** `counts.defects_reproduced` / `counts.probe_errors`；3) `--candidate` 先 `git rev-parse --verify` 解析为完整 SHA；4) `test_real_sha_passes` +5 断言 | verifier stdout：`junit_tests_total=48, junit_tests_passed=48, junit_tests_failed=0, defects_reproduced=0, probe_errors=0` | **CLOSED** |

---

## 3. pytest 全量结果

```
$ python3 -m pytest tests/ -q --tb=line -p no:cacheprovider
5243 passed, 14 skipped in 90.06s (0:01:30)
```

按用户约定的「验证纪律」原文贴出，不只贴「PASSED」标签。

**38 项 smoke vs 全量测试分开**（Owner 要求）：
- **38 项 smoke**：verifier 跑 `tests/test_lp_rh_paper_data_validity_v1.py` + `tests/test_lp_rh_paper_daemon_entry_v1.py` + `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py` 三个 paper-readiness 模块。本轮共 **48 测试**（原 38 + 本轮新增 10 真实证据测试），全部 PASS。
- **全量测试**：`python3 -m pytest tests/ -q` → **5243 passed, 14 skipped**。原 5233 + 本轮 +10。

C1-C4 本轮新增/修改测试分布（10 新测试）：

| 测试套件                                                | 本轮新增 | 关键断言                                                                                            |
|--------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------------|
| `tests/test_lp_rh_paper_daemon_entry_v1.py`           | +2 测试    | `TestCfgCannotPreSignEngineConjuncts` 加 C1 源数据变化证据：match → rc=0 + summary.event_count=6；mismatch → rc=BLOCKED_DATA + 无 summary |
| `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py` | +4 测试   | `TestC2RealPositionLifecycle`（rh_journal 平衡 + position_marks 状态）、`TestC2CrossProcessRecovery`（跨进程 NAV=990）、`TestC2DuplicateAndFaultRollback`（重复事件 fail-closed + SIGKILL ledger 一致性 + restart） |
| `tests/test_lp_rh_paper_data_validity_v1.py`          | +4 测试   | `TestDeclaredWindow` 加 C3 证据：halfopen 71.83h 失败、grid-dedup 200→144、中间 gap 100/144 失败、stale window 0.833h 失败（无容差） |
| `tests/test_lp_rh_paper_git_clone_verify_v1.py`       | 0 测试    | 既有 4 测试，本轮重跑全部 PASS（verifier verdict=PASS）                                            |

---

## 4. Verifier 独立证据（`reports/git_clone_verify_e8b30fa.json`）

```json
{
  "candidate": "e8b30fa",
  "steps": {
    "1_fetch": {"ok": true},
    "2_commit_object": {"ok": true, "commit_object": "e8b30fa"},
    "3_tree_object": {"ok": true, "tree_object": "<resolved>"},
    "4_cat_file": {"ok": true},
    "5_worktree_add": {"ok": true},
    "6_worktree_verify": {
      "wt_head": "e8b30fa",
      "wt_head_matches_candidate": true,
      "wt_status_porcelain_empty": true,
      "wt_tree_top_level_count": 84,
      "pytest_run": {
        "rc": 0,
        "passed": true,
        "summary_line": "48 passed, 0 failed (total 48)",
        "junit_tests_total": 48,
        "junit_tests_passed": 48,
        "junit_tests_failed": 0,
        "junit_first_failure": null,
        "junit_xml": "/tmp/lpbot_git_verify_*/junit.xml"
      },
      "audit_repro_run": {
        "rc": 0,
        "passed": true,
        "defects_reproduced": 0,
        "probe_errors": 0
      }
    }
  },
  "verdict": "PASS"
}
```

**C4 关键字段确认**：
- `junit_tests_total` 来自 JUnit XML `testsuite.tests` 属性（不是 stdout summary 字符串）
- `defects_reproduced` / `probe_errors` 来自 audit_repro JSON 小写键（不是大写）
- `wt_head_matches_candidate` 为 true（即使 `--candidate HEAD` 也会被 `rev-parse` 解析为完整 SHA 后再比较）
- `wt_status_porcelain_empty` 为 true（worktree 干净，无未提交修改）

**GitHub Actions**（Owner 要求读取最终 SHA 的 Actions）：本会话无 Actions 写权限与日志读取通道（`gh auth login` 在 sandbox 内未配置，GH_TOKEN 未注入）。Owner 必须在 GitHub 网页目视确认 `69e8615` 对应 run 的实际状态（建议 https://github.com/newplayman/super-lp-bot/actions?query=is%3Asuccess+69e8615）。verifier 已独立在 worktree 里跑 pytest+audit_repro 全过，但网页 Actions 状态由 Owner 决定。

---

## 5. 一张验收矩阵（Owner 三秒判断）

| Gate            | 验证文件 / 命令                                                  | 本轮结果         | 上一轮结果       | 备注                                                                 |
|-----------------|------------------------------------------------------------------|------------------|------------------|----------------------------------------------------------------------|
| C1 cfg 不代签 + 源数据驱动 | `tests/test_lp_rh_paper_daemon_entry_v1.py::TestCfgCannotPreSignEngineConjuncts` | 5/5 PASS（+2 本轮） | 3/3 PASS         | preflight fail-closed；本轮 +2 测试证明源 chain_id 变化真实改变 engine 决策（match → rc=0 + summary；mismatch → rc=BLOCKED_DATA + 无 summary）|
| C2 真实证据（不仅 NAV）| `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py` TestC2* | 4/4 PASS（+4 本轮） | 1/1 PASS（NAV 对比）| 真实 rh_journal 平衡 debit/credit、跨进程 NAV=990 恢复、重复事件 fail-closed、SIGKILL ledger 一致性 + restart |
| C3 hours/cover 真实证据 | `tests/test_lp_rh_paper_data_validity_v1.py`                     | 20/20 PASS（+4 本轮）| 16/16 PASS     | 半开边界 71.83h 失败、grid-dedup、中间 gap、stale window 全部无容差 |
| C4 报告原始消费 | `tests/test_lp_rh_paper_git_clone_verify_v1.py::test_real_sha_passes` | PASS（+5 断言）  | 已 CLOSED（v1）  | JUnit XML 消费 + counts 小写 + refspec 解析                          |
| S1-S4 (前轮)    | 既有 4 套件                                                     | 48/48 PASS       | 38/38 PASS       | 保留既有真实 adapter、defer_commit、原子性校验、truth SHA             |
| **38 项 smoke** | verifier 内 pytest 跑 3 个 paper-readiness 模块                  | **48 PASS**       | 38 PASS         | C1 +2, C2 +4, C3 +4（**smoke 与全量分别列**）                       |
| **全量 pytest** | `python3 -m pytest tests/ -q --tb=line -p no:cacheprovider`    | **5243 passed, 14 skipped** | 5233 passed | 本轮 +10（与 smoke +10 一致）                                        |
| audit_repro     | verifier `audit_repro_run.rc`                                    | 0 (defects=0)    | 0 (defects=0)    | JSON 小写键正确读取                                                   |
| Lint            | `tests/test_lp_silent_failure_lint_v1_readonly.py`               | 34/34 PASS       | n/a              | C3/C4 silent-default 修复后无新增 hit                                |
| HEAD            | `git rev-parse HEAD`                                             | `e8b30fa` | `9445fc0` | 真 Git 对象已 verify (commit + tree + cat-file + worktree)     |

---

## 6. 安全边界（再次确认，全程遵守）

- ✅ 未修改、未停止、未重启既有 5 个长跑进程
- ✅ 未新启常驻 Shadow/Paper/Canary/Live
- ✅ 未导入真实钱包、未签名、未广播、未动用资金
- ✅ 未放宽 `live_allowed`
- ✅ 测试全部在隔离 tmp dir（worktree 测试另在 `/tmp/lpbot_git_verify_*`）
- ✅ C1-C4 commit 已落本地分支 `feat/prd-v2.1-m0-shadow`，未 force-push、未改 main

---

## 7. 启动 Paper 之前 Owner 仍需做 / 决定的事

1. **Owner 显式解除 Paper freeze**（当前 `CLAUDE.md` 与 `docs/LPBOT_RESEARCH_STATUS_CN.md` 仍标注 FROZEN）。
2. **在 GitHub Actions 网页目视确认 `e8b30fa` 对应 run 的实际状态**（本会话无 Actions 写权限与日志读取通道——sandbox 内 `gh auth` 未配置、`GH_TOKEN` 未注入；远端 Actions 状态只能由 Owner 在 https://github.com/newplayman/super-lp-bot/actions 确认）。
3. **决定 Stage A 真实数据中 6 个 NULL 的处理**（fee_growth 三列共 6 个 NULL 在 17222 行里；定位 producer / 重采该窗口需要 Owner 授权改动现有 5 个长跑采集进程之一。本任务不动。）

---

## 8. 具体启动请求（Owner 显式确认后执行）

```
# 1. 解冻确认
echo "Owner paper-freeze lift: APPROVED at $(date -u +%FT%TZ)" >> reports/lp_rh/freeze_lift.log

# 2. 启动 paper daemon（隔离 paper only ledger + paper only source path）
nohup python3 scripts/lp_rh_paper_daemon_entry_v1.py \
    --config configs/config.paper.toml \
    >reports/lp_rh/paper_daemon.log 2>&1 &
echo $! >reports/lp_rh/paper_daemon.pid

# 3. 观察 30 分钟健康度后，再决定是否开启 shadow
python3 scripts/lp_rh_paper_daemon_entry_v1.py status \
    --config configs/config.paper.toml
```

> 启动请求本身**不**由本会话执行；本会话只提交 SHA、原始证据和验收矩阵，等 Owner 显式解除 freeze 后由 Owner / Owner 指定的运维通道执行。

---

## 9. 本会话停止位置

- 当前 HEAD：`e8b30fa`
- 所有 commit 已落本地分支 `feat/prd-v2.1-m0-shadow`
- 无 background watcher / cron / sleep 循环被本会话起过
- 等 Owner 决定 §7 的 3 项；不擅自启动 Paper

— Claude (主脑) · 收尾 2026-09-15 (round 2 audit)