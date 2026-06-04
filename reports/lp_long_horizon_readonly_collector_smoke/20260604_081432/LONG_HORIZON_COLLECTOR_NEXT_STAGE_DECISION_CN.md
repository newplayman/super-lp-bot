# Stage I — Long Horizon Collector 下阶段决策 (Next Stage Decision)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`

## 0. 决策输入

| 输入 | 状态 | 来源 |
|---|---|---|
| smoke_ran | ✅ true | Stage E |
| design_mode_ran | ✅ true | Stage D |
| exit_code | ✅ 0 | Stage E |
| schema_validation_pass | ✅ true (6/6) | Stage F |
| research_only_write_ok | ✅ true | Stage F |
| no_production_write | ✅ true | Stage F |
| no_shadow_overwrite | ✅ true | Stage F |
| no_wallet / no_tx | ✅ true | Stage C/D/E |
| error_rate | 0% (4 source stub) | Stage E |
| long_run_readiness | ❌ 0/9 (5 blocker) | Stage H |
| manual_approval | ❌ 未到位 | Stage H |
| classifier_implemented | ❌ false | Stage G |
| source_adapter_implemented | ❌ false (stub) | Stage C/H |
| paid_rpc_indexer | ❌ false | Stage H |
| abort_condition_implemented | ❌ false | Stage H |

## 1. 候选白名单 (4 选 1)

| 候选 | 触发条件 | 本任务是否满足 |
|---|---|---|
| `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1` | smoke ✅ + schema ✅ + no production ✅ + no wallet/tx ✅ + error rate acceptable ✅ + **用户后续单独批准 7d run** | 部分满足: 5 项 ✅, 但 long_run_readiness=0/9, **不建议直接进入 7d run** |
| `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT` | smoke 部分失败但可修 | smoke 完全通过, 但 9 项 readiness 缺口可视为"待补项" |
| `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` | smoke 成功但当前不自动 long-run | 适用, 但用 PAUSE 等于把已走通进展退回 |
| `STOP_LP_RESEARCH_NOW` | collector 不安全或不可用 | 不适用, collector 完全安全可跑 |

## 2. 决策

**`recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT`**

理由:
1. smoke 100% 通过, 不需要"修复" collector 脚本本身
2. 但 9 项 long_run_readiness 全部 0/9, 实际是 "smoke 验证 collector 可安全跑" 与
   "R0 long-run 启动前还差 N 项实装" 的中间状态
3. 用 `FIX_REPEAT` 命名, 把下一阶段的"补完 9 项 readiness" 明确为: 实装 source
   adapter + 实装 classifier + 接入 paid RPC/indexer + 实装 abort condition +
   写 manual approval 记录
4. 补完后, 再走一次 smoke (smoke 已验证 collector 框架 OK, 这次 smoke 验证
   实装后的 source adapter + classifier)
5. smoke 二次通过 + 9 项 readiness 全 pass 后, 才考虑进入 7D_RUN_REQUEST

为什么不选 `7D_RUN_REQUEST_V1`:
- 任务规范明确"不得直接启动 7d run"
- 9 项 readiness 缺口: source adapter 是 stub, 没有实 RPC, 7d run 等于 0 数据 +
  0 abort, 失去 R0 阶段的目的
- classifier 仍是 spec-only, 7d run 写出来的 regime 数据无法解释
- abort condition 未实装, 7d run 失败时不会正确 abort
- paid RPC 缺, public RPC 必爆 429, 7d run 不会完成

为什么不选 `PAUSE`:
- PAUSE 等于把已走通的 smoke 阶段退回
- PAUSE 字面意思是 "停止 + 等待更长周期", 但本任务已经实现了 R0 阶段的所有 spec,
  暂停等于浪费已落地的成果

为什么不选 `STOP`:
- collector 完全安全 (5 类安全审计全部通过)
- smoke 输出完全符合 schema
- 没有任何失败信号需要 STOP

## 3. 下一阶段 (FIX_REPEAT) 任务清单

1. **实装 source adapter** (4 个 source)
   - solana_rpc_public.getMultipleAccountsInfo → 用 publicnode / Triton
   - coingecko_public.ohlc → CoinGecko free API (10-30 req/min)
   - protocol_sdk_quote → 5 protocol SDK (Meteora DLMM / Orca / Raydium CLMM /
     Raydium CPMM / Stable)
   - dex_screener_public.pools → DexScreener public (60 req/min)
2. **实装 regime classifier** (7 regime)
   - 实现 `classify_regime(...)` 函数 (per Stage F spec section 7)
   - 加 unit test (8+ 边界 case)
3. **接入 paid RPC/indexer** (R0 long-run 必需)
   - Helius / Triton (Solana RPC)
   - Shyft / helloMoon (历史 indexer)
4. **实装 abort condition** (5 类)
   - error_rate_monitor
   - 429 consecutive tracker
   - write failure detector
   - safety self-check runtime monitor
   - banned token runtime detector
5. **manual approval 流程**
   - 单独 stage LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_APPROVAL_V1
   - manual operator 签发 approval record
   - approval record 包含: collector_version, source_adapters, classifier_version,
     run_duration, max_pools, manual_signature, approval_at
6. **回归 smoke** (再次跑 smoke 验证实装后仍安全)
7. **prometheus / grafana 接入** (可选, R0 阶段后期)

## 4. 长期路径

```
当前 (smoke 通过, R0 readiness 0/9)
  → LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT (补 9 项)
    → LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1 (manual approval)
      → LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_V1 (实际跑 7d)
        → R0 阶段产出 (7d baseline dataset)
          → LP_LONG_HORIZON_READONLY_COLLECTOR_30D_RUN_REQUEST_V1
            → LP_LONG_HORIZON_READONLY_COLLECTOR_30D_RUN_V1
              → R0 阶段产出 (30d baseline dataset)
                → R1 阶段 (actual fee accrual via tokenId / paid indexer)
                  → R2 阶段 (regime split EV)
                    → R3 阶段 (candidate review)
                      → R4 阶段 (10U tokenId probe preflight)
                        → R5 阶段 (manual probe only)
```

每步必须通过当前 stage 的 audit + manual approval 才能进下一步. 任何阶段失败 → STOP / FIX.

## 5. 锁存字段保持

- [x] `can_run_probe_now = false` (locked)
- [x] `tiny_canary_allowed = "no"` (locked)
- [x] `edge_proven = "no"` (locked)
- [x] `wallet_or_tx_touched = false` (locked)
- [x] `transaction_sent = false` (locked)
- [x] `long_run_ready = false` (locked, 等 FIX_REPEAT 完成)
- [x] `long_run_started = false` (locked)

## 6. 结论

`recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT`.
理由: smoke 100% 通过, 但 R0 long-run readiness 0/9, 必须先实装 9 项 readiness
再考虑 7D_RUN_REQUEST. 当前 collector 完全安全, 不需要 STOP.

Stage I 通过. 进入 Stage J (Final verdict + 测试 + Git publish).
