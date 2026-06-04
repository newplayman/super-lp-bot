# Stage H — Collector Health / Failure Mode

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`

## 0. 目的

评审 collector 在 long-run 阶段的 health / failure mode 准备度. smoke 阶段
(本任务) source adapter 全部 stub, 不会触发任何真实 RPC / SDK / HTTP, 所以
"health" 在 smoke 阶段是 trivial (永远 ok). 本节重点是 **R0 阶段 long-run
启动前必须准备就绪的 failure mode 策略**.

## 1. smoke 阶段 health 总结

| 维度 | 状态 |
|---|---|
| exit_code | 0 |
| source adapter errors | 0 (4 全部 stub) |
| source adapter rate_limited | 0 (4 全部 stub) |
| source adapter ok | 0 (4 全部 stub, placeholder only) |
| write errors | 0 (7 个文件全部成功) |
| partial data | false (no partial) |
| source_aborted | false |

smoke 阶段无真实网络, 无 timeout, 无 429, 无 SDK error. 这是预期.

## 2. long-run 阶段 failure mode 准备度

### 2.1 RPC errors (per Stage D architecture spec)

| 错误类型 | 处理策略 | 准备状态 |
|---|---|---|
| solana_rpc_public timeout (> 5s) | retry 3 次, exponential 1s/2s/4s | ✅ spec defined, R0 long-run 必须实装 |
| solana_rpc_public 429 (rate limit) | retry with backoff, 5 连发 abort | ✅ spec defined |
| solana_rpc_public 5xx | retry 3 次, then skip pool | ✅ spec defined |
| solana_rpc_public 4xx (non-429) | skip pool, log error, continue | ✅ spec defined |
| getMultipleAccountsInfo 部分返回 null | 记 error_code, 继续下一个 notional | ✅ spec defined |

### 2.2 API errors (per Stage D architecture spec)

| 错误类型 | 处理策略 | 准备状态 |
|---|---|---|
| coingecko_public 4xx (e.g. 429) | retry 3 次, backoff 60s/120s/240s | ✅ spec defined |
| coingecko_public 5xx | retry 3 次, then skip | ✅ spec defined |
| coingecko_public timeout | retry 3 次 | ✅ spec defined |
| dex_screener_public 429 | retry 3 次, backoff 30s/60s/120s | ✅ spec defined |
| dex_screener_public 4xx (non-429) | skip pool, log | ✅ spec defined |

### 2.3 SDK errors (per Stage D architecture spec)

| 错误类型 | 处理策略 | 准备状态 |
|---|---|---|
| protocol_sdk_quote tick_array_not_initialized | 记 `quote_success=false`, 继续下一个 notional | ✅ spec defined |
| protocol_sdk_quote liquidity_too_low | 记 `quote_success=false`, 继续 | ✅ spec defined |
| protocol_sdk_quote pool_not_found | 记 `quote_success=false`, skip pool | ✅ spec defined |

### 2.4 429 handling

| 源 | 策略 | 准备状态 |
|---|---|---|
| solana_rpc_public | retry 3x with backoff, 5 consecutive 429 → abort source | ✅ spec defined |
| coingecko_public | retry 3x with 60-240s backoff | ✅ spec defined |
| dex_screener_public | retry 3x with 30-120s backoff | ✅ spec defined |
| protocol_sdk_quote | 跟随 solana_rpc_public | ✅ spec defined |

abort condition (per final freeze long_run_safety_gates): **5 consecutive 429 → abort source**, no retry.

### 2.5 timeout handling

| 源 | timeout | 准备状态 |
|---|---|---|
| solana_rpc_public | 5s per call | ✅ spec defined |
| coingecko_public | 默认 (10-30s) | ✅ spec defined |
| dex_screener_public | 默认 (10-30s) | ✅ spec defined |
| protocol_sdk_quote | 跟随 solana_rpc_public | ✅ spec defined |

retry 3x with exponential backoff, 然后 skip.

### 2.6 missing data handling

| 场景 | 处理 | 准备状态 |
|---|---|---|
| OHLC 7d 缺失 (CoinGecko 4xx) | 跳过当日, regime = `unknown`, 不写 record | ✅ spec defined |
| pool reserve 缺失 (on-chain 返回 null) | 记 `error_code`, 继续下一个 pool | ✅ spec defined |
| volume 30d 缺失 (DexScreener rate limited) | skip, 继续 | ✅ spec defined |
| LM events 缺失 (协议 farm program log 不可达) | 记 `incentive_active=false`, 继续 | ✅ spec defined |

regime `unknown` 是 R0 阶段新增 placeholder, R1 阶段才实装 (per Stage F spec section 5).

### 2.7 partial data handling

| 场景 | 处理 | 准备状态 |
|---|---|---|
| 1 个 pool 部分 quote 失败 | 记 `quote_success=false`, 继续下一个 notional | ✅ spec defined |
| 1 个 source adapter 中途 abort | smoke_summary.json 标记 `source_aborted=true`, 继续下一个 source | ✅ spec defined |
| write 失败 (磁盘满) | 立即 abort, 不重试 | ✅ spec defined |
| 1 个 pool 完全失败 | 记 error, 继续下一个 pool | ✅ spec defined |

**R0 long-run 的 partial 不阻断**: 只要 error rate < 20% 继续; 达到 20% 立即 abort.

### 2.8 abort condition readiness

per final freeze long_run_safety_gates:
- [x] abort on error rate > 20% (smoke_summary.json 应该 monitor)
- [x] abort on 5 consecutive 429 from any source
- [x] abort on write failure (immediate)
- [x] abort on safety self-check fail (immediate)
- [x] abort on any banned token detected at runtime (immediate)

R0 long-run 必须实装以上 5 类 abort condition, 在 `smoke_summary.json` (或
`run_summary.json` for long-run) 中 explicit log "abort reason" + 触发时间.

### 2.9 long-run readiness

R0 阶段 long-run 启动前必须完成:

- [x] source adapter 实装 (4 个 stub → real) — 需独立 stage + audit
- [x] classifier 7 regime 实装 (spec → code) — 需独立 stage + audit
- [x] rate limit / retry / backoff 实装 (per Stage D spec)
- [x] abort condition 实装 (per long_run_safety_gates)
- [x] sqlite 启用 (R0 long-run 数据量 100MB+, jsonl 不够)
- [x] paid RPC / indexer 接入 (R0 long-run 7-30d 必需, public RPC rate limit 阻塞)
- [x] error rate monitor (smoke_summary 应该 log 到 prometheus)
- [x] cron / systemd 配置 (R0 long-run 必须 background process)
- [x] manual approval 记录 (单独 stage 文档)

**当前 long-run readiness = false** (9 项中只有 0 项实装).

### 2.10 current blocker

阻塞 R0 long-run 启动的关键项:
1. **source adapter stub** — 脚本 stub 4 个 source, 实装需要 audit + manual approval
2. **classifier spec-only** — 7 regime 分类器仅 spec, 实装需要 audit
3. **paid RPC 缺** — public RPC 7d run 必爆 429
4. **abort condition 未实装** — 需独立 stage
5. **manual approval 未到位** — 当前 recommended_next_stage 是
   `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1`, 必须独立 stage 才能跑

## 3. 健康监控 metrics (R0 long-run 推荐)

R0 long-run 启动时, 应实时记录:
- `collector_pool_snapshot_total` (counter, 累计 pool_snapshots record)
- `collector_quote_success_total` (counter, quote_success=true)
- `collector_quote_failure_total` (counter, quote_success=false)
- `collector_source_error_total{source=...}` (counter, per source)
- `collector_source_429_total{source=...}` (counter, per source)
- `collector_source_429_consecutive{source=...}` (gauge, max consecutive 429)
- `collector_run_duration_seconds` (gauge)
- `collector_abort_total{reason=...}` (counter, per abort reason)
- `collector_error_rate_pct` (gauge, error rate in last 1h)
- `collector_can_run_probe_now` (gauge, always 0)
- `collector_send_hard_disable_active` (gauge, always 1)

R0 long-run 启动前**无需** prometheus / grafana 配置, 但应在 audit doc 中列
出 metrics 列表, R0 阶段实装时再 enable.

## 4. 长期 run 假设风险

| 风险 | 触发条件 | 影响 | 缓解 |
|---|---|---|---|
| public RPC rate limit | 7d run 每 5min 1 sample, 池数 100+ | 429 阻塞 | paid RPC (Helius/Triton) |
| 数据漂移 | pool_address 改变 (池 close / 迁移) | 数据无效 | 加 source = "abandoned" tag |
| regime classifier 偏差 | OHLC 数据源不可信 (CoinGecko 限流) | regime 错分类 | 多数据源交叉验证 |
| IL/LVR proxy 误差 | heuristic vs actual 差距大 | EV 估计错误 | R1 阶段用 actual fee |
| fee_velocity 估算偏差 | quote fee_rate ≠ actual fee | fee_velocity 错 | R1 actual fee |
| 磁盘满 | sqlite 100MB+ | write 失败 | 12-month archive + cold storage |
| 脚本 bug | 任何未预期 case | 数据 corruption | smoke + 7d 短 run 验证 + 30d 升 run 验证 |

## 5. 结论

- smoke 阶段 health 100% OK (4 source stub, 0 error, 0 429, 0 partial)
- long-run failure mode 策略在 spec 中**完整定义** (4 source 错误 + 3 SDK 错误 +
  4 429 策略 + 5 timeout 策略 + 4 missing data 策略 + 4 partial data 策略 +
  5 abort condition)
- long-run readiness 当前 0/9, 需独立 stage 实装
- current blocker: source adapter stub + classifier spec-only + paid RPC 缺 +
  abort condition 未实装 + manual approval 未到位
- 监控 metrics 列表给出, R0 long-run 启动时 enable

Stage H 通过. 进入 Stage I (下阶段决策).
