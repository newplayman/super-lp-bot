# Stage F — Public API + Solana RPC Adapter 实现

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`

## 0. 实现文件

- `scripts/lp_long_horizon/adapters/public_api_coingecko.py`
- `scripts/lp_long_horizon/adapters/solana_rpc_readonly.py`

## 1. PublicApiCoinGeckoAdapter (CoinGecko OHLC, read-only)

API:
```python
class PublicApiCoinGeckoAdapter:
    def __init__(self, *, abort_controller=None, timeout_s=5.0): ...
    def fetch_ohlc(self, coin_id, vs_currency="usd", days=7) -> list[OhlcBar]: ...
```

- HTTP GET `https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc`
- retry 2 次, base_delay 0.5s (CoinGecko free tier 10-30 req/min)
- timeout 5s per call
- 失败 (network / 4xx / 5xx / 429) → 返回 [] + 记 error / 429
- 不 raise

OhlcBar dataclass: `ts / open / high / low / close / volume / real_data / data_source`

## 2. SolanaRpcReadOnlyAdapter (getMultipleAccountsInfo, read-only)

API:
```python
class SolanaRpcReadOnlyAdapter:
    def __init__(self, *, abort_controller=None, timeout_s=5.0, endpoint=None): ...
    def fetch_accounts(self, addresses: list[str]) -> list[AccountInfo]: ...
```

- HTTP POST `https://api.mainnet-beta.solana.com` (or 3 alternative endpoints)
- JSON-RPC `getMultipleAccountsInfo` (read-only, no signing)
- retry 2 次, base_delay 0.5s
- timeout 5s per call
- 失败 → 返回 [] + 记 error / 429
- 不 raise

AccountInfo dataclass: `address / data_len / owner / lamports / executable / rent_epoch / real_data / data_source`

## 3. 关键 opt-in 设计

两个 adapter 都默认 **opt-in**, runner 必须显式 `--use-public-api=1` 或
`--use-solana-rpc=1` 才会调用. 默认 `--use-public-api=0 --use-solana-rpc=0`,
这样 VPS 跑 smoke 时不会触发网络, **不依赖** VPS 网络可达性.

local_artifact_replay_adapter **不 opt-in**, 始终跑, 因为它只读本地 JSON.

## 4. retry / 429 / timeout 工具集成

两个 adapter 都使用 `retry_with_backoff` (Stage D 实现) + `classify_429` +
`with_timeout`. retryable: classify_429(e) OR isinstance(URLError / TimeoutError_).

abort_controller 集成:
- 成功: `abort_controller.record_ok()` + `record_429_cleared()`
- 429: `abort_controller.record_429()` (触发 5 连发 abort)
- 其它错误: `abort_controller.record_error()` (触发 error rate abort)

## 5. safety check (静态)

每个 adapter 文件都内置 `_self_check()` 函数, 启动时跑 AST + tokenize 扫描,
任何 banned token 在 real code 中出现 → SystemExit. 包括:

- private_key / mnemonic / seed_phrase / keypair.from_secret_key / fromSecretKey
- new Signer / new Wallet
- sendTransaction / eth_sendRawTransaction / signTransaction
- add_liquidity / remove_liquidity / collect_fee / approve / mint
- wormhole.core / wormhole.bridge / mayan.forward / portal.bridge

任何未来 edit 引入 banned token 都会立即失败.

## 6. 单元测试 (Stage L)

- `test_coingecko_ohlc_url_format`
- `test_coingecko_returns_empty_on_network_failure`
- `test_coingecko_records_429_in_abort_controller`
- `test_coingecko_records_ok_in_abort_controller_on_success`
- `test_coingecko_ohlc_bar_dataclass`
- `test_solana_rpc_request_body_format`
- `test_solana_rpc_returns_empty_on_network_failure`
- `test_solana_rpc_records_429`
- `test_solana_rpc_account_info_dataclass`
- `test_coingecko_self_check_passes`
- `test_solana_rpc_self_check_passes`

## 7. 结论

Public API + Solana RPC adapter 实装完成, 默认 opt-in, 不依赖网络仍可跑.
Stage F 通过. 进入 Stage G (regime classifier).
