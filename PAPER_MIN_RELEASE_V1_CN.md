# PAPER_MIN_RELEASE_V1_CN.md

RH_CORE_PAPER_MINIMUM_RELEASE_V1 最小发布候选包（commit baseline `a767740`）。

## 0. 一句话摘要

关闭四个缺口：

1. **Gap 1 — Paper run_once/run_daemon/status 接真实研究引擎**：替换 `return EXIT_NO_TRADE` 的 stub；现在 `run_once()` 调 `_run_episode_persisted`（与 D1 E2E 正控制同入口），开 `tmp ledger.db` 持久化 3 gate + 3 mark + 1 reservation + 1 tx_intent + 1 summary 行。`status()` 读 `rh_episode_summary` 真实表取 `episodes_run` 与 `last_tick_at`，不再 hard-code 0 / None。`run_daemon()` 改为 single-shot 包装（仍 `NotImplementedError` 守护长跑 loop，per OBSERVE_ONLY）。
2. **Gap 2 — 严格 E2E 正控制（无条件 NAV 1000→990、PnL=-10）**：`tests/test_lp_rh_paper_daemon_entry_v1.py::TestPaperRunOncePositiveControl` 跑 `run_once()` 真实入口 + tmp ledger，断言：
   - `rh_gate_decisions == 3`（每步一行）
   - `rh_position_marks == 3`（真实模拟持仓 mark，不是 stub）
   - `rh_bucket_reservations == 1`，bucket=`CORE`，amount=100，状态在 `{PENDING, RELEASED, BROADCAST_UNKNOWN, EXPIRED}`
   - `rh_tx_intents >= 1`，state ⊆ `{RESEARCH_ONLY_NOT_SIMULATED, PROPOSED, WHITELIST_PASSED, SIMULATED_OK, WHITELIST_REJECTED}`（live 状态被禁止）
   - `rh_journal >= 1`
   - `rh_episode_summary == 1`，**严格 Decimal 等值**：`nav_start == 1000`，`nav_end == 990`，`net_pnl == -10`
   - `status().episodes_run == 1`，`last_tick_at` 非空
   - **禁止**：`granted_count >= 0`、`net_pnl is None`、`net_pnl == 0`、mock、skip
3. **Gap 3 — Forward Paper 数据有效性 + Stage A 真算**：`scripts/lp_rh_paper_data_validity_v1.py::check_forward_paper_data_validity(db_path)` 直接 query `rh_market_states`（MIN/MAX/COUNT + key-column null ratio），调用现有 `stage_a_status` 纯函数给 verdict。
   - 缺 DB / 表 / 数据 → `NOT_PROVEN`
   - hours < 72 → `FAIL` (HOURS_COVERED_INSUFFICIENT)
   - coverage < 0.99 → `FAIL` (COVERAGE_INSUFFICIENT)
   - 否则 → `PASS`
   - **禁止**：PID alive、last_tick delta、row count alone 代理
4. **Gap 4 — 干净 checkout 重验**：在当前 working tree（最终 commit）跑全量 pytest + audit_repro，原始 JUnit / 日志 / JSON 全存到 `reports/lp_rh/release_candidate_a767740/`。若与远端 Actions 不一致，verdict 保持 NOT_PROVEN，不择优引用。

## 1. 验证命令与结果

```bash
# pytest（最终 SHA 的全量验证，5209 passed / 0 failed / 14 skipped）
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider \
  --junitxml=reports/lp_rh/release_candidate_a767740/junit_full.xml
# → 5209 passed, 14 skipped in 65.46s

# audit_repro
python3 tools/audit_repro/audit_repro.py --repo . --allow-other-head \
  --json-out reports/lp_rh/release_candidate_a767740/audit_repro.json
python3 -c "import json;d=json.load(open('reports/lp_rh/release_candidate_a767740/audit_repro.json'));assert d['schema_version']=='audit_repro/1';assert d['head_sha'];assert d['mode'];assert d['counts']['defects_reproduced']==0;assert d['counts']['probe_errors']==0;print('PASS head_sha=', d['head_sha'])"
# → PASS head_sha= a7677405c2ecaaf100fe01124973ffec4511abfb
```

## 2. 改动的文件

| 路径 | 改动 |
|------|------|
| `scripts/lp_rh_paper_daemon_entry_v1.py` | 接真实研究引擎：run_once 调 _run_episode_persisted；status 读 rh_episode_summary；run_daemon 改为 single-shot 包装 |
| `scripts/lp_rh_paper_data_validity_v1.py` | **新建**：Stage A 真算（query rh_market_states） |
| `tests/test_lp_rh_paper_daemon_entry_v1.py` | **改造**：删 stub 测试，加 TestPaperRunOncePositiveControl（无条件正控制） |
| `tests/test_lp_rh_paper_data_validity_v1.py` | **新建**：7 个数据有效性测试（覆盖 NOT_PROVEN / FAIL / PASS + 禁止代理） |

## 3. 硬线遵守（per CLAUDE.md / OBSERVE_ONLY）

- ✅ 未启动新 collector / shadow / paper / live daemon（run_daemon 改为 single-shot，不创建 sleep loop）
- ✅ 未停止 / 重启 / 修改 5 个长跑 RH 进程
- ✅ 未签名 / 未广播 / 未导入私钥 / 未动资金
- ✅ 未改 `tiny_live_authorized`
- ✅ 未触碰 main 分支
- ✅ `signing_enabled=false`、`broadcasting_enabled=false` 在 paper cfg 保持
- ✅ `verify_calldata=False`（与 D1 一致；calldata whitelist 是单独 W2 工作）

## 4. 残留事项（owner 验收决策）

| 项 | 我的倾向 | 依据 |
|----|---------|------|
| 是否推送本轮 commit | **推送** | 测试齐备；CI 闭环需远端 |
| 是否启动 Paper daemon | **不启动** | owner 必须显式 `run_once` 一次试运行后再启长跑 |
| 是否扩 verify_calldata | 否 | 下次迭代（W2 工程范围内） |
| 是否扩 scope 到 R3 余下分支 | 否 | 不在本期 |

## 5. 远端 Actions 一致性

> 本机完成所有 Gap 验证；远端 `python-rh-tests` 与 `audit-regression` 必须也在同一最终 SHA 报 PASS。若不一致，verdict 保持 NOT_PROVEN，不引用任何一侧的通过数。