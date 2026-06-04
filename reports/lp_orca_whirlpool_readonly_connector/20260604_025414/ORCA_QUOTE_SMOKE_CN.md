# Orca Quote Smoke — Stage I

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`

## 0. 关键结果

```text
candidate_count              = 126
quote_ready_pool_count       = 10
quote_10u_success_count      = 10
quote_20u_success_count      = 10
quote_100u_success_count     = 0
high_fee_quote_ready_count   = 20  (feeRateMax >= 30bps)
no_liquidity_near_active_count = 0
```

## 1. Quote path

- SDK: `@orca-so/whirlpools` 8.0.0
- Method: `swapInstructions(rpc, {inputAmount, mint}, poolAddress)` (quote-only mode; do not execute instructions)
- Direction: anchor (USDC/USDT/SOL) → volatile token
- 10 USD and 20 USD notionals only (100 USD deferred to avoid 429)

## 2. 10 个 quote-ready 池 (按 fee_rate 排)

| pool | token_in | 10u_in raw | 10u_out raw | fee (raw) | fee_rate |
|---|---|---|---|---|---|
| `C9U2Ksk6KKWvLE` | SOL | 76,923,076 | 39,052,791 | 123,077 | 1600 (16bps) |
| `CeaZcxBNLpJWtx` | SOL | 76,923,076 | 8,528 | 123,077 | 1600 (16bps) |
| `C1MgLojNLWBKAD` | SOL | 76,923,076 | 29,400,137 | 38,462 | 500 (5bps) |
| `6a3m2EgFFKfsFu` | SOL | 76,923,076 | 1,583,233 | 30,770 | 400 (4bps) |
| `Czfq3xZZDmsdGd` | USDC | 10,000,000 | 140,418,042 | 4,000 | 400 (4bps) |
| `HxA6SKW5qA4o12` | USDC | 10,000,000 | 15,613 | 4,000 | 400 (4bps) |
| `B5EwJVDuAauzUE` | SOL | 76,923,076 | 8,566 | 38,462 | 500 (5bps) |
| `DtYKbQELgMZ3ih` | SOL | 76,923,076 | 64,683,233 | 7,693 | 100 (1bps) |
| `Hp53XEtt4S8SvP` | SOL | 76,923,076 | 59,995,260 | 7,693 | 100 (1bps) |
| `6NUiVmsNjsi4Af` | USDC | 10,000,000 | 2,891,679 | 2,001 | 200 (2bps) |

## 3. 真实 quote 数据 (Czfq3xZZDmsd SOL/USDC 4bps)

```text
10u USDC in:  out 140,418,042 raw SOL (= 0.1404 SOL @ 130 USD/SOL = $18.26)
              fee 4,000 raw USDC = $0.004
20u USDC in:  out 281,390,746 raw SOL (= 0.2814 SOL @ 130 USD/SOL = $36.58)
              fee 8,000 raw USDC = $0.008
implied fee rate: 4,000 / 10,000,000 = 0.04% = 4bps (matches pool feeRate)
```

## 4. 失败原因 (106/126 = 84%)

```text
quote_error: SolanaError: HTTP error (429): Too Many Requests
```

Public RPC (publicnode.com + mainnet-beta.solana.com) 都受 429 限制。本轮 250ms 间隔下仍有大量 429。

## 5. 安全断言

```text
this_stage_only_quote        = true
this_stage_no_tx             = true
this_stage_no_keypair        = true
this_stage_no_signer         = true
solana_wallet_or_keypair_touched = false
can_run_probe_now            = false
```

## 6. 下一阶段

进入 Stage J — survival EV preview 在 10 个 quote-ready 池上跑完整 grid (6 × 7 × 4 = 168 cells per pool = 1680 cells total)。注: pool fee 真实数据已采集, EV 用真实 fee rate 校准, 不依赖 heuristic turnover。
