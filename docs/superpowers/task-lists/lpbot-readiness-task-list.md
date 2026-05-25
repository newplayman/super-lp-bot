# LPBot 全量任务清单（基于审计与现场交付）

版本：2026-05-23  （同步自最近夜间自动化与人工干预）

## 任务总览

- 优先级：P0（高）→ P3（低）
- 状态：`[done]` 已完成，`[wip]` 进行中，`[todo]` 待做
- 每项附带证据、下一步与最后更新时间

## 全量任务列表

### P0（上线必要）

- [x] **P0-01 接口风险闸门对齐**：`live.enabled=false` 时禁止 canary 入口广播交易，避免 CLI 与可观测状态不一致。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/configs/config.canary.toml`、`/Users/bendu/lp-bot/v3/cmd/lpbot/canary_mint.go`、`/Users/bendu/lp-bot/v3/cmd/lpbot/canary_preflight.go`
  - 证据：Superpowers 审计高风险项。
  - 下一步：定义明确的 manual_canary_override 语义，默认 fail-closed；dashboard/readiness 与 cli 行为一致。
  - 记录：`2026-05-23` 已完成：引入 `LPBOT_MANUAL_CANARY_OVERRIDE` 显式人工覆盖开关，`canary_preflight`/`prepare`/`mint`/`exit` 与 `canary_readiness` 已共用同一 gate 语义。

- [x] **P0-02 真实可控 live 路径必须读取 DB KillState**：主循环 risk gate 使用 `riskRepo`/`killState`，不应只依赖内存配置。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/cmd/lpbot/main.go`
  - 证据：`main.go:608`、`main.go:616` 中未完整注入。
  - 下一步：接入 `KillState` 与 `RiskRepo`，并在 readiness 和 loop 中统一失败阻断。
  - 记录：`2026-05-23` 已完成：`wireMainLoop()` 改为给 `RiskGate` 注入 `app.store.RiskRepo()`，主循环已不再只依赖内存态。

- [x] **P0-03 完整 live 状态机**：`open -> open_in_progress -> open_confirmed -> hold -> close -> settle` 的状态链路与幂等性。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/cmd/lpbot/main.go`
  - 证据：提交与广播写入顺序有“脏状态”风险，见 `main.go:1394`/`1404`/`1426`。
  - 下一步：重构 live path，让 DB 与链上状态二次确认。
  - 记录：`2026-05-23` 已完成：主 live 开仓已改为“先构建/签名，再落库 approved/opening”，确认后自动转 `tx=confirmed` 与 `position=open`；live close / collect / rebalance 全部接入 canary-safe Base V3 路径，失败时统一落 `exit_failed/rejected`，reopen 失败也会留下可审计的新仓位记录。

- [ ] **P0-04 事务记录可观测性**：`broadcast_at` 必须落库，支持失败重试、超时和重复 tx 去重。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/internal/adapters/store/postgres/tx_repo.go`
  - 证据：`main.go` 与 `tx_repo.go` 在广播后状态链未闭环。
  - 下一步：补 `broadcast_at`、失败原因、重试次数；增加 `state` 转移记录。
  - 记录：`2026-05-23` 已完成：`TxRepo.UpsertTx()` 和 `UpdateTxStatus()` 开始自动写入 `broadcast_at`，空 hash 时退回 `tx.ID` 防止 built 记录冲突。

- [ ] **P0-05 可审计 PnL/账本链路**：避免 `le-{block}` 冲突，保证每次事件持久化且幂等。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/internal/adapters/store/postgres/ledger_repo.go`
  - 证据：`ledger_id` 规则存在同块重用风险。
  - 下一步：改用稳定唯一 ID（如 tx hash + 事件类型 + 链上 nonce/log index）并补写入场景。
  - 记录：`2026-05-23` 已完成：`LedgerRepo.Append()` 改为稳定哈希 ID（position/kind/amount/block/tx 组合），去掉 `le-{block}` 冲突。

- [ ] **P0-06 Solana 签名/广播安全上限**：去掉默认 `SkipPreflight=true`，加入可配置预检阈值。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/internal/adapters/broadcast/live/broadcast.go`
  - 证据：当前设置降低可观测性，放大异常风险。
  - 下一步：引入环境变量控制 preflight 与 dry-run 模式。
  - 记录：`2026-05-23` 已完成：live broadcaster 默认不再跳过 Solana preflight；如确需跳过，必须显式传入 `BroadcastConfig.SolanaSkipPreflight=true`。

### P1（质量与稳定性）

- [ ] **P1-01 Scanner 与池子仓库关系理顺**：`Scanner` 与 `PoolRepo` 写入应分层，主循环不再直接插入重复逻辑。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/internal/core/scanner/scanner.go`、`/Users/bendu/lp-bot/v3/cmd/lpbot/main.go`
  - 证据：`scanner` 未完整作为 source-of-truth。
  - 下一步：明确数据拥有者；让扫描器写入仓库，主循环只消费。
  - 记录：`2026-05-23` 已完成：`scanner.Config` 注入 `PoolRepo`，扫描器在 `ScanOnce()` 内持久化池子，`app.evaluateStrategies()` 不再重复写池。

- [ ] **P1-02 去除主循环阻塞扫描**：`Scanner.Run(ctx)` 在 `evaluate` tick 中阻塞应改为异步 worker。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/internal/core/loop/loop.go`、`/Users/bendu/lp-bot/v3/internal/core/scanner/scanner.go`
  - 下一步：把扫描器放入独立 goroutine + channel 通知。
  - 记录：`2026-05-23` 已完成：`internal/core/loop` 不再在 tick 中调用阻塞式 `Scanner.Run(ctx)`，扫描职责留给外层 app strategy loop。

- [ ] **P1-03 Pool 数据库字段补齐**：持久化 TVL/24h volume/tick range/feeAPR/DEX 基础字段。
  - 现状态：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/migrations/postgres/000001_init_schema.sql`、`/Users/bendu/lp-bot/v3/internal/adapters/store/postgres/pool_repo.go`
  - 下一步：数据库迁移+适配器兼容+滚动 backfill。
  - 记录：`2026-05-23` 已完成：补充 Postgres migration `000003_pool_runtime_columns.sql`，`PoolRepo` 已读写 `liquidity/tick/tvl_usd/vol_24h/fee_apr_24h`。

- [ ] **P1-04 风险仓位总暴露快照**：`AllocationManager` 要有 `PositionRepo` 聚合，阻止超限仓位。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/internal/core/risk/alloc.go`、`/Users/bendu/lp-bot/v3/cmd/lpbot/main.go`
  - 下一步：将 `available_balance`、`position_value` 与 `max_exposure` 严格联动。
  - 记录：`2026-05-23` 已完成：`wireMainLoop()` 使用 `NewAllocationManagerWithRepo(...)`，`loop.EvaluatePool()` 已优先走 snapshot-based per-pool / total exposure 检查。

- [x] **P1-05 close/rebalance/collect stubs 落地**：关闭、再平衡、手续费收集从 stub 改为可执行。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/cmd/lpbot/main.go`
  - 证据：`close/rebalance/collect` 仍有占位实现。
  - 下一步：至少实现安全版 stub 的实际调用链（dry-run→shadow→canary→live）。
  - 记录：`2026-05-23` 已完成：shadow 模式下 `Close/Rebalance/CollectFees` 全部改为 repo-backed 实现；live 模式下三者也已接入 canary-safe Base V3 真实链路，不再假成功。

- [ ] **P1-06 Solana 可见性与可发现性统一**：去除静态 discovery 回退，防止 readiness 报告假阳性。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/cmd/lpbot/solana_readiness.go`
  - 下一步：将“可验证链上发现”与“兜底示例”分离并透明展示。
  - 记录：`2026-05-23` 已完成：移除 static known pool 假数据回退，仅允许真实 datasource、known pool 或 postgres cache。

### P2（安全与可观测）

- [x] **P2-01 Shadow 与 dashboard 指标同步**：Base/Solana canary 指标读取 DB 并写入面板。
  - 状态：`[done]`
  - 记录：`2026-05-22`~`2026-05-23`（可见指标：Base opened/closed、Fee/IL、shadow decision trace）

- [x] **P2-02 WETH/USDC pool 强制与可控 canary**：约束可执行池，支持<=5U安全测试。
  - 状态：`[done]`
  - 记录：`2026-05-23` 已完成 7 次 Base canary 开平仓

- [x] **P2-03 LP 套利链路可读性增强**：面板读取数据库展示代替部分直接链上查询（降低重复链负荷）。
  - 状态：`[done]`
  - 记录：`2026-05-23` DB 驱动的 Dashboard 数据展示已逐步补齐

- [x] **P2-04 Dashboard XSS 与内网访问策略**：`innerHTML` 使用改为安全渲染，避免 `127.0.0.1` 绕行。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/web/dashboard.js`、`/Users/bendu/lp-bot/v3/cmd/lpbot/dashboard.go`
  - 下一步：逐项替换危险插值、约束来源和 Token 权限。
  - 记录：`2026-05-23` 已完成：`cmd/lpbot/dashboard.html` 主要动态文本统一走 `esc()`；`web/dashboard.js` 已移除剩余 `innerHTML/insertAdjacentHTML` 热点，scanner、positions、exit preflights、audit、execution、logs、header/chips 全部改为 DOM-safe 渲染，并通过 `node --check`。

- [ ] **P2-05 dashboard / API 链上实时读写量降噪**：避免在每次请求都打链上 RPC，改为缓存+异步更新。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/cmd/lpbot/dashboard.go`
  - 下一步：增加 15~30s 缓存与 TTL 失效。
  - 记录：`2026-05-23` 已完成：dashboard snapshot 增加 15s 进程内缓存，显著减少 canary readiness 和链上余额/allowance 重复读取。

- [ ] **P2-06 Canary schema 建表改造**：移除运行时 DDL 创建/ALTER；改为迁移版本化。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/cmd/lpbot/canary_state.go`
  - 下一步：迁移脚本 + 并发安全初始化。
  - 记录：`2026-05-23` 已完成：新增 `migrations/postgres/000002_canary_state.sql`，`canary_state.ensure()` 改为只校验 schema，不再业务路径里 `CREATE/ALTER TABLE`。

### P3（工程/运维）

- [ ] **P3-01 CI/Govulncheck/chaos 质量门禁**：修复当前 `ci.yml` 的不稳定点，确保自动化可重复。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/.github/workflows/ci.yml`
  - 下一步：拆分“必过”与“观察”检查。
  - 记录：`2026-05-23` 已完成：工作流新增 `schedule` 触发；将 `quality-gate` 与 `advisory-audit` 分离，`govulncheck` 从 advisory job 运行，不再与必过门禁混杂。

- [x] **P3-02 PostgreSQL 测试强化**：增加真实 SQL/integration 测试覆盖扫描->仓库->风控->ledger。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/internal/adapters/store/postgres/postgres_test.go`
  - 下一步：测试容器化最小数据流程。
  - 记录：`2026-05-23` 已完成：除 `stableLedgerEntryID`、`txBroadcastTimestamp` 外，新增 docker-postgres 最小集成测试，真实覆盖 `PositionRepo`、`TxRepo`、`PoolRepo` round-trip，已执行通过。

- [x] **P3-03 Solana/链上参数配置一致化**：将 RPC、滑点、超时集中于配置文件与环境变量。
  - 现状：`[done]`
  - 关联文件：`/Users/bendu/lp-bot/v3/configs/config.canary.toml`、`/Users/bendu/lp-bot/v3/cmd/lpbot`
  - 下一步：整理配置 schema 与示例 env。
  - 记录：`2026-05-23` 已完成：`config.ChainConfig` 的 `skip_preflight` 已落地；`execution` 配置新增 `tx_deadline_seconds`、`exit_deadline_seconds`、`sign_timeout_seconds`、`send_timeout_seconds`、`mint_slippage_bps`，Base live open/close/rebalance/collect 已切到配置驱动。

## 已完成高价值动作（可复用记录）

- Base canary 已完成 7 轮 mint/exit（同池 `0x6c561b446416e1a00e8e93e221854d6ea4171372`）
- Solana canary 完成 3 笔小额 swap（可继续做链路验证）
- DB 连接链路从多源转读统一为 PostgreSQL 驱动（历史数据可持久化）
- Dashboard API token 与可达性问题修复
- `scripts/run_canary_with_env.sh` 统一运行环境装载

## 执行日志

### 2026-05-23 00:00-06:00
- 完成夜间 run：Base/ Solana 纸面与可控实盘演练。
- 主要结果：Base canary `opened=7 / closed=7`, `transactions=53`。

### 2026-05-23 07:00-至今
- 完成审计回顾后，建立本文任务清单并开始按 P0->P1 优先级推动。
- 当前结论：已完成 `P0-01`、`P0-02`，并推进 `P0-03` 的 live 开仓状态持久化顺序修复。
- 编译记录：`2026-05-23` 执行 `go test -run '^$' -tags=live ./cmd/lpbot` 通过（仅编译校验，不跑测试）。
- 后续推进：已继续完成 `P0-04`、`P0-05`、`P0-06`、`P1-02`、`P1-03`、`P2-05`、`P2-06`。
- 当前阶段：已继续完成 `P1-01`、`P1-04`、`P1-06`、`P3-01`，并推进 `P1-05`、`P2-04`、`P3-03`。
- 本轮补充：`P0-03` 已支持 confirmed->open 自动收口；`P3-02` 已有关键仓库行为测试，并已实际执行通过。
- 本轮补充：`P1-05` 的 shadow `close/rebalance/collect` 已从空 stub 改为真实 repo-backed 状态流，并开始写入确认态 tx 审计记录。
- 本轮补充：`cmd/lpbot/main_test.go` 已统一修正为可复用 sqlite 临时库夹具，并新增 `Close/Rebalance/CollectFees` 的 shadow 行为测试，实际执行通过。
- 本轮补充：`web/dashboard.js` 已进一步去掉一批高频 `innerHTML/insertAdjacentHTML` 热点，日志与状态区改为 DOM-safe 渲染。
- 本轮补充：`main.go` 已补 canary-safe live close helper，并确认 `go test ./cmd/lpbot -run 'TestWire_|TestOrderManagerAdapter_'` 与 `go test -run '^$' -tags=live ./cmd/lpbot` 均通过。
- 本轮补充：`main.go` 已继续补 canary-safe live `CollectFees`，并再次确认 `go test ./cmd/lpbot -run 'TestWire_|TestOrderManagerAdapter_'` 与 `go test -run '^$' -tags=live ./cmd/lpbot` 均通过。
- 本轮补充：`web/dashboard.js` 已继续移除 `audit` / `execution` 区域的模板注入热点，`node --check` 通过。
- 本轮补充：`live_sizing.go` 已新增自定义 ticks 的 mint builder，`main.go` 已接 canary-safe live `Rebalance`，并再次确认 `go test -run '^$' -tags=live ./cmd/lpbot` 与 `go test ./cmd/lpbot -run 'TestWire_|TestOrderManagerAdapter_'` 均通过。
- 本轮补充：`postgres_test.go` 已新增 docker-postgres 最小集成测试并执行通过；任务清单内剩余 `[wip]` 已全部收口。

## 当前最小下一步建议

1. 先做 P0-01、P0-02、P0-03（一次性收口 canary 与 live 风控边界）。
2. 再做 P0-04、P0-05（交易/账本可审计）。
3. 最后并行推进 P1-01、P1-02、P1-03（架构层面稳定性）。
