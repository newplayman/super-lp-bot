# READ_FIRST_20260914_CN.md

**owner 验收必读**：本轮任务（commit 4da8bc0 → 后续本任务 commit 起点）的执行概要。

## 1. 一句话摘要

只读闭环复跑 + 5 个 B/C/D/E/F 任务交付完毕，OBSERVE_ONLY 维持，
**未启动 paper / live，未推送远端**，等 owner 视觉验收 GitHub Actions 后再决定。

## 2. 阅读顺序（10 分钟）

1. **`FINAL_VERDICT_20260914_CN.md`** — 一表说清 PASS/FAIL、本期 vs 残留 blockers
2. **`OBSERVE_ONLY_DECISION_RULES_CN.md`** — 5 条 hard gate + 允许/阻断动作清单
3. **`ACCEPTANCE_EVIDENCE_20260914_CN.md`** — pytest / audit_repro / 5 进程审计原文
4. **`SCOPE_REQUEST_20260914_CN.md`** — 本期改了哪些文件 + owner 决策请求
5. **`BLOCKERS_20260914_CN.csv`** — 11 条 blocker 状态（5 残留 + 6 已 RESOLVED）
6. **`CI_EVIDENCE_20260914_CN.md`** — 本地 CI 等价证据 + owner 推送后待填字段
7. **`VULNERABILITY_RESOLUTION_20260914_CN.md`** — 9 漏洞修复 + 5 残留原因

## 3. 关键事实（直接抄送）

- HEAD = `4da8bc0`（本任务起点）
- TASK_STARTED_MODE = `NONE`
- HOST_EXISTING_RH_READONLY_PROCESSES = `5`（PID 列表见 OBSERVE_ONLY_DECISION_RULES_CN.md §7）
- pytest = `5201 passed / 0 failed / 14 skipped`
- audit_repro = `defects=0, probe_errors=0`
- CORE_PAPER_ENGINEERING_GATE = `FAIL`（已知；详见 BLOCKERS.csv）

## 4. 立即可执行（无需 owner 批准）

- 阅读本目录所有 .md
- 在本地跑 `python3 -m pytest tests/ -q --tb=line -p no:cacheprovider`
- 跑 `python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head --json-out /tmp/x.json`
- 跑 `cat reports/lp_rh/STAGE_A_REQUALIFICATION.json` 复核 5 进程
- 跑 `ps -p 2271374,157737,119849,118592,2685886` 复核存活

## 5. 需 owner 决策

| 决策 | 推荐 |
|------|------|
| 是否推送本轮 commit | 是 |
| 是否继续 OBSERVE_ONLY | 是 |
| 是否扩 scope 到 R3 REWORK 余下分支 | 否（下次迭代） |
| 是否重启 5 个长跑进程 | 否 |
| 是否把 `tiny_live_authorized` 改 true | **否**（CLAUDE.md freeze 强约束） |

## 6. 不要做的事

- ❌ 删 `reports/lp_rh/scanner.db` 或触发 `_run_episode_persisted` 之外的手动 schema 改写
- ❌ 直接编辑 `reports/lp_rh/GRADUATION_VERDICT.json` 改 verdict 字段
- ❌ 关闭 GitHub Actions workflow
- ❌ 在 `git status` 之外手动 push 到 origin