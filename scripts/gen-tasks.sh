#!/usr/bin/env bash
# 生成 docs/tasks/phase-0/T-XXX.md 全部任务文件
# 数据源：本脚本内嵌的 manifest（id|milestone|title|spec|files|deps|invariants）
# 用法：从仓库根目录运行 `bash scripts/gen-tasks.sh`
set -euo pipefail

OUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/../docs/tasks/phase-0"
mkdir -p "$OUT_DIR"

# manifest 字段：T-XXX|M0.x|title|spec_section|files(空格分隔)|deps(空格分隔)|inv(空格分隔)
read -r -d '' MANIFEST <<'EOF' || true
T-001|M0.0|生成 per-task markdown 模板|§10.3|docs/tasks/phase-0/_template.md docs/tasks/phase-0/T-*.md|none|
T-002|M0.0|初始化 git 仓库 + .gitignore|§10.1|.gitignore|T-001|
T-003|M0.0|go.mod 初始化 + 核心依赖|§10.1|go.mod go.sum|T-002|
T-004|M0.0|Makefile（build / test / lint targets）|§10.1|Makefile|T-003|
T-005|M0.0|golangci-lint 配置|§9.6|.golangci.yml|T-004|
T-006|M0.0|cmd 占位 main.go（4 个）|§2.1|cmd/lpbot/main.go cmd/lpbot-backtest/main.go cmd/lpbot-recon/main.go cmd/lpbot-cli/main.go|T-005|
T-007|M0.0|configs toml 模板|§2.4|configs/config.dryrun.toml configs/config.shadow.toml configs/config.live.toml|T-006|
T-008|M0.0|基础 README|§10|README.md|T-007|
T-010|M0.1|domain ChainID + BlockRef|§2|internal/domain/chain.go internal/domain/chain_test.go|T-008|
T-011|M0.1|domain Address（EVM hex + Solana base58）|§2|internal/domain/address.go internal/domain/address_test.go|T-010|
T-012|M0.1|domain Tier 枚举 + 阈值容器|§5.4|internal/domain/tier.go internal/domain/tier_test.go|T-010|
T-013|M0.1|domain Pool 元数据|§3|internal/domain/pool.go internal/domain/pool_test.go|T-011 T-012|
T-014|M0.1|domain PoolState（V2 reserves + V3 sqrtPriceX96/tick/liquidity）|§3|internal/domain/pool_state.go internal/domain/pool_state_test.go|T-013|
T-015|M0.1|domain TokenAmount（Token + decimal.Decimal）|§4.1|internal/domain/token_amount.go internal/domain/token_amount_test.go|T-013|
T-016|M0.1|domain Position 状态机|§4.3|internal/domain/position.go internal/domain/position_test.go|T-013|2
T-017|M0.1|domain Tx 状态机|§4.3|internal/domain/tx.go internal/domain/tx_test.go|T-016|
T-018|M0.1|domain Score（多维评分容器）|§3.1|internal/domain/score.go internal/domain/score_test.go|T-013|
T-019|M0.1|domain AuditFinding|§3.2|internal/domain/audit_finding.go internal/domain/audit_finding_test.go|T-013|
T-020|M0.1|domain Event（bus 信封）|§3.2|internal/domain/event.go internal/domain/event_test.go|T-010|
T-021|M0.2|pkg/decimal 基础类型 + From/To string|§4.1|pkg/decimal/decimal.go pkg/decimal/decimal_test.go|T-008|
T-022|M0.2|pkg/decimal 算术 Add/Sub/Mul/Div/Pow|§4.1|pkg/decimal/arith.go pkg/decimal/arith_test.go|T-021|
T-023|M0.2|pkg/decimal 比较 + Min/Max + Abs|§4.1|pkg/decimal/compare.go pkg/decimal/compare_test.go|T-022|
T-024|M0.2|pkg/decimal SQLite Scanner/Valuer|§4.1|pkg/decimal/sql.go pkg/decimal/sql_test.go|T-023|
T-025|M0.3|pkg/tickmath 常量与边界|§6.1|pkg/tickmath/consts.go pkg/tickmath/consts_test.go|T-021|
T-026|M0.3|TickToSqrtPriceX96|§6.1|pkg/tickmath/tick_to_sqrt.go pkg/tickmath/tick_to_sqrt_test.go|T-025|
T-027|M0.3|SqrtPriceX96ToTick + 可逆 property|§6.1|pkg/tickmath/sqrt_to_tick.go pkg/tickmath/sqrt_to_tick_test.go|T-026|
T-028|M0.3|PriceToTick（带 token decimals）|§6.1|pkg/tickmath/price_tick.go pkg/tickmath/price_tick_test.go|T-027|
T-029|M0.3|LiquidityForAmounts|§6.1|pkg/tickmath/liquidity.go pkg/tickmath/liquidity_test.go|T-027|
T-030|M0.3|AmountsForLiquidity（反向）|§6.1|pkg/tickmath/amounts.go pkg/tickmath/amounts_test.go|T-029|
T-031|M0.4|pkg/il V2 IL 公式|§3.5.2|pkg/il/v2.go pkg/il/v2_test.go|T-024|
T-032|M0.4|V2 IL USDC 计价转换|§3.5.2|pkg/il/v2_usd.go pkg/il/v2_usd_test.go|T-031|
T-033|M0.4|V3 IL（基于 sqrtPriceX96 + tickRange）|§3.5.2|pkg/il/v3.go pkg/il/v3_test.go|T-029 T-031|
T-034|M0.4|V3 fee 累计模拟|§3.5|pkg/il/v3_fee.go pkg/il/v3_fee_test.go|T-033|
T-035|M0.4|V3 Position 全量重算|§3.5|pkg/il/v3_position.go pkg/il/v3_position_test.go|T-034|
T-036|M0.4|V2 Position 全量重算|§3.5|pkg/il/v2_position.go pkg/il/v2_position_test.go|T-031|
T-037|M0.4|联合 IL+Fee → Net PnL（无 gas）|§3.5.1|pkg/il/net_pnl.go pkg/il/net_pnl_test.go|T-035 T-036|
T-038|M0.4|V2/V3 联合 property test|§9.2|pkg/il/property_test.go|T-037|
T-040|M0.5|ports.Chain + EVMChain + SolanaChain|§6.1|internal/ports/chain.go internal/ports/chain_test.go|T-014 T-020|
T-041|M0.5|ports V2Pool + V3Pool|§6.2|internal/ports/pool.go internal/ports/pool_test.go|T-040|
T-042|M0.5|ports.Simulator|§6.3|internal/ports/simulator.go internal/ports/simulator_test.go|T-041|
T-043|M0.5|ports.Bus + Subscription + EventDedup|§3|internal/ports/bus.go internal/ports/bus_test.go|T-020|
T-044|M0.5|ports.PoolRepo|§4.4|internal/ports/store_pool.go internal/ports/store_pool_test.go|T-043|
T-045|M0.5|ports.PositionRepo|§4.4|internal/ports/store_position.go internal/ports/store_position_test.go|T-016|
T-046|M0.5|ports.TxRepo|§4.4|internal/ports/store_tx.go internal/ports/store_tx_test.go|T-017|
T-047|M0.5|ports.LedgerRepo|§4.4|internal/ports/store_ledger.go internal/ports/store_ledger_test.go|T-024|
T-048|M0.5|ports.RiskRepo + ReconRepo + ConfigSnap|§4.4|internal/ports/store_risk.go internal/ports/store_recon.go internal/ports/store_config.go|T-047|
T-049|M0.5|ports.Wallet + WalletProvider|§6.6|internal/ports/wallet.go internal/ports/wallet_test.go|T-040|
T-050|M0.5|ports.Broadcaster + MEVSubmitter|§6.7|internal/ports/broadcast.go internal/ports/mev.go|T-049|
T-051|M0.5|ports.Datasource + HistoricalDatasource|§8.1|internal/ports/datasource.go internal/ports/datasource_test.go|T-013|
T-052|M0.5|ports.Alerter|§7.4|internal/ports/alerter.go internal/ports/alerter_test.go|T-020|
T-055|M0.6|platform/log（zap JSON）|§7.1|internal/platform/log/log.go internal/platform/log/log_test.go|T-008|
T-056|M0.6|platform/idgen（UUID v7 + trace_id）|§3.2|internal/platform/idgen/idgen.go internal/platform/idgen/idgen_test.go|T-055|
T-057|M0.6|platform/config（toml + env interp + sha256）|§2.4|internal/platform/config/config.go internal/platform/config/config_test.go|T-056|
T-058|M0.6|platform/metrics（prometheus 包装）|§7.3|internal/platform/metrics/metrics.go internal/platform/metrics/metrics_test.go|T-055|
T-059|M0.6|platform/trace（OTel noop exporter）|§7.1|internal/platform/trace/trace.go internal/platform/trace/trace_test.go|T-058|
T-060|M0.6|platform/decimal_db（serializer 包装）|§4.1|internal/platform/decimal_db/decimal_db.go internal/platform/decimal_db/decimal_db_test.go|T-024|
T-061|M0.6|platform/timex（区块时间戳工具）|§6.2|internal/platform/timex/timex.go internal/platform/timex/timex_test.go|T-014|
T-062|M0.6|platform/health（/healthz /readyz handlers）|§7.7|internal/platform/health/health.go internal/platform/health/health_test.go|T-058|
T-070|M0.7|core/scanner 骨架|§3.1|internal/core/scanner/README.md internal/core/scanner/interface.go internal/core/scanner/scanner.go internal/core/scanner/scanner_test.go|T-052|
T-071|M0.7|core/audit 骨架|§3.2|internal/core/audit/README.md internal/core/audit/interface.go internal/core/audit/audit.go internal/core/audit/audit_test.go|T-052|
T-072|M0.7|core/risk 骨架（含 RiskGate）|§5|internal/core/risk/README.md internal/core/risk/interface.go internal/core/risk/risk.go internal/core/risk/risk_test.go|T-048|1
T-073|M0.7|core/strategy 骨架|§3.4|internal/core/strategy/README.md internal/core/strategy/interface.go internal/core/strategy/strategy.go internal/core/strategy/strategy_test.go|T-072|
T-074|M0.7|core/execution 骨架（OrderManager 子接口）|§6.4|internal/core/execution/README.md internal/core/execution/interface.go internal/core/execution/execution.go internal/core/execution/execution_test.go|T-050|4
T-075|M0.7|core/simulation 骨架|§6.3|internal/core/simulation/README.md internal/core/simulation/interface.go internal/core/simulation/simulation.go internal/core/simulation/simulation_test.go|T-042|
T-076|M0.7|core/pnl 骨架（接口）|§3.5|internal/core/pnl/README.md internal/core/pnl/interface.go internal/core/pnl/pnl.go internal/core/pnl/pnl_test.go|T-037|5
T-077|M0.7|core/reconcile 骨架|§4.6|internal/core/reconcile/README.md internal/core/reconcile/interface.go internal/core/reconcile/reconcile.go internal/core/reconcile/reconcile_test.go|T-040|8
T-078|M0.7|core/watchdog 骨架|§5.1|internal/core/watchdog/README.md internal/core/watchdog/interface.go internal/core/watchdog/watchdog.go internal/core/watchdog/watchdog_test.go|T-052|1 6
T-079|M0.7|core/auditlog 骨架（bus 订阅落盘）|§3.5|internal/core/auditlog/README.md internal/core/auditlog/interface.go internal/core/auditlog/auditlog.go internal/core/auditlog/auditlog_test.go|T-043|
T-080|M0.7|不变量 #1 property test 占位|§9.2|tests/property/inv01_exposure_test.go|T-072|1
T-081|M0.7|不变量 #2 property test 占位|§9.2|tests/property/inv02_no_double_position_test.go|T-072|2
T-082|M0.7|不变量 #3 property test 占位|§9.2|tests/property/inv03_dryrun_no_broadcast_test.go|T-100|3
T-083|M0.7|不变量 #4 property test 占位|§9.2|tests/property/inv04_min_out_deadline_test.go|T-074|4
T-084|M0.7|不变量 #5 property test 占位|§9.2|tests/property/inv05_pnl_reconcile_test.go|T-076|5
T-085|M0.7|不变量 #6–#10 property test 占位|§9.2|tests/property/inv_06_to_10_test.go|T-072|6 7 8 9 10
T-090|M0.8|adapters/chain/base stub|§6.1|internal/adapters/chain/base/README.md internal/adapters/chain/base/chain.go internal/adapters/chain/base/chain_test.go|T-040|
T-091|M0.8|adapters/chain/solana stub|§6.1|internal/adapters/chain/solana/README.md internal/adapters/chain/solana/chain.go internal/adapters/chain/solana/chain_test.go|T-040|
T-092|M0.8|adapters/pool/uniswap_v3 stub|§6.2|internal/adapters/pool/uniswap_v3/README.md internal/adapters/pool/uniswap_v3/pool.go internal/adapters/pool/uniswap_v3/pool_test.go|T-041|
T-093|M0.8|adapters/pool/whirlpool stub|§6.2|internal/adapters/pool/whirlpool/README.md internal/adapters/pool/whirlpool/pool.go internal/adapters/pool/whirlpool/pool_test.go|T-041|
T-094|M0.8|adapters/pool/aerodrome stub（Phase 4）|§6.2|internal/adapters/pool/aerodrome/README.md internal/adapters/pool/aerodrome/pool.go|T-041|
T-095|M0.8|adapters/pool/raydium_clmm stub（Phase 4）|§6.2|internal/adapters/pool/raydium_clmm/README.md internal/adapters/pool/raydium_clmm/pool.go|T-041|
T-096|M0.8|adapters/store/sqlite 目录 + interface 校验|§4|internal/adapters/store/sqlite/README.md internal/adapters/store/sqlite/.keep|T-044|
T-097|M0.8|adapters/store/postgres stub|§4|internal/adapters/store/postgres/README.md internal/adapters/store/postgres/.keep|T-044|
T-098|M0.8|adapters/bus/inproc 目录|§3|internal/adapters/bus/inproc/README.md|T-043|
T-099|M0.8|adapters/bus/nats stub|§3|internal/adapters/bus/nats/README.md internal/adapters/bus/nats/.keep|T-043|
T-100|M0.8|adapters/broadcast/disabled（panic + counter）|§2.4|internal/adapters/broadcast/disabled/broadcaster.go internal/adapters/broadcast/disabled/broadcaster_test.go|T-050|3
T-101|M0.8|adapters/broadcast/live stub（build tag live）|§6.7|internal/adapters/broadcast/live/broadcaster.go|T-050|
T-102|M0.8|adapters/mev/flashbots stub|§6.7|internal/adapters/mev/flashbots/README.md internal/adapters/mev/flashbots/submitter.go|T-050|
T-103|M0.8|adapters/mev/jito stub|§6.7|internal/adapters/mev/jito/README.md internal/adapters/mev/jito/submitter.go|T-050|
T-104|M0.8|adapters/wallet/none（panic + counter）|§2.4|internal/adapters/wallet/none/wallet.go internal/adapters/wallet/none/wallet_test.go|T-049|
T-105|M0.8|adapters/wallet/keystore stub|§3.6|internal/adapters/wallet/keystore/README.md internal/adapters/wallet/keystore/wallet.go|T-049|
T-106|M0.8|adapters/wallet/kms stub|§3.6|internal/adapters/wallet/kms/README.md internal/adapters/wallet/kms/wallet.go|T-049|
T-107|M0.8|adapters/datasource/dexscreener 目录|§8.1|internal/adapters/datasource/dexscreener/README.md|T-051|
T-108|M0.8|adapters/datasource/geckoterminal stub|§2.3|internal/adapters/datasource/geckoterminal/README.md internal/adapters/datasource/geckoterminal/client.go|T-051|
T-109|M0.8|adapters/datasource/birdeye stub|§2.3|internal/adapters/datasource/birdeye/README.md internal/adapters/datasource/birdeye/client.go|T-051|
T-110|M0.8|adapters/datasource/defillama stub|§2.3|internal/adapters/datasource/defillama/README.md internal/adapters/datasource/defillama/client.go|T-051|
T-111|M0.8|adapters/alerter/log 完整实装|§7.4|internal/adapters/alerter/log/alerter.go internal/adapters/alerter/log/alerter_test.go|T-052 T-055|
T-112|M0.8|adapters/alerter/telegram stub|§7.4|internal/adapters/alerter/telegram/README.md internal/adapters/alerter/telegram/alerter.go|T-052|
T-113|M0.8|adapters/simulator/anvil stub|§6.3|internal/adapters/simulator/anvil/README.md internal/adapters/simulator/anvil/simulator.go|T-042|
T-114|M0.8|adapters/simulator/sol_rpc stub|§6.3|internal/adapters/simulator/sol_rpc/README.md internal/adapters/simulator/sol_rpc/simulator.go|T-042|
T-115|M0.8|adapters/store/sqlite/cas 目录|§4|internal/adapters/store/sqlite/cas/.keep|T-096|
T-120|M0.9|migrations/sqlite/0001_init.sql 全表 schema|§4.2|migrations/sqlite/0001_init.sql migrations/sqlite/0001_init_test.go|T-096|2
T-121|M0.9|sqlite migrate runner|§4.5|internal/adapters/store/sqlite/migrate.go internal/adapters/store/sqlite/migrate_test.go|T-120|
T-122|M0.9|sqlc 配置 + Pool 第一份 query|§4.4|sqlc.yaml internal/adapters/store/sqlite/queries/pool.sql|T-121|
T-123|M0.9|PoolRepo 实装（UPSERT + Get + ListByChain）|§4.4|internal/adapters/store/sqlite/repo_pool.go internal/adapters/store/sqlite/repo_pool_test.go|T-122 T-044|
T-124|M0.9|LedgerRepo 实装（Append + ListByPosition + DailyAggregate）|§4.4|internal/adapters/store/sqlite/repo_ledger.go internal/adapters/store/sqlite/repo_ledger_test.go|T-122 T-047|5
T-125|M0.9|EventDedup 实装（INSERT OR IGNORE + 7 天 TTL）|§3.2|internal/adapters/store/sqlite/repo_dedup.go internal/adapters/store/sqlite/repo_dedup_test.go|T-122|
T-126|M0.9|ConfigSnap 实装（Save + ListLatest）|§2.4|internal/adapters/store/sqlite/repo_config.go internal/adapters/store/sqlite/repo_config_test.go|T-122|7
T-127|M0.9|ReconRepo 实装|§4.6|internal/adapters/store/sqlite/repo_recon.go internal/adapters/store/sqlite/repo_recon_test.go|T-122|8
T-128|M0.9|PositionRepo 实装|§4.4|internal/adapters/store/sqlite/repo_position.go internal/adapters/store/sqlite/repo_position_test.go|T-122 T-045|
T-129|M0.9|TxRepo 实装|§4.4|internal/adapters/store/sqlite/repo_tx.go internal/adapters/store/sqlite/repo_tx_test.go|T-122 T-046|
T-130|M0.9|RiskRepo 实装|§4.4|internal/adapters/store/sqlite/repo_risk.go internal/adapters/store/sqlite/repo_risk_test.go|T-122 T-048|
T-131|M0.9|AuditFindingRepo 实装|§4.4|internal/adapters/store/sqlite/repo_audit_finding.go internal/adapters/store/sqlite/repo_audit_finding_test.go|T-122|
T-132|M0.9|AuditEventRepo + JSONL 落盘|§3.5|internal/adapters/store/sqlite/repo_audit_event.go internal/adapters/store/sqlite/repo_audit_event_test.go|T-122|
T-140|M0.10|bus/inproc 基础 pub/sub|§3|internal/adapters/bus/inproc/bus.go internal/adapters/bus/inproc/bus_test.go|T-043 T-098|
T-141|M0.10|bus/inproc 通配符订阅|§3.3|internal/adapters/bus/inproc/wildcard.go internal/adapters/bus/inproc/wildcard_test.go|T-140|
T-142|M0.10|bus/inproc drop policy + metrics|§3.4|internal/adapters/bus/inproc/dropper.go internal/adapters/bus/inproc/dropper_test.go|T-141|
T-143|M0.10|auditlog 订阅者落 JSONL|§3.5|internal/core/auditlog/auditlog.go internal/core/auditlog/auditlog_test.go|T-079 T-141|
T-144|M0.10|bus/inproc property test（不丢不重）|§9.2|internal/adapters/bus/inproc/property_test.go|T-142|
T-145|M0.10|bus/inproc benchmark|§3|internal/adapters/bus/inproc/bench_test.go|T-144|
T-150|M0.11|HistoricalDatasource 接口扩展|§8.1|internal/ports/datasource_history.go internal/ports/datasource_history_test.go|T-051|
T-151|M0.11|DexScreener 客户端|§2.3|internal/adapters/datasource/dexscreener/client.go internal/adapters/datasource/dexscreener/client_test.go|T-150|
T-152|M0.11|DexScreener 历史 swap 解析|§8.1|internal/adapters/datasource/dexscreener/history.go internal/adapters/datasource/dexscreener/history_test.go|T-151|
T-153|M0.11|GeckoTerminal 历史价格|§2.3|internal/adapters/datasource/geckoterminal/client.go internal/adapters/datasource/geckoterminal/client_test.go|T-150 T-108|
T-154|M0.11|Subgraph 客户端（Base Uniswap V3）|§8.1|internal/adapters/datasource/subgraph/README.md internal/adapters/datasource/subgraph/client.go internal/adapters/datasource/subgraph/client_test.go|T-150|
T-155|M0.11|Solana 历史源（Solscan/Helius）|§8.1|internal/adapters/datasource/helius/README.md internal/adapters/datasource/helius/client.go internal/adapters/datasource/helius/client_test.go|T-150|
T-156|M0.11|多源聚合（偏差 > 5% 报错）|§2.4|internal/adapters/datasource/aggregate.go internal/adapters/datasource/aggregate_test.go|T-152 T-153 T-154|
T-157|M0.11|缓存层（写入 SQLite cache_*）|§4|internal/adapters/datasource/cache.go internal/adapters/datasource/cache_test.go|T-156 T-122|
T-158|M0.11|rate limiter（per-source）|§2.3|internal/adapters/datasource/ratelimit.go internal/adapters/datasource/ratelimit_test.go|T-156|
T-159|M0.11|fixture loader（离线 testdata 历史）|§9.4|internal/adapters/datasource/fixture.go internal/adapters/datasource/fixture_test.go|T-156|
T-160|M0.11|integration smoke test（手动跑）|§9.5|tests/integration/datasource_smoke_test.go|T-159|
T-165|M0.12|pnl.AccrueFees|§3.5|internal/core/pnl/accrue.go internal/core/pnl/accrue_test.go|T-076 T-034|
T-166|M0.12|pnl.RealizeIL|§3.5|internal/core/pnl/realize.go internal/core/pnl/realize_test.go|T-076 T-033|
T-167|M0.12|pnl.NetPnL（fee − IL − gas，简化）|§3.5.1|internal/core/pnl/net.go internal/core/pnl/net_test.go|T-165 T-166|
T-168|M0.12|pnl 累计聚合|§3.5|internal/core/pnl/aggregate.go internal/core/pnl/aggregate_test.go|T-167|
T-169|M0.12|pnl property test：单调非负 fee|§9.2|internal/core/pnl/property_fee_test.go|T-165|
T-170|M0.12|pnl property test：IL 非正|§9.2|internal/core/pnl/property_il_test.go|T-166|
T-171|M0.12|pnl property test：sum_per_block == realized_at_close|§9.2|internal/core/pnl/property_reconcile_test.go|T-168|5
T-172|M0.12|pnl golden test：教科书例对照|§3.5.2|internal/core/pnl/golden_test.go internal/core/pnl/testdata/golden.json|T-167|
T-173|M0.12|pnl 按池/Tier 分组聚合|§7.3|internal/core/pnl/group.go internal/core/pnl/group_test.go|T-168|
T-174|M0.12|pnl ledger 写入 helper|§4.2|internal/core/pnl/ledger.go internal/core/pnl/ledger_test.go|T-168 T-124|
T-175|M0.12|pnl 输出 verdict（误差报告）|§8.1|internal/core/pnl/verdict.go internal/core/pnl/verdict_test.go|T-174|
T-180|M0.13|backtest CLI flag 解析|§8.1|cmd/lpbot-backtest/cli.go cmd/lpbot-backtest/cli_test.go|T-008 T-057|
T-181|M0.13|从 datasource 拉数据 + 写 SQLite cache|§8.1|cmd/lpbot-backtest/fetch.go cmd/lpbot-backtest/fetch_test.go|T-180 T-157|
T-182|M0.13|range 模拟 add → block-by-block mark → close|§8.1|cmd/lpbot-backtest/simulate.go cmd/lpbot-backtest/simulate_test.go|T-181 T-035|
T-183|M0.13|写 pnl_ledger|§8.1|cmd/lpbot-backtest/persist.go cmd/lpbot-backtest/persist_test.go|T-182 T-174|
T-184|M0.13|与真实 collect_fees 从 Subgraph 对照|§8.1|cmd/lpbot-backtest/baseline.go cmd/lpbot-backtest/baseline_test.go|T-183 T-154|
T-185|M0.13|输出 verdict.md / pnl_series.csv / summary.json|§8.1|cmd/lpbot-backtest/output.go cmd/lpbot-backtest/output_test.go|T-184 T-175|
T-186|M0.13|backtest CLI 集成 test（fixture 全流程）|§9.4|cmd/lpbot-backtest/integration_test.go|T-185 T-159|
T-187|M0.13|错误：数据缺失|§8.1|cmd/lpbot-backtest/errors.go cmd/lpbot-backtest/errors_test.go|T-181|
T-188|M0.13|错误：池不存在|§8.1|cmd/lpbot-backtest/errors.go cmd/lpbot-backtest/errors_test.go|T-187|
T-189|M0.13|错误：时间窗口非法|§8.1|cmd/lpbot-backtest/errors.go cmd/lpbot-backtest/errors_test.go|T-188|
T-190|M0.13|backtest 主函数串联|§8.1|cmd/lpbot-backtest/main.go|T-185 T-189|
T-200|M0.14|tests/property/helpers（rapid 通用生成器）|§9.3|tests/property/helpers.go tests/property/helpers_test.go|T-038|
T-201|M0.14|tests/property/mocks（ports mocks）|§9.3|tests/property/mocks/chain.go tests/property/mocks/store.go tests/property/mocks/bus.go|T-052|
T-202|M0.14|tests/fork/anvil_runner|§9.4|tests/fork/anvil_runner.go tests/fork/anvil_runner_test.go|T-090|
T-203|M0.14|tests/fork/sol_simulate|§9.4|tests/fork/sol_simulate.go tests/fork/sol_simulate_test.go|T-091|
T-204|M0.14|tests/fork/fixtures（pin 区块 ground truth）|§9.4|tests/fork/fixtures/README.md|T-202|
T-205|M0.14|tests/chaos/mockchain（HTTP 注入故障）|§9.5|tests/chaos/mockchain.go tests/chaos/mockchain_test.go|T-201|
T-206|M0.14|tests/chaos/scenarios|§9.5|tests/chaos/scenarios.go tests/chaos/scenarios_test.go|T-205|
T-207|M0.14|不变量 #1 完整 property test|§9.2|tests/property/inv01_exposure_test.go|T-080|1
T-208|M0.14|不变量 #2 完整 property test|§9.2|tests/property/inv02_no_double_position_test.go|T-081|2
T-209|M0.14|不变量 #3 完整 property test|§9.2|tests/property/inv03_dryrun_no_broadcast_test.go|T-082|3
T-210|M0.14|不变量 #4 完整 property test|§9.2|tests/property/inv04_min_out_deadline_test.go|T-083|4
T-211|M0.14|不变量 #5 完整 property test|§9.2|tests/property/inv05_pnl_reconcile_test.go|T-084 T-171|5
T-212|M0.14|不变量 #6 占位 property test|§9.2|tests/property/inv06_stop_loss_timing_test.go|T-085|6
T-213|M0.14|不变量 #7 完整 property test|§9.2|tests/property/inv07_config_signed_test.go|T-126|7
T-214|M0.14|不变量 #8 占位 property test|§9.2|tests/property/inv08_recon_required_test.go|T-085|8
T-215|M0.14|不变量 #9+#10 占位 property test|§9.2|tests/property/inv09_10_approve_test.go|T-085|9 10
T-220|M0.15|.github/workflows/ci.yml|§9.6|.github/workflows/ci.yml|T-005|
T-221|M0.15|scripts/check-test-files.sh|§9.6|scripts/check-test-files.sh|T-220|
T-222|M0.15|scripts/preflight.sh|§9.6|scripts/preflight.sh|T-220|
T-223|M0.15|依赖审计（govulncheck）|§9.6|.github/workflows/security.yml|T-220|
T-224|M0.15|覆盖率门槛（diff 80% / pkg 100%）|§9.6|scripts/coverage-gate.sh|T-220|
T-225|M0.15|CI 文档|§9.6|docs/ci.md|T-224|
T-230|M0.16|选 5+5 池 + 90 天窗口|§8.1|docs/tasks/phase-0/T-230-pools.csv|T-186|
T-231|M0.16|批量回测脚本|§8.1|scripts/run-phase0-verdict.sh|T-230|
T-232|M0.16|聚合脚本|§8.1|scripts/aggregate-verdict/main.go|T-231|
T-233|M0.16|标准复核：误差 < 10%|§8.1|verdict-phase0/check.sh|T-232|
T-234|M0.16|VERDICT-phase0.md|§9.7|docs/superpowers/specs/VERDICT-phase0.md|T-233|
T-235|M0.16|spec 根文件标注 Phase 0 完成 + 触发 Phase 1 brainstorming|§10.5|docs/superpowers/specs/lp-bot-superpower-rearchitecture-v1.md|T-234|
EOF

while IFS='|' read -r id ms title sec files deps invs; do
  [[ -z "$id" ]] && continue
  out="$OUT_DIR/${id}.md"
  files_md=$(echo "$files" | tr ' ' '\n' | sed 's/^/- `v3\//; s/$/`/')
  deps_md=$([ "$deps" = "none" ] && echo "无" || echo "$deps")
  invs_md=$([ -z "$invs" ] && echo "（无 - 脚手架/支撑任务）" || (echo "$invs" | tr ' ' '\n' | sed 's/^/- #/'))
  cat > "$out" <<MD
# ${id}：${title}

## 关联
- **Plan**：[../../superpowers/plans/2026-05-19-lp-bot-phase-0.md](../../superpowers/plans/2026-05-19-lp-bot-phase-0.md)（${ms}）
- **Spec**：[../../superpowers/specs/lp-bot-superpower-rearchitecture-v1.md](../../superpowers/specs/lp-bot-superpower-rearchitecture-v1.md)（${sec}）
- **依赖任务**（必须先合入）：${deps_md}

## 文件范围
**允许修改/创建**：
${files_md}

**禁止修改**（CI 校验 *_test.go 不被改）：
- 其他任何文件

## 任务步骤（TDD）
1. 阅读 spec ${sec} 节、本任务依赖任务的实现、相关模块 README
2. 跑当前所有失败测试，确认本任务相关测试在失败列表中
3. 实现到测试由红变绿
4. 跑全套 unit + property（不破坏其他绿测）
5. 跑 lint，无新增 warning
6. 单 commit：\`<type>: ${id} <一句话>\`

## Definition of Done
- [ ] 所有指定测试通过
- [ ] 不破坏既有 *_test.go
- [ ] 单一逻辑提交（squash 后 1 commit）
- [ ] 任务范围外文件未被修改

## 不变量关联
${invs_md}

## 备注
（实现提示由实施 subagent 自行根据 spec 与依赖任务推导）
MD
done < <(printf '%s\n' "$MANIFEST")

echo "Generated $(ls "$OUT_DIR"/T-*.md | wc -l | tr -d ' ') task files in $OUT_DIR"
