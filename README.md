# lp-bot v3

链上 AMM LP 自动套利机器人。Go + TypeScript，六边形模块化单体架构，build tag 隔离 dryrun/shadow/live 三种运行模式。

## 文档

- **PRD**：[../链上 AMM LP 自动套利机器人 PRD（升级版）.md](../链上%20AMM%20LP%20自动套利机器人%20PRD（升级版）.md)
- **根 spec**：[../docs/superpowers/specs/lp-bot-superpower-rearchitecture-v1.md](../docs/superpowers/specs/lp-bot-superpower-rearchitecture-v1.md)
- **Phase 0 plan**：[../docs/superpowers/plans/2026-05-19-lp-bot-phase-0.md](../docs/superpowers/plans/2026-05-19-lp-bot-phase-0.md)
- **任务清单**：[../docs/tasks/phase-0/](../docs/tasks/phase-0/)
- **接力 Agent 指令**：[../docs/AGENT_HANDOFF.md](../docs/AGENT_HANDOFF.md)

## 当前阶段

Phase 0 — 历史回测 + 全套测试基础设施 + 代码骨架。

## Current Research Status

- **2026-06-04 LP Research Final Freeze** — `STOP_LP_RESEARCH_NOW`
- 5/5 Solana AMM protocols reject retail 10-20U 2000 USD LP (cumulative 28560 EV cells, 0 in optimistic/realistic/conservative)
- can_run_probe_now = `false`, tiny_canary_allowed = `no`, edge_proven = `no`
- See `docs/LPBOT_RESEARCH_STATUS_CN.md` and `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json`
- Historical final freeze: `reports/final_freeze/20260531_124000/FINAL_VERDICT.json`
- No live/canary/paper execution is allowed.

## 快速命令

```bash
make tidy          # go mod tidy
make lint          # golangci-lint
make test          # unit + 默认 build tag 测试
make test-property # property tests
make test-fork     # fork integration tests（需要 anvil）
make test-chaos    # chaos tests
make build-all     # 编译三个 mode 二进制 + backtest
make backtest      # 仅编译 backtest
```

## Canary / Live 准备

- `configs/config.canary.toml`：默认保守 canary 模板，仍是 `fail-closed`，不会因为填了环境变量就自动实单。
- `configs/config.live.toml`：完整 live 模板，必须配套 `.sha256`，并且当前 `cmd/lpbot` 仍未接入真实执行器。
- `BASE_RPC_PRIMARY` / `BASE_WS`：这里填你的 QuickNode Base HTTPS/WSS。
- `QUICKNODE_API_KEY`：可选。若是带 Admin/Console 权限的 key，程序会自动发现账户下的 Base/Solana endpoint，并把它们放在公共 RPC 之后作为低优先级备用。
- `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_API_PASSPHRASE`：这里填你的 OKX Onchain API 凭据；仅当 `execution.backend = "okx-onchain"` 时需要。
- `OKX_PROJECT_ID`：当前 DEX API 不是必填，只为后续更深的 OKX 集成预留。
- 推荐先从 [`.env.canary.example`](/Users/bendu/lp-bot/v3/.env.canary.example) 衍生实例环境，再由 systemd `EnvironmentFile=` 注入。

## 模式隔离（spec §2.4）

| 模式 | build tag | broadcaster | wallet | DB 前缀 |
|---|---|---|---|---|
| dryrun | `dryrun` | disabled (panic) | none | `dryrun_*` |
| shadow | `shadow` | disabled (panic) | none | `shadow_*` |
| live | `live` | live | keystore/kms | `live_*` |

## 目录结构

```
cmd/         # 4 个二进制：lpbot / lpbot-backtest / lpbot-recon / lpbot-cli
internal/
  domain/    # 领域类型
  core/      # 业务逻辑（仅依赖 domain + ports）
  ports/     # 抽象接口
  adapters/  # 接口实现（chain/pool/store/bus/wallet/...）
  platform/  # 横切：log/metrics/trace/config
pkg/         # 纯函数库：decimal/tickmath/il
migrations/  # SQL DDL（sqlite + postgres）
configs/     # toml 模板
tests/       # property/fork/chaos 框架
web/         # Next.js dashboard（Phase 1+）
```

依赖方向：`cmd → core → ports ← adapters`，core 永不 import adapters。

## 不变量（spec §9.2）

PRD 列出的 10 条系统不变量，每条都有 property test + 运行时 metric/alert 双重保障。详见 spec §9.2 表格。

## 贡献

按 TDD 红→绿→单 commit 节奏。每个任务对应 `docs/tasks/phase-N/T-XXX.md`。详见接力 Agent 指令。
