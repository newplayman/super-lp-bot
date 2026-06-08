# 🔍 paper-trading-engine 代码审计 — 最终报告

- **repo**: `git@github.com:newplayman/paper-trading-engine.git`
- **branch**: `master`
- **commit**: `a2ed684` (adapt alphacore data handoff)
- **规模**: 104 Go files, 40,985 LoC
- **审计范围**: A (AlphaCore data ingest) + B (Universe selection) + C (Event consumer/DLQ/ACK) + D (Historical replay) + E (Paper execution/outcome) + F (Strategy search) + G (Dashboard) + H (Test quality)
- **审计员**: 资深 Go 后端 / 交易系统 / 数据接口审计工程师
- **审计时间**: 2026-06-08
- **审计方式**: 4 个并行 subagent 全仓阅读 104 个 .go 文件 + 3 篇 doc, **只读, 不修改任何代码**

---

## 1. Executive Summary

### 整体风险等级: **P1 (中等风险, 可继续推进回测/paper, 但有 5 个 P0 必修 + 11 个 P1 建议修)**

| 维度 | 评级 | 说明 |
|---|---|---|
| **AlphaCore 数据接入** | A- (P0/P1 各 1) | 主路径安全, fail-open 边界 1 处需修 |
| **Universe 候选池** | A- (P0 1 / P1 3) | whitelist 严格, 缺 1 个 source-view gate 测试 |
| **Event Consumer / DLQ / ACK** | A (P0 0 / P1 0 / P2 2) | validate→idempotency→reload→snapshot→eval→persist→ACK 顺序正确 |
| **Historical Replay** | A- (P0 0 / P1 0 / P2 4) | 未来数据无泄漏, 确定性 OK, 但 cmd 端 wall-clock 不固定 |
| **Paper Execution / Outcome** | C+ (P0 4 / P1 2) | 多个数据正确性问题: trade plan 校验不全 / status enum 错配 / MFE-MAE 全是 last-price |
| **Strategy Search** | B (P0 0 / P1 2) | warnings 已记录但 dashboard 没红 banner 警示非盈利 |
| **Dashboard** | C (P0 1 / P1 2) | 字段脱敏在 render-time 不在 write-time, 长文本无 size cap |
| **Test 质量** | C (P0 2 / P1 4) | 缺 race 测试, fake vs real schema drift 风险 |

### 是否适合继续推进回测 / paper 测试?

✅ **有条件适合**. 5 个 P0 必须先修 (尤其 E1/E2/E4/G4/H2/H4 中影响 R 数据正确性和敏感数据泄漏的); 修完可继续推进 paper trading + 后续 A 组数据接入. **不** 适合宣传"策略盈利" — 风险并未实际证明 LP edge (`edge_proven=no` 维持).

---

## 2. Findings (按 P0 / P1 / P2 / P3 排序)

### 🔴 P0 (5 条 — 必须修)

#### P0-1 — Trade plan `ValidateComplete` 校验不全, 缺字段类型/范围/枚举校验
- **文件 / 行号**: `internal/tradeplan/tradeplan.go:75-101`
- **问题**: `ValidateComplete` 校验 entry zone, price, stop loss, take profit, exit triggers, risk, 但**不**校验:
  - `Entry.Type` ∈ 允许的 enum
  - `Entry.MaxEntrySlippageBPS` 是 (0, 10000] 区间内 decimal 字符串
  - `StopLoss[].Type/Price/Condition` 完整 + well-formed
  - `TakeProfit[].SizePct` 之和 ≈ 100%
  - `TakeProfit[].PriceRule` ∈ 允许 enum
  - `Risk.MaxLossR` 是正 decimal
  - `ExpiresAt > CreatedAt`
  - `ExitTriggers[].MaxSecondsAfterTrigger > 0`
- **为什么重要**: 畸形 plan 污染下游 NetCostR/MFE/MAE, 传播到 `outcome.Record`. 整段"完整性校验"形同虚设.
- **建议修复**: 扩展 `ValidateComplete` 类型校验每个字段; 用 `contracts.IsDecimalString`; closed enum for `Entry.Type` / `StopLossRule.Type` / `TakeProfitRule.PriceRule` / `ExitTrigger.Type`; reject `ExpiresAt <= CreatedAt`; sum `SizePct == 100`.
- **建议测试**: `TestValidateComplete_RejectsBadSlippageBPS`, `TestValidateComplete_RejectsExpiryInPast`, `TestValidateComplete_RejectsTPNotSummingTo100`.
- **责任方**: **B 组修** (in-house).
- **引用**: E1 in subagent audit.

#### P0-2 — Paper order status enum 错配, 漏 entry_zone_expiry 终态, slippage cap 未与 plan 对照
- **文件 / 行号**: `internal/paperexchange/paperexchange.go:163-187, 247, 258-266, 292, 194`
- **问题**:
  1. `OrderSimExpired` 用于"ask price 超出 entry zone", 但**不**是真的 TTL expiry; `plan.ExpiresAt` 字段在整文件**从未**被 consult
  2. 没有 `OrderEntryZoneExpired` 区分
  3. `MaxEntrySlippageBPS` 从 plan 读入但**未**与实际 slippage 比较 (`simulateFill` 写死的 `slippageBPS+priceImpactBPS` 加到 ask, **不**与 plan cap 对照)
  4. `Fill.FailedTxCostUSD` 写死 `"0"`, 失败回滚无 path
  5. `GetOrderStatus` **总是**返回 `OrderSimSubmitted`, 与 recorder 存储不一致
- **为什么重要**: "paper exchange" 应该 model real frictions (entry-zone, slippage cap, liquidity reject), 静默让 orders 以错配 status 通过, 下游 driver 用 `GetOrderStatus` 永远看到 "submitted" → 状态机 query-incoherent.
- **建议修复**: 加 `OrderEntryZoneExpired`; consult `plan.ExpiresAt`; 任何 observed slippage `> plan.Entry.MaxEntrySlippageBPS` → `OrderSimPartiallyFilled` or `OrderSimRejected`; `GetOrderStatus` 读 recorder 真实状态.
- **建议测试**: `TestSubmitOrderRejectedWhenPlanExpired`, `TestGetOrderStatusReflectsPersistedState`, `TestSimulatedSlippageExceedingPlanCapRejected`.
- **责任方**: **B 组修** + 建议 A 组在 plan schema 文档中明示 `Entry.MaxEntrySlippageBPS` 语义.
- **引用**: E2 in subagent audit.

#### P0-3 — Outcome MFE/MAE 用 LastPrice 当 High/Low, 数据失真
- **文件 / 行号**: `internal/positionmonitor/service.go:163-167`; `internal/position/position.go:67-73`; `internal/outcome/outcome.go:173-175`
- **问题**: `MarketSnapshot` 只有 `LastPrice`, 没有 `HighPrice` / `LowPrice`. Monitor 把 `market.LastPrice` 同时填入 High 和 Low. MFE = `(high-entry)/risk` 与 MAE = `(low-entry)/risk` 因此**总是相等**, 等于 `(LastPrice-entry)/risk`, 几乎为 0. 测试因手工塞 high/low 才看到 `MFE=2.6, MAE=-0.08`. 真实生产数据 MFE/MAE 几乎全为 0 → leaderboard 看到 "existed but didn't move".
- **为什么重要**: MFE/MAE 喂 strategy search score + report-api dashboard, 失真数据直接误导 B 组对策略表现的判断.
- **建议修复**: 扩 `MarketSnapshot` 加 `HighPrice/LowPrice` (或 fetch open 窗口的 windowed high/low); 累加 mark-to-market extremes 在 position 自身; `outcome.go:94` 加 `if exit <= 0 { return ..., ErrInvalidPrices }`.
- **建议测试**: `TestRecordOutcomeRejectsZeroOrNegativeExit`, `TestMonitorWritesDistinctHighLowToOutcome`.
- **责任方**: **B 组修**.
- **引用**: E4 in subagent audit.

#### P0-4 — Dashboard 字段脱敏**不**在 write-time, leaderboard JSON 文件可泄漏 DSN/token
- **文件 / 行号**: `cmd/replay-smoke/dashboard.go:62-119`; `cmd/strategy-search/main.go:646-657`; `cmd/report-api/handler.go:228-255`
- **问题**:
  1. Redact 仅在 render HTML 时, **不**在 `writeLeaderboard` 写文件时
  2. `report-api handler.handleStrategyLeaderboard` 读文件 raw 返回任意 HTTP caller → `STRATEGY_SEARCH_OUTPUT_PATH` 可泄漏含 `dsn` 字段的 leaderboard
  3. `sensitiveKeys` 仅匹配精确 key 名, **不**匹配 `bearer_token` / `authorization` / `*_dsn` 后缀 / DSN-shaped URL 值 (`postgresql://...`)
  4. 测试只查 leaderboard struct **不**含 `dsn`, 不查 `SearchConfig.DSN` 实际写入路径
- **为什么重要**: Dashboard 部署后, 任何拿到 leaderboard 路径的 caller 都能拿到 Postgres DSN. 真实生产 incident 风险.
- **建议修复**: 扩 `sensitiveKeys` 含 `token/bearer/authorization/connection_string/*_dsn/*_key`; 值若像 `postgresql://` URL 也 redact; **write-time redact** (在 `writeLeaderboard` 写文件时已脱敏).
- **建议测试**: `TestRedactStripsBearerToken`, `TestRedactStripsDSNValue`, `TestWriteLeaderboardRedactsOutput`.
- **责任方**: **B 组修**.
- **引用**: G4 in subagent audit.

#### P0-5 — 缺 `go test -race` 测试覆盖关键并发结构 (InMemoryRecorder / persist path / monitor)
- **文件 / 行号**: `internal/observability/observability.go:51-148`; `internal/paperexchange/paperexchange.go:202-207`; `internal/positionmonitor/service.go:108-212`
- **问题**:
  1. `InMemoryRecorder` 用 `sync.Mutex` 但**无**任何 race 测试
  2. `paperexchange.persist` 写 `OrderRecorder`, 并发 `SubmitOrder` (parallel orchestrator 场景) **无**测试
  3. `positionmonitor.ScanOnce` 与"另一实例正在 close 同 position" 无 race 测试
  4. `cmd/position-monitor` shutdown **无**测试
- **为什么重要**: 并发结构无 race 测试, 真实生产 race condition 不会被发现. paper trading 在单一 goroutine 跑通, **但**未来引入多 worker / multi-source consumer 时会爆.
- **建议修复**: 加 `TestInMemoryRecorder_ConcurrentIncrement` (N goroutines, N increments, snapshot count); 加 `TestInMemoryRecorder_ConcurrentSnapshotIsSafe`; 加 `go test -race` 到 Makefile/CI.
- **建议测试**: 同时 paperexchange fake `OrderRecorder` 加 internal mutex, 两个 goroutine 调 `SubmitOrder` 同时.
- **责任方**: **B 组修**.
- **引用**: H2 in subagent audit.

### 🟠 P1 (11 条 — 建议修)

#### P1-1 — `risk_penalties: {}` 静默 fail-open
- **文件 / 行号**: `internal/alphacore/client.go:105-107`; `cmd/alphacore-check/main.go:159-163`
- **问题**: `RiskPenalties` 是 struct 非 pointer, 空 `{}` 与 absent 行为相同, 默认 `HardBlock=false`. 若 A 组后加 `soft_block` 字段且服务端省略 `hard_block`, 默认为 `false`, recommendation 漏过.
- **建议修复**: 改 `*RiskPenalties` pointer, `nil` = "unknown — treat as potential hard block" + 要求 `Confirmed: true`.
- **建议测试**: `TestRun_FailsOnRecommendationWithMissingHardBlockField`.
- **责任方**: **B 组修** + 建议 A 组确认 `hard_block` 字段始终显式 emit.
- **引用**: A11 in subagent audit.

#### P1-2 — `exclude_blocked=true` 已发送但无 alert 当 filter is no-op
- **文件 / 行号**: `internal/alphacore/client.go:196-224`; `cmd/alphacore-check/main.go:102`
- **问题**: Per recheck doc, A 组生产服务端 default `/tokens` 实际**不** filter blocked items. `alphacore-check` 看到 `0/0` 不告警.
- **建议修复**: 比较 `len(tokens.Items)` 与 `RadarStatus`/`RiskVerdict`/`HardBlock`, 若任意 returned item 仍 blocked 而 `ExcludeBlocked=true` 已 set → `[WARN]`.
- **建议测试**: `TestRun_AlphacoreCheckWarnsOnFilteredLeak`.
- **责任方**: **B 组修** + 建议 A 组补 ensure filter 实际生效.
- **引用**: A3 in subagent audit.

#### P1-3 — `test-universe-builder` **不**调 `/api/onchain-radar/recommendations`
- **文件 / 行号**: `cmd/test-universe-builder/main.go:70-87`
- **问题**: Universe builder 全部来自 `public.radar_v_token_state_history` Postgres view, **不**用 A 组 curated `/recommendations`. 与 `alphacore-check` 不一致.
- **建议修复**: Document 此设计选择; 或加 `UNIVERSE_RECOMMENDATIONS_SOURCE=api` mode 调 recommendations + fallback Postgres.
- **建议测试**: `TestRun_UniverseBuilder_DoesNotCallAPIRecommendations` (negative assertion).
- **责任方**: **B 组修** (documentation); A 组 OK.
- **引用**: A2 in subagent audit.

#### P1-4 — `splitRawView` / `ResolveHistoricalTimeColumn` 在 testuniverse 与 postgresalpha 重复, 无 parity test
- **文件 / 行号**: `internal/testuniverse/query.go:178-194` vs `internal/adapters/postgresalpha/historical.go:344-365`
- **问题**: 两份独立实现, 若 A 组 view 改名, 都要改, 第三方消费者会漏掉.
- **建议修复**: 加 parity test `TestResolveHistoricalTimeColumn_ConsistentAcrossPackages`; 或抽到 `internal/sqlid/` 共享 package.
- **建议测试**: table-driven 参数化.
- **责任方**: **B 组修**.
- **引用**: A18 in subagent audit.

#### P1-5 — Universe builder 缺 required-column gate (P0 概念缺口)
- **文件 / 行号**: `internal/testuniverse/query.go:24-88`
- **问题**: `QueryUniverseRowsWithColumn` 接受任何 view name, **不**验证 view 含 `radar_status` / `risk_verdict` / `chain` / `token_address` / `radar_score` (state view 必备列). Future contributor 可能错指 event log view.
- **建议修复**: 扩 `resolveExtraColumns` 同时 gate 必需列, 缺一即 refuse.
- **建议测试**: 指向只含 `event_time + event_type` 的 fake view, assert 函数返回 error.
- **责任方**: **B 组修**.
- **引用**: B6 in subagent audit.

#### P1-6 — Universe `RiskVerdict` 比较大小写敏感 + 未 trim
- **文件 / 行号**: `internal/testuniverse/builder.go:79-81`
- **问题**: A 组若返回 `"Blocked"` 或 `" BLOCKED "`, 行漏过. status filter 已 `ToLower+TrimSpace`, 这里未一致.
- **建议修复**: `rv := strings.ToLower(strings.TrimSpace(row.RiskVerdict))`.
- **建议测试**: `TestSelectTokens_FiltersBlockedVerdictCaseInsensitive`.
- **责任方**: **B 组修**.
- **引用**: B3 in subagent audit.

#### P1-7 — Universe SQL `hard_block` 缺列 fallback 静默设 `false`
- **文件 / 行号**: `internal/testuniverse/query.go:137-143`
- **问题**: 当 view 既无 `hard_block` 列也无 `risk_penalties` JSON 列, SQL 写死 `false`, hard-blocked token 漏进 universe.
- **建议修复**: 第三分支 log warning + surface metric `universe_hard_block_column_missing` 或 refuse.
- **建议测试**: 指向无 `hard_block` 列的 view, assert warning emitted.
- **责任方**: **B 组修**.
- **引用**: B4 in subagent audit.

#### P1-8 — Position state machine 缺 `ReducePosition` + ForceClose 缺 transition check
- **文件 / 行号**: `internal/position/position.go:9-17, 93-96, 161`
- **问题**: `StatusPartiallyReduced` 在 transition table 中但**无**任何代码 path emit. `ForceClosePosition` 调 `ValidateTransition` 后**不**再调一次以禁止 `Closed → ForceClosed` 重入. 双 force-close 静默允许.
- **建议修复**: 加 `ReducePosition(p, sizeDelta, price, clock)`; `ForceClosePosition` 末尾加 `ValidateTransition(p.Status, StatusForceClosed)`.
- **建议测试**: `TestForceCloseRejectsAlreadyClosed`, `TestReducePositionTransitionsToPartial`.
- **责任方**: **B 组修**.
- **引用**: E3 in subagent audit.

#### P1-9 — Decimal 字符串约束**未**统一, 5 个手写 parser + 3 个 float-to-string
- **文件 / 行号**: `internal/paperexchange/paperexchange.go:353-359`; `internal/position/position.go:217-248`; `internal/outcome/outcome.go:212-243`; `internal/report/report.go:207-238`; `internal/tradeplan/tradeplan.go:311-342`; `cmd/strategy-search/main.go:832-847`
- **问题**: 5 份独立 `decimalToFloat` parser, 3 份 `floatToDecimal` 转换. `0.00120 * 1.0005` 经 `FormatFloat(-1)` 输出 `0.0012006` 而非 `0.00120`, plan ID hash mutate.
- **建议修复**: 引入统一 `pkg/decimal` (或用 `github.com/shopspring/decimal` per CLAUDE.md mandate), 替换所有 hand-rolled parser; 单一 typed `Decimal` lossless round-trip.
- **建议测试**: `TestDecimalStringRoundTrip_SingleCanonicalForm`.
- **责任方**: **B 组修**.
- **引用**: E5 in subagent audit.

#### P1-10 — Dashboard `strategy_search_error` 不影响 badge 状态 (UX 不一致)
- **文件 / 行号**: `cmd/replay-smoke/dashboard.go:289-300, 518`
- **问题**: "无阶段错误" 卡片可 `[ ]` 但 status bar 显示 `OK`. 用户看到 OK 不去查 checklist.
- **建议修复**: `else if(S.strategy_search_enabled && S.strategy_search_error){status='warn';sText='WARN';}` 在 OK 分支前.
- **建议测试**: dashboard 单元测试.
- **责任方**: **B 组修**.
- **引用**: G2 in subagent audit.

#### P1-11 — Strategy search low-sample 标记缺失, "best_candidate" 仍展示
- **文件 / 行号**: `internal/strategysearch/strategysearch.go:233-247`; `cmd/replay-smoke/dashboard.go:466-481`
- **问题**: Score 含 `lowSamplePenalty`, 但 `BestCandidate` 可来自 `OpenedCount=2` 试验 (low-sample) 仍被展示为 winner. Dashboard 无 "low-sample" 视觉标记.
- **建议修复**: 加 `LowSample bool` 字段, all-failed 时 `best_candidate = null` + warning. Dashboard low-sample 行 status-warn color.
- **建议测试**: `TestScore_LowSampleFlagSet`, `TestSortLeaderboard_AllLowSampleEmitsWarning`.
- **责任方**: **B 组修**.
- **引用**: F3 in subagent audit.

#### P1-12 (额外) — Thin string-only tests 多处
- **文件 / 行号**: `internal/paperexchange/fill_test.go:124-127`; `internal/position/position_test.go:35-43`; `internal/strategysearch/strategysearch_test.go:228-238, 240-251`; `internal/outcome/outcome_test.go:151-164`
- **问题**: 测试**只** assert literal 字符串, 不验证真实行为. 多个 "no-op" 测试无法区分 first call vs repeat call.
- **建议修复**: 替换 string-only assertion 为 semantic round-trip (e.g. "MFE = (high - entry) / risk when low < entry < high").
- **责任方**: **B 组修**.
- **引用**: H1 in subagent audit.

#### P1-13 (额外) — Integration / contract tests 缺失
- **文件 / 行号**: `cmd/strategy-search/main.go:633-644`; `cmd/report-api/handler.go:23-35`; `internal/contracts/`
- **问题**: `report-api handler` 无 test file; `defaultNewHistoricalReader` 走真 Postgres 但**无** integration test; `contracts` package 无 round-trip test 验 `SchemaVersion` 强制.
- **建议修复**: 加 handler test (ListReplayRuns 限 limit, GetReplayRun 404 mapping); 加 contracts round-trip test; 加 strategy-search 真实 Postgres integration test.
- **责任方**: **B 组修**.
- **引用**: H3 in subagent audit.

#### P1-14 (额外) — Regression test gaps
- **文件 / 行号**: `cmd/replay-smoke/main.go:472-490`; `cmd/position-monitor/main.go:198-201`; `internal/position/position.go:44-65` (缺 `Side` 字段)
- **问题**:
  1. 空 report body 仍设 `replay_report_path` → dashboard 误报 success
  2. `POSITION_MONITOR_ONCE=0` 永远 exit 4 但无 test
  3. Position 缺 `Side` 字段, short-side R 公式没测试
- **建议修复**: 加 `TestReplaySmoke_NoBodyNoReportPath`, `TestPositionMonitor_LoopModeNotImplementedExit`, 扩 Position 加 `Side` + short-side R test.
- **责任方**: **B 组修**.
- **引用**: H5 in subagent audit.

### 🟡 P2 (12 条 — 中等)

#### P2-1 — `cmd/strategy-search/main.go:309-316` 只存第一个 fixture path 到 leaderboard (虽 Datasets 字段含全部)
- **责任方**: B 修
- **引用**: F2 in subagent audit.

#### P2-2 — Custom stream ACK/DLQ `source_stream` 不一致风险
- **文件 / 行号**: `internal/eventconsumer/eventconsumer.go:521-542`; `cmd/event-consumer/main.go:350-357`
- **问题**: DLQ `source_stream` 是 message-claimed, ACK stream 是 consumer-configured. 跨系统 audit join 可能 off by mismatch.
- **建议修复**: 总是 `eventMsg.SourceStream = stream.Stream()`.
- **引用**: C5 in subagent audit.

#### P2-3 — Replay cmd clock 未注入, 每次 `created_at` 不同
- **文件 / 行号**: `cmd/replay-runner/main.go:436`; `cmd/replay-smoke/main.go:410, 582`
- **问题**: 内包 deterministic 但 cmd 用 `time.Now().UTC()`, `replay_runs.created_at` run-to-run 不同. 阻碍 idempotent re-run.
- **建议修复**: 接受 `REPLAY_RUN_CLOCK` (RFC3339) env var.
- **建议测试**: `TestReplayRunCmd_DeterministicCreatedAt`.
- **引用**: D2 in subagent audit.

#### P2-4 — `historical.listEventsQuery` ORDER BY 缺次级 tie-breaker
- **文件 / 行号**: `internal/adapters/postgresalpha/historical.go:184, 209`
- **问题**: 当 `timeCol = token_updated_at` 同一秒多条 state snapshot, `LIMIT 1` 任意选取. 可能破坏 "pick latest at or before eventTime" 语义.
- **建议修复**: 加次级 tie-breaker (e.g. `snapshot_id`).
- **引用**: D6 cross-cutting in subagent audit.

#### P2-5 — `historical.NewHistoricalReaderFromDB` 不 auto-detect time column
- **文件 / 行号**: `internal/adapters/postgresalpha/historical.go:69-79, 168-173`
- **问题**: 静默 default `token_updated_at`, 即使 view 有 `event_time`. 与 auto-detecting 构造函数 `NewHistoricalReaderWith` 不一致.
- **建议修复**: 合并两构造函数; 或强制 `NewHistoricalReaderFromDB` 也 auto-detect.
- **引用**: D6 in subagent audit.

#### P2-6 — `computeSummary` AverageHoldingTimeSeconds divisor 是 `len(records)` 而非 `count_with_positive_duration`
- **文件 / 行号**: `internal/replay/orchestrator.go:860-922`
- **问题**: 若 `HoldingDurationSeconds == 0` (e.g. force-close failure 或 open 立即 close), 平均向上偏.
- **建议修复**: 只除 `count > 0` 部分; 或 doc contract.
- **引用**: D5 in subagent audit.

#### P2-7 — DLQ dedup on identical `source_event_id` 静默丢失
- **文件 / 行号**: `internal/replay/orchestrator.go:644-695, 818-829`
- **问题**: `routeDeadLetter` 与 `recordDeadLetter` 忽略 `inmemory.Store.Write` 返回的 `ErrDuplicate`. 两 force-close DLQ 行 for same `RadarEventID` 实际只写一条.
- **建议修复**: Propagate 错误或 suffix with `position_id`.
- **引用**: D4 nit in subagent audit.

#### P2-8 — `recent_60m_count` 字段 parsed but never used (dead field)
- **文件 / 行号**: `internal/alphacore/client.go:119-124`
- **问题**: Parsed 但 decision rule 只看 `status`. A 组 recheck 暗示 `recent_60m_count=0` 应作 `[WARN]`.
- **建议修复**: 删字段; 或暴露 accessor + log warning.
- **引用**: A6 in subagent audit.

#### P2-9 — `risk_verdict` / `radar_status` enum 用 denylist, 建议 whitelist
- **文件 / 行号**: `cmd/alphacore-check/main.go:149, 154`
- **问题**: Denylist 不能拒 typo (e.g. "blocke"). testuniverse 用 whitelist 不一致.
- **建议修复**: Mirrored whitelist; 或 doc asymmetric.
- **引用**: A12, A13 in subagent audit.

#### P2-10 — `historical.go` 不 probe 新列, hard-codes schema
- **文件 / 行号**: `internal/adapters/postgresalpha/historical.go:175-210`
- **问题**: 若 A 组加新列 (e.g. `effective_score`), historical reader 需 code change. testuniverse 已硬化.
- **建议修复**: 共享 `extraColumns` machinery; 或 doc dependency.
- **引用**: A17 in subagent audit.

#### P2-11 — Universe `Chain` case-sensitive (无 ToLower)
- **文件 / 行号**: `internal/testuniverse/builder.go:79-83`; `internal/testuniverse/universe.go:103`
- **问题**: A 组返回 `"Solana"` vs `"solana"`, dedup 失败.
- **建议修复**: 统一 lowercase.
- **引用**: B cross-cutting in subagent audit.

#### P2-12 — `cmd/strategy-search` framing caveat 在 dashboard 上不显眼
- **文件 / 行号**: `cmd/replay-smoke/dashboard.go:205-206`; `cmd/report-api/handler.go:282-296`
- **问题**: 小灰字 caveat, 用户易忽略 `[最佳候选]` 绿色行.
- **建议修复**: 红 border banner: "Strategy search scores are dev-validation only — not a profitability signal."
- **引用**: F1, G5 in subagent audit.

### 🟢 P3 (5 条 — 优先级低 / 文档)

#### P3-1 — `risk_penalties` 与 absent field 行为相同 (silent fail-open 已提升到 P1-1)
- 已在 P1-1 处理.

#### P3-2 — `datasource_health: null` 走 array unmarshal by accident
- **文件 / 行号**: `internal/alphacore/client.go:164-166`
- **问题**: `len(null)==0` 误判, 实际 `null` 是 4 字节.
- **建议修复**: Explicit `bytes.Equal(..., []byte("null"))` guard.
- **引用**: A9 in subagent audit.

#### P3-3 — `NewHistoricalReaderFromDB` skips time-column resolution (已提升到 P2-5)
- 已在 P2-5.

#### P3-4 — `evidenceQualityFromConfidence` 解析失败返 `""` 不传
- **文件 / 行号**: `internal/alphacore/client.go:322-335`
- **问题**: 解析失败返 `""` 而非 `"low"`, 未来 caller 可能误判.
- **建议修复**: 统一 `"unknown"` 或 doc.
- **引用**: A14 in subagent audit.

#### P3-5 — `ToTokenState` drops `RecommendationScore` / `RiskPenalties` / holder fields
- **文件 / 行号**: `internal/alphacore/client.go:293-313`
- **问题**: TokenState struct 无这些字段, replay 拿不到.
- **建议修复**: 扩 `radarreader.TokenState` 加字段, 两 reader 同步; doc absence.
- **引用**: A15 in subagent audit.

---

## 3. Positive Observations ✅

| 维度 | 做得好的地方 |
|---|---|
| **Universe whitelist** | `testuniverse/builder.go:72-75` 用 closed-world whitelist (4 状态), 比 denylist 安全; 新状态自然 fail-close. |
| **B+ 4 active states 全覆盖** | candidate / setup_watch / pullback_ready / setup_triggered 一一测试 (`TestSelectTokens_KeepsAllActiveStatuses`). |
| **Event consumer 顺序** | validate → idempotency → reload → snapshot → eval → persist → ACK 顺序严格 (`eventconsumer.go:237-294`). |
| **DLQ write before ACK** | 严格, DLQ 失败返 `ErrRetryable` 不 ACK (`eventconsumer.go:535-555`). |
| **Source event ID** | `event_id` → `stream:<msg-id>` → `unknown` 三级 fallback, 唯一 dedup. |
| **Replay future-data guard** | `eventTime` bound 严格, `GetTokenStateAt` + `SnapshotTS > eventTime` 拒绝 + 测覆盖. |
| **Replay determinism (in-package)** | `Service.RunReplay` / `BacktestOrchestrator.Run` 在 fixed clock 下 deterministic (`TestReplayProducesDeterministicResults`). |
| **Close failure keeps open position** | `closePositionAndRecordOutcome` 失败返 `(false, nil)`, 位置**不**从 `openBySig` 删. 多测覆盖. |
| **Force-close quote exhaustion → DLQ** | DLQ 写 + counter 增 + `firstErr` 设, 位置**不**删. |
| **HistoricalReader time column resolution** | auto-detect `event_time` → fallback `token_updated_at` → fail-close (`historical.go:344-365`). |
| **Postgres historical reader schema-aware** | `testuniverse/query.go:98-145` probe 5 个新 optional columns (`recommendation_score` 等), 缺列 graceful degrade. |
| **System-health 严格用 `status` 字段** | `client.go:238-255` 不读 `recent_60m_count`; tested. |
| **Datasource_health dual-schema** | object / array 两种 schema 兼容 (`client.go:144-181`), 7 个测试. |
| **NIL-safe token summary** | `recommendation_score` / `risk_penalties` 用 `any` + `decimalJSONToString` 处理 null/missing. |
| **Idempotency backstop** | `paperpostgres` 全部用 `ON CONFLICT (radar_event_id) DO NOTHING`. |
| **Strategy search warnings 记录** | 显式列 "DefaultStopLossBPS 不能 inject" 等 warnings (`strategy-search/main.go:205-209`). |
| **Dashboard time handling** | 离线 elapsed / timeout detection (`dashboard.go:289-293`), 5 种 status 完整. |
| **Decimal string output 一致性** | 至少 5 个模块各自内部 round-trip 正确. |
| **Force-close 错误退出** | `Run` 返 non-zero error. |
| **Test coverage (E/D/C section)** | 多测覆盖 close-failure / time-travel / DLQ. |
| **Cmd cmd-level 调度** | `cmd/replay-smoke`, `cmd/replay-runner`, `cmd/strategy-search`, `cmd/position-monitor`, `cmd/event-consumer` 5 个二进制职责清晰. |
