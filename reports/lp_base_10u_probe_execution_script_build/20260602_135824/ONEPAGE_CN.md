# Base 10U Probe Executor Build 总览

```text
stage                                       = LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1
run_id                                      = 20260602_135824
status                                      = PASS
previous_stage                              = LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1 (20260602_133221)
previous_status                             = PASS

candidate_chain                             = Base (chain_id 8453)
candidate_pool                              = 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38
candidate_pair                              = WETH/USDC
candidate_fee_tier                          = 100 (0.01%)
candidate_npm                               = 0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1

wallet                                      = 0xb05b2872ace4564ff247555b6f7b097d31f3d835
notional_usd                                = 10
hold_window                                 = 15m
tick range                                  = lower=-200643, upper=-200243 (medium)

executor script                             = scripts/lp_base_10u_probe_executor_v1.py
executor_script_built                       = true
executor_will_run_this_round                = false

builder components
  preflight_mode_built                       = true
  print_unsigned_mode_built                  = true
  approval_parser_built                      = true
  telemetry_writer_built                     = true
  stop_condition_engine_built                = true
  execution_stubs_disabled                   = true
  self_check_ran                             = true (11 cases all correct)

modes
  --mode preflight                          = read-only chain state; PASS at block 46810094
  --mode print-unsigned                     = structured JSON; unsigned_only/no_signature/no_send/execution_not_authorized
  --mode validate-approval                  = regex + whole-word dangerous-word check + cross-check; valid=True but executes_now=False
  --mode execute-disabled                   = STUB; exit_code=1; EXECUTION_DISABLED_IN_BUILD_STAGE
  --mode execute                            = REJECTED at argparse

safety locks (all intact)
  can_run_probe_now                         = false
  can_execute_with_current_script           = false
  execution_requires_fresh_user_approval    = true
  approval_phrase_effective_this_round      = false
  edge_proven                               = no
  actual_fee_ready                          = false
  token_id_available                        = false
  tiny_canary_allowed                       = no
  fabrication_blocked                       = true
  wallet_or_tx_touched                      = false

recommended_next_stage                      = LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1
                                              (review the executor script; still NOT execution)
```

## 一句话

构建了 `scripts/lp_base_10u_probe_executor_v1.py` skeleton（4 个 mode + 1 个 reject 路径 + 7 个 disabled execution stubs + 13 个 stop condition + 5 个 telemetry schema + 15 个 forbidden env var patterns + 27 个 dangerous word patterns）；11 个 self-check case 全部通过；**不构造 signer / 钱包 client / 加载任何私钥**；**不发任何交易**；**不写 production 表**。

## 严格禁区（本轮已遵守）

```text
× 未读私钥 / 助记词 / keystore
× 未创建 signer / wallet client
× 未发送 eth_sendTransaction / eth_sendRawTransaction
× 未 approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap
× 未启动 live / canary / paper
× 未自动 bridge / swap
× 未在 production lpbot 表上写入
× 未覆盖 shadow 原始表
× 未修改任何策略执行路径
× 未执行真实 probe
× 未把审批短语作为本轮可执行短语接受
× 未实现 --mode execute 的真实逻辑（必须保持 disabled stub）
```

## 偏离（deviation）声明

1. **DANGEROUS_WORD_PATTERNS 起初是 substring 匹配**；这导致 canonical 短语（含子串 "EXEC"）被错误拒绝。修复为 whole-word regex via `re.search(pat, phrase)`。9 个 validate-approval 测试 case 全部产生正确 accept/reject 结果。
2. **env-var safety check 起初过宽**（`^.*_API_KEY$`）；会拒绝 `ANTHROPIC_API_KEY` 等合法 AI tooling env。修复为只 block crypto / wallet / secret-store env names（PRIVATE_KEY, MNEMONIC, KEYSTORE, WALLET_KEY, SIGNER_KEY, *_DATABASE_URL, *_POSTGRES_DSN 等）。

## 操作员后续抉择

```text
路径 A（推荐）：进入 LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1
              未来阶段会 review executor script（仍不执行）
              review 通过后仍需操作员在执行时点重新键入审批短语才会真正提交

路径 B：修改 build
              LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_FIX_REPEAT
              适合想换 stop conditions / telemetry schema / approval phrase regex 的人

路径 C：暂停 LP 研究
              recommended_next_stage = STOP_LP_RESEARCH_NOW
              所有 artifacts 完整保留可日后复用
```

## 安全门禁（本轮守住）

```text
wallet_or_tx_touched         = false
can_run_probe_now            = false
tiny_canary_allowed          = no
edge_proven                  = no
fabrication_blocked          = true
approval_phrase_effective_this_round = false
executor_built_this_round    = true  (skeleton; not executable)
executor_will_run_this_round = false
```
