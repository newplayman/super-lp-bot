# 单页总览（REJECTED）

```text
stage                                       = LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1
run_id                                      = 20260602_100951
status                                      = FAIL
fail_reason                                 = approval_phrase_rejected_at_phase_A

wallet_address_bound                        = false   (because phrase was rejected)
wallet_loaded                               = false
signer_created                              = false
transaction_sent                            = false
selected_notional_usd                       = null    (not extracted from rejected phrase)

candidate_pool                              = 0x172fcd41e0913e95784454622d1c3724f546f849
candidate_pair                              = USDT/WBNB
candidate_fee_tier                          = 100

balance_sufficient                          = false   (not checked — phase D skipped)
approval_needed_usdt                        = null    (not checked — phase D skipped)
approval_needed_wbnb                        = null    (not checked — phase D skipped)
gas_estimate_success                        = false   (not attempted — phase G skipped)
market_safe_for_dry_run                     = false   (not assessed — phase E skipped)
wallet_bound_unsigned_package_built         = false   (phase H skipped)

can_run_probe_now                           = false
can_prepare_probe_execution_spec_next       = false
manual_approval_required_for_execution      = true
edge_proven                                 = no
actual_fee_ready                            = false
token_id_available                          = false
tiny_canary_allowed                         = no
wallet_or_tx_touched                        = false

recommended_next_stage                      = LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_FIX_REPEAT
```

## 为什么 FAIL（不是 PASS / WARN）

收到的审批短语是**模板字面值**，不是真实的 wallet 地址和 notional：

```text
APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=USER_PROVIDED_WALLET_ADDRESS notional=USER_SELECTED_NOTIONAL
```

上一阶段冻结的校验正则要求 `wallet=0x<40 hex chars>` + `notional=(10|20)`。
两个字段都失败 ⇒ Phase A 立即 STOP，按 brief 的硬规定不进入任何链上读取。

## 严格未做的事

```text
× 未调用 eth_getBalance / balanceOf / allowance / eth_estimateGas
× 未加载 wallet / signer / 私钥 / 助记词
× 未 approve / mint / decrease / collect / burn / swap
× 未发送任何 tx
× 未启动 live / canary / paper
× 未修改任何链上状态或 production 表
× 未触发下一阶段
```

## 重新发送的格式

```text
APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x<您的40位十六进制钱包地址> notional=<10 或 20>
```

只发**公开地址**。**不**发私钥/助记词。

详细的字段诊断与示例见 `APPROVAL_PHRASE_REJECTED_CN.md`。
