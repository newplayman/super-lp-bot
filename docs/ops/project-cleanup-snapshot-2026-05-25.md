# 整理快照（2026-05-25）

本快照用于保持可追溯，不丢已完成工作。基于当前工作树状态生成，未进行功能性回退。

## 一、已修改文件（已存在于版本控制）

- `.env.example`
- `.github/workflows/ci.yml`
- `.gitignore`
- `cmd/lpbot/canary_mint.go`
- `cmd/lpbot/canary_state.go`
- `cmd/lpbot/dashboard.go`
- `cmd/lpbot/dashboard.html`
- `cmd/lpbot/main.go`
- `cmd/lpbot/solana_readiness.go`
- `configs/config.canary.toml`
- `configs/config.canary.toml.sha256`
- `internal/adapters/datasource/geckoterminal/adapter.go`
- `internal/adapters/datasource/geckoterminal/client.go`
- `internal/adapters/rpc/roundrobin.go`
- `internal/adapters/store/postgres/position_repo.go`
- `internal/domain/position.go`
- `internal/platform/metrics/metrics.go`

## 二、新增文件（建议保留，不做删除）

- `cmd/lpbot/base_tierc_discovery.go`
- `cmd/lpbot/base_tierc_holder_snapshot_refresh.go`
- `cmd/lpbot/base_tierc_market_quality.go`
- `cmd/lpbot/solana_funding_plan.go`
- `cmd/lpbot/solana_lp_close_canary_live.go`
- `cmd/lpbot/solana_lp_close_canary_stub.go`
- `cmd/lpbot/solana_lp_metrics.go`
- `cmd/lpbot/solana_lp_metrics_test.go`
- `cmd/lpbot/solana_lp_open_canary_gate.go`
- `cmd/lpbot/solana_lp_open_canary_live.go`
- `cmd/lpbot/solana_lp_open_canary_stub.go`
- `cmd/lpbot/solana_lp_open_canary_test.go`
- `cmd/lpbot/solana_lp_pnl_reconcile.go`
- `cmd/lpbot/solana_lp_prefund_canary_live.go`
- `cmd/lpbot/solana_lp_prefund_canary_stub.go`
- `cmd/lpbot/solana_meteora_lp_build.go`
- `cmd/lpbot/solana_meteora_lp_preflight.go`
- `cmd/lpbot/solana_native_discovery.go`
- `cmd/lpbot/solana_pancake_layout_test.go`
- `cmd/lpbot/solana_tierc_deep_audit.go`
- `cmd/lpbot/solana_tierc_discovery.go`
- `configs/tierc_holder_overrides.json`
- `configs/tierc_negative_samples.json`
- `docs/ops/`（含新建的整理与运维文档）
- `docs/runbooks/base-canary-ops.md`
- `docs/superpowers/plans/2026-05-24-solana-same-chain-funding-plan.md`
- `docs/superpowers/plans/2026-05-24-tier-c-audit-pack.md`
- `docs/superpowers/specs/2026-05-24-solana-same-chain-funding-design.md`
- `docs/superpowers/task-lists/`
- `internal/adapters/holderconcentration/`
- `internal/adapters/pool/pancakeswap_v3_solana/`
- `internal/core/tierc/`
- `migrations/postgres/000005_positions_runtime_metadata.sql`
- `scripts/refresh_and_sync_tierc_holder_snapshot.sh`
- `scripts/sync_tierc_holder_snapshot_to_vps.sh`
- `tools/`（含 meteora 工具链与说明）

## 三、边界治理动作（本轮已完成）

1. `.gitignore` 已更新，新增忽略项：
   - `tools/**/node_modules/`
   - `run/`
   - `run/audits/`
   - `tmp_sync_placeholder/`
   - `logs/`
   - `*.log`
   - `bin/`
   - `build/`
   - `artifacts/`
   - `._*`
2. 已新增 [整理说明](/Users/bendu/lp-bot/v3/docs/ops/project-cleanup-log-2026-05-25.md) 与本快照文档，作为后续交接基准。

## 四、下一步执行顺序（不丢工作，直接照做）

1. 固定保留清单后，先提交本次整理的边界文件（`.gitignore`、两个整理文档）。
2. 再按模块分批次提交/同步：`cmd`、`internal`、`configs`、`scripts`、`internal adapters`、`docs`。
3. 同步 VPS 时只同步已跟踪文件与必要配置；将 `run/`、`tmp_sync_placeholder/`、`tools/**/node_modules/` 作为运行产物排除。
4. 后续再进入功能整顿，不受已完成工作影响。

