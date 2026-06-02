# Mint Tx Builder 实现

- stage: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`
- phase: F
- run_id: `20260602_163036`

## 实现

`scripts/lp_base_10u_probe_executor_v2.py` 中 `build_mint_position_tx`：

```python
build_mint_position_tx(
    wallet, tick_lower, tick_upper,
    amount0_desired_wei, amount1_desired_raw,
    amount0_min_wei, amount1_min_raw,
    notional_usd=10
) -> dict
```

## 校验

- `notional_usd == 10`（first-round only；raise ValueError 否则）
- `deadline = int(time.time()) + 3600`（runtime 实时生成；**不是** v1 的 placeholder 4070908800 (2099-01-01)）
- `recipient = wallet`（绑死）

## 输出

```text
{
  "function": "mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))",
  "selector": "0x88316456",
  "from": wallet,
  "to": NPM,
  "value_wei": 0,
  "deadline": <int>,  # runtime: now + 3600
  "deadline_iso": "ISO 8601 string",
  "deadline_relative_seconds": 3600,
  "deadline_is_now_plus_3600": true,
  "deadline_is_NOT_legacy_placeholder_2099": true,
  "data": "0x88316456... (778 hex chars)",
  "params": {
    "token0": WETH, "token1": USDC, "fee": 100,
    "tickLower": tick_lower, "tickUpper": tick_upper,
    "amount0Desired_wei": 0, "amount1Desired_raw": 10_000_000,
    "amount0Min_wei": 0, "amount1Min_raw": 9_949_999,
    "recipient": wallet,
  },
  "recipient_bound_to_wallet": true,
  "unsigned_only": true, "no_send": true, "no_signature": true,
  "transaction_sent": false,
}
```

## 数据编码 bug 修正

本轮发现 `encode_mint` 之前产生 `0x0x88316456...`（双 0x 前缀）。修复：把 offset body 的 leading `0x` strip 掉再与 SEL_MINT 拼接。**data 现在正确以 `0x88316456` 开头，length 778**。

## 测试 1 项 PASS

| test | result |
|---|---|
| build_mint_position_tx(10 USDC, dynamic range -200908/-200508) | **PASS** |

## 安全

```text
unsigned_only         = true
no_send               = true
no_signature          = true
transaction_sent      = false
deadline_is_now_plus_3600 = true
deadline_is_NOT_legacy_placeholder_2099 = true
recipient_bound_to_wallet = true
no_signer_created     = true
no_wallet_client_created = true
wallet_or_tx_touched  = false
can_run_probe_now     = false
tiny_canary_allowed   = no
```
