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
