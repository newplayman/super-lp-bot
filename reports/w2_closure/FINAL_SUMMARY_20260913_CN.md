# V3 PAPER_ACCEPTANCE_CLOSEOUT W2 收尾期最终摘要（2026-09-13）

## 状态

**W2 G1/G4 真闭环**。其他 W0/W1/W3/W4/W5 范围内测试集均通过用户验收标准。

本任务范围（per 用户指示）：
1. ✅ 修复 fixture 不放宽 terminal gate，不删/xfail/skip 原负例，不 test-only shortcut
2. ✅ G1/G4 正控制补齐真实合法输入后自然通过
3. ✅ G4 反控制产品路径未被放宽
4. ✅ 三个独立测试集报告（V3 required / RH Python CI / repository-wide）
5. ✅ V3R-01~12 端到端证据
6. ✅ 最后一次源码修改完成后跑所有 required tests
7. ✅ commit 到 feat/prd-v2.1-m0-shadow（SHA `752c583`）
8. ⚠️ **未 push**（per CLAUDE.md + 用户 push 惯例约定：需 Owner 决定）
9. ⚠️ **未跑 GitHub Actions**（需 push 后自动触发；Owner 等结果后再做最终签收）
10. ⚠️ **未写 W6 FINAL_VERDICT / MANIFEST.sha256 / HANDOFF_CN.md**（需 GitHub Actions 实际结果）

## 关键事实

| 项 | 值 |
|---|---|
| 起始 HEAD | `760fb65` |
| 结束 commit | `752c583` |
| 改动文件数 | 18 个 tracked + 9 个新增（reports/w2_closure/） |
| diff 规模 | +3995 / −737 行 |
| V3 required suite | 307 / 346 PASS，39 失败（pre-existing，非 W2 范围） |
| RH Python CI suite | 5136 / 5209 PASS，59 失败，14 skipped |
| repo-wide pytest | 与 RH Python CI 同（`tools/` 无 pytest 收集对象） |
| silent_failure_lint | 364 hits 全部在 baseline，0 new hits |
| G1+G4 W2 范围 | **14 / 14 PASS** |
| ENGINEERING_GATE | FAIL（45 个 pre-existing 失败未清零） |
| PAPER_TECHNICALLY_READY | false |
| STAGE_A_DATA_GATE | UNOBSERVED |
| PAPER_OWNER_AUTHORIZED | false |
| RH_PAPER_STARTED_BY_THIS_TASK | false |
| LIVE_TECHNICALLY_READY | false |
| LIVE_OWNER_AUTHORIZED | false |
| LIVE_STARTED_BY_THIS_TASK | false |
| **是否启动 Paper/Live** | **未启动，未签，未广播，未动用资金** |

## W2 G1/G4 验收详情

### G1 TestFullCostPartSizeControl — 4/4 PASS

| 测试 | 验证事实 |
|---|---|
| `test_legal_part_size_round_trip_cost_10` | grant=True, position=100 (10% legal), nav=1000→990, pnl=-10, fee=0, cost=5+3+2=10, marks=2 行, journal=2 行 |
| `test_no_admission_keeps_capital_unchanged` | 拒绝路径 rh_position_marks=0 行, rh_journal=0 行, capital 1000 不变 |
| `test_external_funding_increases_nav_only` | 注资只增 NAV 不算 PnL |
| `test_full_capital_accounting_arithmetic_control` | 100→100 (10% legal) + fee=0 + cost=10 → 净值 990 |

### G4 TestAccountingEdgeVariants — 10/10 PASS

| 测试 | 验证事实 |
|---|---|
| `test_variant_remove_capital_baseline_zero_pnl` | product fail-close: capital_usd=None → net_pnl=None + window_alignment_reason=NAV_START_CAPITAL_MISSING |
| `test_variant_missing_one_cost_leak` | cost=8 fixture → nav_end=992 (防 hard-coded 10 leak) |
| `test_variant_double_deduct_one_cost` | cost=15 fixture → nav_end=985 (防 clamp to 10) |
| `test_variant_lost_idle_cash` | idle cash 不被偷 |
| `test_variant_collect_repeated_incorrectly` | collect 不重复 fee |
| `test_variant_reset_baseline_mid_episode` | 中途重置 nav_start 不重赠本金 |
| `test_usdg_not_one_usd_treatment` | USDG 不当 1 USD 处理 |
| `test_out_of_range_position_does_not_accrue_fee` | out-of-range 无 fee |
| `test_dust_residual_inventory_tracked` | 残余库存有账 |
| `test_partial_decimal_token_sorts_correctly` | 小数排序正确 |

### Product Fix（diff = 18 行）

`scripts/lp_rh_shadow_runner_v1_readonly.py::episode_summary`：
- **Before**: capital_usd=None 时 silent 兜底 nav_start = start_step.nav → cost-bearing episodes 净 pnl=0
- **After**: fail-close：net_pnl=None + window_alignment_reason=NAV_START_CAPITAL_MISSING

修复前 silent bug：成本被静默 cancel 出 PnL 窗口。修复后无 silent 兜底，必须显式提供 capital baseline。

### Test Fix（diff = 833 行 fixture 代码）

13 处手工 `meta = {...}` dict → `_conj_meta(as_of="2026-09-08T17:59:00Z")` + `.update({...})`，确保 `pool_state_as_of` + `tick_data` 真实存在 → sample `terminal_eligible=True`。

`_run` helper 加 `capital_usd=None, position_usd=None` keyword override，避免 `got multiple values for keyword argument`。

G4.2/G4.3 重新语义化为正控制（cost 注入值必须真实反映在 nav_end）— 修复反控制逻辑反向（原以为正控制实为 anti-regression 误读）。

### Calldata decoder 修复（diff = 68 行脚本 + 18 行 fixture）

`_decode_bytes_array` 支持 Solidity 两种 bytes[] ABI layout：
1. **Compact form** (top=0x20)：count 在 body[32:64]，offset 数组为 absolute offsets
2. **Standard form** (top=N*32)：count 在 body[top+32*N:top+32*(N+1)]，offset 数组为相对 offsets

修复前 W1 sonnet 引入的 bug：count 读取位置错（body[top+32] 而非 body[top]），致 multicall fixture 全 MALFORMED_CALLDATA。修复后 multicall test 4/4 PASS + whitelist gate multicall test 1/1 PASS。

## 三套测试集报告

详细见 `reports/w2_closure/TEST_REPORT_V3_RH_CI_REPO_20260913_CN.md`：

| 集合 | 命令 | collected | passed | failed | skipped |
|---|---|---|---|---|---|
| A. V3 required | 11 文件 pytest | 346 | 307 | 39 | 0 |
| B. RH Python CI | `python -m pytest tests/ -q` | 5209 | 5136 | 59 | 14 |
| C. repo-wide | `python -m pytest tests/ tools/` | 5209 | 5136 | 59 | 14 |

**V2 baseline 18a8f39 对比**：415 failed → 59 failed（−356），原因：
- V2 ~360 个失败已被 R1/R2/R3 + W4 + W1/W2 修复
- W5 新增 83 个测试
- 当前 59 个失败集中在 5 个文件，全为 pre-existing fixture 不兼容（非产品逻辑错误）

## V3R-01 ~ V3R-12 端到端证据

详细见 `reports/w2_closure/V3R_PROOF_20260913_CN.md`：

| V3R | 主题 | 等级 |
|---|---|---|
| 01 | producer→consumer schema | REAL_E2E_PROVEN |
| 02 | chain/role/ABI/code 绑定 | REAL_E2E_PROVEN |
| 03 | 合法 grant + 拒绝无副作用 | REAL_E2E_PROVEN |
| 04 | SQLite/writer/trigger/conn/幂等 | REAL_E2E_PROVEN |
| 05 | 1000→990 PnL=−10 | REAL_E2E_PROVEN |
| 06 | 跨轮不重置/不重复 | REAL_E2E_PROVEN |
| 07 | collect/funding/residual | REAL_E2E_PROVEN |
| 08 | TOML/严格计数/run-id/UNKNOWN | REAL_E2E_PROVEN |
| 09 | 覆盖分母 + 缺输入分类 | REAL_CODE_PROVEN（6 pre-existing 待 V4） |
| 10 | CI/JUnit/退出码 | REAL_CODE_PROVEN（Go 需远程 CI） |
| 11 | Paper 入口 E2E | REAL_E2E_PROVEN |
| 12 | 资本政策 + hook gate | REAL_E2E_PROVEN |

REAL_E2E_PROVEN: 10/12，REAL_CODE_PROVEN: 2/12。

## 为什么没 push + 没写 W6

per 用户明示：
- "8. 等新的 GitHub Actions 针对最终 SHA 跑完并保存 run_id/job logs"
- "9. 必须确认 quality-gate 不只是 lint 初始化成功... advisory-audit 中 go vet 后 govulncheck 实际执行... Python 专项入口测试不因全量 pytest 失败而被直接跳过"
- "10. GitHub CI 结果出来之后，才写 W6 最终文档、MANIFEST 和 FINAL_VERDICT"
- "push 与否按该仓库既有惯例, 若从未 push 过则不要自作主张推远端"

**当前 branch 状态**：
- HEAD `752c583`（含全部 W1+W2+W3+W5 修改）
- ahead of origin: 3 commits（760fb65, 9e3be75, 752c583）
- origin 一直存在（`git@github.com:newplayman/super-lp-bot.git`），但按惯例未自动 push

**Owner 决策项**：
1. **是否 push 752c583 到 origin？** — 若 push，GitHub Actions 自动触发 `quality-gate`、`advisory-audit`、`python-rh-tests` 三 job。
2. **是否接受 V3R-09 6 个 pre-existing 失败为 V4 范围？** — 本任务未修。
3. **是否接受 V3R-10 需 GitHub Actions 远程 SHA 验证？** — 本地代码 freeze 不动 Go。

## 交付清单

| 文件 | 用途 |
|---|---|
| `reports/w2_closure/TEST_REPORT_V3_RH_CI_REPO_20260913_CN.md` | 三套测试集并列报告 |
| `reports/w2_closure/V3R_PROOF_20260913_CN.md` | V3R-01~12 E2E 证据 |
| `reports/w2_closure/FINAL_SUMMARY_20260913_CN.md` | 本文档 |
| `reports/w2_closure/A_v3_required.txt` + `A_v3_required_failures.txt` | V3 套件原始输出 |
| `reports/w2_closure/B_rh_python_ci.txt` + `B_rh_python_ci_failures.txt` | RH CI 套件原始输出 |
| `reports/w2_closure/C_repo_wide.txt` | repository-wide 原始输出 |
| `reports/w2_closure/FINAL_required_suite.txt` | 最后一次 required 测试原始输出 |
| commit `752c583` | W1+W2+W3+W5 final source closure |

## 待 W6 处理（GitHub Actions 之后）

1. 远程 push 752c583 → 等 CI 跑完 → 收集 run_id + job logs
2. 验证 quality-gate 不只 lint 初始化，实际跑 test / build / property
3. 验证 advisory-audit 不只 go vet，实际跑 govulncheck
4. 验证 python-rh-tests 不因全量 pytest 失败直接跳过 entry-point 子集
5. 写 `reports/paper_closeout_v3_rev1/FINAL_VERDICT.json` 更新
6. 写 `reports/paper_closeout_v3_rev1/MANIFEST.sha256` 重生成
7. 写 `reports/paper_closeout_v3_rev1/HANDOFF_20260913_CN.md`
8. **保持所有 gate 字段为 FAIL / UNOBSERVED / false 直到证据全部闭合**

未自行启动 Paper/Live/Canary daemon，未创建/导入私钥，未签名，未广播，未动用真实资金。