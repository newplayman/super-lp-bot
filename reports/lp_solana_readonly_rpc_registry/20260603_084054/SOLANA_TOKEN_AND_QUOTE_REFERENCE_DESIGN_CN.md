# Solana Token & Quote Reference Design — Stage G

- stage: `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`
- run_id: `20260603_084054`

## 0. 设计原则

- **read-only only** — 所有 source 都是 public RPC / public API
- **不** swap / **不** bridge / **不** 构造 transaction
- **不**调用 sendTransaction / **不** load keypair / **不** sign
- Jupiter Quote API **只**用作 price/route reference，**不**触发实际 swap

## 1. 8 个 token / quote 维度

### 1.1 SPL token metadata source

**Source**: SPL Token Registry (on-chain) via `getAccountInfo(mint_pubkey)` + manual decode

```python
# pseudo (read-only)
def get_spl_token_metadata(mint_pubkey: str) -> dict:
    info = solana_rpc.get_accountInfo(mint_pubkey, encoding="base64")
    owner = info["value"]["owner"]  # expected: TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA
    data_len = len(info["value"]["data"][0])
    return {"mint": mint_pubkey, "owner": owner, "data_len": data_len}
```

**验证**: `owner == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"` (Token Program)
**可选 (not this stage)**: Metaplex Token Metadata program (22258...) 查 name / symbol / uri

### 1.2 decimals source

**Source**: on-chain via `getAccountInfo(mint)` + manual parse

```python
# pseudo
def get_decimals(mint_pubkey: str) -> int:
    info = solana_rpc.getAccountInfo(mint_pubkey, encoding="base64")
    raw = base64_decode(info["value"]["data"][0])
    # SPL Mint layout: [0..36] mint_authority, [36..44] supply, [44] decimals, ...
    return raw[44]
```

**USDC**: 6 decimals
**SOL / wSOL**: 9 decimals
**BTC (cbBTC)**: 8 decimals

### 1.3 Jupiter quote API (read-only)

**Endpoint**: `https://quote-api.jup.ag/v6/quote?inputMint=X&outputMint=Y&amount=Z&slippageBps=50`

```python
# pseudo (HTTP GET, no tx)
import urllib.request
url = f"https://quote-api.jup.ag/v6/quote?inputMint={USDC_MINT}&outputMint={SOL_MINT}&amount={10_000_000}&slippageBps=50"
req = urllib.request.Request(url)
with urllib.request.urlopen(req, timeout=10) as r:
    data = json.loads(r.read())
    # data["data"][0]["outAmount"], data["data"][0]["priceImpactPct"]
    # NOTE: Jupiter /swap endpoint NOT used (would build tx)
```

**Rate limit**: ~10 req/s unauthenticated
**Cache**: 30s TTL (per upstream spec)
**Note**: `outAmount` 是 raw token amount; 转 USD 需先得到 SOL/USDC price

### 1.4 token account balance source

**Source**: `getTokenAccountBalance(ata_pubkey)` 或 `getAccountInfo(ata_pubkey, encoding="jsonParsed")`

```python
# pseudo
def get_ata_balance(wallet: str, mint: str) -> int:
    ata = derive_ata(wallet, mint)  # PDA
    info = solana_rpc.getTokenAccountBalance(ata)
    return int(info["value"]["amount"])
```

### 1.5 SOL/USD anchor

**Source**: Jupiter quote API (SOL → USDC)

```python
def get_sol_usd_price() -> float:
    # 1 SOL → ? USDC
    data = jupiter_quote(SOL_MINT, USDC_MINT, 1_000_000_000)  # 1 SOL raw
    out_usdc_raw = int(data["outAmount"])
    return out_usdc_raw / 1_000_000  # 6 decimals
```

**Refresh**: 30s TTL (per upstream)

### 1.6 USDC/USD anchor

**Assumption**: USDC = $1.00 (per public stablecoin peg)

- **不**对 USDC 做 price query
- 任何 USDC 数量都按 1:1 USD 计算
- 偏差: < 0.5% (depeg 风险；10/20U probe 体量下可忽略)

### 1.7 wrapped SOL handling

**wSOL** = `So11111111111111111111111111111111111111112` (well-known public constant; same pattern as system program)

- **不** wrap / unwrap; **只** 读 mint + decimals
- LP protocol (Meteora DLMM, Orca) 通常 pair 是 `wSOL/USDC`，但 protocol 内部处理 wrapping
- 我们读 mint / decimals 即可，不动 token accounts

### 1.8 token mint registry

**Format**: local JSONL (research-only; not in production DB)

```json
{
  "symbol": "USDC",
  "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  "decimals": 6,
  "coingecko_id": "usd-coin",
  "verified": "via_getAccountInfo_owner_eq_spl_token_program"
}
```

**Initial set** (for first connector):
- USDC, USDT (EVM bridged on Solana), wSOL, SOL (native)
- cbBTC (Coinbase BTC) on Solana
- jitoSOL, jupSOL (LSTs)

### 1.9 pool token pair validation

**Per-pool check** (read-only):
```python
def validate_pool_tokens(pool_meta: dict, expected_mint: str) -> bool:
    return pool_meta["token_a_mint"] == expected_mint or pool_meta["token_b_mint"] == expected_mint
```

**Output**: in `solana_lp_pool_universe_v1` (per upstream schema), with `invalid_reason` if mismatch.

## 2. 不在本阶段做

- ❌ 不调 Jupiter **swap** endpoint (只会 quote)
- ❌ 不 wrap / unwrap SOL
- ❌ 不调 sendTransaction
- ❌ 不读 wallet (only pubkey for ATA derivation)
- ❌ 不 construct transaction

## 3. 已知依赖 / 缺口

1. **Jupiter rate limit** ~10 req/s; cache 必需
2. **Metaplex Token Metadata** program (22258...) — 用于读 name / symbol / uri; 复杂；v1 可不读
3. **Token-2022** (Token Extensions) — 复杂 mints; v1 不支持
4. **Stablecoin depeg** — USDC = $1 assumption; v1 可接受
5. **Token account 反推导** — 需要知道 owner 程序 (TokenkegQ...) 才能 derive ATA

## 4. 安全断言

```text
this_stage_only_design_sources     = true
this_stage_did_not_load_keypair    = true
this_stage_did_not_call_jupiter_swap = true
this_stage_did_not_wrap_sol         = true
this_stage_did_not_sign             = true
this_stage_did_not_send_tx          = true
solana_wallet_or_keypair_touched    = false
can_run_probe_now                   = false
```

## 5. 下游使用

未来 stage (LP_METEORA_DLMM_READONLY_CONNECTOR_V1 等) 引用本设计文档：
- SPL token metadata: `get_spl_token_metadata(mint)`
- decimals: `get_decimals(mint)`
- quote: `jupiter_quote(...)`
- balance: `get_ata_balance(wallet, mint)`
- price anchor: `get_sol_usd_price()` + USDC=$1 assumption
