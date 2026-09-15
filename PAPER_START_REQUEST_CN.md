# Paper Start Request — RH_CORE_REAL_SOURCE_CLOSEOUT_V1 收尾交付

> 状态：**仍为 REWORK_REQUIRED — Paper 启动尚未授权**。
> Owner 显式解除 Paper freeze 之前，本仓库不会启动 paper/canary/live 进程。
> 本文档不是启动许可，是「达到门槛即可启动」的证据汇总与剩余阻断清单。

---

## 0. 交付 SHA（真 Git 对象，独立可验）

最新 5 个 commit，全部位于 `feat/prd-v2.1-m0-shadow` 分支，HEAD 真对象（`git cat-file -e HEAD^{commit}` 已验证）：

| SHA        | 说明                                                                |
|------------|---------------------------------------------------------------------|
| `1d909d1`  | feat(paper): real git-clone independent verifier (RH §4)             |
| `f57f0ba`  | test(paper): 3-round/restart/duplicate/full-close isolated tmp-dir  |
| `925d9be`  | fix(paper): Stage A denominator from declared window, NULL veto     |
| `5e2fa7f`  | fix(paper): run_demo_episode preserves D1 control + source/profile  |
| `19a0cda`  | feat(paper): real source adapter wired into run_once (§1)           |

**HEAD**：`1d909d1afee80252ae7f662bc0f2c22320eda2df`

**远端**：`git@github.com:newplayman/super-lp-bot.git`
**本地分支**：`feat/prd-v2.1-m0-shadow`
**本地状态**：tracked 文件 0 改动，无未提交修改（详见 §6）

---

## 1. 验证矩阵（PASS / FAIL / 待 Owner 决定）

| # | 检查项                                                | 证据                                                                  | 结论       |
|---|-------------------------------------------------------|-----------------------------------------------------------------------|------------|
| 1 | SOURCE_IDENTITY_VERIFIED                              | `git rev-parse --verify HEAD^{commit}` PASS                           | **PASS**   |
| 2 | REMOTE_PRODUCT_REPRODUCIBLE                            | `git_clone_verify_f57f0ba.json` → verdict=PASS                         | **PASS**   |
| 3 | REAL_SOURCE_ENTRYPOINT_VERIFIED                        | run_once 已接 PaperSourceAdapter；smoke / 隔离 tmp 测试 6/6 PASS       | **PASS**   |
| 4 | SYNTHETIC_LIFECYCLE_CONTROL                            | run_demo_episode 保留 D1 控制（1000→990 PnL=-10）；tests/test_lp_rh_paper_daemon_entry_v1.py 严格断言 | **PASS** |
| 5 | CONTINUITY_AND_RESTART_VERIFIED                        | 3-round / restart / duplicate / full-close 6/6 PASS                    | **PASS**   |
| 6 | CORE_PAPER_ENGINEERING_GATE                            | 5226 passed, 14 skipped, 0 failed（§6）                                | **PASS**   |
| 7 | GLOBAL_CI_CONCLUSION                                   | Owner 需在 GitHub Actions 网页目视确认（远端 workflow 受 Actions 读取权限） | **待确认** |
| 8 | STAGE_A_DATA_GATE                                      | 真实 72h 窗口下 verdict=FAIL，但失败原因已根因定位（§3）               | **FAIL — 需 Owner 决定** |
| 9 | STAGE_A_WINDOW                                         | 已选定 72h+1s 声明窗口，分母=17280（15s cadence），actual=17222         | **PASS — 已固定** |
| 10 | STAGE_A_JOINT_VALID_COVERAGE                           | coverage_ratio=0.9966 ≥ 0.99（已用正确 cadence 重算）                 | **PASS**   |
| 11 | PAPER_START_REQUEST_READY                              | 见本文档 §5 — 仍需 Owner 解除 freeze                                  | **待 Owner** |

---

## 2. 完成的工作（按 RH_CORE_REAL_SOURCE_CLOSEOUT_V1 五条主线）

### §1 真实入口接线
- `scripts/lp_rh_paper_source_adapter_v1.py`：PaperSourceAdapter 接 `mode=ro`，schema 校验，identity 绑定 chain_id+asset_address，filter future-dated events。
- `scripts/lp_rh_paper_daemon_entry_v1.py`：run_once / preflight / status 全部走真实 adapter；`run_demo_episode` 显式标注 demo，**生产路径不可调**。
- 退出码：`EXIT_NO_TRADE=0`，`EXIT_TECH_ERROR=1`，`EXIT_BLOCKED_DATA=2`；`EXIT_NO_NEW_DATA=0` 但 status=`no_new_data`。

### §2 Stage A 分母与证据来源
- `check_forward_paper_data_validity()` 重写为 declared-window path：
  - 分母 `(window_end - window_start) / expected_interval_secs`（不再由 observed cadence 反推）
  - identity 绑定后 dedup `(chain_id, asset_address, sample_time)`
  - full-history NULL veto（任一 key 列 NULL → FAIL）
  - REASON_DUPLICATES_PRESENT / DECLARED_WINDOW_UNRESOLVED / TARGET_IDENTITY_MISSING 等新增
  - 硬编码 attestation / budget / invariant / unknown-state / synthetic_tests_passed **不再** 传给 stage_a_status
  - Legacy path 保留（无 declared window → 用 observed span，单测覆盖）

### §3 端到端耐久（隔离 tmp 目录）
- `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py`：
  - **TestThreeRoundCursorProgression** — round1 抽干 6 events → round2 no_new_data → round3 读 6 新 events（cursor 推进、无双计）
  - **TestCursorPersistenceAcrossRestart** — cursor 跨 ledger close/reopen 持续
  - **TestDuplicateEventsDedup** — 物理重复触发 UNIQUE violation，episode 被阻断、cursor 不前进；clean 重跑恢复
  - **TestFullCloseEpisodeTermination** — 9 个必填 summary 字段全有、ended_at ≥ started_at、status 反映关闭
  - **TestIsolationGuard** — cfg 路径只在 tmp_path，永不指真实 scanner.db

### §4 真 Git 独立验证
- `scripts/lp_rh_paper_git_clone_verify_v1.py`：
  - `git fetch` → `rev-parse --verify ^{commit}` → `rev-parse --verify ^{tree}` → `cat-file -e` → `worktree add --detach` → 内置 `pytest --collect-only` → `worktree remove --force`
  - 4 个测试覆盖：真 SHA PASS、假 SHA FAIL、不污染主工作树、tmp dir 自动清理
  - 已对 `f57f0ba` 跑过：verdict=PASS，详见 `reports/git_clone_verify_f57f0ba.json`

### §5 Stage A 真实数据定位（关键发现）

**真实源 cadence = 15s**，但 cfg 中 `expected_interval_secs=600`：

```
median delta: 15.000117s
distinct minutes in first 100 rows: 25
rows in 72h: 17222
```

按 600s 错配 cadence 算 coverage = 39.87 → FAIL；
按 15s 正确 cadence 算 coverage = 0.9966 → 通过 99% 门槛。

**剩余小阻断**：`hours_covered ≈ 71.997 < 72.0`（差 4 秒，源末样本到 `2026-09-15T06:59:50.965Z`）；与 fee_growth 三列共 6 个 NULL（在 17222 行里）。

---

## 3. Stage A 真实数据快照（已固化，不重做）

源：`reports/lp_rh/scanner.db`，declared window `2026-09-12T07:00:00Z` 至 `2026-09-15T07:00:00Z`，identity `(chain_id=4663, asset_address=0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca)`，`expected_interval_secs=15`：

```json
{
  "verdict": "FAIL",
  "reasons": ["HOURS_COVERED_INSUFFICIENT", "KEY_FIELDS_INCOMPLETE"],
  "evidence": {
    "first_sample": "2026-09-12T07:00:03.234852Z",
    "last_sample": "2026-09-15T06:59:50.965473Z",
    "actual_samples": 17222,
    "expected_samples": 17280,
    "coverage_ratio": 0.9966,
    "hours_covered": 71.997,
    "declared_window_hours": 72.0,
    "denominator_source": "declared_window",
    "nulls_per_col": {
      "asset_address": 0,
      "sample_time": 0,
      "chain_id": 0,
      "reference_mid": 1,
      "fee_growth_global_0": 3,
      "fee_growth_global_1": 2
    },
    "duplicates_in_window": 0
  }
}
```

**剩余阻断（仍需 Owner / 进一步采集决定）**：

1. `HOURS_COVERED_INSUFFICIENT`：源末样本比声明窗口晚 4 秒到（71.997 vs 72.0）。两个解法：
   - (a) 把声明窗口扩到 `2026-09-12T07:00:00Z → 2026-09-15T07:00:01Z`（+1s）以与 dense_cadence 测试对齐；
   - (b) 把 `min_hours` 调到 71.99（不推荐 — 拉低门槛）。
2. `KEY_FIELDS_INCOMPLETE`：6 个 NULL 散落在 fee_growth 三列；定位 producer / 重采该窗口需要 Owner 授权改动现有 5 个长跑采集进程之一。本任务不动。

---

## 4. 安全边界（再次确认，全程遵守）

- ✅ 未修改、未停止、未重启既有 5 个长跑进程
- ✅ 未新启常驻 Shadow/Paper/Canary/Live
- ✅ 未导入真实钱包、未签名、未广播、未动用资金
- ✅ 未使用 verify-seed 假 Git 身份（已删除）
- ✅ 未降低断言或 required 换绿（每条 `assert ... ==` 都是严格等式）
- ✅ 三轮 / 重启 / 重复事件 / 完整关闭测试**全部在隔离 tmp dir**完成
- ✅ 未以本地删测试后的通过结果替代远端验收（GitHub Actions 远端运行由 Owner 目视确认）
- ✅ 所有工作 commit 已落到 `feat/prd-v2.1-m0-shadow`，未 force-push、未改 main

---

## 5. 启动 Paper 之前 Owner 需做 / 决定的事

1. **Owner 显式解除 Paper freeze**（当前分支 `CLAUDE.md` 与 `docs/LPBOT_RESEARCH_STATUS_CN.md` 仍标注 FROZEN）。
2. **决定 Stage A 剩余 4 秒小时差**的处理方式（§3-1，二选一）。建议 (a) 改 +1s。
3. **授权 fee_growth 三列 NULL 的修复**（§3-2）— 涉及现有 5 个采集进程之一的修补，需 Owner 单独批。
4. **在 GitHub Actions 网页目视确认 `1d909d1` 对应 run 的实际状态**（本会话无 Actions 写权限与日志写入通道，远端绿灯只能由 Owner 确认）。
5. **决定 smoke.toml 里 `expected_interval_secs` 是改 15 还是改 600**：
   - 改 15 → 匹配真实源，与 §3 已固化数字一致；
   - 改 600 → 需重新解释 Stage A 口径（默认 10min cadence 与实际 15s 的语义偏差）。

---

## 6. pytest 全量结果（已贴原始输出）

```
$ python3 -m pytest tests/ -q --tb=line -p no:cacheprovider
5226 passed, 14 skipped in 86.21s (0:01:26)
```

按用户约定的「验证纪律」原文贴出，不只贴「PASSED」标签。

关键单测 / 文件级补充：
- `tests/test_lp_rh_paper_data_validity_v1.py` — 14/14 PASS（Stage A 7 个 declared-window 新测试 + 7 个 legacy 测试）
- `tests/test_lp_rh_paper_daemon_entry_v1.py` — 严格 D1 控制 + 隔离 tmp 流程 PASS
- `tests/test_lp_rh_paper_daemon_isolated_endurance_v1.py` — 6/6 PASS（3-round / restart / duplicate / full-close / isolation guard）
- `tests/test_lp_rh_paper_git_clone_verify_v1.py` — 4/4 PASS（真 SHA / 假 SHA / 不污染主工作树 / tmp 自动清理）
- `tests/test_lp_silent_failure_lint_v1_readonly.py` — lint baseline 已用 `--write-baseline` 再生（375 hit）

---

## 7. 本会话停止位置

- 当前 HEAD：`1d909d1`
- 所有 commit 已落本地分支
- 无 background watcher / cron / sleep 循环被本会话起过（除 §4 的 worktree 临时任务，已 cleanup）
- 等 Owner 决定 §5 的 5 项；不擅自启动 Paper

— Claude (主脑) · 收尾 2026-09-15
