# P0_EXISTING_CODE_MAP — 现有工程真实文件地图（RH-00，2026-09-07）

来源：Qwen 只读调研 `qwen/Q1.md`（13 个文件的存在性/行数/公开符号/import 关系，主脑抽核计数：`scripts/lp_*_readonly.py` 101 个、`tests/test_*.py` 135 个，与 B1 §8 一致）。HEAD `279b047`（代码同 `0e2b6e6`）。

## 1. PRD §2.2 复用表 → 真实接口

| PRD 复用点 | 真实文件（行数） | 关键接口（行号） | 被谁调用（Python 研究层） | RH 改造边界 |
|---|---|---|---|---|
| RPC 池 | `scripts/lp_rpc_pool_v1_readonly.py`（511） | `RpcPool:219`、`call:343`、`_penalize:277`、`health_snapshot:287`、`CHAINS` 表 :68-180 | 10 个脚本（scanner daemon、paper runner、resolve_and_rank、solana stage2 …） | **必须先修 `:280` 指数退避溢出（见 LEGACY_FAILURE_AUTOPSY）**，再为 RH 增加 chain 4663 配置与 provider 独立性字段 |
| 粗筛 | `lp_universe_screener_v1_readonly.py`（571） | `score_pool:316`、`assess:382`、`fetch_pools:428`、`main:502` | 7 个脚本 | RH 发现入口独立（`lp_rh_registry`/`pool_probe`），DefiLlama/Gecko 只给种子 |
| 输入装配 | `lp_netcover_inputs_v1_readonly.py`（1428） | `assemble_clmm_netcover_inputs:824`、`assemble_netcover_inputs:1404`、`LVR_COEFFICIENT_MODEL:94` | 7 个脚本 | 新 `lp_rh_netcover_inputs` 输出同一字段契约；不改此文件 |
| 经济引擎 | `lp_netcover_engine_v1_readonly.py`（399） | `evaluate_netcover:177`、`absolute_profit_gate:233`、`position_cap_usd:256`、`apply_netcover_gate:282`；常量 :18,19,24,26 | 12 个脚本 | 不修改；RH 直接 import |
| 成本模型 | `lp_swap_cost_model_v1_readonly.py`（331） | `clmm_token0_value_fraction:184`、`exit_conversion_cost_usd:220`、`roundtrip_cost_usd:243` | 5 个脚本 | 新增 RH 路由费用观测作为输入，不改公式 |
| 采数 daemon / 终闸 | `lp_scanner_daemon_v1_readonly.py`（1871） | `ScannerStore:417`、`_enforce_fifth_gate:1242`、`_score_row:362`、`export_latest_vetted_menu:1433`、`ScannerDaemon:1606` | 3 个脚本 + 8 个测试 | 不重启旧 daemon；RH 新 runner 复用 `ScannerStore` 的 schema 思想但写独立 `reports/lp_rh/scanner.db` |
| 影子证据闸 | `lp_shadow_gate_v1_readonly.py`（513） | `GateStore:150`、`record_rpc_health:283`、`evaluate_shadow_gate:325` | panel、paper runner、daemon | RH 增加数据覆盖/账本输入，不绕开 |
| 漏斗解剖 | `lp_funnel_autopsy_v1_readonly.py`（536） | `gate_bits:73`、`recomputed_accepted:92`、`decay_table:158`、`build_report:301`；需要 `--stage1-screen` 产物 | `lp_tp_d_compare` | RH `lp_rh_funnel_autopsy` 按 §8.4 五类拆分 |
| 股票 universe / policy / acceptance | `lp_stock_token_universe_v1_readonly.py`（450）、`lp_stock_tier_policy_v1_readonly.py`（271）、`lp_stock_tier_acceptance_v1_readonly.py`（205） | `identify_stock_token:141`、`evaluate_c_gate:160`、`build_acceptance:57`（读 `existing_terminal_conjunction` :79，**无生产者**） | universe 无 import 方；policy 被 e5 report/acceptance 调用 | 复用归一化纯逻辑；RH 股票终闸必须有真实生产者 |
| 执行安全契约 | `execution/base_m1_executor_v1.py`（940） | `Intent:298`、`ExecutionPolicy:372`、`IntentValidator:432`、`NonceManager:647`、`verify_keystore_permissions:667`、`LiveUnlock:717`、`Broadcaster:734`、`dry_run:912` | 4 个只读脚本（c6 preflight、sepolia smoke、c5 dry run、npm verify） | 作为模板；RH-07 才新建适配器 |
| 面板 | `lp_panel_server_v1_readonly.py`（838） | `StateBuilder:463`、`PanelHTTPServer:564`、`build_server:768`；`REPO_ROOT` 用 `resolve()`（本机布局须真身在 `/opt/lpbot`） | 仅测试 | RH-08 加 RH 标签页 |
| Go 层 | `internal/ cmd/ pkg/`（go test 57 ok） | 无 Python 调用（B1 §3.1） | — | 冻结 |

## 2. 数据落点（迁移库实测）

`reports/lp_scanner/scanner.db`：`pool_snapshots` 2,971,610、`opportunity_scores` 114,422（列：`id, as_of, pool, symbol, fee_ev_usd, reward_ev_usd, il_ev_usd, lvr_ev_usd, risk_usd, expected_net_yield_usd, expected_net_yield_pct, netcover_ratio, accepted, rejection_reason, score_json, source`）、`market_sessions` 0、`rpc_severe_incidents` 0、`shadow_*` 0。第二库 `reports/lp_scanner_v2_20260823/scanner.db`：`pool_snapshots` 2,119,085、`opportunity_scores` 80,880。

## 3. 第一条 CORE Shadow 闭环最少改哪些文件（PRD §24 Q8）

**先修一处共享缺陷（RH-00b，1 行 + 1 测试）**：`scripts/lp_rpc_pool_v1_readonly.py:280` 指数封顶；`tests/test_lp_rpc_pool_v1_readonly.py` 加配对测试。不改任何阈值。

**然后新增（不改旧文件）**，按 PRD §2.2 命名：

| 包 | 新文件 | 复用 |
|---|---|---|
| RH-01 | `scripts/lp_rh_registry_v1_readonly.py`、`lp_rh_capabilities_v1_readonly.py`、`lp_rh_pool_probe_v1_readonly.py` + 3 个配对测试 | `RpcPool`（加 chain 4663 到 `CHAINS`，或在 RH 模块内以参数注入端点表，**优先后者**，避免动共享表） |
| RH-02 | `lp_rh_pool_collector_v1_readonly.py`、`lp_rh_market_state_v1_readonly.py`；`reports/lp_rh/scanner.db` 的 `rh_*` 15 张表 | `ScannerStore` 的 WAL/单 writer 模式思想（复制模式，不 import daemon） |
| RH-03 | `lp_rh_netcover_inputs_v1_readonly.py`、`lp_rh_portfolio_policy_v1_readonly.py`、`lp_rh_terminal_gate_v1_readonly.py`、`lp_rh_funnel_autopsy_v1_readonly.py` | import `lp_netcover_engine_v1_readonly`（不改）、`lp_swap_cost_model_v1_readonly` |
| RH-04 | `lp_rh_pnl_v1_readonly.py`、`lp_rh_shadow_runner_v1_readonly.py` | `GateStore.record_rpc_health` 模式 |

配置解析：新 parser 读 `docs/rh_pivot/config.rh.shadow.example.toml`（Python 3.12 自带 `tomllib`）。

## 4. 与文档不一致处（先报）

1. B1 §6.1 列四个进程，实测五个（第二个 scanner 写 `lp_scanner_v2_20260823`）。
2. B1 §10.3 "两张死表 0 写入者"过时：有 writer、未触发（见 FIELD_PRODUCER_MAP）。
3. B1 §10.6 "backup 副本仅 50–140M"不成立：压实后 2.06G / 1.44G。
4. B1 §10.2 根因已定位：非 RPC/市场退化，是 `RpcPool._penalize` 溢出（LEGACY_FAILURE_AUTOPSY）。
5. 文档预期 HEAD `1e1d9bd`，实际 `0e2b6e6`（纯文档 commit）。
