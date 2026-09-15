# Paper Start Request — RH_CORE_REAL_SOURCE_CLOSEOUT_V1 收尾交付（第二轮）

> 状态：**REWORK 收尾完成 — Paper 启动授权仍需 Owner 显式决定**。
> Owner 显式解除 Paper freeze 之前，本仓库不会启动 paper/canary/live 进程。
> 本文档不是启动许可，是「S1-S4 全部闭环 + 达到技术门槛」的证据汇总。
> 提交 SHA = `5e72d5d`，HEAD 真对象已通过 verifier 独立验证（pytest rc=0、audit_repro rc=0、defects=0、probe_errors=0）。

---

## 0. 交付 SHA（真 Git 对象，独立可验）

最新 5 个 commit，全部位于 `feat/prd-v2.1-m0-shadow` 分支，HEAD 真对象（`git cat-file -e HEAD^{commit}` 已验证）：

| SHA        | 说明                                                                       |
|------------|----------------------------------------------------------------------------|
| `5e72d5d`  | fix(paper): exclude recursive verifier test from verifier pytest run      |
| `e5158b6`  | fix(paper): S4 verifier runs real pytest + audit_repro, gates on rc        |
| `6f01a6b`  | fix(paper): S3 Stage A grid-aligned hours gate                             |
| `0b27527`  | fix(paper): S2 engine+summary+cursor in single transaction                |
| `c912d61`  | fix(paper): S1 wire reference_age_secs + source_event_time from real source|

**HEAD**：`5e72d5ddc775e0c95b6b99611f0c67cd6195ec85`（注：commit hash 与上述 list 中 e5158b6 同 prefix，e5158b6 自身是 S4 commit，5e72d5d 是其修复递归 verifier 的微调。verifier 报告 verbatim：`"wt_head": "5e72d5ddc775e0c95b6b99611f0c67cd6195ec85"`）

**远端**：`git@github.com:newplayman/super-lp-bot.git`
**本地分支**：`feat/prd-v2.1-m0-shadow`
**本地状态**：tracked 文件 0 改动，无未提交修改（详见 §6）
**Verifier 证据**：`reports/git_clone_verify_5e72d5d.json` → verdict=PASS, pytest_run.rc=0, audit_repro_run.rc=0, defects_reproduced=0, probe_errors=0

---

## 1. S1-S4 闭环证据表（Owner 给定 4 项阻断）

| # | 阻断项                                                                              | 修复                                                                                                                                                                                            | 证据文件 / 测试                                                                       | 结论     |
|---|-------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|----------|
| S1 | 生产路径混入 PAPER_SAMPLE_BASE / PAPER_POOL_META_FRESH / 模拟成本归零 / 来源时间身份未贯通 | 1) `REQUIRED_EVENT_COLUMNS` 增 `reference_age_secs` + `source_event_time`（真实 rh_market_states 已有列）；2) adapter SQL 同步增列、过滤 NULL；3) `_events_to_samples` 直接读 event、fail-closed 缺列；4) pool_meta 改读源 DB `rh_pool_meta` 表（不再是 fixture）；5) 引擎参数全部从 cfg `[engine_params]`（必需键缺失 → SourceConfigError 阻断）；6) cost 来源从 cfg `[costs.defaults]` 或 per-event 注入；7) identity `chain_id`/`asset_address`/`source_event_time` 嵌入样本与 engine_cfg；8) pool_meta SQL 改 `LOWER(pool_address)=LOWER(?)`（rule 3 通过） | `tests/test_lp_rh_paper_daemon_entry_v1.py`（11/11 PASS）, `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py`（7/7 PASS） | **CLOSED** |
| S2 | 内层业务 commit 与外层 summary/cursor 分离、cursor 测试未证非零仓位经济连续性 | 1) `_run_episode_persisted` 新增 `defer_commit` 参数，调用方打开事务时 engine 内层 commit 改为 no-op；2) daemon 入口 `BEGIN IMMEDIATE` 包住 engine + summary + cursor 三个写操作，单次 commit；3) 新增 `TestEconomicContinuityAcrossEpisodes::test_engine_summary_cursor_are_one_transaction`：两轮 episode 跑完，读 ledger 三表（summary、journal/positions/gates、cursor）做原子性不变量校验（distinct episode_id ≤ summary 行数 = cursor 行数 = 1） | `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py::TestEconomicContinuityAcrossEpisodes`（PASS） | **CLOSED** |
| S3 | 声明 72h 半开窗口却要求首末样本跨度=72h、distinct 时间戳不等于联合有效计划格 | 1) `hours_covered` 公式由 `(last - first) / 3600` 改为 `actual_samples * expected_interval_secs / 3600`（grid-aligned）；2) `evidence` 同时保留 `observed_span_hours` 作为诊断字段；3) 新增两条测试：`grid_aligned_hours_passes_when_first_sample_late`（首末各偏移 30s，grid=72.17h, span=71.98h，仍 PASS）；`grid_aligned_hours_fails_when_too_few_samples`（425×600s=70.83h < 71h，FAIL 回归保护） | `tests/test_lp_rh_paper_data_validity_v1.py::TestDeclaredWindow` 新增 2 测试 + 14 旧测试全 PASS | **CLOSED** |
| S4 | 独立验证器只 collect 不检查退出码、最终 SHA 实际 CI 仍失败 | 1) verifier 不再 `pytest --collect-only`，改为真实跑 pytest（4 个 paper-readiness 模块）+ `tools/audit_repro/audit_repro.py --repo --allow-other-head`；2) 捕获 rc + summary 行 + defects/probe_errors；3) verdict 必须 pytest rc=0 且 audit_repro rc=0 才 PASS；4) 修复 verifier 暴露的 entry 测试 fixture bug：`REPO_ROOT/reports/lp_rh/scanner.db` 硬编码改为 tmp_path 内的 stub scanner.db（含必需列 + 1 条 event） | `tests/test_lp_rh_paper_git_clone_verify_v1.py`（4/4 PASS），verifier 自身 verdict=PASS | **CLOSED** |

---

## 2. pytest 全量结果

```
$ python3 -m pytest tests/ -q --tb=line -p no:cacheprovider
5229 passed, 14 skipped in 87.98s (0:01:27)
```

按用户约定的「验证纪律」原文贴出，不只贴「PASSED」标签。

S1-S4 新增测试分布：

| 测试套件                                                | 新增/修改 | 关键断言                                                                                            |
|--------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------------|
| `tests/test_lp_rh_paper_daemon_entry_v1.py`           | 改 fixture | `_write_config` 改用 tmp_path stub scanner.db；5 个 preflight 测试在 worktree 也能 PASS              |
| `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py` | +1 测试    | `TestEconomicContinuityAcrossEpisodes::test_engine_summary_cursor_are_one_transaction`              |
| `tests/test_lp_rh_paper_data_validity_v1.py`          | +2 测试    | `grid_aligned_hours_passes_when_first_sample_late` / `grid_aligned_hours_fails_when_too_few_samples` |
| `tests/test_lp_rh_paper_git_clone_verify_v1.py`       | 改断言     | `test_real_sha_passes` 增加 `pytest_run.rc==0` 与 `audit_repro_run.rc==0` 断言                       |

---

## 3. Verifier 独立证据（`reports/git_clone_verify_5e72d5d.json`）

```json
{
  "candidate": "5e72d5d...",
  "steps": {
    "1_fetch": {"ok": true},
    "2_commit_object": {"ok": true},
    "3_tree_object": {"ok": true},
    "4_cat_file": {"ok": true},
    "5_worktree_add": {"ok": true},
    "6_worktree_verify": {
      "wt_head_matches_candidate": true,
      "wt_status_porcelain_empty": true,
      "wt_tree_top_level_count": 84,
      "pytest_run": {
        "rc": 0,
        "passed": true,
        "summary_line": "52 passed in ~2s"
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

---

## 4. 完成的工作（按 RH_CORE_REAL_SOURCE_CLOSEOUT_V1 五条主线）

### §1 真实入口接线（S1 增强）
- `scripts/lp_rh_paper_source_adapter_v1.py`：PaperSourceAdapter 接 `mode=ro`，REQUIRED_EVENT_COLUMNS 增 `reference_age_secs` + `source_event_time`（真实 rh_market_states 已有列）；SQL 同时读这两列并过滤 NULL。
- `scripts/lp_rh_paper_daemon_entry_v1.py`：run_once / preflight / status 全部走真实 adapter；`_events_to_samples` 直接读 event + cfg engine_params + cfg costs，无 PAPER_SAMPLE_BASE / 无零成本兜底；pool_meta 从源 DB `rh_pool_meta` 读（SQL `LOWER(pool_address)=LOWER(?)` 满足 rule 3）；identity 嵌入样本与 engine_cfg；`_run_episode_persisted(defer_commit=True)` 让 engine + summary + cursor 三次写共用一个事务。
- 退出码：`EXIT_NO_TRADE=0`，`EXIT_TECH_ERROR=1`，`EXIT_BLOCKED_DATA=2`；`EXIT_NO_NEW_DATA=0` 但 status=`no_new_data`。

### §2 Stage A 分母与证据来源（S3 增强）
- `check_forward_paper_data_validity()` declared-window path：
  - 分母 `(window_end - window_start) / expected_interval_secs`
  - identity 绑定后 dedup `(chain_id, asset_address, sample_time)`
  - full-history NULL veto
  - `hours_covered` 改 grid-aligned：`actual_samples * expected_interval_secs / 3600`（不要求首末跨度=72h）
  - `observed_span_hours` 仍作为诊断字段
  - `hours_formula="grid_aligned"` 标记新语义

### §3 端到端耐久（隔离 tmp 目录，S2 新增 economic continuity）
- `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py`：
  - `TestThreeRoundCursorProgression` — round1 抽干 → round2 no_new_data → round3 读新
  - `TestCursorPersistenceAcrossRestart` — cursor 跨 ledger close/reopen 持续
  - `TestDuplicateEventsDedup` — 物理重复触发 UNIQUE violation，episode 阻断
  - `TestFullCloseEpisodeTermination` — 9 个必填 summary 字段全有
  - `TestIsolationGuard` — cfg 路径只在 tmp_path
  - **`TestEconomicContinuityAcrossEpisodes`（S2 新增）** — 两轮 episode，跑完读 ledger 三表做不变量校验：distinct episode_id ≤ summary 行数 = cursor 行数 = 1，原子性签名

### §4 真 Git 独立验证（S4 增强）
- `scripts/lp_rh_paper_git_clone_verify_v1.py`：
  - `git fetch` → `rev-parse --verify ^{commit}` → `rev-parse --verify ^{tree}` → `cat-file -e` → `worktree add --detach` → 真实 `pytest tests/...` + `audit_repro.py --repo --allow-other-head` → `worktree remove --force`
  - verdict 必须 pytest rc=0 且 audit_repro rc=0
  - 4 个测试覆盖真 SHA PASS / 假 SHA FAIL / 不污染主工作树 / tmp 自动清理

---

## 5. 安全边界（再次确认，全程遵守）

- ✅ 未修改、未停止、未重启既有 5 个长跑进程
- ✅ 未新启常驻 Shadow/Paper/Canary/Live
- ✅ 未导入真实钱包、未签名、未广播、未动用资金
- ✅ 未放宽 `live_allowed`
- ✅ 测试全部在隔离 tmp dir（worktree 测试另在 `/tmp/lpbot_git_verify_*`）
- ✅ S1-S4 所有 commit 已落本地分支 `feat/prd-v2.1-m0-shadow`，未 force-push、未改 main

---

## 6. 启动 Paper 之前 Owner 仍需做 / 决定的事

1. **Owner 显式解除 Paper freeze**（当前 `CLAUDE.md` 与 `docs/LPBOT_RESEARCH_STATUS_CN.md` 仍标注 FROZEN）。
2. **在 GitHub Actions 网页目视确认 `5e72d5d` 对应 run 的实际状态**（本会话无 Actions 写权限与日志写入通道，远端绿灯只能由 Owner 确认）。
3. **决定 Stage A 真实数据中 6 个 NULL 的处理**（fee_growth 三列共 6 个 NULL 在 17222 行里；定位 producer / 重采该窗口需要 Owner 授权改动现有 5 个长跑采集进程之一。本任务不动。）

---

## 7. 本会话停止位置

- 当前 HEAD：`5e72d5d`
- 所有 commit 已落本地分支
- 无 background watcher / cron / sleep 循环被本会话起过
- 等 Owner 决定 §6 的 3 项；不擅自启动 Paper

— Claude (主脑) · 收尾 2026-09-15
