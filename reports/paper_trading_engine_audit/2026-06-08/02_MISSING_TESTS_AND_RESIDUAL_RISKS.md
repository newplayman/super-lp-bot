## 4. Missing Tests / Residual Risks

### 4.1 缺失测试

| 缺失测试 | 严重度 |
|---|---|
| `TestInMemoryRecorder_ConcurrentIncrement` (race detector) | P0 (H2) |
| `TestSelectTokens_BlockedVerdictCaseInsensitive` (P1-6) | P1 |
| `TestRun_FailsOnRecommendationWithMissingHardBlockField` (P1-1) | P1 |
| `TestResolveHistoricalTimeColumn_ConsistentAcrossPackages` (P1-4) | P1 |
| `TestRun_UniverseBuilder_DoesNotCallAPIRecommendations` (P1-3) | P1 |
| `TestSelectTokens_RequiredColumnGate` (P1-5) | P1 |
| `TestRedactStripsBearerToken` / `TestWriteLeaderboardRedactsOutput` (P0-4) | P0 |
| `TestSubmitOrderRejectedWhenPlanExpired` / `TestGetOrderStatusReflectsPersistedState` (P0-2) | P0 |
| `TestRecordOutcomeRejectsZeroOrNegativeExit` / `TestMonitorWritesDistinctHighLowToOutcome` (P0-3) | P0 |
| `TestValidateComplete_RejectsBadSlippageBPS` etc. (P0-1) | P0 |
| `TestForceCloseRejectsAlreadyClosed` / `TestReducePositionTransitionsToPartial` (P1-8) | P1 |
| `TestScore_LowSampleFlagSet` / `TestSortLeaderboard_AllLowSampleEmitsWarning` (P1-11) | P1 |
| `TestReplaySmoke_NoBodyNoReportPath` (P1-14) | P1 |
| `TestPositionMonitor_LoopModeNotImplementedExit` (P1-14) | P1 |
| `TestReplayRunCmd_DeterministicCreatedAt` (P2-3) | P2 |
| `TestDecimalStringRoundTrip_SingleCanonicalForm` (P1-9) | P1 |
| `TestHistoricalReader_QueryBuilders_TokenUpdatedAtFallback` (P2-5) | P2 |
| `TestSystemHealth_NullDatasourceHealthIsOK` (P3-2) | P3 |
| `TestSchemaVersion_ContractRoundTrip` (H3) | P1 |
| `TestEndToEnd_ReportAPIHandler_404` (H3) | P1 |
| `go test -race` in CI / Makefile (H2) | P0 |

### 4.2 残余风险

| 风险 | 备注 |
|---|---|
| **fake vs real schema drift** (H4) | `positionmonitor.service.go:149-176` 硬编码 `RiskBudgetPct: "0.02"` 与真实 source 不符. 集成前必测. |
| **Float 精度在 paper R 中累积** (E5) | 短期 OK, 长期建议统一 `pkg/decimal` (`shopspring/decimal` 已可用 per LP-bot CLAUDE.md). |
| **DLQ dedup 静默丢失** (P2-7) | 若 `RadarEventID` dedup collision (low probability), force-close DLQ 行丢. |
| **`Service.RunReplay` 与 `BacktestOrchestrator.Run` 双实现** (D cross-cutting) | `Service` 已是 dead code 在 cmd 路径. 长期应合并. |
| **Position 缺 `Side` 字段** (H5) | short-side R 公式没测. 未来加 short-strategy 时会爆. |
| **2 个 ExitReason enum 平行** (H4) | `position.ExitReason` 与 `contracts.ExitReason` drift 风险. 建议 collapse. |
| **`average_r` 与 `mfe/mae` 失真** (E4) | 修 P0-3 前 leaderboard 数据不可信. |
| **空 report body 仍设 path** (P1-14) | `cmd/replay-smoke/main.go:472-490` 路径. |
| **`StrategyID` 未校验** (F1) | B 组 tradeplan schema 未 enforce strategy ID 注入. |
| **`_ = idempotency.EvaluationID`** placeholder (D cross-cutting) | 实际用 `defaultEvaluationID`, 未来 swap 可能 break. |
| **Dashboard `<script type="application/json">` 无 size cap** (G3) | 大 report 可能让 HTML 巨大. |

---

## 5. Next Actions (B 组, 5-10 个, 按优先级)

1. **修 P0-1 (Trade plan ValidateComplete)** — `internal/tradeplan/tradeplan.go:75-101` 加全字段校验 + 5 个新 test. **estimated: 1-2 人天**.
2. **修 P0-4 (Dashboard write-time redaction)** — `cmd/strategy-search/main.go:646-657` writeLeaderboard 加 redact; `sensitiveKeys` 扩; 4 个新 test. **estimated: 0.5-1 人天** (高 ROI, 防止 DSN 泄漏).
3. **修 P0-2 (Paper order status enum)** — 加 `OrderEntryZoneExpired`; consult `plan.ExpiresAt`; persist-aware `GetOrderStatus`; 3 个新 test. **estimated: 1-2 人天**.
4. **修 P0-3 (MFE/MAE High/Low 真实化)** — `MarketSnapshot` 扩字段 + `positionmonitor` 喂真实 high/low + 2 个新 test. **estimated: 1 人天**.
5. **修 P0-5 (race tests + `go test -race` in CI)** — 加 3 个 race test + Makefile/CI 加 `-race`. **estimated: 0.5 人天**.
6. **修 P1-1 (risk_penalties fail-open)** — `internal/alphacore/client.go:105-107` 改 `*RiskPenalties` + 1 test. **estimated: 0.5 人天**.
7. **修 P1-5 + P1-6 + P1-7 (Universe hardening)** — required-column gate + case-insensitive `RiskVerdict` + `hard_block` 缺列 warning. **estimated: 1 人天**.
8. **修 P1-8 (Position state machine Reduce)** — 加 `ReducePosition` + 修 `ForceClosePosition` transition. **estimated: 0.5 人天**.
9. **修 P1-9 (Decimal 统一)** — 引入 `pkg/decimal` (或 `shopspring/decimal`), 替换 5 个 hand-rolled parser. **estimated: 1-2 人天**.
10. **建议 A 组同步** (out of B scope, but spec asks): P1-1 (`hard_block` 字段始终显式 emit) + P1-2 (filter 实际生效). A 组需确认.

---

## 附录: 责任方总览

| 责任方 | 数量 | Findings |
|---|---|---|
| **B 组修 (in-house)** | 22 | P0-1, P0-2, P0-3, P0-4, P0-5, P1-1, P1-3, P1-4, P1-5, P1-6, P1-7, P1-8, P1-9, P1-10, P1-11, P1-12, P1-13, P1-14, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6, P2-7, P2-8, P2-9, P2-10, P2-11, P2-12, P3-2, P3-3, P3-4, P3-5 |
| **A 组补 (合作)** | 2 | P1-1 (确认 `hard_block` 字段始终 emit) + P1-2 (确认 `exclude_blocked` filter 实际生效) |
| **架构 / Doc** | 1 | P1-3 (document universe builder 不调 recommendations 原因) |

---

**审计完成. 不修改任何代码. 不泄露 DSN / token / 密钥. 仅输出报告.**

报告版本: 2026-06-08. 报告作者: 资深 Go 后端 / 交易系统 / 数据接口审计工程师 (per user request).
审计对象: `paper-trading-engine` @ `a2ed684` (master branch).
