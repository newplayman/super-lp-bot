# LP Research Conclusion Scope Audit — One-Pager

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_060659`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (口径修正通过, 不改变 STOP_LP_RESEARCH_NOW 结论)

## 0. 一句话

final freeze 结论是 **stable** 的 (`STOP_LP_RESEARCH_NOW`), 但**口径**需要精确化:
当前结论**仅在 current_data + current_model + short_window + downtrend regime + retail
10/20U 2000 USD 范围**内成立, **不等于 global LP rejected**, **不等于长期 LP 没价值**.

## 1. 核心字段

| 字段 | 值 | 含义 |
|---|---|---|
| `current_probe_allowed` | `false` | 当前自动 probe 不允许 (locked) |
| `global_lp_rejected` | `false` | **不**代表所有 LP 永久没价值 |
| `current_model_rejects_auto_probe` | `true` | 当前模型不支持继续自动 probe |
| `conclusion_scope` | `current_data_current_model_short_window` | 结论的精确范围 |
| `long_term_lp_value_judged` | `false` | 长期价值本任务没判定 |
| `needs_longer_horizon_validation` | `true` | 需要更长周期数据 |
| `needs_actual_fee_accrual` | `true` | 需要真实 position tokenId |
| `needs_market_regime_split` | `true` | 需要按 regime 切分 |
| `market_downtrend_bias_acknowledged` | `true` | 短窗口 downtrend 已知让结论偏负 |
| `can_run_probe_now` | `false` | 锁存项 |
| `tiny_canary_allowed` | `no` | 锁存项 |
| `edge_proven` | `no` | 锁存项 |
| `docs_updated` | `true` | docs/LPBOT_RESEARCH_STATUS_CN.md + README.md |

## 2. 当前结论能证明什么

1. 自动 LP probe 不应启动 (locked)
2. retail 10/20U 2000 USD 没足够 EV 支撑 (locked)
3. 5 类 Solana AMM 都没 realistic positive (locked)
4. 5 个 connector 成果可保留 (locked)
5. 自动扩协议应暂停 (locked)

## 3. 当前结论**不能**证明什么

1. 所有 LP 永久没价值
2. 大资金 / institutional LP 没价值
3. 激励 LP / reward farming 没价值
4. hedge / vault / JIT / active management 没价值
5. 长周期或不同 regime 下仍负
6. 真实 fee accrual 一定低于 proxy

## 4. 模型边界 (6 维度)

| 维度 | 影响 | 缺口 |
|---|---|---|
| data_window | HIGH | 90d+ / 跨 regime 缺失 |
| fee_data | HIGH | 实际 position-level / dynamic fee 激活率 |
| il_lvr | HIGH | 真实 LP 回放 / regime 切分 |
| pool_selection | HIGH | 激励 / vault / managed LP / bribe |
| cost_data | MEDIUM | 真实 cost 拆分 / batch tx |
| capital_scale | MEDIUM | $10K-$1M 未跑 |

## 5. 市场 regime 偏差

- 短窗口 downtrend 已知让结论偏负 (mechanism: IL/LVR proxy 偏高 1.5-2×)
- 自动 probe 任何 regime 都禁止, locked 不依赖 regime
- 长期判断需要 7 regime 分类 + 加权 EV (R2 阶段任务)

## 6. 重开 6 阶段 (R0-R5)

```
R0 长期 read-only 数据基线 (7/14/30/90/180/365d)
  → R1 真实 fee accrual 设计 (tokenId / collect fee / dynamic fee)
    → R2 市场 regime split (7 regime + weighted EV)
      → R3 重开候选池 review (激励 / vault / managed / bribe)
        → R4 10U tokenId probe preflight (单池 / 单假设)
          → R5 手动 probe only (manual approval)
            → can_run_probe_now = true (有条件) → canary / probe / live
```

任何阶段失败 → STOP, 不允许跳过. 重开 ≠ 直接实盘.

## 7. 7 重开条件 → R 阶段映射

| 7 条件 | 对应阶段 |
|---|---|
| 真实 fee accrual | R1 |
| 协议激励 / bribe | R3 |
| 稳定高 fee velocity 池 | R3 |
| 更低成本链路 | R4 + R5 |
| paid RPC / indexer | R0 |
| 用户具体池 / 资金 / 策略 | R1 + R3 |
| 非普通 LP 结构性策略 | R3 |

## 8. 安全状态

- 5/5 protocol verdict: transaction_sent = false, wallet_or_tx_touched = false,
  solana_wallet_or_keypair_touched = false
- final freeze: send_hard_disable_still_active = true
- 本任务: 不读 .env / .runtime.shadow.env / *.keystore, 不创建 signer, 不发 tx,
  不动 config.live.toml / config.canary.toml / migrations / cmd/lpbot 入口

## 9. 后续读取入口

- `docs/LPBOT_RESEARCH_STATUS_CN.md` (顶层状态)
- `reports/lp_research_conclusion_scope_audit/20260604_060659/FINAL_VERDICT.json` (本阶段 verdict)
- `reports/lp_research_conclusion_scope_audit/20260604_060659/CURRENT_CONCLUSION_SCOPE_CN.md` (适用范围)
- `reports/lp_research_conclusion_scope_audit/20260604_060659/LONG_HORIZON_REOPEN_PLAN_CN.md` (R0-R5 计划)
- `reports/lp_research_final_freeze/20260604_051254/FINAL_VERDICT.json` (上阶段 freeze)
- `reports/lp_research_final_freeze/20260604_051254/LP_RESEARCH_REOPEN_CONDITIONS_CN.md` (7 条件)

## 10. 警示

- 当前不得运行 live / canary / paper。
- 当前不得把任何研究结论转成 micro-live。
- 当前只允许阅读历史报告、补文档、做工程清理。
- 任何重开 LP research 必须先读 R0-R5 6 阶段计划, 任一阶段失败 → STOP, 不允许跳过。
- `internal/core/execution/hard-disable` 仍 active, 不释放。
