# ApproveExact Builder 实现

- stage: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`
- phase: E
- run_id: `20260602_163036`

## 实现

`scripts/lp_base_10u_probe_executor_v2.py` 中 3 个函数：

| 函数 | 签名 | 描述 |
|---|---|---|
| `build_approve_exact_usdc_tx` | `(wallet, amount_raw) -> dict` | ERC20.approve(USDC, NPM, amount) |
| `build_revoke_usdc_tx` | `(wallet) -> dict` | ERC20.approve(USDC, NPM, 0) |
| `build_revoke_weth_tx` | `(wallet) -> dict` | ERC20.approve(WETH, NPM, 0) |

## 校验

- `build_approve_exact_usdc_tx`:
  - `amount_raw > 0`（raise ValueError 否则）
  - `amount_raw < UINT256_MAX // 2`（raise ValueError 否则；**禁止 ApproveMax**）
- `build_revoke_usdc_tx` / `build_revoke_weth_tx`:
  - `amount_raw = 0`（intentional revoke）

## 输出

每个函数返回结构化 dict：

```text
{
  "function": "approve(address,uint256)",
  "selector": "0x095ea7b3",
  "from": "0xb05b...",
  "to": "0x8335... | 0x4200...",
  "spender": "0x03a520b3...",
  "amount_raw": <int>,
  "amount_human": "10.000000 USDC" | "0 USDC" | "0 WETH",
  "policy": "ApproveExact (never ApproveMax)" | "post-exit revoke",
  "data": "0x095ea7b3...",
  "value_wei": 0,
  "approvemax_forbidden": true,
  "approve_exact_only": true,
  "unsigned_only": true,
  "no_send": true,
  "transaction_sent": false,
}
```

## 5 项测试 全部 PASS

| # | test | result |
|---|---|---|
| 1 | build_approve_exact_usdc_tx(10 USDC) | **PASS** (amount_raw=10000000, approvemax_forbidden=True, no_send=True) |
| 2 | build_revoke_usdc_tx(0) | **PASS** (amount_raw=0, no_send=True) |
| 3 | build_revoke_weth_tx(0) | **PASS** (amount_raw=0, no_send=True) |
| 4 | build_approve_exact_usdc_tx(UINT256_MAX//2) | **PASS rejected** (ValueError: "ApproveMax forbidden") |
| 5 | build_approve_exact_usdc_tx(0) | **PASS rejected** (ValueError: "must be > 0") |

## 安全

```text
approvemax_forbidden  = true
approve_exact_only     = true
transaction_sent       = false
all_txs_unsigned_only  = true
all_txs_no_send        = true
no_signer_created      = true
no_wallet_client_created = true
no_eth_send_transaction_called = true
no_eth_send_raw_transaction_called = true
wallet_or_tx_touched   = false
can_run_probe_now      = false
tiny_canary_allowed    = no
```
