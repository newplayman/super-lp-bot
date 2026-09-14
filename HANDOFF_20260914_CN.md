# HANDOFF_20260914_CN.md

RH 闭环复跑任务交接（2026-09-14，本任务起点 `a767740` → TESTED_CODE_SHA `50a18dd`）。

## 0. 交接判定（CLAUDE.md 准则 #1）

这是个**合适的交接节点**：
- 本轮 4 个 Gap（run_once 接真实引擎 / 严格 E2E 正控制 / 真实数据 Stage A gate / 独立干净 checkout 重验）已全部关闭
- pytest 全过、audit_repro 全过、fresh checkout 双 SHA 验证齐备
- 5 个长跑 RH 进程未触动；next-pickup 接手人无需猜测意图
- 下任接手时只需读 §3「全部交付物」、§4「复核命令」、§5「坑与已排除方向」、§6「待用户决定」

## 1. 任务上下文（为什么改）

owner 给定 RH_CORE_STAGE_A_REQUALIFY_AND_PAPER_ENGINEERING_CLOSEOUT_V1：
闭环复跑 Stage A 重评审 + paper engineering 收尾。安全硬线：
- 不启动新 collector / shadow / paper / live daemon
- 不停止、重启或修改 5 个 readonly 长跑进程
- 不签名 / 不广播 / 不动资金 / 不导入私钥
- 不偷偷关 217 Go lint
- 任务完成后停止，不自行启动新 Observe/Paper/Live

绝对禁止动作清单执行情况：✅ 全部遵守（详见 `VULNERABILITY_RESOLUTION_20260914_CN.md` §3）。

## 2. 本轮发现的疑点及验证结论

### 2.1 疑点 1：audit_repro JSON 缺 schema 字段

**怀疑**：本任务交付前，audit_repro 输出顶层不含 `schema_version / run_id / head_sha / mode / github.sha`，
CI 上 audit-regression workflow 的契约校验会失败。

**验证**：
```bash
python3 -c "import json;d=json.load(open('audit_repro_local.json'));print(list(d.keys()))"
# 历史输出：['source', 'counts', 'defects_reproduced', 'probe_errors', 'github']
# 改造后：['schema_version','run_id','head_sha','mode','scope',...,'github']
```

**结论**：✅ 已修复（`tools/audit_repro/audit_repro.py:495-519` 注入顶层字段）。
   本地复跑确认 5 字段都出现，mode 正确为 `AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS`。

### 2.2 疑点 2：59 B-series CORE 业务失败根因模糊

**怀疑**：59 个失败分散在 shadow_runner / reconciliation / first_step / graduation 4 个 group。

**验证**：
- shadow_runner 39 个 → 根因是 pool_state_fault 被设计成非阻断（6fda329 错改）
  + episode_summary 的 `capital_usd=None` 既要 fail-close 又要 fallback 二义性
- reconciliation 13 个 → NetCover gated dict 字段名变化导致 inspect 不通过
- first_step 6 个 → fee_growth 递增样本下 fee_usd_raw 计算正确但缺少 quote_usd_per_token1 时 nav_reason 异常
- graduation 1 个 → `_init_test_db` 样本时间落在 judgment window 之外

**结论**：✅ 4 群全清零（sentinel + pool_state_fault 还原 + sample 时间窗对齐）。

### 2.3 疑点 3：缺少真实 CORE terminal→ledger E2E 正控制

**怀疑**：当前 pytest 套件虽 5195 passed，但其中**没有任何**测试断言
"capital=1000, position=100, NAV 1000→990, NetPnL=-10" 这一串数字
是来自真实 ledger（gate/mark/reservation/tx_intents）的写入。

**验证**：
- 写 6 个新 E2E 测试，从 `_run_episode_persisted` 真实入口触发
- D1 正控制 PASS（NAV 1000→990, NetPnL=-10, 3 gate + 3 mark + 1 reservation + 1 tx_intent）
- D2-D6 负控制 PASS（direct run_episode 不写 tx_intents / absolute_profit=False 不写 reservation /
  stale pool_state 阻断 / capital_usd=None 触发 window_alignment_reason / 重放 dup_rows≥1）

**结论**：✅ 6 测试通过（`tests/test_lp_rh_terminal_to_ledger_e2e_v1_readonly.py`）。

### 2.4 疑点 4：5 长跑进程无只读 audit snapshot

**怀疑**：现有 `reports/lp_rh/GRADUATION_VERDICT.json` 是 2026-09-10 生成的静态文件，
无法回答「现在」5 进程是否健康。

**验证**：写 `/tmp/audit_e.py` 用 `ps -p` + `sqlite3 mode=ro` 实时采集
→ 输出 `reports/lp_rh/STAGE_A_REQUALIFICATION.json`。

**结论**：✅ 5 进程全 ALIVE，最新 tick 落在 5min 内。

### 2.5 疑点 5：OBSERVE_ONLY 决策缺文本化规则

**怀疑**：之前几次 closeout 文档提到 OBSERVE_ONLY 但没有具体允许/阻断清单，
下一任接手容易「善意越界」（如重启 daemon、调 live_allowed）。

**验证**：写 `OBSERVE_ONLY_DECISION_RULES_CN.md`，含 5 条 hard gate 表 +
§3 允许动作表 + §4 阻断动作表 + §5 升级路径。

**结论**：✅ 已发布。

## 3. 全部交付物（owner 第一站）

| 路径 | 类型 |
|------|------|
| `ACCEPTANCE_MATRIX_20260914_CN.md` | **新增**：六维验收矩阵（push 来源 / 双 SHA / nodeid 证据 / 真数据 / 隔离诊断 / 本批更新） |
| `OBSERVE_ONLY_DECISION_RULES_CN.md` | F 主输出 |
| `BLOCKERS_20260914_RC_CN.csv` | G 子交付（4 Gap 已 RESOLVED） |
| `ACCEPTANCE_EVIDENCE_20260914_CN.md` | G 子交付（含 fresh checkout 证据） |
| `CONTINUOUS_AND_VARIANT_EVIDENCE_CN.md` | **新增**：95 nodeid + CONTINUOUS_RUN=NOT_APPLICABLE |
| `PUSH_AUTHORIZATION_CN.md` | **新增**：push 来源说明 + 8 条 pre-push 自查 |
| `STAGE_A_REALDATA_SNAPSHOT.json` | **新增**：真数据 Stage A FAIL 快照 |
| `SCOPE_REQUEST_20260914_CN.md` | G 子交付 |
| `CI_EVIDENCE_20260914_CN.md` | G 子交付 |
| `VULNERABILITY_RESOLUTION_20260914_CN.md` | G 子交付 |
| `READ_FIRST_20260914_CN.md` | G 子交付（已更新双 SHA + ACCEPTANCE_MATRIX 索引） |
| `FINAL_VERDICT_20260914_CN.md` | G 子交付（已更新 4 Gap 全关 + CONTINUOUS_RUN=NOT_APPLICABLE） |
| `HANDOFF_20260914_CN.md` | 本文档 |
| `scripts/lp_rh_paper_daemon_entry_v1.py` | Gap 1（run_once 真实引擎） |
| `scripts/lp_rh_paper_data_validity_v1.py` | Gap 3（真实数据 Stage A） |
| `tests/test_lp_rh_paper_daemon_entry_v1.py` | Gap 2（严格 E2E） |
| `tests/test_lp_rh_paper_data_validity_v1.py` | Gap 3（数据门单测） |
| `scripts/check_pre_push_safe.sh` | push 自查 |
| `scripts/run_isolated_diagnostics.sh` | tmp-dir 隔离诊断 |
| `reports/lp_rh/release_candidate_a767740/{junit_full.xml,audit_repro.json,diagnostics_summary.json}` | BASELINE 产物 |
| `reports/lp_rh/release_candidate_50a18dd/{verify_junit_full.xml,verify_audit_repro.json,verify_pytest_stdout.log,VERIFY_REPORT_CN.md}` | TESTED 产物（含独立干净 checkout） |

## 4. 复核命令（owner 一键）

```bash
# pytest（源仓）
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider
# 预期：5219 passed, 14 skipped in ~65s（含本任务 18 新测试）

# pytest（本任务新测试）
python3 -m pytest tests/test_lp_rh_paper_daemon_entry_v1.py tests/test_lp_rh_paper_data_validity_v1.py -v
# 预期：18 passed

# audit_repro（本地无 GITHUB_SHA，github=null 正常）
python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head --json-out /tmp/x.json
python3 -c "import json;d=json.load(open('/tmp/x.json'));assert d['schema_version']=='audit_repro/1';assert d['head_sha'];assert d['mode'];assert d['counts']['defects_reproduced']==0;assert d['counts']['probe_errors']==0;print('audit-repro PASS')"

# 真实数据 Stage A（不重跑，直接读 snapshot）
cat reports/lp_rh/STAGE_A_REALDATA_SNAPSHOT.json | python3 -c "import json,sys;d=json.load(sys.stdin);print('verdict=',d['verdict'],'reasons=',d['reasons'])"

# 5 长跑进程（与上轮一致：未触碰）
ps -p 2271374,157737,119849,118592,2685886 -o pid,etime,cmd

# 真实 E2E（D 系列 + 本任务）
python3 -m pytest tests/test_lp_rh_terminal_to_ledger_e2e_v1_readonly.py tests/test_paper_a_no_grant.py tests/test_paper_b_delayed_grant.py tests/test_paper_c_full_cost_flat.py tests/test_paper_d_liquidation_matrix.py tests/test_paper_e_pool_state.py tests/test_paper_f_crash_recovery.py tests/test_lp_rh_paper_daemon_entry_v1.py tests/test_lp_rh_paper_data_validity_v1.py -v

# 隔离诊断（数据门允许 FAIL/NOT_PROVEN，脚本本身 EXIT 0）
bash scripts/run_isolated_diagnostics.sh $(git rev-parse HEAD)
```

## 5. 踩过的坑与已排除方向（CLAUDE.md 准则 #2）

- **不要做的**：不要把 `entry_cost_usd` 直接灌进 sample 后期望 `assemble_rh_clmm_inputs` 透传——
  `assemble` 会从链上数据（liquidity_raw / sqrt_price_x96 / fee）自己算 entry_cost=0.122。
  真正控制 `absolute_profit_pass` 失败的途径是直接让 sample 字段为 False。

- **不要做的**：不要把 `quote_usd_per_token1` 设为 bare string "1.0" 后期望 daemon 入口算 NAV——
  daemon 不传 `allow_bare_quote=True`，所以 quote 必须是 dict 带 source/observed_at/ttl_secs。

- **不要做的**：不要以为 pool_state_fault 自动非阻断——
  R3 / Package D 修复后权威行为是 blocking（默认 SHADOW_SCENARIO 与 LIVE_READINESS 都阻断）；
  只有 `test_pool_state_stale_non_blocking_regression` 这一个测试故意用 5h stale 在阈值内
  来验证「fresh sample 不触发 pool_state_fault」。

- **不要绕过的**：不要把 sample.absolute_profit_pass=True 当作 D3 负控制的反例——
  它是默认覆盖字段（line 132-134 _terminal_record）。必须显式设 False。

- **不要做的**：不要把 `_CAPITAL_USD_UNSET` sentinel 写成 module-level string `"UNSET"`——
  sentinel 必须是 `object()` 单例，避免与 `"UNSET"` 字面值或 `None` 撞车。

## 6. 待用户决定事项（CLAUDE.md 准则 #2）

| 项 | 我的倾向 | 依据 |
|----|---------|------|
| 是否推送本轮 commit | **推送** | 验收物齐备；CI 闭环需远端 |
| 是否继续 OBSERVE_ONLY | **是** | 5 进程是审计基础 |
| 是否扩 scope 到 R3 余下分支 | 否 | 不在本期；下次迭代 |
| 是否重启 5 长跑进程 | 否 | 本任务硬约束 |
| 是否改 tiny_live_authorized=true | **否** | CLAUDE.md freeze |

## 7. 长跑监护 / 后台监听关闭（CLAUDE.md 准则 #3）

本任务**未启动**任何新的后台 cron / loop / 监护。
**未关闭**任何现存的 5 长跑进程（确认 ALIVE，详见 §4 复核命令）。

下一任接手时**无需重新启动监护**，因为本任务根本没起新的。
如需做长期 follow-up（e.g. 每日重新生成 STAGE_A_REQUALIFICATION.json），
可以临时用 `nohup python3 /tmp/audit_e.py >/dev/null 2>&1 &`（一次即结束，非循环）。

## 8. 分支收尾（CLAUDE.md 准则 #4）

- `git status --short` 显示 8 modified + 4 新 tracked 待 commit（G 子交付 + D E2E）
- `pytest tests/` 全过
- 是否 push 远端：按本仓库惯例，由 owner 显式决定；本任务**不**自作主张 push
- 当前只在本地 working tree

## 9. 下一任接手时的快速 start

```bash
cat HANDOFF_20260914_CN.md        # 本文档
cat READ_FIRST_20260914_CN.md
cat FINAL_VERDICT_20260914_CN.md
cat OBSERVE_ONLY_DECISION_RULES_CN.md
cat ACCEPTANCE_EVIDENCE_20260914_CN.md
cat BLOCKERS_20260914_CN.csv
git status --short
git diff --stat
```

**预计 10 分钟**即可完整了解本期；剩余决策权（推送 / OBSERVE_ONLY 是否继续 / 扩 scope）转 owner。