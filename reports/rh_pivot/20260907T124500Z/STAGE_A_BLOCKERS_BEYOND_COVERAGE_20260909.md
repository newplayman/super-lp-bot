# Stage A 的两个阻塞项与覆盖率无关（2026-09-09 04:0x UTC）

`STAGE_A_GATES_EVIDENCE.json` 的取证（20 条检查、0 判定词）暴露两件事，
**都不会因为多跑时间而解决**。这正是不等到 90 小时才查的理由。

## 阻塞一：五张证据表全空

| 表 | 行数 |
|---|---:|
| `rh_contract_attestations` | **0** |
| `rh_assets` | **0** |
| `rh_pool_registry` | **0** |
| `rh_economic_evaluations` | **0** |
| `rh_gate_decisions` | **0** |

采集器源码中**一次都没有提到这五张表**（`grep -c` = 0），也没有任何脚本 insert 它们。

PRD §21.1 要求 Stage A「**身份和能力证据清楚**」。承载该证据的表里一条记录都没有，
所以**即使覆盖率在第 90 小时跨过 99%，Stage A 仍然毕不了业**。

这不是采集器的 bug——它从设计上就只写 `rh_market_states` / `rh_rpc_health` /
`rh_source_snapshots` 三张表。缺的是一个**把身份与能力证据落库的生产者**。
相关模块（`lp_rh_registry`、`lp_rh_capabilities`、`lp_rh_pool_probe`）都存在且有测试，
**只是没人把它们的产出写进库**。

## 阻塞二：`reference_age_secs` 被写死成 0，freshness 闸因此永不触发

```python
# scripts/lp_rh_collector_v1_readonly.py:233
"reference_age_secs": 0 if price_text else None,
```

对照实测：

| 库 | min | max | 不同取值 | 行数 |
|---|---:|---:|---:|---:|
| `scanner.db`（采集器写） | 0 | 0 | **1** | 5,254 |
| `premium.db`（录制器实测） | 1.5 | **89.3** | **1,596** | — |

**真实报价龄在 1.5 到 89.3 秒之间波动，采集器把它写成恒 0，
等于声称每一条报价都是完美新鲜的。**

后果是具体的：我在 `compute_conjuncts` 里写的 freshness 闸是

```python
elif float(age) > REFERENCE_MAX_AGE_SECS:   # 120
    fail("data_complete_and_fresh", ...)
```

**在这个采集器的数据上它永远不会触发。** 闸存在、测试通过、实际上是空的。

### 这比 `session="UNKNOWN"` 更坏

今晚已经抓到采集器把 `session` 硬编码成 `"UNKNOWN"`（4,361 行全同）。
两者同族，但方向相反：

| 字段 | 写死的值 | 下游行为 |
|---|---|---|
| `session` | `"UNKNOWN"` | **fail-closed**——未知时段不许开仓，保守 |
| `reference_age_secs` | `0` | **fail-open**——永远「新鲜」，闸形同不存在 |

**一个写死的保守值只是浪费机会；一个写死的乐观值会让闸门失效而无人察觉。**

## 顺带两条观察（不构成阻塞，但需记录）

1. **`rh_rpc_health` 只有一个 provider、一个 method**
   （`rpc.mainnet.chain.robinhood.com` / `pool_state_round`，5,091 行）。
   PRD §8.3 的多提供方证据不在这张表里——它在独立的
   `provider_health.db`（提供方可用性录制器），两处数据没有打通。
2. **预算口径三个数不一致**：`du` 与 `ls` 都给 6,029,312 字节，
   `budget_status()` 给 9,539,400。取证报告已指出源于查询时刻不同与 WAL 大小变化。
   占软预算 0.44%，不构成风险，但口径应统一。

## 处置

两个阻塞项各自需要一个包：

- **RH-02h**：把 registry / capabilities / pool_probe 的产出落进
  `rh_assets` / `rh_pool_registry` / `rh_contract_attestations`。
- **RH-02i**：采集器写真实 `reference_age_secs`（从 REST 的 `generatedAt`
  与取样时刻相减），并加一条**自证其罪测试**：
  断言该列的 `distinct` 值 > 1，防止再次退化成常量。

**在这两项落地前，Stage A 的毕业时间表不应按「第 90 小时」计划。**
