# BSC RPC eth_getLogs capability matrix

- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
- endpoint_count: `5`
- usable_count: `1`
- high_confidence_count: `0`

| endpoint_id | source | chainId | block | getCode | 500 | 1000 | 2000 | 4000 | rec | usable | conf | err |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `pub_98edada9` | `public_fallback:bsc-dataseed.binance.org` | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | - | no | low |  |
| `pub_54e95980` | `public_fallback:bsc-dataseed1.defibit.io` | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | - | no | low |  |
| `pub_5a701356` | `public_fallback:bsc-rpc.publicnode.com` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 4000 | yes | medium |  |
| `pub_87a12a31` | `public_fallback:rpc.ankr.com/bsc` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | - | no | low | chainId_failed |
| `pub_524b13a6` | `public_fallback:binance.nodereal.io` | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | - | no | low |  |

## Note

Endpoint URLs are not printed (only an 8-char SHA-256 of the host). 'env:*' entries come from BSC_RPC_PRIMARY / LPBOT_BSC_RPC_URL / BSC_RPC_URL / BNB_RPC_URL / RPC_BSC_URL / LPBOT_BSC_RPC_FALLBACK environment variables.

## 关键发现：PancakeSwap V3 Swap topic 与 Uniswap V3 不同

旧 overnight runner（仓库内 `scripts/lp_bsc_fee_velocity_overnight_runner.py` 与 `/tmp/.../scripts/lp_bsc_fee_velocity_overnight_runner.py`）将 `SWAP_TOPIC_V3` 硬编码为 Uniswap V3 的：

```text
0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67
```

但 PancakeSwap V3 在 BSC 上的 Swap 事件多了两个 `protocolFeesToken0/1` 字段，因此 keccak256 不同：

```text
0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83
```

直接的诊断证据（publicnode endpoint，read-only）：

```text
pool 0x172fcD41E0913e95784454622d1c3724f546f849  (WBNB/USDT fee=100)
  - 100-block 无 topic 过滤: 277 logs（活跃池）
  - 200-block 无 topic 过滤: 594 logs，全部 topic[0] = 0x19b47279...
  - 任意 chunk + Uniswap V3 topic 过滤: log_count = 0
  - 4000-block + 正确 PancakeSwap V3 topic: log_count = 5912
```

所以旧 run 出现 `decoded_swap_log_count=0` 的根因 **不是** public_fallback RPC 失败，**而是 topic filter 不匹配**（runner 同时也有 RPC 限流问题，但即便修复 RPC，topic 不对也拿不到任何 swap）。

本 matrix 已使用正确 topic（`SWAP_TOPIC_PANCAKE_V3 = 0x19b47279...`）；下游 Phase 3/4 必须沿用同一常量。

## 推荐配置

```text
recommended_endpoint_id   = pub_5a701356  (publicnode)
recommended_chunk_size    = 4000 blocks  (~3.3 hours @ 3s/block)
swap_topic                = 0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83
confidence                = medium  (single public endpoint, no env override)
```

如要提升为 `high`，需通过 `BSC_RPC_PRIMARY` / `LPBOT_BSC_RPC_URL` 注入付费 endpoint。
