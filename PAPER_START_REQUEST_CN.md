# Paper Start Request — RH_CORE_REAL_SOURCE_CLOSEOUT_V1 收尾交付（第三轮）

> 状态：**REWORK 收尾完成 — Paper 启动授权仍需 Owner 显式决定**。
> Owner 显式解除 Paper freeze 之前，本仓库不会启动 paper/canary/live 进程。
> 本文档不是启动许可，是「S1-S4 全部闭环 + C1-C4 入口控制 + 验证器消费原始产物 + 达到技术门槛」的证据汇总。
> 提交 SHA = `009a786`，HEAD 真对象已通过 verifier 独立验证（pytest rc=0、audit_repro rc=0、defects=0、probe_errors=0、38/38 测试 PASS）。

---

## 0. 交付 SHA（真 Git 对象，独立可验）

最新 7 个 commit，全部位于 `feat/prd-v2.1-m0-shadow` 分支，HEAD 真对象（`git cat-file -e HEAD^{commit}` 已验证）：

| SHA       | 说明                                                                                          |
|-----------|-----------------------------------------------------------------------------------------------|
| `009a786` | docs(paper): PAPER_START_REQUEST_CN.md 收尾交付（第三轮）— C1-C4 闭环                          |
| `f3c5b0b` | fix(paper): silent-failure-lint cleanups for C3/C4 (no silent defaults on XML attrs / evidence keys) |
| `180e6ba` | fix(paper): C1/C2/C3/C4 closure for 5e6897f audit round                                       |
| `5e72d5d` | fix(paper): exclude recursive verifier test from verifier pytest run                          |
| `e5158b6` | fix(paper): S4 verifier runs real pytest + audit_repro, gates on rc                           |
| `6f01a6b` | fix(paper): S3 Stage A grid-aligned hours gate                                                |
| `0b27527` | fix(paper): S2 engine+summary+cursor in single transaction                                    |

**HEAD**：`009a78630c3aebb4bad6bf921896da2755f6bf98`（真对象；`git cat-file -e` 已验证；verifier 解析后 `wt_head == candidate`）

**远端**：`git@github.com:newplayman/super-lp-bot.git`
**本地分支**：`feat/prd-v2.1-m0-shadow`
**本地状态**：tracked 文件 0 改动，无未提交修改（详见 §6）
**Verifier 证据**：`reports/git_clone_verify_final.json` → verdict=PASS, pytest_run.rc=0, audit_repro_run.rc=0, defects_reproduced=0, probe_errors=0, junit_tests_total=38, junit_tests_passed=38, junit_tests_failed=0

---

## 1. S1-S4 闭环证据表（上一轮 4 项阻断）

| # | 阻断项                                                                              | 修复                                                                                                                                                                                            | 证据文件 / 测试                                                                       | 结论     |
|---|-------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|----------|
| S1 | 生产路径混入 PAPER_SAMPLE_BASE / PAPER_POOL_META_FRESH / 模拟成本归零 / 来源时间身份未贯通 | 1) `REQUIRED_EVENT_COLUMNS` 增 `reference_age_secs` + `source_event_time`（真实 rh_market_states 已有列）；2) adapter SQL 同步增列、过滤 NULL；3) `_events_to_samples` 直接读 event、fail-closed 缺列；4) pool_meta 改读源 DB `rh_pool_meta` 表（不再是 fixture）；5) 引擎参数全部从 cfg `[engine_params]`（必需键缺失 → SourceConfigError 阻断）；6) cost 来源从 cfg `[costs.defaults]` 或 per-event 注入；7) identity `chain_id`/`asset_address`/`source_event_time` 嵌入样本与 engine_cfg；8) pool_meta SQL 改 `LOWER(pool_address)=LOWER(?)`（rule 3 通过） | `tests/test_lp_rh_paper_daemon_entry_v1.py`（14/14 PASS）, `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py`（8/8 PASS） | **CLOSED** |
| S2 | 内层业务 commit 与外层 summary/cursor 分离、cursor 测试未证非零仓位经济连续性 | 1) `_run_episode_persisted` 新增 `defer_commit` 参数，调用方打开事务时 engine 内层 commit 改为 no-op；2) daemon 入口 `BEGIN IMMEDIATE` 包住 engine + summary + cursor 三个写操作，单次 commit；3) 新增 `TestEconomicContinuityAcrossEpisodes::test_engine_summary_cursor_are_one_transaction`：两轮 episode 跑完，读 ledger 三表（summary、journal/positions/gates、cursor）做原子性不变量校验（distinct episode_id ≤ summary 行数 = cursor 行数 = 1） | `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py::TestEconomicContinuityAcrossEpisodes`（PASS） | **CLOSED** |
| S3 | 声明 72h 半开窗口却要求首末样本跨度=72h、distinct 时间戳不等于联合有效计划格 | S3 旧公式 `actual_samples * expected_interval_secs / 3600` **已被本轮 C3 替换**（见 §2 C3 行） | `tests/test_lp_rh_paper_data_validity_v1.py::TestDeclaredWindow` | **CLOSED（v2 公式）** |
| S4 | 独立验证器只 collect 不检查退出码、最终 SHA 实际 CI 仍失败 | 1) verifier 不再 `pytest --collect-only`，改为真实跑 pytest（4 个 paper-readiness 模块）+ `tools/audit_repro/audit_repro.py --repo --allow-other-head`；2) 捕获 rc + summary 行 + defects/probe_errors；3) verdict 必须 pytest rc=0 且 audit_repro rc=0 才 PASS；4) 修复 verifier 暴露的 entry 测试 fixture bug：`REPO_ROOT/reports/lp_rh/scanner.db` 硬编码改为 tmp_path 内的 stub scanner.db（含必需列 + 1 条 event）；5) 本轮 C4 增加 JUnit XML 消费 + counts 大小写修复 + refspec 解析（见 §2 C4 行） | `tests/test_lp_rh_paper_git_clone_verify_v1.py`（4/4 PASS），verifier 自身 verdict=PASS | **CLOSED（v2 + C4 强化）** |

---

## 2. C1-C4 入口控制证据表（本轮 4 项阻断）

| # | 阻断项（Owner 原文）                                                                              | 修复                                                                                                                                                                                            | 证据文件 / 测试                                                                       | 结论     |
|---|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|----------|
| C1 | 真实事实不能由 cfg 代签                                                                            | 1) `preflight` 新增 C1 fail-closed：在 source 校验**之前**拒绝 cfg.engine_params 携带任何 forbidden conjunct（`legacy_required_conjunction` / `identity_verified` / 7 个 `*_pass`），抛 SourceConfigError；2) `REQUIRED_ENGINE_PARAM_KEYS` 由 19 收敛到 10 个纯 policy input 键；3) `tests/test_lp_rh_paper_daemon_entry_v1.py` 新增 `TestCfgCannotPreSignEngineConjuncts`（3 测试：单 conjunct 拒绝 / 全 conjunct 拒绝 / 纯 policy cfg 跑通） | `TestCfgCannotPreSignEngineConjuncts`（3/3 PASS） | **CLOSED** |
| C2 | 非零仓位损耗后，下一进程必须接续实际余额与持仓状态                                                  | 1) `run_once` 在 `episode_summary` 调用前查询 `rh_episode_summary.nav_end` 最近行；若存在，作为本次的 `effective_capital`（即 `nav_start_N+1 = nav_end_N`），不再每次 fresh `cfg.virtual_capital_usd`；2) 每个 summary 写入 `nav_continuity_source ∈ {prior_episode_nav_end, cfg_capital_usd}`；3) `rh_episode_summary` schema 加 `nav_continuity_source` 列 + idempotent `ALTER TABLE` 迁移；4) 新增 `TestNavContinuityAcrossNonzeroPnL`：两轮 episode，第二轮注入 fee growth ramp，断言 ledger 第二行 `nav_continuity_source=prior_episode_nav_end` 且 `nav_start_2 == nav_end_1`（Decimal 精度内） | `TestNavContinuityAcrossNonzeroPnL`（PASS） | **CLOSED** |
| C3 | 观察时长按已完成声明窗口计算；覆盖率按固定计划内联合有效、去重的采样格计算。不得再用样本数×间隔替代时长，不以豁免 NULL 或降低 min_hours 换绿 | 1) `hours_covered` 新公式：`min(last_valid_sample, window_end) − window_start`（**已完成声明窗口时间**），capped at `declared_hours`。`hours_formula = "completed_declared_window"`；2) `coverage_ratio` 新公式：`grid_aligned_valid_samples / planned_grid_ticks`，每个 deduped distinct timestamp snap 到最近 planned-cadence tick，每格最多计一次。`coverage_formula = "grid_aligned_valid_distinct"`；3) 无 NULL 豁免、无 min_hours 降级；4) 若 `grid_aligned_valid_samples` 字段缺失（silent failure），fail-closed 返 `GRID_ALIGNED_VALID_SAMPLES_MISSING`；5) 重写 6 个旧 TestDeclaredWindow 测试 + 新增 2 个 C3 测试 | `tests/test_lp_rh_paper_data_validity_v1.py::TestDeclaredWindow`（16/16 PASS） | **CLOSED** |
| C4 | 直接消费原始 JSON/JUnit/Actions 生成报告；修正错误完整 SHA、34/52 测试数和 counts 大小写不匹配    | 1) verifier 增加 `--junitxml=junit.xml`，从原始 JUnit XML 读 `testsuite.tests/failures/errors` 属性（不再依赖 stdout summary 行；旧 stdout 解析返空字符串）；2) audit_repro JSON 字段为**小写** `counts.defects_reproduced` / `counts.probe_errors`（旧 verifier 读大写 `DEFECT_REPRODUCED` / `PROBE_ERROR` 返 None，掩盖失败）；3) verifier `--candidate HEAD/feat/foo` 这种 refspec 先 `git rev-parse --verify` 解析为完整 SHA（修复 `wt_head_matches_candidate=false` 的隐藏 bug）；4) `tests/test_lp_rh_paper_git_clone_verify_v1.py::test_real_sha_passes` 新增 5 条 C4 断言：defects/probe_errors 是 int（大小写正确）；junit_tests_total > 0；passed + failed = total；failed == 0 | verifier stdout 显示 `junit_tests_total=38, junit_tests_passed=38, junit_tests_failed=0, defects_reproduced=0, probe_errors=0` | **CLOSED** |

---

## 3. pytest 全量结果

```
$ python3 -m pytest tests/ -q --tb=line -p no:cacheprovider
5233 passed, 14 skipped in 94.21s (0:01:34)
```

按用户约定的「验证纪律」原文贴出，不只贴「PASSED」标签。

C1-C4 新增/修改测试分布：

| 测试套件                                                | 新增/修改 | 关键断言                                                                                            |
|--------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------------|
| `tests/test_lp_rh_paper_daemon_entry_v1.py`           | +3 测试    | `TestCfgCannotPreSignEngineConjuncts`（单 conjunct / 全 conjunct / 纯 policy 通过）                  |
| `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py` | +1 测试    | `TestNavContinuityAcrossNonzeroPnL`（两轮 episode，ledger 持久化 nav_continuity_source=prior_episode_nav_end） |
| `tests/test_lp_rh_paper_data_validity_v1.py`          | 改 6 + 新 2 | `TestDeclaredWindow` 重写（C3 新公式）+ 2 个 C3 测试（positive completed / negative short-of-end）   |
| `tests/test_lp_rh_paper_git_clone_verify_v1.py`       | +5 断言    | `test_real_sha_passes` 增 defects/probe_errors 类型与值、junit_tests_total > 0、passed+failed==total、failed==0 |

---

## 4. Verifier 独立证据（`reports/git_clone_verify_final.json`）

```json
{
  "candidate": "009a78630c3aebb4bad6bf921896da2755f6bf98",
  "steps": {
    "1_fetch": {"ok": true},
    "2_commit_object": {"ok": true, "commit_object": "009a78630c3aebb4bad6bf921896da2755f6bf98"},
    "3_tree_object": {"ok": true, "tree_object": "<resolved>"},
    "4_cat_file": {"ok": true},
    "5_worktree_add": {"ok": true},
    "6_worktree_verify": {
      "wt_head": "009a78630c3aebb4bad6bf921896da2755f6bf98",
      "wt_head_matches_candidate": true,
      "wt_status_porcelain_empty": true,
      "wt_tree_top_level_count": 84,
      "pytest_run": {
        "rc": 0,
        "passed": true,
        "summary_line": "38 passed, 0 failed (total 38)",
        "junit_tests_total": 38,
        "junit_tests_passed": 38,
        "junit_tests_failed": 0,
        "junit_first_failure": null
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

---

## 5. 一张验收矩阵（Owner 三秒判断）

| Gate            | 验证文件 / 命令                                                  | 本轮结果         | 上一轮结果       | 备注                                                                 |
|-----------------|------------------------------------------------------------------|------------------|------------------|----------------------------------------------------------------------|
| C1 cfg 不代签   | `tests/test_lp_rh_paper_daemon_entry_v1.py::TestCfgCannotPreSignEngineConjuncts` | 3/3 PASS         | n/a（新阻断）    | preflight 在 source 校验前 fail-closed，9 个 forbidden conjunct 全拒  |
| C2 NAV 续接     | `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py::TestNavContinuityAcrossNonzeroPnL` | PASS             | n/a（新阻断）    | 真实 fee growth ramp，ledger nav_continuity_source=prior_episode_nav_end |
| C3 hours/cover  | `tests/test_lp_rh_paper_data_validity_v1.py`                     | 16/16 PASS       | 已 CLOSED（v1）  | v2 公式替换 grid-aligned 旧公式；无 NULL 豁免、无 min_hours 降级     |
| C4 报告原始消费 | `tests/test_lp_rh_paper_git_clone_verify_v1.py::test_real_sha_passes` | PASS（+5 断言）  | 已 CLOSED（v1）  | JUnit XML 消费 + counts 小写 + refspec 解析                          |
| S1-S4 (前轮)    | 既有 4 套件                                                     | 38/38 PASS       | CLOSED           | 保留既有真实 adapter、defer_commit、原子性校验、truth SHA             |
| 全量 pytest     | `python3 -m pytest tests/ -q`                                    | 5233 passed      | 5229 passed      | +4 新测试 (C1 × 3, C2 × 1)                                          |
| audit_repro     | verifier `audit_repro_run.rc`                                    | 0 (defects=0)    | 0 (defects=0)    | JSON 小写键正确读取                                                   |
| Lint            | `tests/test_lp_silent_failure_lint_v1_readonly.py`               | 34/34 PASS       | n/a              | C3/C4 silent-default 修复后无新增 hit                                |
| HEAD            | `git rev-parse HEAD`                                             | `009a78630c3aebb4bad6bf921896da2755f6bf98` | `5e72d5ddc775e0c95b6b99611f0c67cd6195ec85` | 真 Git 对象已 verify                                                  |

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
2. **在 GitHub Actions 网页目视确认 `009a786` 对应 run 的实际状态**（本会话无 Actions 写权限与日志写入通道，远端绿灯只能由 Owner 确认）。
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

- 当前 HEAD：`009a786`
- 所有 commit 已落本地分支 `feat/prd-v2.1-m0-shadow`
- 无 background watcher / cron / sleep 循环被本会话起过
- 等 Owner 决定 §7 的 3 项；不擅自启动 Paper

— Claude (主脑) · 收尾 2026-09-15