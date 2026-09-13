# W5 SPEC — 交付可部署的独立 Paper 包（不是立即启动）

**目标 SHA**: 18a8f39744af2d61d16737b7311d88cd88accea9 (W1+W2+W3 完成后)
**owner-授权**: 已批 V3 taskpack（部署包**不**自动启动）

## 范围

只动：
- `configs/paper_rh_core_v1.toml` (NEW — 版本化 paper 配置)
- `scripts/lp_rh_paper_daemon_entry_v1.py` (NEW — preflight/status/--once 入口)
- `scripts/lp_rh_paper_pid_lock_v1.py` (NEW — PID lock 工具)
- `tests/test_lp_rh_paper_daemon_entry_v1.py` (NEW — 受控 E2E)
- `tests/test_lp_rh_paper_pid_lock_v1.py` (NEW — 并发保护)
- `docs/runbooks/paper_rh_core_ops.md` (NEW — 受控运行手册)
- `reports/paper_closeout_v3_rev1/PAPER_DEPLOYMENT_RUNBOOK_CN.md` (NEW — 部署 runbook)
- `reports/paper_closeout_v3_rev1/PAPER_APPROVAL_REQUEST_CN.md` (NEW — 申请模板)
- `reports/paper_closeout_v3_rev1/TINY_LIVE_ROADMAP_CN.md` (NEW — 路线图)
- `reports/paper_closeout_v3_rev1/FINAL_VERDICT.json` (NEW — 最终状态)
- `reports/paper_closeout_v3_rev1/MANIFEST.sha256` (NEW)
- `specs/W5_PAPER_DEPLOY_PACKAGE_V3.md` (本文件追加 patch log)

**不许动**：
- 任何运行中 daemon / systemd unit
- 旧 canary / 旧 paper / scanner / watchdog
- 持久化生产 DB
- 私钥 / signer / broadcaster
- 六个冻结常量
- main 分支

## 必须交付

### I1: 版本化配置 `configs/paper_rh_core_v1.toml`

```toml
[meta]
profile = "rh-core-paper-v1"
scope = "paper_only_no_signing"
expected_approval = false

[chain]
chain_id = 4663
network = "robinhood_mainnet"

[pool]
profile = "CORE_V3"
unknown_hook_policy = "REJECT_UNSUPPORTED"
tvl_cap_usd = 1000

[capital]
virtual_capital_usd = 1000
position_size_usd = 100
idle_cash_usd = 900
external_funding_initial_usd = 0

[economics]
stable_min_frac = 0.7
netcover_shadow = 1.0
expected_min_netcover = 1.5
position_tvl_share = 0.0005
hard_position_tvl_share = 0.001
lvr_coefficient_model = 0.50

[execution]
mode = "paper_only"
signing_enabled = false
broadcasting_enabled = false

[paths]
ledger_db = "/var/lib/lpbot/paper_rh_core_v1.db"
reports_dir = "/var/lib/lpbot/reports/paper_rh_core_v1/"
pid_file = "/var/run/lpbot-paper-rh-core-v1.pid"

[resources]
max_rss_mb = 512
max_disk_mb = 2048
max_rpc_requests_per_minute = 60
rpc_timeout_seconds = 30

[safety]
shutdown_on_window_close = true
shutdown_on_data_stale_seconds = 600
shutdown_on_invariant_violation = true
```

### I2: Paper daemon entry script

新建 `scripts/lp_rh_paper_daemon_entry_v1.py`:
- `def preflight(cfg_path) -> tuple[bool, list[str]]`：检查配置 + DB 路径可写 + pid 文件不存在 + resources budget 充足；返回 (ok, [reason])
- `def status(cfg_path) -> dict`：返回当前状态 (mode, started_at, last_tick_at, episodes_run, total_pnl, capital)
- `def run_once(cfg_path) -> int`：跑一轮 episode；合法 NO_TRADE 返回 0，技术异常返回 1
- `def run_daemon(cfg_path)`：常驻运行循环，事件驱动 + 异常上报

每个函数**默认不启动**，由调用方决定。

### I3: PID lock 工具

新建 `scripts/lp_rh_paper_pid_lock_v1.py`:
- `acquire(path) -> bool`：原子写 pid，失败返回 False
- `release(path)`：读 pid 检查 alive 后删除
- `is_alive(path) -> bool`：读 pid 检查进程是否仍活
- 使用 `os.O_EXCL | os.O_CREAT` + flock

### I4: 受控 E2E 测试

新建 `tests/test_lp_rh_paper_daemon_entry_v1.py`:
- `test_preflight_passes_with_valid_config` — 临时 valid TOML → ok=True
- `test_preflight_fails_when_pid_file_held` — 假 PID 文件存在 → ok=False with reason
- `test_run_once_returns_zero_on_no_trade` — 无候选 → return 0 (合法 NO_TRADE)
- `test_run_once_returns_one_on_tech_error` — 故意技术错 → return 1
- `test_status_reflects_initial_state` — 启动后 status 含 mode=paper_only, episodes_run=0
- `test_daemon_loop_handles_sigtem_cleanly` — SIGTERM → 优雅退出 + PID 释放

新建 `tests/test_lp_rh_paper_pid_lock_v1.py`:
- `test_acquire_succeeds_when_no_existing_lock`
- `test_acquire_fails_when_lock_held_by_other`
- `test_release_removes_lock`
- `test_is_alive_returns_true_for_running_process` — 当前 PID
- `test_is_alive_returns_false_for_stale_lock` — PID 已退出

### I5: 部署 runbook + 申请模板

新建 `reports/paper_closeout_v3_rev1/PAPER_DEPLOYMENT_RUNBOOK_CN.md`:
- 受控启动步骤（preflight → status → run_once 验证 → 限时运行）
- 资源预算检查清单
- 故障恢复步骤
- 日志位置 + 监控项
- 明确禁止动作清单

新建 `reports/paper_closeout_v3_rev1/PAPER_APPROVAL_REQUEST_CN.md`:
- 基于 `OWNER_APPROVAL_REQUEST_TEMPLATE_CN.md` 模板
- 填入：本轮具体 SHA / W0-W4 完成证据 / 5 类门 PASS 状态
- `approval_granted = false`
- 列出需要 Owner 决策的事项（cap policy、限时段、停止条件等）

新建 `reports/paper_closeout_v3_rev1/TINY_LIVE_ROADMAP_CN.md`:
- E0 → A → B → C → D 阶段路径
- 每阶段必须拿到的结果
- 不在 V3 任务范围：明确不授权 live

### I6: FINAL_VERDICT.json + MANIFEST.sha256

新建 `reports/paper_closeout_v3_rev1/FINAL_VERDICT.json`:
```json
{
  "schema_version": "final-verdict/3",
  "as_of_date": "2026-09-13",
  "reviewed_sha": "18a8f39...",
  "ENGINEERING_GATE": "PASS|FAIL|BLOCKED",
  "STAGE_A_DATA_GATE": "PASS|FAIL|UNOBSERVED",
  "COLLECTION_START_GATE": "PASS|FAIL|BLOCKED",
  "PAPER_TECHNICALLY_READY": true|false,
  "PAPER_OWNER_AUTHORIZED": false,
  "RH_PAPER_STARTED_BY_THIS_TASK": false,
  "LIVE_TECHNICALLY_READY": true|false,
  "LIVE_OWNER_AUTHORIZED": false,
  "LIVE_STARTED_BY_THIS_TASK": false,
  "PAPER_START_REQUIRES_EXPLICIT_OWNER_APPROVAL": true,
  "evidence_files": [...],
  "residual_blockers": [...]
}
```

新建 `reports/paper_closeout_v3_rev1/MANIFEST.sha256`:
- 所有 reports/paper_closeout_v3_rev1/ 下文件的 SHA256 清单

## 验收命令

```bash
# I1+I2+I3: 写完后 import smoke test
python3 -c "import sys; sys.path.insert(0,'.'); from scripts.lp_rh_paper_daemon_entry_v1 import preflight, status, run_once; from scripts.lp_rh_paper_pid_lock_v1 import acquire, release; print('imports OK')"

# I4: 受控 E2E 测试
python -m pytest tests/test_lp_rh_paper_daemon_entry_v1.py tests/test_lp_rh_paper_pid_lock_v1.py -v --tb=short -p no:cacheprovider 2>&1 | tail -15

# I6: 最终产物
sha256sum reports/paper_closeout_v3_rev1/*.{md,json,toml,xml} > reports/paper_closeout_v3_rev1/MANIFEST.sha256 2>&1
python -c "import json; d=json.load(open('reports/paper_closeout_v3_rev1/FINAL_VERDICT.json')); print(json.dumps(d, indent=2))"

# Final full regression
python -m pytest tests/ -q --tb=line -p no:cacheprovider 2>&1 | tail -5
```

## 风险与边界

- 不实际启动 paper daemon
- 不修改旧 canary/scanner/watchdog
- 不创建 systemd unit 启动（只写配置文件）
- 不连 RPC（preflight 跳过 RPC 检查）
- 不导入私钥
- 不签名 / 不广播

## 输出要求

每个 I 分块贴 pytest 输出。最终 FINAL_VERDICT.json 原文 + MANIFEST.sha256 头 5 行。
