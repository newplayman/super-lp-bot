# Mint Receipt / TokenId Schema

- stage: `LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_V1`
- phase: F
- run_id: `20260602_184806`
- deviation 落地: `mint_receipt_schema_not_defined`
- **本阶段不执行 mint，不查真实 receipt。仅定义未来执行时如何解析与校验。**

## expected mint tx hash

```text
expected_mint_tx_hash = <broadcast 后返回的 tx hash>
                     = `eth_sendRawTransaction` 返回值（在未来执行阶段；当前 stage 永远不调用）
                     格式: 0x[0-9a-f]{64}
```

## expected receipt 必备字段

通过 `eth_getTransactionReceipt(tx_hash)` 获取：

| field | 期望 | 失败动作 |
|---|---|---|
| `status` | `0x1` (success) | 若 `0x0` ⇒ mint reverted；写 telemetry status=mint_failed；不进入后续 hold/exit；进入 manual intervention |
| `transactionHash` | 与 broadcast 返回 hash 一致 | mismatch ⇒ manual intervention |
| `from` | `0xb05b...d835` (wallet) | mismatch ⇒ manual intervention |
| `to` | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` (NPM) | mismatch ⇒ manual intervention |
| `contractAddress` | `null` (mint 不创建合约) | 非 null ⇒ manual intervention |
| `gasUsed` | < 800_000 sanity check | 远超 ⇒ warn |
| `logs` | 至少 1 个 ERC721 Transfer + 1 个 IncreaseLiquidity event | logs 不足 ⇒ manual intervention |
| `blockNumber` / `blockHash` | 记录入 telemetry | n/a |

## expected logs

### ERC721 `Transfer(address indexed from, address indexed to, uint256 indexed tokenId)`

- topic0 = `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef` (keccak256("Transfer(address,address,uint256)"))
- topic1 (from, indexed) = `0x000000000000000000000000` + `0x0000000000000000000000000000000000000000` = `0x00...00`
- topic2 (to, indexed) = `0x000000000000000000000000` + `wallet` lower hex
- topic3 (tokenId, indexed) = `0x0000000000000000000000000000000000000000000000000000000000` + tokenId hex
- address = NPM (`0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1`)

### IncreaseLiquidity (Uniswap V3 NonfungiblePositionManager)

- signature: `IncreaseLiquidity(uint256 indexed tokenId, uint128 liquidity, uint256 amount0, uint256 amount1)`
- topic0 = `0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f` (keccak256)
- topic1 (tokenId, indexed) = tokenId hex padded to 32 bytes
- data = `liquidity (uint128) || amount0 (uint256) || amount1 (uint256)`
- address = NPM
- **可选** — 主依赖 ERC721 Transfer 提取 tokenId；IncreaseLiquidity 用于双重验证

## tokenId 提取方法

```text
1. 在 receipt.logs 中筛选 address == NPM AND topic0 == ERC721_TRANSFER_TOPIC0
2. 在过滤结果中再筛选 topic1 == padded(0x0) AND topic2 == padded(wallet)
3. 若匹配数量 == 0 ⇒ FAIL_TOKEN_ID_NOT_FOUND ⇒ manual intervention
4. 若匹配数量 > 1 ⇒ FAIL_MULTIPLE_TOKEN_TRANSFERS ⇒ manual intervention（异常，需调查）
5. tokenId_hex = topic3
6. tokenId = int(tokenId_hex, 16)
7. 写入 telemetry: token_id_extracted, token_id_decimal, token_id_hex, log_index
```

## 校验 — tokenId 必须属于本 wallet

```text
1. 调用 NPM.ownerOf(tokenId) 通过 eth_call
2. owner == wallet ?
   - yes -> 通过
   - no  -> FAIL_TOKEN_ID_NOT_OWNED_BY_WALLET ⇒ manual intervention
```

## 校验 — `NPM.positions(tokenId)` 与 expected 匹配

```text
positions = NPM.positions(tokenId)
返回 12-tuple:
  nonce (uint96)
  operator (address)
  token0 (address)
  token1 (address)
  fee (uint24)
  tickLower (int24)
  tickUpper (int24)
  liquidity (uint128)
  feeGrowthInside0LastX128 (uint256)
  feeGrowthInside1LastX128 (uint256)
  tokensOwed0 (uint128)
  tokensOwed1 (uint128)
```

校验:

| field | expected | fail action |
|---|---|---|
| `token0` | `0x4200000000000000000000000000000000000006` (WETH) | manual_intervention |
| `token1` | `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913` (USDC) | manual_intervention |
| `fee` | 100 | manual_intervention |
| `tickLower` | == mint call 中的 tickLower | manual_intervention |
| `tickUpper` | == mint call 中的 tickUpper | manual_intervention |
| `liquidity` | > 0 | manual_intervention if 0 |
| `operator` | 通常为 `0x0` 或 wallet；不强求 | warn only |

## 失败处理 — 必须 manual intervention，不允许继续 hold/exit 自动流程

| failure | meaning | next action |
|---|---|---|
| `FAIL_TOKEN_ID_NOT_FOUND` | ERC721 Transfer event 未出现 | manual intervention；操作员手动 inspect tx；调查是否 mint reverted |
| `FAIL_MULTIPLE_TOKEN_TRANSFERS` | 同 receipt 出现多次 Transfer | manual intervention；可能合约异常或前后端 mismatch |
| `FAIL_TOKEN_ID_NOT_OWNED_BY_WALLET` | `ownerOf(tokenId)` ≠ wallet | manual intervention；可能 receipt 被改 / RPC 不一致 |
| `FAIL_POSITION_PARAMS_MISMATCH` | `positions(tokenId)` 的字段与 mint call 输入不一致 | manual intervention；可能 mint 中途参数被覆盖 |
| `FAIL_POSITION_LIQUIDITY_ZERO` | `positions(tokenId).liquidity == 0` | manual intervention；mint 实际未注入流动性 |

manual intervention 期间：
- **不允许** 自动 retry mint
- **不允许** 自动 decreaseLiquidity
- **不允许** 自动 collect
- **不允许** 启动后续阶段
- 写 telemetry: `manual_intervention_required=true, reason=<failure_id>`
- 操作员手动调查后决定下一步

## telemetry artifact 落盘

```text
reports/lp_base_10u_probe_execution_runtime/<RUN_ID>/mint_receipt.json
{
  "schema": "lp_probe_mint_receipt_v1",
  "tx_hash": "0x...",
  "status": "success|reverted|missing",
  "block_number": <int>,
  "block_hash": "0x...",
  "gas_used": <int>,
  "from": "0xb05b...d835",
  "to": "0x03a520b3...",
  "tokenId": <int|null>,
  "tokenId_hex": "0x...",
  "log_index_for_transfer": <int|null>,
  "owner_of_token_id_observed": "0x... or null",
  "positions_observed": {
    "token0": "0x4200...0006",
    "token1": "0x8335...2913",
    "fee": 100,
    "tickLower": <int>,
    "tickUpper": <int>,
    "liquidity": <int>,
    "feeGrowthInside0LastX128": <int>,
    "feeGrowthInside1LastX128": <int>,
    "tokensOwed0": <int>,
    "tokensOwed1": <int>
  },
  "validation_pass": true|false,
  "failure_id": null|"FAIL_TOKEN_ID_NOT_FOUND"|"FAIL_TOKEN_ID_NOT_OWNED_BY_WALLET"|"FAIL_POSITION_PARAMS_MISMATCH"|...,
  "manual_intervention_required": true|false
}
```

## 本轮不执行声明

本 stage 是文档定义；**未** 执行 mint，**未** 解析任何真实 receipt，**未** 调用任何 `eth_getTransactionReceipt` 或 `NPM.positions` 写入路径。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
mint_executed                 = false
token_id_extracted_this_round = false
can_run_probe_now             = false
execution_allowed_now         = false
```
