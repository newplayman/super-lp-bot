# P1 Test Suite Stabilization — RPC Flake Fix Report

- **stage**: `LP_BOT_ENGINEERING_P1_TEST_SUITE_STABILIZATION_V1`
- **run_id**: `20260609_053000`
- **base_commit**: `63fd5aa`
- **branch**: `feat/supabase-postgres-deployment`
- **workdir**: `/opt/lpbot/lp-bot-v3`

## 1. 问题陈述

`go test ./...` 当前 (base 63fd5aa) 报 FAIL，因为 `internal/adapters/rpc/TestRoundRobinProvider_Endpoint` 是 flake：

```
$ go test ./internal/adapters/rpc/ -run TestRoundRobinProvider_Endpoint -v
=== RUN   TestRoundRobinProvider_Endpoint
2026/06/09 07:23:20 [rpc:test-chain] initial rpc order: [https://endpoint2.example.com https://endpoint1.example.com]
    roundrobin_test.go:45: expected first endpoint, got https://endpoint2.example.com
--- FAIL: TestRoundRobinProvider_Endpoint (0.03s)
```

flake 表现：`initial rpc order` 的两个 endpoint 顺序每次 run 不一致。测试断言 `[endpoint1, endpoint2]` 顺序，但有时返回 `[endpoint2, endpoint1]`。

## 2. Root Cause 分析

`internal/adapters/rpc/roundrobin.go` 的 `rankEndpointsDetailed` 函数 (第 1003-1052 行)：

```go
func rankEndpointsDetailed(ctx context.Context, endpoints []string, httpClient *http.Client, timeout time.Duration) ([]endpointProbeResult, string) {
    if len(endpoints) <= 1 {
        // ...
        return results, ""
    }

    results := make(chan endpointProbeResult, len(endpoints))
    var wg sync.WaitGroup
    wg.Add(len(endpoints))

    for idx, endpoint := range endpoints {
        go func(i int, endpoint string) {
            defer wg.Done()
            latency, err := probeEndpointLatency(ctx, endpoint, httpClient, timeout)
            // ...
            results <- endpointProbeResult{
                endpoint: endpoint,
                latency:  latency,
                index:    i,
                ok:       err == nil,
                errMsg:   errMsg,
            }
        }(idx, endpoint)
    }

    wg.Wait()
    close(results)

    probeResults := make([]endpointProbeResult, 0, len(endpoints))
    allFailed := true
    for r := range results {              // <-- 非 deterministic 顺序
        if r.ok {
            allFailed = false
        }
        probeResults = append(probeResults, r)
    }

    if allFailed {
        // 返回 probeResults, 不排序
        return probeResults, strings.Join(failSummary, ", ")
    }
    // ...
}
```

`for r := range results` 从 channel 接收，**channel 接收顺序由 goroutine 完成时间决定，不是 input index 决定**。当所有 endpoint 都失败时 (`allFailed=true`)，不排序就返回，**所以顺序非 deterministic**。

测试 scenario：test 给 `[endpoint1.example.com, endpoint2.example.com]`，两个都失败 DNS lookup，命中 `allFailed` 分支。返回顺序由两个 probe goroutine 哪个先完成决定 → 50% 概率返回 `[endpoint1, endpoint2]`，50% 概率返回 `[endpoint2, endpoint1]`。

**关键**: `probeResults[i].index` 字段**存在但没用上** — 修复时就是用这个。

## 3. 修复方案

修改 `rankEndpointsDetailed` 的 `allFailed` 分支，按 input index 排序后再返回：

```go
if allFailed {
    // When all endpoints fail, preserve the caller's input order. The
    // channel-driven collection above is non-deterministic across
    // goroutine scheduling; we re-sort by the original index so the
    // first endpoint in the config is the first one tried, matching
    // the documented "primary endpoint" semantics.
    sort.SliceStable(probeResults, func(i, j int) bool {
        return probeResults[i].index < probeResults[j].index
    })
    failSummary := make([]string, 0, len(probeResults))
    for _, result := range probeResults {
        failSummary = append(failSummary, fmt.Sprintf("%s:FAIL(%s)", result.endpoint, result.errMsg))
    }
    return probeResults, strings.Join(failSummary, ", ")
}
```

**Diff 范围**: 6 行 (含注释 + sort 调用 + 闭包)。

**未删任何真实断言**。
**未扩大测试范围到真实 RPC 网络** (仍然使用 test.example.com 触发 DNS 失败)。
**未修改 input 参数**。

## 4. 验证

修复后：

```
$ go test ./internal/adapters/rpc/ -run TestRoundRobinProvider_Endpoint -v
=== RUN   TestRoundRobinProvider_Endpoint
2026/06/09 07:24:09 [rpc:test-chain] initial rpc order: [https://endpoint1.example.com https://endpoint2.example.com]
2026/06/09 07:24:09 [rpc:test-chain] switched rpc endpoint: https://endpoint1.example.com -> https://endpoint2.example.com
--- PASS: TestRoundRobinProvider_Endpoint (0.04s)
PASS
```

`initial rpc order` 现在 deterministic 是 `[endpoint1, endpoint2]`，after `nextEndpoint()` 切换到 `[endpoint2, ...]`。测试的两个断言都通过。

## 5. 稳定性测试 (新增 8 个, 防止 regression)

文件: `internal/adapters/rpc/roundrobin_stability_test.go`

| Test | 覆盖 |
|---|---|
| `TestRoundRobinProvider_InitialOrderStableAcrossRuns` | 20 runs, 检 order drift |
| `TestRoundRobinProvider_InitialOrderPreservesInputIndex` | 5 input orderings, 验证 input order preservation |
| `TestRoundRobinProvider_InitialOrderNotSortedAlphabetically` | 防御性: 确认 NOT alphabetic sort |
| `TestRoundRobinProvider_NextEndpointDeterministic` | 3 sizes × 2 rotations = 6 cycles |
| `TestRoundRobinProvider_RepeatedCallsNoMapIterationDependency` | 50 runs, 锁定 map-iter 依赖 |
| `TestRoundRobinProvider_EndpointHostExtractorDoesNotMutateInput` | input slice 不可变 |
| `TestRoundRobinProvider_SingleEndpointStableForRepeatedCalls` | edge case: 1 endpoint |
| `TestRoundRobinProvider_EndpointStringPreserved` | endpoint 字符串 identity 检查 |

所有 8 个新 test PASS。

## 6. make test-race 入口

新增 Makefile target:

```makefile
test-race:
    $(GO) test -race -count=1 ./internal/adapters/store/postgres ./internal/adapters/rpc
```

覆盖两个最高 contention 的 adapter package (postgres adapter 现在写真 Postgres, rpc adapter 有 health loop + probe latency goroutine)。**全仓 race 故意不做** (iteration 太慢) — 在 P1-EXPAND 后续 stage 扩展。

`make test-race` PASS: postgres 17.9s + rpc 9.6s, 0 race detected.

## 7. 全部 6 个必跑命令结果

| Command | Result | Duration |
|---|---|---|
| `go test ./internal/adapters/rpc` | PASS | 5.7s |
| `go test ./internal/adapters/store/postgres/` | PASS | ~20s |
| `go test ./...` | **PASS** (0 FAIL across 40 packages) | ~30s |
| `make test-race` | PASS | ~28s |
| `make build-shadow` | PASS | 40 MB |
| `make build-dryrun` | PASS | 40 MB |
| `make build-live` | PASS | 41 MB |

**`go test ./... = PASS`** — base 63fd5aa 上的 `FAIL_WITH_KNOWN_PREEXISTING_FLAKE` 解除.

## 8. 严禁 (维持)

- ❌ 不修改 strategy / live / execution / trading path
- ❌ 不启动 R1 / R2 / canary / live / paper / probe
- ❌ 不连 wallet / signer / keypair
- ❌ 不发 tx / mint / add liquidity / remove / approve / collect / swap / bridge
- ❌ 不接 paid RPC
- ❌ 不写真实 secret
- ❌ 不 merge main / dev
- ❌ 不修改 R1 reports / data dirs
- ❌ 不重跑 long horizon collector
- ❌ 不修改 LP strategy 研究状态
- ❌ LPBOT_CONFIRM_LIVE 永不设 YES

## 9. 一句话

RPC flake 根因是 `rankEndpointsDetailed` 在 allFailed 分支按 channel 顺序返回 (非 deterministic), 修复: 6 行 diff, 按 input index 排序. 新增 8 个稳定性 test, 新增 make test-race 入口, 全部 6 个必跑命令 PASS. `go test ./...` 从 FAIL_WITH_KNOWN_PREEXISTING_FLAKE 升级为 PASS. status=PASS.
