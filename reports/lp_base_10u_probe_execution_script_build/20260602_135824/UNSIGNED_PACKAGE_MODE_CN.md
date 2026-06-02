# Unsigned Package Mode Spec

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- phase: E
- run_id: `20260602_135824`
- script: `scripts/lp_base_10u_probe_executor_v1.py --mode print-unsigned`

## 命令

```bash
python3 scripts/lp_base_10u_probe_executor_v1.py --mode print-unsigned --run-id <RUN_ID> [--out-dir <DIR>]
```

## 输出结构

```text
candidate:
  chain: base
  chain_id: 8453
  pool: 0x72ab388e...
  pair: WETH/USDC
  protocol: Uniswap V3 (Base)
  fee_tier: 100
  tick_lower: -200643
  tick_upper: -200243
  tick_spacing: 1
  npm: 0x03a520b3...
  quoter_v2: 0x3d4e44Eb...
  weth: 0x4200...0006
  usdc: 0x8335...2913
wallet:
  address: 0xb05b...
  from: 0xb05b...
  recipient: 0xb05b...
notional:
  usd: 10
  amount0_desired_wei_WETH: 0
  amount1_desired_raw_USDC: 10000000
  amount0_min_wei: 0
  amount1_min_raw: 9949999
approve_usdc_if_needed:
  to: 0x8335...2913
  function: approve(address,uint256)
  selector: 0x095ea7b3
  spender: 0x03a520b3...
  amount_raw: 10000000
  amount_human: 10.000000 USDC
  policy: ApproveExact (never ApproveMax)
  data: 0x095ea7b3...
  value_wei: 0
  from: 0xb05b...
approve_weth_if_needed:
  skipped: true
  reason: amount0_desired_wei_WETH = 0; WETH approve unnecessary for this range/notional
mint_params:
  to: 0x03a520b3...
  function: mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))
  selector: 0x88316456
  data: 0x88316456...
  value_wei: 0
  from: 0xb05b...
  deadline: 4070908800
  deadline_iso: 2099-01-01T00:00:00Z
  deadline_is_placeholder: true
  note: deadline is a PLACEHOLDER; user overrides at execution time to now+3600
```

## 顶层 flags（必须为 true）

```text
unsigned_only           = true
no_signature            = true
no_send                 = true
execution_not_authorized = true
no_abi_bytes_unless_marked = true
```

## 输出位置

- `reports/lp_base_10u_probe_execution_runtime/<run_id>/unsigned_package.json`（local only）

## 安全

```text
wallet_or_tx_touched = false
```
