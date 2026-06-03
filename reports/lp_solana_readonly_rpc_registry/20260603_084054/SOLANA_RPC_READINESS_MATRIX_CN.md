# Solana RPC Readiness Matrix — Stage C

- stage: `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`
- run_id: `20260603_084054`
- script: `scripts/lp_solana_readonly_rpc_registry_v1.py`

## 1. 关键结果

```text
endpoint_count           = 2
usable_endpoint_count    = 2
primary_endpoint_id      = public_publicnode-110e5a18
primary_source_type      = public_publicnode
primary_host_hash        = 110e5a18
```

## 2. Endpoint matrix（redacted）

| endpoint_id | source_type | host_hash | health | version | slot | blockheight | latest_blockhash | epochinfo | genesishash | accountinfo | avg_latency_ms | usable |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `public_mainnetbeta-d6092b5f` | public_mainnet_beta | d6092b5f | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 339.62 | ✅ |
| `public_publicnode-110e5a18` | public_publicnode | 110e5a18 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 314.54 | ✅ |

## 3. 读到的实际数据

- **solana-core version**: 4.0.0
- **current slot**: 423,992,924
- **current block height**: 402,076,312
- **current epoch**: 981
- **system program** (11111111...): executable, verified

## 4. RPC methods 验证

8 个 method 全部通过 (`getHealth`, `getVersion`, `getSlot`, `getBlockHeight`, `getLatestBlockhash`, `getEpochInfo`, `getGenesisHash`, `getAccountInfo` on system program)。

## 5. 关键修正

- 必须设 `User-Agent: lpbot-solana-readonly-rpc/1.0`；否则 publicnode 返回 403
- publicnode 延迟略低于 mainnet-beta (314ms vs 340ms)，被选为 primary

## 6. RPC URL redaction policy

- **不**打印完整 URL 到 CSV/JSON/MD
- 只输出 `endpoint_id` / `source_type` / `host_hash` (sha256[0:8])
- 完整 URL 仅写入 `_primary_endpoint.txt` (sidecar; 不入 git; 不输出到任何最终 artifact)

## 7. 已知 public RPC 限制

- `api.mainnet-beta.solana.com`: 40 req/10s per IP (per upstream spec)
- `solana.publicnode.com`: 50 req/10s per IP
- 任何 Helius/QuickNode paid RPC (env var 设置) 都只能用 endpoint 身份接入，URL 永不打印

## 8. 安全断言

```text
this_stage_only_read_only       = true
this_stage_did_not_send_tx      = true
this_stage_did_not_load_keypair = true
this_stage_did_not_sign         = true
this_stage_did_not_swap         = true
this_stage_did_not_open_lp      = true
this_stage_did_not_bridge       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
tiny_canary_allowed              = "no"
```

## 9. 下一阶段

primary endpoint `public_publicnode-110e5a18` 可用于 Stage E (program ID verification) + Stage F (account discovery feasibility smoke) + Stage H/I (P0/P1 readiness)。
