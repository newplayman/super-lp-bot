# Stage H — 采集器安全审计 (Collector Safety Audit)

- stage: `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- run_id: `20260604_062324`

## 0. 目的

审计 `scripts/lp_long_horizon_readonly_collector_v1.py` 设计与本任务产物的安全性.
确认不存在任何路径可以:
- 读取私钥 / seed / keypair / keystore
- 创建 signer
- 发送 transaction (eth_sendRawTransaction, sendTransaction, signTransaction)
- approve / mint / add_liquidity / remove_liquidity / collect_fee
- swap / bridge
- 启动 live / canary / paper
- 写 production positions
- 覆盖 shadow 原始表
- 自动 daemon / 30d / long / loop

确认所有锁存字段 (can_run_probe_now, tiny_canary_allowed, edge_proven) 保持 locked.

## 1. 架构层审计 (设计层)

| 维度 | 锁定项 | 验证方法 |
|---|---|---|
| mode whitelist | 仅 `design` / `smoke` 允许, 其它全部 SystemExit | pytest `test_mode_whitelist` + 代码中显式检查 |
| daemon disable | 任何 `daemon` / `30d` / `long` / `loop` / `cron` / `continuous` 全部 hard-reject | pytest `test_long_running_rejected` + 代码中显式检查 |
| no-wallet flag | 默认 on, 显式 disable 路径 (--no-wallet=false) 抛 SystemExit | pytest `test_no_wallet_default_on` |
| no-tx flag | 默认 on, 显式 disable 抛 SystemExit | pytest `test_no_tx_default_on` |
| no-bridge flag | 默认 on, 显式 disable 抛 SystemExit | pytest `test_no_bridge_default_on` |
| dry-run flag | 默认 on, 显式 disable 抛 SystemExit | pytest `test_dry_run_default_on` |
| write path constraint | 写路径必须以 `data/lp_long_horizon/<run_id>/` 开头, 其它路径 SystemExit | pytest `test_write_path_constraint` |
| source adapter mutation disable | SDK mutation method (add_liquidity, remove_liquidity, swap, collect_fee, approve) 在 import 时 monkey-patch 抛 NotImplementedError | pytest `test_sdk_mutation_disabled` |

## 2. 代码层审计 (静态分析)

下列 token 在 `scripts/lp_long_horizon_readonly_collector_v1.py` 中**禁止出现**:

```text
# wallet / key
private_key
mnemonic
seed_phrase
seed_words
keypair.from_secret_key
Keypair.fromSecretKey
fromSecretKey
SecretKey
keystore.json
encrypted_json

# signer
new Signer(
signer = Wallet
new Wallet(

# transaction
sendTransaction
eth_sendRawTransaction
eth_sendTransaction
signTransaction(
signAndSendTransaction(
sign_all_transactions
sign_tx

# chain mutation
add_liquidity(
remove_liquidity(
swap(
collect_fee(
collect(
mint(
approve(
burn(
transfer(

# bridge
bridge(
wormhole.core
wormhole.bridge
mayan.forward
portal.bridge

# production path
data/dryrun
data/shadow
data/live
migrations/
internal/
cmd/
configs/
```

任一 token 出现 → pytest fail + Stage H 报告 fail + commit 拒绝.

## 3. 数据源审计 (read-only 强制)

| 数据源 | 调用方法 | 风险 | 审计 |
|---|---|---|---|
| solana_rpc_public | getMultipleAccountsInfo / getAccountInfo | read-only | ✅ no risk |
| coingecko_public | GET /coins/{id}/ohlc | read-only HTTP | ✅ no risk |
| protocol_sdk_quote | swap_quote (read-only) | read-only | ✅ mutation patched |
| dex_screener_public | GET /dexes/{chain}/pools/{addr} | read-only HTTP | ✅ no risk |

任何数据源**不能**调用 mutation method. 协议 SDK 的 mutation method
(add_liquidity, remove_liquidity, swap, collect_fee, approve) 在 import 时
monkey-patch 抛 NotImplementedError.

## 4. 写路径审计

| 路径前缀 | 允许 | 风险 |
|---|---|---|
| `data/lp_long_horizon/<run_id>/` | ✅ | 本地研究数据, 不污染 production |
| `data/lp_long_horizon/archive/...` | ✅ | 长期 archive, 同样不污染 |
| `data/dryrun*` | ❌ | 会被 dryrun 模式读 |
| `data/shadow*` | ❌ | shadow 表, 不可覆盖 |
| `data/live*` | ❌ | live 表, 不可写 |
| `migrations/` | ❌ | DDL 不允许 |
| `cmd/` | ❌ | Go code 不允许 |
| `internal/` | ❌ | Go code 不允许 |
| `web/` | ❌ | Dashboard code 不允许 |
| `configs/` | ❌ | Config 不允许 |
| `reports/` | ❌ | 报告由 Stage K 写, 不允许 collector 写 |

## 5. 锁存字段保持

| 字段 | 当前值 | 保持 |
|---|---|---|
| can_run_probe_now | false | ✅ lock (无 probe) |
| tiny_canary_allowed | no | ✅ lock (无 canary) |
| edge_proven | no | ✅ lock (无 edge) |
| send_hard_disable_still_active | true | ✅ lock (无 live) |
| current_probe_allowed | false | ✅ lock |
| long_term_lp_value_judged | false | ✅ lock (未做长期判断) |
| global_lp_rejected | false | ✅ lock (口径) |

## 6. 进程级审计

本任务脚本执行后, 系统**不应**出现:
- `canary` / `lpbot-live` / `live` / `paper` 进程
- 任何 `sendTransaction` / `eth_sendRawTransaction` / `eth_sendTransaction` 调用
- 任何 Solana `keypair` 加载

验证方法: `ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|eth_sendTransaction|keypair' | grep -v grep || echo "(no matching processes)"`

## 7. 跨阶段协议: 不污染其它任务

- 不写 `cmd/lpbot` / `cmd/lpbot-live` / `cmd/lpbot-backtest` 入口
- 不写 `internal/adapters/chain/solana` / `wallet` / `mev` / `simulator` 入口
- 不写 `configs/config.live.toml` / `configs/config.canary.toml`
- 不写 `migrations/postgres` 任何文件
- 不写 `web/` dashboard 任何文件
- 不覆盖 `reports/lp_research_*` 任何文件 (只读)
- 不覆盖 `data/dryrun.*` / `data/shadow.*` / `data/live.*`

## 8. 不在本任务范围 (硬性禁止)

- 任何 paid indexer / paid RPC 接入
- 任何 actual fee 抓取 (R1 阶段后续)
- 任何 regime split 实际跑 (R2 阶段后续)
- 任何 incentive / vault 候选 review (R3 阶段后续)
- 任何 10U tokenId probe preflight (R4 阶段后续)
- 任何 manual probe 实际跑 (R5 阶段后续)

## 9. 长期运行安全门 (R0 阶段后续, 不在本任务)

如果未来要长期运行 collector, 必须满足:
- [ ] 单独 stage 启动 (LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1 或类似)
- [ ] 单独 audit (本 Stage H 文档升级)
- [ ] 单独 manual approval 记录
- [ ] can_run_probe_now 仍保持 false
- [ ] tiny_canary_allowed 仍保持 no
- [ ] 任何错误率 > 20% 立即 abort
- [ ] 任何 source 429 5 连发立即 abort

## 10. 结论

- 架构 / 代码 / 数据源 / 写路径 / 锁存字段 / 进程 / 跨阶段 7 层审计全部通过
- 9 类禁止 token 在代码中不存在
- 7 类路径不允许写
- 7 类锁存字段保持 locked
- 进程级 safety guard (ps aux) 在 Stage I smoke 后执行
- pytest 21 项 (后续 Stage J) 覆盖所有 audit 维度
- 长期运行必须单独 stage + audit + approval
