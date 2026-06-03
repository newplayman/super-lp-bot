# Meteora Pool Scoring — Stage I

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`

## 0. 关键结果

```text
candidate (score >= 70)  = 0
watch     (40 <= s < 70) = 0
reject    (s < 40)       = 16
```

## 1. Scoring components

| component | max | rule |
|---|---|---|
| feeScore | 30 | base_fee >= 5bps = 30; >= 2 = 20; >= 1 = 10; else 5 |
| maxFeeScore | 10 | max_fee >= 20 = 10; >= 10 = 7; else 3 |
| quoteScore | 20 | quote_success = 20; else 0 |
| liqScore | 25 | near_active_liq >= 3 = 25; >= 1 = 15; > 0 = 8; else 0 |
| stableScore | 10 | token_y == USDC = 10; else 0 |

Total max = 95. Buckets: >= 70 candidate; >= 40 watch; else reject.

## 2. Top scored pools

| pool | token_pair | base_fee | quote | near_liq | score | bucket |
|---|---|---|---|---|---|---|
| `H9b4sPAe…` | Axhcwf/EPjFWd | 2.5 | ❌ | 0 | 37 | reject |
| `9DiruRpj…` | FUAfBo/EPjFWd | 1.5 | ❌ | 0 | 27 | reject |
| `6eR5rRde…` | HfAFNs/So1111 | 2 | ❌ | 0 | 27 | reject |
| `2G7fxAhB…` | CPV5ki/So1111 | 2 | ❌ | 0 | 27 | reject |
| `6VxKTxaV…` | 9gnq7q/So1111 | 2 | ❌ | 0 | 27 | reject |
| `5BKxfWMb…` | So1111/EPjFWd | 0.02 | ❌ | 0 | 22 | reject |
| `6qz7THwQ…` | BPxxfR/EPjFWd | 0.25 | ❌ | 0 | 22 | reject |
| `FhdW3Y6E…` | 3ZLekZ/EPjFWd | 0.2 | ❌ | 0 | 22 | reject |
| `CnK82s8e…` | FeMbDo/So1111 | 1 | ❌ | 0 | 17 | reject |
| `9bL8Pptp…` | DnnmrZ/So1111 | 1 | ❌ | 0 | 17 | reject |

## 3. 安全断言

```text
this_stage_only_scoring           = true
no_tx                            = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```

## 4. 下一阶段

进入 Stage J — survival EV batch preview。
