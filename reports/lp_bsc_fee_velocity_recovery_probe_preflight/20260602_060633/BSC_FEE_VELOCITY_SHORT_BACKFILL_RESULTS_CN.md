# BSC PancakeSwap V3 — 8池短窗口 fee velocity 回填

- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
- run_id: `20260602_060633`
- rpc_source: `public_fallback:bsc-rpc.publicnode.com` (host_hash=`5a701356`)
- selected_windows: `24h, 72h` (no 14d/30d)

## 总览

- selected_pool_count = `8`
- expected_pool_window_count = `16`
- completed_pool_window_count = `16`
- swap_log_pool_count = `7`
- decoded_swap_log_count = `273563`
- fee_ready_pool_count = `7`
- volume_usd_total = `166164166.41`
- pool_fee_usd_proxy_total = `19462.2750`
- root_cause_distribution = `{}`

## Per-(pool, window) 明细

| pool | pair | fee | window | raw_logs | decoded | volume_usd_proxy | fee_usd_proxy | partial | fee_ready |
|---|---|---|---|---|---|---|---|---|---|
| `0xf2688Fb5...` | USDC/WBNB | 100 | 24h | 17671 | 17671 | 12624154.80 | 1262.4155 | no | **yes** |
| `0xf2688Fb5...` | USDC/WBNB | 100 | 72h | 49484 | 49484 | 38784158.76 | 3878.4159 | no | **yes** |
| `0x81A9b5F1...` | USDC/WBNB | 500 | 24h | 490 | 490 | 23199.86 | 11.5999 | no | **yes** |
| `0x81A9b5F1...` | USDC/WBNB | 500 | 72h | 1589 | 1589 | 86243.27 | 43.1216 | no | **yes** |
| `0xc721dECC...` | USDC/WBNB | 2500 | 24h | 54 | 54 | 259.15 | 0.6479 | no | **yes** |
| `0xc721dECC...` | USDC/WBNB | 2500 | 72h | 149 | 149 | 668.95 | 1.6724 | no | **yes** |
| `0x18C5aFFA...` | USDC/WBNB | 10000 | 24h | 0 | 0 | 0.00 | 0.0000 | no | no |
| `0x18C5aFFA...` | USDC/WBNB | 10000 | 72h | 0 | 0 | 0.00 | 0.0000 | no | no |
| `0x172fcD41...` | USDT/WBNB | 100 | 24h | 50860 | 50860 | 27153423.04 | 2715.3423 | no | **yes** |
| `0x172fcD41...` | USDT/WBNB | 100 | 72h | 145642 | 145642 | 80550470.20 | 8055.0470 | no | **yes** |
| `0x36696169...` | USDT/WBNB | 500 | 24h | 2082 | 2082 | 2481003.27 | 1240.5016 | no | **yes** |
| `0x36696169...` | USDT/WBNB | 500 | 72h | 5095 | 5095 | 4449384.06 | 2224.6920 | no | **yes** |
| `0x1401ff94...` | USDT/WBNB | 2500 | 24h | 86 | 86 | 2119.59 | 5.2990 | no | **yes** |
| `0x1401ff94...` | USDT/WBNB | 2500 | 72h | 341 | 341 | 8972.63 | 22.4316 | no | **yes** |
| `0x6805E0E5...` | USDT/WBNB | 10000 | 24h | 4 | 4 | 20.68 | 0.2068 | no | **yes** |
| `0x6805E0E5...` | USDT/WBNB | 10000 | 72h | 16 | 16 | 88.15 | 0.8815 | no | **yes** |

## 安全

```text
wallet_or_tx_touched   = false
can_run_probe_now      = false
tiny_canary_allowed    = no
edge_proven            = no
```
