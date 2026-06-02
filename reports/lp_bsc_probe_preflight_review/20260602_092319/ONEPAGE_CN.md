# Probe Preflight Review — 单页总览

```text
stage                                = LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1
run_id                               = 20260602_092319
status                               = PASS

candidate_pool                       = 0x172fcd41e0913e95784454622d1c3724f546f849
candidate_pair                       = USDT/WBNB
candidate_fee_tier                   = 100 (0.01%)
candidate_notional_usd               = 10-20
candidate_hold_window                = 15m

fee_ready                            = true
quote_ready                          = true
tick_ready                           = true
cost_ready                           = true
realistic_positive_ev                = false  (best realistic = -$0.0156)
near_break_even                      = true   (best realistic above -$0.020)
actual_fee_ready                     = false  (probe is the only way to obtain)
token_id_available                   = false  (probe is the only way to obtain)

probe_preflight_review_complete      = true
dry_run_builder_allowed_next         = true
can_run_probe_now                    = false
manual_approval_required_for_probe   = true
edge_proven                          = no
tiny_canary_allowed                  = no
wallet_or_tx_touched                 = false

recommended_next_stage               = LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1
```

## 含义

- 数据层（quote / tick / cost / fee）全部 ready。
- realistic 情境下 EV 仍为负；本 probe **不是** +EV 押注。
- probe 的目的是通道验证 + tokenId + actual fee accrual 校准。
- 审查包完整：candidate review / risk limits / telemetry spec / dry-run builder spec / approval packet 全部就位。
- 下一步只能进入 `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`（构建 unsigned tx package 并用 eth_call 模拟），**不能**进入执行。

## 严格禁区（本轮已遵守）

```text
本轮未做：
  - 加载 wallet                ✓
  - 读取私钥                   ✓
  - 创建 signer                ✓
  - approve / mint / burn      ✓
  - increaseLiquidity / decreaseLiquidity ✓
  - collect / swap             ✓
  - 任何 tx submit             ✓
  - 启动 live / canary / paper ✓
  - 把 preflight 变成 execution ✓
  - 翻转 can_run_probe_now / tiny_canary_allowed ✓
```
