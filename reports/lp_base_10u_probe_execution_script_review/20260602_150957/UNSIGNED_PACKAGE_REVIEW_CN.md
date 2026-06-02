# Unsigned Package Review

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- phase: F
- run_id: `20260602_150957`
- artifact: `reports/lp_base_10u_probe_execution_runtime/20260602_150957/unsigned_package.json` (3149 bytes)

## 1. 顶层 5 个 flag

| flag | 期望 | 观察 | 通过 |
|---|---|---|---|
| `unsigned_only` | true | **true** | ✓ |
| `no_signature` | true | **true** | ✓ |
| `no_send` | true | **true** | ✓ |
| `execution_not_authorized` | true | **true** | ✓ |
| `no_abi_bytes_unless_marked` | true | **true** | ✓ |

## 2. Candidate 与 frozen 一致性

| 字段 | unsigned_package | frozen (Phase C) | 通过 |
|---|---|---|---|
| chain | base | base | ✓ |
| chain_id | 8453 | 8453 | ✓ |
| pool | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | 同 | ✓ |
| pair | WETH/USDC | WETH/USDC | ✓ |
| fee_tier | 100 | 100 | ✓ |
| tick_lower | -200643 | -200643 | ✓ |
| tick_upper | -200243 | -200243 | ✓ |
| tick_spacing | 1 | 1 | ✓ |
| npm | 0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1 | 同 | ✓ |
| weth | 0x4200...0006 | 同 | ✓ |
| usdc | 0x8335...2913 | 同 | ✓ |

## 3. Wallet 字段

| 字段 | 值 | 备注 |
|---|---|---|
| `wallet.address` | 0xb05b...d835 | 与 frozen 一致 |
| `wallet.from` | 0xb05b...d835 | 与 frozen 一致 |
| `mint_params.from` | 0xb05b...d835 | 与 frozen 一致 |

> ⚠️ **修正上一轮 review 的措辞**：上一轮 `596b411` 报告说 `mint_params.recipient` 是一个 top-level 字段；这是**不对的**。recipient **没有**作为 top-level 字段；它**只**被编码在 `mint_params.data` 的第 10 个 word（offset 0x280）。data 本身是正确的（解码后是 0xb05b...d835），但描述不准。本轮 review 修正此点。

## 4. Notional 合理性

| 字段 | 值 | 备注 |
|---|---|---|
| usd | 10 | 与 frozen 一致 |
| amount0_desired_wei_WETH | 0 | V3 in-range math: a0 << a1 |
| amount1_desired_raw_USDC | 10,000,000 | 10 USDC |
| amount0_min_wei | 0 | WETH 端 sub-1-wei；amountMin 必须 0 避免 revert |
| amount1_min_raw | 9,950,000 | 9.95 USDC (0.5% slippage) |

**amount0_min=0 是必要的**（0 wei mint 时 amount0Min 必须 0）。

## 5. Deadline

```text
deadline = 4070908800  (2099-01-01T00:00:00Z)
deadline_is_placeholder = true
note: "deadline is a PLACEHOLDER; user overrides at execution time to now+3600"
```

**是 placeholder；future stage 必须在执行前改为 now+3600**。

## 6. Approve 校验

| 字段 | 值 | 备注 |
|---|---|---|
| spender | 0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1 (NPM) | 正确 |
| amount_raw | 10,000,000 | 10 USDC |
| amount_human | 10.000000 USDC | 匹配 |
| policy | "ApproveExact (never ApproveMax)" | 显式声明 |
| uint256_max | 115792089237316195423570985008687907853269984665640564039457584007913129639935 | 未用 |

**amount_raw = 10,000,000 << uint256_max → 确认是 ApproveExact**。

## 7. Mint call data 校验

```text
function: mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))
selector: 0x88316456
data: 0x88316456 + 0x20 + 11 fields (offset 0x20 + 11 * 32-byte words)
data_length: 778 hex chars (4 + 64 + 11*64 = 772; +6 from leading 0x + leading word padding)
```

11 字段 = token0, token1, fee, tickLower, tickUpper, amount0Desired, amount1Desired, amount0Min, amount1Min, **recipient** (offset 0x280), deadline。

**没有 r/s/v 签名**（signed tx 会多 65 bytes = 130 hex chars；这里没有）。

## 8. 隐私数据扫描

| 检查 | 结果 |
|---|---|
| 64-hex 字符串 (private key shape) | 0 found |
| 仅 40-hex 公开地址 + amount + selector | ✓ |
| 没有 keystore / mnemonic / seed | ✓ |

## 9. 总结

```text
all_top_level_flags_true         = true
candidate_matches_freeze         = true
wallet_bound                     = true
deadline_is_placeholder          = true
amounts_reasonable               = true
tick_range_matches_freeze        = true
approve_exact_only               = true
no_approvemax                    = true
no_signature_or_rsv              = true
no_private_data                  = true
```

Unsigned package **符合未来执行 stage 的要求**。

## 安全

```text
wallet_or_tx_touched = false
```
