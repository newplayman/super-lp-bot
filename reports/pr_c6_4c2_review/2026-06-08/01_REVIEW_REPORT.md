# PR-C6 4c.2 EventStore.subscribe 复核报告

- **报告版本**: 2026-06-08
- **复核对象**: `auto-trade` 仓库 PR-C6 4c.2 (EventStore.subscribe reclaim options 兼容)
- **被审 commit**: `5466d83` (fix(pr-c6.4c.2): wire EventStore subscribe reclaim options correctly)
- **相关前置 commit**: `7989c5d` (4c.1) / `a7bbb57` (4c)
- **真实仓库**: `/home/deploy/auto-trade`
- **当前 branch**: `strategy-accounting-p0`
- **当前 HEAD**: `5466d83` (3 commits ahead of `pr-c6-reduce-only-pel-recovery-base`)
- **复核员**: 资深 Go 后端 / 交易系统 / 数据接口审计工程师

---

## 0. 1 段总结 (executive TL;DR)

⚠️ **用户描述的"问题"实际不成立**. PR-C6 4c.2 主修 commit `5466d83` + 前置 `1a24370` **已经**修了 EventStore.subscribe 三参 + execution-service 五参兼容问题. 真实代码 `apps/execution-service/src/index.ts:133, 140, 193` **已经**用 5 参形式 `(stream, group, consumer, handler, reclaimOptions)`. EventStore.subscribe (`packages/event-store/src/event-store.ts:519-647`) **已经**支持 4 个 form. 4 个新测试 case (TC-4c, TC-4d, TC-4e, TC-4f) + execution-service wiring test **全部 PASS** (execution-service 71 + event-store 56 + pnpm test 总 171 = 298 passed). strategy-service typecheck 6 errors **全 in node_modules** (pre-existing 361b6d2, **与 4c.2 无关**, 5466d83 commit message 已明确说明). **不**提交新 commit (无新内容), **不**静默修 scope 外 (strategy-service typecheck), **不**进入 4d, **不**启动 2h paper, USE_MOCK=true (paper mode).

---

## 1. 实际代码审计 (Step 1: source 验证)

### 1.1 EventStore.subscribe 4 个 form (event-store.ts:519-647)

| Form | 签名 | 用途 |
|---|---|---|
| 1 | `subscribe(stream, handler, reclaimOptions?)` | 3 参简化, 默认 group/consumer |
| 2 | `subscribe(stream, group, consumer, handler, reclaimOptions?)` | 5 参完整 |
| 3 | `subscribe(stream, group, handler, reclaimOptions?)` | 3 参 group+handler, 默认 consumer |
| 4 | `subscribe(stream, group, consumer, handler)` (无 per-call reclaim) | 5 参无 per-call, fallback to effective defaults |

**关键观察**: EventStore.subscribe **已经**支持 3 参形式 (form 1 + form 3) — 1a24370 commit 引入. 用户描述的"EventStore.subscribe 签名只支持 5 参"**不**成立.

### 1.2 execution-service 5 参调用 (index.ts:133, 140, 193)

```typescript
// line 133-138 (paper mode, order_intents)
const unsubscribe = await eventStore.subscribe(
  "stream.order_intents",
  group,        // "execution-service"
  consumer,     // "consumer-${process.pid}"
  executor.executeOrder,
  reclaimOptions,  // EXECUTION_SUBSCRIBE_RECLAIM_OPTIONS
);
```

```typescript
// line 193-199 (live mode, order_intents)
const unsubscribe = await eventStore.subscribe(
  "stream.order_intents",
  group,
  consumer,
  async (messages) => { await processor.processIntents(messages); },
  reclaimOptions,
);
```

**关键观察**: execution-service **已经**用 5 参形式 (form 2). 用户描述的"`eventStore.subscribe("stream.order_intents", executor.executeOrder, reclaimOptions)` (3 参)"**不**存在.

### 1.3 EXECUTION_SUBSCRIBE_RECLAIM_OPTIONS (index.ts:36-43)

```typescript
export const EXECUTION_SUBSCRIBE_RECLAIM_OPTIONS: SubscribeReclaimOptions = {
  minIdleMs: 1_000,
  reclaimIntervalMs: 5_000,
  maxDeliveryCount: 5,
  blockMs: 2_000,
  count: 10,
  deadLetterHandler: undefined,
};
```

**关键观察**: per-call reclaim options **已经** 显式 set, **不** 是 default. paper + live 共享同一 reclaim profile (5466d83 集中化).

### 1.4 RedisStreams.subscribe 5 参 (event-store.ts:647)

```typescript
const sub = this.redis.subscribe(stream, group, consumer, handler, merged);
```

`merged` 是 EventStore 把 per-call options + defaults merge 后的最终配置. **不** 落 default. Reclaim options **会** flow 到底层 RedisStreams.subscribe.

---

## 2. 测试结果 (Step 2-4: pnpm test + typecheck)

### 2.1 针对性测试 (user 要求)

| 命令 | 结果 |
|---|---|
| `pnpm --filter @auto-trade/execution-service test` | ✅ **71 passed** (8 files, 0 failures) |
| `pnpm --filter @auto-trade/event-store test` | ✅ **56 passed** (3 files, 0 failures) |

### 2.2 完整测试

| 命令 | 结果 |
|---|---|
| `pnpm test` (all packages, 20 files) | ✅ **171 passed** (0 failures) |

### 2.3 Typecheck 单独跑

| 包 | typecheck 结果 |
|---|---|
| `apps/execution-service` | ✅ **PASS** (clean) |
| `packages/event-store` | ✅ **PASS** (clean) |
| `apps/strategy-service` | ❌ 6 errors — **全部 in `node_modules`** (`@vitest/expect` vs `@types/chai` duplicate identifier) |

**Typecheck 错误** (来自 6 errors 全部):
- `../../node_modules/.pnpm/@vitest+expect@2.1.9/.../chai.d.cts(17-158)`: TS2300 Duplicate identifier 'Message' / 'ObjectProperty' / 'ChaiPlugin' / 'AssertionArgs' / 'Operator' / 'OperatorComparable'
- `../../node_modules/@types/chai/index.d.ts(6-2132)`: same set
- `../../node_modules/@types/chai/index.d.ts(2132,23)`: TS2484 Export declaration conflicts

**关键观察**:
- PR-C6 4c.2 直接影响的 2 个包 (`apps/execution-service` + `packages/event-store`) **都 clean**
- `apps/strategy-service` 6 errors **全 in node_modules**, **与 4c.2 无关**
- pre-existing in 361b6d2, 5466d83 commit message 已明确说明:
  > "Pre-existing @types/chai vs @vitest/expect duplicate-identifier conflict in node_modules remains (confirmed exists on parent commit 361b6d2 — unrelated to this PR)."

### 2.4 5466d83 引入的 4 个测试 (per commit message)

| TC ID | 测试名 | 来源 |
|---|---|---|
| TC-4c | `subscribe(stream, handler, reclaimOptions)` — 3 参 simplified | `packages/event-store/src/event-store.test.ts` |
| TC-4d | `subscribe(stream, group, consumer, handler, reclaimOptions)` — full | same |
| TC-4e | 5 参无 per-call reclaim falls back to effective defaults | same |
| TC-4f | `subscribe(stream, group, handler, reclaimOptions)` — group+handler shape | same |
| (execution-service) | "PR-C6 4c.2 — execution-service subscribe reclaimOptions wiring" describe block (2 tests) | `apps/execution-service/src/execution.test.ts` |

**execution-service wiring test 关键断言** (lines 1083-1089):
```typescript
// The critical assertion: the SAME reclaim object reaches subscribe()
expect(captures[0].reclaimOptions).toBe(EXECUTION_SUBSCRIBE_RECLAIM_OPTIONS);
expect(captures[0].reclaimOptions.minIdleMs).toBe(1_000);
expect(captures[0].reclaimOptions.reclaimIntervalMs).toBe(5_000);
expect(captures[0].reclaimOptions.maxDeliveryCount).toBe(5);
expect(captures[0].reclaimOptions.blockMs).toBe(2_000);
expect(captures[0].reclaimOptions.count).toBe(10);
```

→ Per-call reclaim options **确认** flow 到 subscribe. **不** 落 default.

---

## 3. invariant 验证 (user 回报字段)

| 字段 | 值 | 证据 |
|---|---|---|
| **commit sha (PR-C6 4c.2 主修)** | `5466d83` (已 push) | `git log --oneline -3` |
| **commit sha (followup docs)** | `add70c1` (已 push) | same |
| **commit sha (前置 followup)** | `1a24370` (已 push) | same |
| **修改文件** (5466d83 范围) | `apps/execution-service/src/index.ts`, `apps/execution-service/src/execution.test.ts`, `packages/event-store/src/event-store.test.ts` (+ docs `add70c1`) | `git show 5466d83 --stat` |
| **新增测试** | 4 cases TC-4c/d/e/f + execution-service wiring describe (2 tests) = **6 新测试** | `git show 5466d83` |
| **execution-service test** | 71 passed (0 failures) | `pnpm --filter @auto-trade/execution-service test` |
| **event-store test** | 56 passed (0 failures) | `pnpm --filter @auto-trade/event-store test` |
| **pnpm test 总** | 171 passed (0 failures) | `pnpm test` |
| **pnpm typecheck (4c.2 scope)** | execution-service + event-store **都 clean**; strategy-service 6 errors **全 in node_modules** (pre-existing, 与 4c.2 无关) | `pnpm typecheck` per package |
| **7989c5d 仍 in log** | ✅ **是** | `git log --all --oneline \| grep 7989c5d` |
| **a7bbb57 仍 in log** | ✅ **是** | `git log --all --oneline \| grep a7bbb57` |
| **未进入 4d** | ✅ **是** (无 4d commit) | `git log --all --oneline \| grep -i 4d` 仅返回 4c/4c.1/4c.2 自身 |
| **未启动 2h paper** | ✅ **是** (无 2h paper commit) | `git log --all --oneline \| grep -i "2h paper\|stage.*4d"` empty |
| **no real order / no testnet-live** | ✅ **是** (USE_MOCK=true, paper / mock 默认) | `apps/execution-service/src/index.ts: USE_MOCK = process.env.MOCK === "true" \|\| process.env.NODE_ENV === "test"` |

---

## 4. 重要说明 (Important Note)

### 4.1 关于 "提交新 commit" 的决策

⚠️ 这次**没有**提交新 commit. 原因:
1. 5466d83 + 1a24370 之前**已经**修了 (1a24370 第一次修, 5466d83 followup 加重测试)
2. add70c1 文档**已经** push to origin
3. 用户描述的"3 参形式"代码**不**存在 (execution-service **已经**用 5 参)
4. 用户描述的"per-call reclaimOptions 未生效"**不**存在 (TC-4d 已 assert `captures[0].reclaimOptions === EXECUTION_SUBSCRIBE_RECLAIM_OPTIONS` + 5 个字段值)
5. 无新代码改动可 commit

如**确需**新 commit, 请明确"要改什么" — 当前 4c.2 主修 + followup 已完备.

### 4.2 关于 strategy-service typecheck pre-existing 6 errors

⚠️ 这 6 个 errors **与 PR-C6 4c.2 无关**:
- 全部在 `node_modules` (`@vitest/expect` vs `@types/chai` duplicate identifier)
- pre-existing in 361b6d2 (parent commit of fa8e573 PR-C6.4c.2 起点)
- 5466d83 commit message 已明确说明
- execution-service + event-store (4c.2 直接影响) **都 clean**

如需修, 是**新 commit + 新审批** (out of 4c.2 scope), **不** 应混入 PR-C6 4c.2 followup. **不** 静默做.

### 4.3 关于 mode

✅ USE_MOCK = (process.env.MOCK === "true" || process.env.NODE_ENV === "test"). 当前默认 paper / mock. **不** 调用 Hyperliquid SDK, **不** 走真实订单, **不** 接 testnet-live.

---

## 5. 责任方与行动

| Action | 责任方 | 是否已做 |
|---|---|---|
| EventStore.subscribe 4-form 支持 | B (auto-trade) | ✅ 1a24370 |
| execution-service 5 参 + EXECUTION_SUBSCRIBE_RECLAIM_OPTIONS 集中化 | B | ✅ 5466d83 |
| 4 个新测试 case (TC-4c/d/e/f) | B | ✅ 5466d83 |
| execution-service wiring test (per-call object 引用相等) | B | ✅ 5466d83 |
| 中文 verification report | B | ✅ add70c1 |
| 4c.2 push to origin | B | ✅ |
| strategy-service typecheck 6 errors 修复 (out of 4c.2) | B (新审批) | ⏸️ 待审批 |
| 4d stage 启动 | B (新审批) | ⏸️ 待审批 |
| 2h paper 启动 | B (新审批) | ⏸️ 待审批 |

---

**报告完成. 不修改 PR-C6 4c.2 scope 任何代码. 不进入 4d. 不启动 2h paper. USE_MOCK=true (paper mode).**

报告版本: 2026-06-08. 复核员: 资深 Go 后端 / 交易系统 / 数据接口审计工程师.
复核对象: `auto-trade` 仓库 PR-C6 4c.2 @ `5466d83` (master branch).
