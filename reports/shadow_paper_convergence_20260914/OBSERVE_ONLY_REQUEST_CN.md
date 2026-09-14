# OBSERVE_ONLY 申请包（不启动）

> 任务：RH_CORE_OBSERVE_TO_PAPER_CONVERGENCE_V1 / P3
> 状态：**本任务不启动任何常驻采集**。本文件是申请材料 + 已验证命令，待 Owner 显式批准后再按窗口启动。
> 命名严格：本文 `OBSERVE_ONLY` 仅指"公共数据读取、候选与拒绝原因记录、影子决策意向"——**不**产生被宣称为已成交的正式 Paper 仓位、**不**触发真实交易能力。

## 1. 固定代码/配置摘要

```
code_sha:          7dd4e6458ad43e964b17b0a58258b198cdab4c65 (HEAD = docs fd0ffa6, business code = 7dd4e64)
branch:            feat/prd-v2.1-m0-shadow
config_file:       configs/paper_rh_core_v1.toml
expected_approval: false  (in toml)
signing_enabled:   false  (in toml)
broadcasting_enabled: false  (in toml)
profile:           rh-core-paper-v1
```

## 2. 显式链/池/合约角色

```
chain_id:          4663
chain_role:        robinhood_mainnet
pool_profile:      CORE_V3
tvl_cap_usd:       1000
unknown_hook_policy: REJECT_UNSUPPORTED
chain_manifest_status: UNVERIFIED_PENDING_RPC  (待 OBSERVE_ONLY 启动后通过 RPC 探测 attest)

合约地址 registry（来自 scripts/lp_rh_registry_v1_readonly.py；attested=False 直至 RPC 确认）：
  V3_FACTORY            0x1f7d7550b1b028f7571e69a784071f0205fd2efa
  V3_POSITION_MANAGER   0x73991a25c818bfbf1128deaab1492d45638de0d3
  POOL_USDG_WETH        0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca
  WETH                  0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73
  USDG                  0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168
```

## 3. 公共只读 RPC 方法 + 目标 allowlist

只允许以下方法；含写方法的 batch 同样拒绝。

```
ALLOWED RPC METHODS (eth_* namespace, all read-only):
  eth_chainId
  eth_blockNumber
  eth_getBlockByNumber   (tag=latest or tag=finalized only, no tag=pending)
  eth_call               (to whitelisted addresses only; see §3.1)
  eth_estimateGas        (read-only static; does NOT submit a transaction)
  eth_gasPrice
  eth_getLogs            (filter address=POOL_USDG_WETH only)
  eth_getTransactionReceipt  (tx hash argument; only used to read receipts of historical txs, never ours)

FORBIDDEN RPC METHODS (rejected at RPC adapter layer):
  eth_sendTransaction
  eth_sendRawTransaction
  eth_sign
  personal_sign
  eth_signTypedData*
```

### 3.1 `eth_call` 白名单

`to ∈ { V3_FACTORY, V3_POSITION_MANAGER, POOL_USDG_WETH, WETH, USDG }` + 任何合约 selector ∈ `{ 0x88316456 mint, 0x42966c68 burn, 0xfc6f7865 collect, 0x219f5d17 increaseLiquidity, 0x0c49ccbe decreaseLiquidity, 0xac9650d8 multicall }`

`to == 0x000000000000000000000000000000000000dead` 或 `0x0...01` 或 `0xc3c3c3...` 测试 fixture：拒绝。

## 4. 独立低权限身份 + 新数据目录

```
USER_IDENTITY:    新建 `lpbot-observe` 系统用户（uid 待 Owner 指定，仅 nogroup 权限）
DATA_DIR:         /var/lib/lpbot-observe/paper_rh_core_v1/
  ├── db/         (新 sqlite, NOT /var/lib/lpbot/, NOT /var/lib/lpbot-shadow/, NOT 与 production 共享)
  ├── reports/    (新 reports 根，仅本观察任务可见)
  ├── logs/       (新 logs 根)
  └── pid/        (pid file, mode 0600, owner lpbot-observe:nogroup)
```

**不可达**：NO 钱包 / NO 密钥 / NO SSH / NO 生产配置挂载 / NO docker socket / NO sudo / NO `/var/lib/lpbot/` / NO `/etc/lpbot/` / NO `~/.ssh/` / NO `~/.env*` 访问。

## 5. 子进程 / 动态加载 / 默认环境约束

- 不 spawn Go daemon (`./bin/lpbot-shadow` / `lpbot-live` / `lpbot-dryrun`)
- 不动态 import 生产路径下任何模块
- 不通过 `subprocess.run(['go', ...])` / `subprocess.run(['./bin/lpbot*', ...])`
- 所有 subprocess 调用必须在 OBSERVE_ONLY 启动前以 grep 验证，命令白名单由 Owner 审批
- 错误恢复路径不得 `os.chdir('/var/lib/lpbot')` 或 `Path('/etc/lpbot')` 之类回退

## 6. 单 writer + 资源/磁盘上限 + 信号退出 + 断点恢复

```
MAX_RSS_MB:            512      (from config)
MAX_DISK_MB:           2048     (from config; 软预算)
MAX_RPC_REQUESTS_PER_MINUTE: 60 (from config)
RPC_TIMEOUT_SECONDS:   30       (from config)
SHUTDOWN_ON_WINDOW_CLOSE:       true  (SIGTERM graceful)
SHUTDOWN_ON_DATA_STALE_SECONDS: 600  (10 min 无进展则停)
SHUTDOWN_ON_INVARIANT_VIOLATION: true  (invariant 检测失败立即停)
```

PID lock: `/var/run/lpbot-paper-rh-core-v1.pid`，mode 0600；启动时检查存在 → exit 2。

断点恢复：每 5 min 把 `last_tick_at + window_cursor` 写到 `state.jsonl`；重启后从最后 tick 续跑，不重复采样、不丢窗口。

## 7. 有效性检查（不能只看 PID 或日志 mtime）

- source 时间推进：`block_number` 必须单调递增；倒退 > 2 blocks → stop
- 计划窗口覆盖：每小时抽查一次 `coverage_window_pct = sampled_buckets / planned_buckets`；< 95% 写 warning
- 缺关键字段：任何 pool state record 缺 `pool_address | tick | sqrtPriceX96 | liquidity | observed_at` → stop
- 错误链/池：探测到 `chain_id != 4663` 或 `pool_address not in registry` → stop
- 采样失败/重连：连续 5 次 RPC 失败 → stop + 写 `reports/stop_cause.txt`

## 8. 范围（只一个 RH V3 CORE 池）

```
ALLOWED POOLS: [ POOL_USDG_WETH ]
FORBIDDEN POOLS: STOCK_* / MEME_* / V4 / 任何非 CORE_V3 profile
NO_TRADE 兜底：若 registry attestation 失败或 pool 不在 allowlist → 写 "REJECT_UNSUPPORTED"，不进 Paper 候选
```

## 9. 已验证命令（启动前可预演）

```bash
# 0) Preflight: config 解析 + 签名/broadcasting 都 false
python3 -c "
import sys; sys.path.insert(0,'.')
from scripts.lp_rh_paper_daemon_entry_v1 import preflight
ok, errs = preflight('configs/paper_rh_core_v1.toml')
print('PREFLIGHT:', 'PASS' if ok else 'FAIL', errs)
"
# Expected: PREFLIGHT: PASS []

# 1) Status: 当前 episodes_run=0, last_tick_at=None
python3 -c "
import sys, json; sys.path.insert(0,'.')
from scripts.lp_rh_paper_daemon_entry_v1 import status
print(json.dumps(status('configs/paper_rh_core_v1.toml'), indent=2))
"
# Expected: { "mode": "paper_only", "episodes_run": 0, "last_tick_at": null }

# 2) Chain manifest read-only attestation (no RPC call)
python3 -c "
import sys; sys.path.insert(0,'.')
from scripts.lp_rh_chain_manifest_v1_readonly import MANIFEST_STATUS, is_selector_allowed
print('MANIFEST_STATUS:', MANIFEST_STATUS)
print('selector 0x88316456 (mint) allowed:', is_selector_allowed('0x88316456'))
"

# 3) Single-episode stub run (NO_TRADE, no real chain call)
python3 -c "
import sys; sys.path.insert(0,'.')
from scripts.lp_rh_paper_daemon_entry_v1 import run_once
rc = run_once('configs/paper_rh_core_v1.toml')
print('RUN_ONCE EXIT_CODE:', rc)
"
# Expected: EXIT_CODE 0 (NO_TRADE stub)
```

## 10. 启动条件（Owner 显式批准 + 全部勾选）

- [ ] Owner 给出明确批准：`OBSERVE_OWNER_AUTHORIZED=true`
- [ ] `lpbot-observe` 系统用户已建（uid 范围待定）
- [ ] `/var/lib/lpbot-observe/paper_rh_core_v1/` 已建且 mode 0700
- [ ] `/var/run/lpbot-paper-rh-core-v1.pid` 已建且 mode 0600
- [ ] RPC 公共 endpoint 已确认可达 + 返回 chainId=4663
- [ ] 启动前 6h 设为运维检查点；20-30 min 一次健康检查
- [ ] 失效源不通过"无效空跑"绕过，必须 stop + 写 stop_cause
- [ ] StageA ≥72h 真实前向数据 + 关键证据计划窗口覆盖 ≥99% 后才考虑 FORWARD_PAPER 申请

## 11. 安全边界（CLAUDE.md / 项目 freeze）

- 不启动 paper/live/canary daemon
- 不创建/导入私钥
- 不签名（`signer.sign()` 不允许）
- 不广播（`broadcaster.SendTransaction` 不允许）
- 不使用真实资金
- 不放宽 `live_allowed`
- 不设 `tiny_live_authorized=true`
- 不修改 main 分支
- 不绕过 CLAUDE.md freeze（LP 策略研究仍冻结）

## 12. 已知事实与不做承诺

- `chain_manifest_status = UNVERIFIED_PENDING_RPC`：OBSERVE_ONLY 启动**不**需要把它升级为 VERIFIED；attestation 在 OBSERVE_ONLY 期间逐步完成。
- 旧 100U 政策与 RH CORE 1000U virtual capital 不相容的问题保留至独立资金政策审批；本 OBSERVE_ONLY 不动用任何资金，不修改该政策。
- StageA 数据完整覆盖 ≥99% 与 PROFILE_GRADUATION 14 完整日（且含一个周末）是 **FORWARD_PAPER** 的进入条件，**不**是 OBSERVE_ONLY 的进入条件。
- OBSERVE_ONLY 期间观察到的任何"潜在候选"**仅**记录候选与拒绝原因，**不**进入被宣称为已成交的 Paper 仓位。

## 13. Owner 决策表

| 决策项 | 默认 | 备选 | 备注 |
|---|---|---|---|
| OBSERVE_OWNER_AUTHORIZED | false（未批） | true（明确批准） | 必须有外部实际授权证据 |
| 启动窗口 | （待批） | 限时 6h 检查点 + 48h 续跑 | 任一失效源不绕过 |
| RH V3 CORE 池范围 | 1 个（USDG/WETH） | 多池需重新审批 chain manifest | 不扩大 |
| 是否启动 FORWARD_PAPER | 单独申请 | 不能从"影子"一词推导 | 必须显式 scope_change + Owner 批 |
| 是否启动 LIVE | NEVER（本任务） | 资金政策独立审批 | 不在本任务窗口 |

---

> 本文件随 P3 提交。本任务**不**自行启动 OBSERVE_ONLY；Owner 明确批准 + 上述勾选项全通过后才进入采集窗口。
