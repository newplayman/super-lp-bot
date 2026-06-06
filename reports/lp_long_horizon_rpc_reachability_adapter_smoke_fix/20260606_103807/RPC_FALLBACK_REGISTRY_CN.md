# RPC Fallback Registry

- stage: `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1`
- section: rpc_fallback_registry
- run_id: `20260606_103807`
- branch: `feat/supabase-postgres-deployment`
- generated_at_utc: `2026-06-06T10:40:00Z`

## 0. 总结

✅ **RPC fallback registry 已就位** (`scripts/lp_long_horizon/rpc_registry.py`). 集中管理 3 chains (base / bsc / solana) 的 primary + fallback + env override. **不** 提交任何 paid RPC key, **不** 写真实 secret. env_override_name 仅是变量名 (e.g. `BASE_RPC_URL`), **不** 含 value.

## 1. Registry

| Chain | Primary Public RPC | Fallback List | Env Override | Healthcheck | Chain ID |
|---|---|---|---|---|---|
| **base** | `https://mainnet.base.org` | mainnet.base.org, base-rpc.publicnode.com, base.llamarpc.com, 1rpc.io/base | `BASE_RPC_URL` | eth_chainId | 8453 |
| **bsc** | `https://bsc-dataseed.binance.org` | bsc-dataseed.binance.org, bsc-rpc.publicnode.com, binance.llamarpc.com, 1rpc.io/bnb | `BSC_RPC_URL` | eth_chainId | 56 |
| **solana** | `https://api.mainnet-beta.solana.com` | api.mainnet-beta.solana.com, solana-rpc.publicnode.com, 1rpc.io/solana | `SOLANA_RPC_URL` | getHealth | n/a |

## 2. 设计原则

### 2.1 公共 free endpoint only

所有 endpoint 都是 free public RPC. **不** 包含:
- Alchemy paid tier URL
- Infura paid tier URL
- QuickNode paid tier URL
- 任何需要 API key 的 endpoint

### 2.2 Env Override 模式

用户可以设置环境变量 override primary, **不** 修改代码:
```bash
export BASE_RPC_URL=https://my-private-base-rpc.example.com
# 然后跑 long-horizon collector / adapter smoke
```

- env_override_name 仅为变量**名**, 永远不存 value
- 真实 value 由用户**自己**通过 env var 注入, **不** 提交到 repo
- 用户的 env var 设置不进入 git history (假设使用 .gitignore / .runtime.shadow.env)

### 2.3 多个 Fallback 链

每个 chain 至少 3 个 fallback. 原因:
- 单 endpoint 失败率高 (rate-limit / network / region issue)
- 用户可在 stage runner 环境中临时指定一个 endpoint
- 真实 12h retry / 24h long run 需要稳定 RPC, fallback 链是核心

### 2.4 Read-only healthcheck

| Chain | Method | 验证 |
|---|---|---|
| base / bsc | `eth_chainId` | result 与 expected chain_id (8453 / 56) 一致 |
| solana | `getHealth` | result == "ok" |

**不** 测试:
- `eth_sendRawTransaction`
- `eth_sendTransaction`
- `sendTransaction`
- 任何写方法

## 3. select_best_endpoint 流程

```
for each chain:
    if env_override_name set (e.g. BASE_RPC_URL):
        return env value (highest priority)
    else:
        for endpoint in [primary] + fallback_public_rpc_list:
            if healthcheck returns reachable:
                return this endpoint
        return None (all endpoints unreachable)
```

## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `no_paid_rpc_key_committed` | `true` |
| `no_real_secret_committed` | `true` |
| `long_run_started` | `false` |

## 5. 严禁

- ❌ 不启动 long-running collector
- ❌ 不启动 12h / 24h retry
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不发送 transaction
- ❌ 不接 paid RPC / paid indexer (registry 仅 free public endpoint)
- ❌ 不写真实 secret (private_key, mnemonic, seed, API key)

## 6. 下游

进入 Stage C (RPC reachability matrix) — 用 `_evm_healthcheck` / `_solana_healthcheck` 实测每个 endpoint latency + reachability. 失败 honest 记录.
