# RPC Reachability Matrix

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: rpc_reachability_matrix
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:42:00Z`

## 0. 总结

✅ **RPC reachability matrix 已跑** (11 endpoints probed). Honest 记录: failures 标记 `reachable=False` + error string. **不** 假装成功.

## 1. Per-chain selected (first reachable, for downstream smoke)

| Chain | Selected Endpoint | Reachable |
|---|---|---|
| bsc | `https://bsc-dataseed.binance.org` | ✅ |
| solana | `https://api.mainnet-beta.solana.com` | ✅ |


## 2. Per-chain reachability summary

| Chain | Total Probed | Reachable | Unreachable |
|---|---|---|---|
| base | 4 | 0 | 4 |
| bsc | 4 | 1 | 3 |
| solana | 3 | 1 | 2 |


## 3. Detailed results

| Chain | Endpoint | Reachable | Latency (ms) | Method | Error |
|---|---|---|---|---|---|
| base | `https://mainnet.base.org` | ❌ | 9890 | eth_chainId | HTTPError: HTTP Error 403: Forbidden |
| base | `https://base-rpc.publicnode.com` | ❌ | 528 | eth_chainId | HTTPError: HTTP Error 403: Forbidden |
| base | `https://base.llamarpc.com` | ❌ | 434 | eth_chainId | HTTPError: HTTP Error 403: Forbidden |
| base | `https://1rpc.io/base` | ❌ | 991 | eth_chainId | URLError: <urlopen error [Errno 104] Connection reset by peer> |
| bsc | `https://bsc-dataseed.binance.org` | ✅ | 166 | eth_chainId | - |
| bsc | `https://bsc-rpc.publicnode.com` | ❌ | 430 | eth_chainId | HTTPError: HTTP Error 403: Forbidden |
| bsc | `https://binance.llamarpc.com` | ❌ | 391 | eth_chainId | URLError: <urlopen error [Errno -2] Name or service not known> |
| bsc | `https://1rpc.io/bnb` | ❌ | 1036 | eth_chainId | URLError: <urlopen error [Errno 104] Connection reset by peer> |
| solana | `https://api.mainnet-beta.solana.com` | ✅ | 59 | getHealth | - |
| solana | `https://solana-rpc.publicnode.com` | ❌ | 516 | getHealth | HTTPError: HTTP Error 403: Forbidden |
| solana | `https://1rpc.io/solana` | ❌ | 1106 | getHealth | URLError: <urlopen error [Errno 104] Connection reset by peer> |


## 4. Method

- base/bsc: `eth_chainId` (validate chain_id matches expected 8453 / 56)
- solana: `getHealth` (validate result == "ok")
- All probes are read-only JSON-RPC POST; no signing, no tx
- Timeout: 5.0s per probe

## 5. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |

## 6. 严禁

- ❌ 不启动 long-running collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer
- ❌ 不写真实 secret

## 7. 下游

进入 Stage D (Base retry) + E (BSC retry) + F (Meteora retry). 用本 stage `selected_per_chain` 的 endpoint.
