# Dry-run Builder — 单页总览

```text
stage                                       = LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1
run_id                                      = 20260602_094727
status                                      = PASS

candidate_pool                              = 0x172fcd41e0913e95784454622d1c3724f546f849
candidate_pair                              = USDT/WBNB
candidate_fee_tier                          = 100 (0.01%)
preferred_notional_usd                      = 10
max_notional_usd                            = 20
initial_hold_window                         = 15m

pool_state_refreshed                        = true
tick_range_proposed                         = true   (medium ±1.0%, tickLower=-65280 tickUpper=-65080)
token_amounts_calculated                    = true   (10U: 4.972 USDT + 0.007428 WBNB; 20U: 9.943 USDT + 0.014856 WBNB)
unsigned_tx_package_built                   = true   (structured JSON only; recipient/deadline placeholders)
gas_estimate_feasibility_ready              = true   (static gas units; needs wallet for real estimate)
manual_approval_checkpoint_ready            = true

wallet_address_required_next                = true
wallet_loaded                               = false
signer_created                              = false
transaction_sent                            = false

can_run_probe_now                           = false
can_run_dry_run_with_wallet_address_next    = true
manual_approval_required                    = true
edge_proven                                 = no
actual_fee_ready                            = false
token_id_available                          = false
tiny_canary_allowed                         = no
wallet_or_tx_touched                        = false

recommended_next_stage                      = LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1
```

## 含义

下一阶段 `LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1` 仍是**只读**：
仅在拿到用户提供的 wallet 地址后做 allowance / balance / `eth_estimateGas` 一次精细化。
**仍然不执行 probe，不签名，不发送任何交易。**

执行 probe 是更后面的、单独 spec、单独审批的阶段。

## 严格禁区（本轮已遵守）

```text
本轮未做：
  - 加载 wallet                ✓
  - 读取私钥                   ✓
  - 创建 signer                ✓
  - eth_sendTransaction        ✓
  - eth_sendRawTransaction     ✓
  - approve / mint / burn      ✓
  - increaseLiquidity / decreaseLiquidity / collect / swap   ✓
  - 任何 tx submit             ✓
  - 启动 live / canary / paper ✓
  - 写 production positions    ✓
  - 覆盖 shadow 表             ✓
  - 自动触发下一阶段           ✓
  - 翻转 can_run_probe_now / tiny_canary_allowed   ✓
```

## 下阶段如未来获批

1. 操作员键入唯一允许的短语 `APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x<...> notional=<10|20>`
2. 该短语只解锁"用 wallet 地址做 allowance/balance/estimateGas 只读 dry run"
3. 不解锁签名 / 发送 / 任何写操作
