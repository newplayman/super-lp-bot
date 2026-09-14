# RH CORE Observe → Paper 收敛交付件（feat/prd-v2.1-m0-shadow）

**任务包**：RH_CORE_OBSERVE_TO_PAPER_CONVERGENCE_V1
**任务书**：`/tmp/shadow_paper_audit/SUPER_LP_SHADOW_PAPER_CONVERGENCE_20260914/CODEX_NEXT_TASK_CN.md`
**交付目录**：`reports/shadow_paper_convergence_20260914/`
**最终审查 SHA**：`7dd4e6458ad43e964b17b0a58258b198cdab4c65`（代码）+ `fd0ffa6df136de8dc3849d237ca16aa9a0a9eaa4`（HEAD 含纯文档 commit）
**最终 CI run**：[#34815907654](https://github.com/newplayman/super-lp-bot/actions/runs/34815907654)
**复审 SHA 真实业务证据**：`fd0ffa6`（见 `W2_RERUN_EVIDENCE.json`）

---

## 0. 一句话结论

把外部审计的 5 个失败点全部回应：**217 lint 已按"是否在目标模式依赖路径"分类**（Go 全侧 / Python CORE 0 引用），**Python 全量 5209 tests / 5136 passed / 59 failed 已逐 nodeid 定位到 4 类业务 bug**（非 pre-existing），**W2 G1/G4 已在最终 SHA fd0ffa6 真实复跑通过 45/45**（不是继承 752c583），**未启动任何 daemon、未签任何东西、未动任何资金**。W6 工程签收仍 BLOCKED，但**阻断集已收敛到 59 B-series + 1 G001 + 1 G002**，可独立修复。

---

## 1. 与上轮审计的对应（外审 5 点 → 本轮动作）

| 外审点 | 上轮状态 | 本轮动作 | 状态 |
|---|---|---|---|
| 217 lint 不能 blanket pre-existing | PRE_EXISTING_DEFERRED (整体豁免) | BLOCKERS.csv 子分类 7 子集（unused/revive/gosec/staticcheck/errcheck/gocritic/ineffassign）+ grep 验证 Go 不引用 Python CORE 符号（0 hit） | RESOLVED |
| 355/14 没有统计基础 | 错误统计 | 真实 pytest: collected=5209 / passed=5136 / failed=59 / errors=0 / skipped=14 / xfailed=0 / exit_code=1 | RESOLVED |
| W2 G1/G4 未在最终 SHA 复跑 | 沿用 752c583 继承 | W2_RERUN_EVIDENCE.json: 45/45 PASS on tested_sha=fd0ffa6 | RESOLVED |
| 不能假设 v1.65.0 与 v2.10.0 相同 finding | 假设同 | UNCLASSIFIED by P1.3.1 纪律（无可比基线），子分类用 linter rule + 路径分布证据 | RESOLVED |
| W6 不接受签收 | 错误签收 W6 | BLOCKED + W2 真实复跑通过仍显示 W6_ENGINEERING_SIGNOFF=BLOCKED（因为 B-series 还在阻断） | RESOLVED |

---

## 2. 最终状态（任务书 §8 报告字段）

```
LATEST_SOURCE_EXTERNALLY_AUDITABLE = true  (本地可读 + 7dd4e64/fd0ffa6 完整 diff + run 34815907654 原始日志导出到 raw/)
GLOBAL_CI_CONCLUSION = failure  (CI #34815907654 conclusion=failure; 多个 job 失败但 identity & security 修复已确认)
GLOBAL_ENGINEERING_GATE = FAIL  (g1/g3 B-series 仍 fail；CI 真实 fail 不吞错)
CORE_PAPER_ENGINEERING_GATE = FAIL  (B-series 59 仍 fail；需工程修复)
W2_G1_FINAL_VERSION = PASS  (45/45 on tested_sha=fd0ffa6; 见 W2_RERUN_EVIDENCE.json)
W2_G4_FINAL_VERSION = PASS  (test_paper_c_full_cost_flat_nav_and_pnl_window + ca05 round-trip cost PASS on tested_sha=fd0ffa6)
W6_ENGINEERING_SIGNOFF = BLOCKED_FOR_REVIEW  (B-series 工程修复未完成；但 W2 / CI security / repo governance 均 PASS)
COLLECTION_TECHNICALLY_READY = true  (P3 申请包就绪；待 Owner 批 OBSERVE_OWNER_AUTHORIZED)
STAGE_A_DATA_GATE = UNOBSERVED  (未启动任何 daemon，无前向数据)
SCOPE_CHANGE_STATUS = PROPOSED  (L217 scope_change_pending，需 Owner 批)
OBSERVE_OWNER_AUTHORIZED = false  (P3 申请材料已交，未启动)
PAPER_OWNER_AUTHORIZED = false
LIVE_OWNER_AUTHORIZED = false
RUNNING_MODE = NONE  (实际观察，非配置猜)
```

---

## 3. 修复路径（最小阻断集）

### 3.1 必须修复：B001..B059 (59 Python failures)

按根因分 4 组，可独立修：

| 组 | 数量 | 关键测试 | 根因 |
|---|---|---|---|
| shadow_runner 持久化缺失 | 39 | test_rh02bu2_* / test_rh02by_* / test_rh02ce_* / test_rh02ci_* / test_rh02ck_* / test_rh02cm_* / test_rh02cn_* | rh_position_marks / rh_journal / rh_bucket_reservations / fee_journal 持久化路径在 _run_episode_persisted 中缺失或不完整 |
| reconciliation verdict 错分 | 13 | test_reconciliation_* / test_c3_* | 实际 'INSUFFICIENT_EVIDENCE' vs 预期 'PASS'/'UNEXPLAINED_DIFF'；KeyError 'quote' |
| first_step_accrual NAV 公式 | 6 | test_steps_without_nav_* / test_net_pnl_* / test_end_to_end_nav_start_magnitude | NAV_start 取自非 grant 标记；net_pnl 公式未生效 |
| graduation_evidence | 1 | test_stage_a_not_passed_verdict_is_not_graduated_and_contains_blocker | verdict 分类器在 stage_a 失败时仍可能含 graduate |

### 3.2 可作为范围变更提案：L001..L217 (Go lint)

证据：
- 217 = 50 unused + 50 revive + 50 gosec + 36 staticcheck + 19 errcheck + 11 gocritic + 1 ineffassign ✓
- 路径分布：internal/adapters(74) + internal/core(50) + cmd/lpbot(50) + cmd/lpbot-backtest(17) + scripts/aggregate-verdict(6) + internal/platform(6) + 其它(14)
- 运行时依赖：grep Go 找 `lp_rh | rh02 | rh_position_marks | rh_journal` → **0 hit**
- Python 端 subprocess 仅调 pytest/audit_repro → **不**调 Go daemon

→ 所有 217 都是 Cat 4 (unrelated Go debt) 或 Cat 5 (naming/format)。可作为 `SCOPE_CHANGE_PROPOSED_LINT_GO_DEBT_TO_REVIEW_LATER` 提案；未批之前仍 required 阻断，不悄悄变绿。

### 3.3 已解决（不再阻断）

| ID | 项 | 状态 |
|---|---|---|
| CI002 | golangci-lint v2 typecheck 假阳性 | RESOLVED (.golangci.yml 移除 run.build-tags + sequential 3-pass) |
| CI003 | required-gate / quality-gate 吞错 | RESOLVED (needs.*.result hoist to env + literal 'success') |
| CI004 | redis CVE-2025-29923 | RESOLVED (go-redis/v9 v9.7.1 → v9.7.3; CI govulncheck PASS) |
| CI001 | go_build_unit_property step 6 unit tests flake | PRE_EXISTING_FLAKE (run #34815410119 PASS / #34815907654 FAIL 同 SHA); 待 B-series 修后重跑确认 |

---

## 4. 交付件清单（任务书 §8 最短交付）

```
READ_FIRST_CN.md                                  # 本文件 (主报告)
BLOCKERS.csv                                      # 机器可读债务分层
BLOCKERS_NOTES.md                                 # BLOCKERS 决策明细
ACCEPTANCE_EVIDENCE.json                          # SHA / run / JUnit / W2 持久化事实 (P0)
W2_RERUN_EVIDENCE.json                            # P2 W2 受控闭环复跑证据 (45/45 PASS on fd0ffa6)
OBSERVE_ONLY_REQUEST_CN.md                        # P3 OBSERVE_ONLY 申请包 (未启动)
CI_EVIDENCE.json (原有)                            # CI 修复 + 三次 run 完整事实 (7dd4e64 / 34815907654)
VULNERABILITY_RESOLUTION.json (原有)               # redis 漏洞修复链路
FINAL_VERDICT.json (原有, 本轮未改)                # 旧 closeout verdict (本轮已修正其中 W2_G1 错误继承)
reports/.../raw/                                  # 原始证据: pytest / go test / lint / gate / W2 rerun
```

---

## 5. Owner 决策表

| 决策项 | 默认（本任务） | 备选 | 依据 |
|---|---|---|---|
| 是否启动 OBSERVE_ONLY | 否（仅交付申请） | 是（限时 6h 检查点 + 48h 续跑） | OBSERVE_ONLY_REQUEST_CN.md §10 勾选项全通过才进 |
| L217 是否走 scope_change | 否（仍 required 阻断） | 是（明确版本化批准 + 复查条件） | BLOCKERS.csv L001..L217 scope_change_pending |
| 是否修 B-series | 是（59 项工程修复） | 否（重定向资源） | B-series 决定 FORWARD_PAPER 是否可达 |
| FORWARD_PAPER 进入 | 否（B-series 未修完） | 修完 + StageA ≥72h + 覆盖 ≥99% + 14d OOS | 任务书 §6 / V3_REV1 §6.4 |
| Live | NEVER | 独立资金政策审批 | 100U 旧政策与 CORE 1000U 不相容 |

---

## 6. 关键纪律（CLAUDE.md / 任务书）

- ❌ 未启动 paper/live/canary daemon
- ❌ 未创建/导入私钥
- ❌ 未签名、未广播、未动用真金白银
- ❌ 未放宽 `live_allowed`、未设 `tiny_live_authorized=true`
- ❌ 未改 main 分支
- ❌ 未绕过 CLAUDE.md freeze
- ❌ 未读/写 GitHub secrets、未触碰生产 Redis / chain / wallet state
- ✓ 全程 fail-close：CI 真实 fail，未悄悄变绿
- ✓ W2 真实复跑 on fd0ffa6（无 rewrite）
- ✓ L217 子分类有证据基础（grep 验证），未 blanket 豁免

---

## 7. 与上游交付一致性

| 来源 | 一致 |
|---|---|
| `CODEX_NEXT_TASK_CN.md` §8 报告字段 | 13 个字段全部列出（见 §2） |
| `AUDIT_CN.md` 5 项批评 | 全部回应（见 §1） |
| `CLAUDE.md` 安全硬线 | 全部遵守（见 §6） |
| 旧 `FINAL_VERDICT.json` (本任务包未改) | W2_G1=PASS 错误继承已在本轮 W2_RERUN_EVIDENCE.json 显式修正 |
| 旧 `CI_EVIDENCE.json` (本任务包未改) | run #34815907654 三次对比事实不变 |

---

## 8. 不可绕过的边界（per 任务书 §0 / §1）

- **不自行授予**新 collector/shadow/paper 常驻运行权限
- **不启动** Live
- **不伪造**"工程可签收"以换取 Owner 启动
- **不为通过测试放宽 CORE 或 NetCover**（保留六受保护常量）
- **不为通过 lint 全局禁分析器或加 //nolint:**
- **不悄悄修改 required 范围** — 217 lint 走 SCOPE_CHANGE_APPROVAL，未批不自动豁免

---

## 9. 已发现但**不属于本任务**的常驻进程（仅登记，不动）

`ps` 检查到 5 个长跑 readonly 脚本在 `/opt/lpbot/lp-bot-v3-origin-check` 跑，由**其他会话/VPS** 启动，**不是本会话起的**，本任务不动它们：

```
PID 118592  lp_rh_provider_health_recorder_v1_readonly.py  --period-secs 900
PID 119849  lp_rh_premium_recorder_v1_readonly.py          --period-secs 180
PID 157737  lp_rh_organic_recorder_v1_readonly.py          --period-secs 900
PID 2271374 lp_rh_collector_v1_readonly.py                 --interval-secs 15
PID 2685886 lp_rh_shadow_daemon_v1_readonly.py             --period-secs 900
```

PID files 路径均位于 `reports/lp_rh/`，跟本任务交付目录 `reports/shadow_paper_convergence_20260914/` 互不相干。停掉任一将丢失 OHLCV / quote / pool-meta 历史链；**本任务不替 Owner 决定**。
