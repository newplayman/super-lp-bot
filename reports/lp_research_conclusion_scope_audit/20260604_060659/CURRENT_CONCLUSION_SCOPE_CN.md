# Stage C — 当前结论适用范围 (Current Conclusion Scope)

- stage: `LP_RESEARCH_CONCLUSION_SCOPE_AUDIT_V1`
- run_id: `20260604_060659`

## 0. 写在最前

final freeze 的原文结论是:

> "在当前数据 / 当前资金规模 / 当前自动化模型下, retail 10-20U 2000 USD LP 在所有 5 个
>  Solana AMM protocols 都无法获得 realistic positive EV, STOP_LP_RESEARCH_NOW."

这条结论在 freeze 的字面范围内是 stable 的. 但用户提出一个合理质疑:

> "这不等于'所有 LP 长期没价值'。当前结论最多只能说明: 在当前短窗口数据、当前模型假设、
>  当前没有真实 LP tokenId / actual fee accrual 的前提下, 不允许自动进入 10/20U probe,
>  也不建议继续自动换协议扩展。"

本阶段就是为 final freeze **补一个口径适用范围** (scope of conclusion) addendum, 明确
"什么被证明了" / "什么没有被证明" / "什么不在结论范围".

## 1. 当前结论能证明什么 (CAN be inferred)

1. **当前自动 LP probe 不应启动** — `can_run_probe_now = false`, `tiny_canary_allowed = no`,
   `edge_proven = no` 必须保持. 这条在 5/5 reject 累计 28560 cells 下是 stable 的.
2. **当前 10/20U 小资金探针没有足够 EV 支撑** — 任何 IL > 0 scenario 全部负 EV, 任何
   notional 范围 (10 / 20 / 100 / 500 / 1000 / 2000 USD) 都验证过, 全部 negative.
3. **当前模型下 5 类 Solana AMM 都没有 realistic positive** — 5 个独立 connector 全部
   `positive_realistic = 0`, 全部 `positive_optimistic = 0`, 全部 `positive_conservative = 0`,
   best cell 全部出现在 `zero_il_lvr` 上限假设里. 这是结构性的, 不是 connector 失败.
4. **当前 connector 成果可保留** — 5 个 connector (Meteora DLMM / Orca Whirlpools / Raydium
   CLMM / Raydium CPMM / Meteora Stable + Orca LST) 全部 on-chain verified + SDK decode
   100% + connector path 通. 这是真实的工程成果, 不会因结论收口而失效.
5. **当前需要暂停自动扩协议** — 5 个 mainnet Solana AMM 全部覆盖完, 剩余 candidate 已知
   都不可行 (Lifinity pid unknown / Mercurial deprecated / Saber 已 rebrand / native Curve
   on Solana 不存在). 继续 auto-expand 信息价值低.

## 2. 当前结论**不能**证明什么 (CANNOT be inferred)

1. **不能证明所有 LP 永久没价值** — final freeze 文档本身就是 7 条件下可重开的. STOP
   是 research-only 决策, 不是市场判决.
2. **不能证明大资金专业 LP 没价值** — institutional LP 有 MEV 收入 / bribe 收入 / incentive
   farming 收入 / hedging 工具 / 更低 cost basis, 是与 retail 完全不同的市场. 5/5 reject
   仅是 retail 模型, 不是 institutional 模型.
3. **不能证明激励 LP / reward farming 没价值** — LM (liquidity mining) / IFO rewards /
   veRAMM bribe / Meteora farm 全部未纳入, 仅算 pool.fee_rate. 实际 LP real yield 通常 =
   fee + LM + bribe, 单算 fee 严重低估正 EV.
4. **不能证明 hedge / vault / JIT / active management 没价值** — 5 stages 全部 vanilla LP
   (持有 → 收 fee → IL). Delta-hedged / JIT / single-sided vault / covered-call + LP / MM
   rebate 这 5 类结构性策略都未跑.
5. **不能证明更长周期或不同 market regime 下仍负** — 数据窗口以 7d 持有为主, 30d / 90d /
   365d 不同 regime 都没覆盖. 短窗口负 EV 不等于长周期负 EV.
6. **不能证明真实 fee accrual 一定低于 proxy** — heuristic 0.5%/day turnover 仅是 10/20U
   quote 推导的 100× 上限, actual position-level fee accrual 缺失 (tokenId / collect fee
   数据无). 实际 fee 可能是 heuristic 的 1× 到 0.01×, 没数据不能断定.

## 3. 不在结论范围的领域 (OUT of scope)

| 领域 | 是否在当前结论范围 | 备注 |
|---|---|---|
| EVM V3 LP (Base / Arbitrum / BSC) | ❌ 不在 | 本 phase 未跑 |
| New protocol (Orca v2 / Lifinity) 上线 | ❌ 不在 | 还未存在, 留待未来观察 |
| Manual operator discretionary trade | ❌ 不在 | final freeze 不否定 manual decision |
| Hedging tool / LP monitoring tool | ❌ 不在 | connector / SDK 是 reusable |
| 长期 (>30d) 验证 | ❌ 不在 | 数据窗口仅 7d |
| 真实 fee accrual lineage | ❌ 不在 | tokenId / collect fee 数据无 |
| 大资金 / institutional | ❌ 不在 | 模型仅 retail |
| Incentive farming / LM / bribe | ❌ 不在 | 模型仅 pool.fee_rate |
| Delta-hedged / JIT / vault | ❌ 不在 | 模型仅 vanilla LP |
| 不同 market regime | ❌ 不在 | 数据仅 short-window + 当前 regime |

## 4. 字段锁定 (字段 → 含义)

```json
{
  "global_lp_rejected": false,
  "current_probe_allowed": false,
  "current_model_rejects_auto_probe": true,
  "conclusion_scope": "current_data_current_model_short_window",
  "long_term_lp_value_judged": false
}
```

字段含义 (for operator 复核):

- `global_lp_rejected = false`: 没有任何结论说"所有 LP 没价值", 这个字段明确 false 防止误读.
- `current_probe_allowed = false`: 当前自动 probe 不应启动, 这是 freeze 锁存项.
- `current_model_rejects_auto_probe = true`: 当前模型 / 当前数据 / 当前资金规模下, 5/5 AMM
  不支持自动 probe. 这是 freeze 核心.
- `conclusion_scope = current_data_current_model_short_window`: 结论的精确 scope. 任何超出
  这个 scope 的延伸解释 (例如"长期也没价值") 都不在结论范围.
- `long_term_lp_value_judged = false`: long-term 价值本任务没判定, 留待未来 7 条件 + 长期
  验证重开.

## 5. 与上一轮 scope_audit (053626) 的差异

| 维度 | 上一轮 053626 | 本轮 060659 | 差异原因 |
|---|---|---|---|
| global_lp_rejected | false | false | 保持 |
| conclusion_scope | current_data_current_model_short_window | current_data_current_model_short_window | 保持 |
| long_term_lp_value_judged | false | false | 保持 |
| 文档覆盖 | README + LPBOT_RESEARCH_STATUS_CN | README + LPBOT_RESEARCH_STATUS_CN + ARTIFACT_INDEX | 加 ARTIFACT_INDEX 一致性 |
| 测试 | 无 | 新增 `tests/test_lp_research_conclusion_scope_audit_v1.py` | 加 pytest 防回归 |
| 安全检查 | 文字 | 进程 `ps aux` 列表 + 源码 grep 双重检查 | 加进程级证据 |
| regime 偏差审计 | 缺失 | 新增 Stage E | 新加阶段 |
| 模型边界审计 | 文字提及 | 升级为 6 维度字段化 (Stage D JSON) | 新加阶段 |
| 长期重开计划 | 11 项 checklist | R0-R5 6 阶段 PHASE plan (Stage F) | 升级 |

差异符合"在不重跑任何 protocol 的前提下, 让结论口径更精确" 的本轮目标. 核心结论
(STOP_LP_RESEARCH_NOW 当前) 不变, 增加的是口径边界、regime 偏差、长期重开路径.
