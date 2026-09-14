# PAPER_START_REQUEST_CN.md

owner 显式批准 `paper_only` daemon 启动的请求包。

## 0. 状态快照

| 项 | 值 |
|----|---|
| TASK_STARTED_MODE | NONE |
| HOST_EXISTING_RH_READONLY_PROCESSES | 5 |
| PAPER_STARTED | **false** |
| LIVE_STARTED | **false** |
| KEYS_CREATED | 0 |
| SIGNATURES | 0 |
| BROADCASTS | 0 |
| pytest | **5209 / 0 / 14** |
| audit_repro defects | **0** |
| audit_repro probe_errors | **0** |
| CORE_PAPER_ENGINEERING_GATE | FAIL（已知；不阻断 paper_only 启动） |
| FORWARD_PAPER_DATA_VALIDITY | **NOT_PROVEN**（DB 空；需 owner 启动采集） |
| OBSERVE_ONLY_ACTIVE | true |
| OBSERVE_ONLY_REQUIRES_OWNER_APPROVAL_TO_EXIT | true |

## 1. 已就绪（无需 owner 操作）

- ✅ **Gap 1**：paper `run_once` / `status` 接真实研究引擎（`_run_episode_persisted` + `rh_episode_summary`）
- ✅ **Gap 2**：严格 E2E 正控制（NAV 1000→990、PnL=-10、对账 PASS）通过
- ✅ **Gap 3**：Forward Paper 数据有效性检查器（真算 stage_a_status，禁止 PID/tick/row-count 代理）
- ✅ **Gap 4**：干净 checkout 重验，JUnit / 原始日志保存到 `reports/lp_rh/release_candidate_a767740/`

## 2. 需 owner 决策

### 决策 A：是否推送本轮 commit 到 origin

- 推荐：**推送**
- 依据：所有 Gap 验证通过，release candidate 完整
- 风险：远端 Actions 若 FAIL，本机结论不成立（Gap 4 一致性要求）

### 决策 B：是否启动 paper_only daemon 长跑

- 推荐：**暂不**。先在本地手动跑一次 `run_once`：
  ```bash
  python3 -c "
  import sys; sys.path.insert(0, '.')
  from scripts.lp_rh_paper_daemon_entry_v1 import run_once, status
  print('pre:', status('configs/paper_rh_core_v1.toml'))
  rc = run_once('configs/paper_rh_core_v1.toml')
  print('rc=', rc)
  print('post:', status('configs/paper_rh_core_v1.toml'))
  "
  ```
  预期：`pre.episodes_run=0`、`rc=0`、`post.episodes_run=1, last_tick_at=<ISO>`。
- 启动 daemon 长跑前先确认：
  - 远端 Actions 一致 PASS（决策 A）
  - Forward Paper 数据有效性（决策 C）已开始累积小时级窗口

### 决策 C：是否让采集器在 rh_market_states 表里累积 ≥ 72h 数据

- 推荐：**是**（如果 owner 想让 paper 真跑）
- 依据：当前 DB 0 行 → Forward Paper 数据有效性 `NOT_PROVEN` → paper daemon 写到 `rh_episode_summary` 但仍处于 NOT_PROVEN 状态
- 路径：5 个长跑 RH 进程**继续**只读运行；采集器自动填充 `rh_market_states`（不需 owner 触发）

### 决策 D：是否扩 verify_calldata / 白名单 / 双 provider

- 推荐：**否**（下次迭代；本期硬约束）
- 依据：calldata whitelist、provider independence、quote refresh cron 是 W1/W2/W3/W4 工程，已在 Plan 中但本期不在 scope

## 3. 安全硬线（必须保持）

- ✅ `signing_enabled=false`、`broadcasting_enabled=false`
- ✅ `tiny_live_authorized=false`
- ✅ `live_allowed=false`
- ✅ 5 个长跑进程未触动
- ✅ 不创建/导入私钥、不签名、不广播、不动资金

## 4. 复核命令（owner 一键）

```bash
cat PAPER_MIN_RELEASE_V1_CN.md
cat BLOCKERS_20260914_RC_CN.csv
cat reports/lp_rh/release_candidate_a767740/junit_full.xml | head -5
cat reports/lp_rh/release_candidate_a767740/audit_repro.json | head -20
git diff --stat a767740 -- scripts/lp_rh_paper_daemon_entry_v1.py scripts/lp_rh_paper_data_validity_v1.py tests/test_lp_rh_paper_daemon_entry_v1.py tests/test_lp_rh_paper_data_validity_v1.py
```

通过 → ACCEPT；任一不一致 → REJECT，标 NOT_PROVEN。