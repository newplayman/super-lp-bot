# MARKET SNAPSHOT M0

**as_of:** 2026-08-08T18:25:18Z（UTC）  
**用途边界：** M0 shadow 背景快照，不是执行价格、入场授权或未来可用性承诺。所有链上动作仍须运行时重读；本文件只记录一次免费公开重核。

## 1. 公共 RPC 能力与限制

| 网络 | 本次只读实测 | 当前官方能力/限制 | 直接来源 |
|---|---|---|---|
| Solana mainnet | `getSlot` → `438043340`；随后两个真实 xStocks pool `getAccountInfo` 均返回非空账户 | 官方 mainnet endpoint 为 `https://api.mainnet.solana.com`；100 requests/10s/IP、单 RPC 方法 40/10s/IP、40 并发、100MB/30s；官方明确公共端点不面向生产且限额可变。项目 WP01 以 ≤50% 配额预算轮巡。 | [Solana clusters/public RPC](https://solana.com/docs/references/clusters), `https://api.mainnet.solana.com` |
| Base mainnet | `eth_chainId` → `0x2105` (=8453)；`eth_blockNumber` → `0x2f68bd6` | 官方 Standard HTTP/WSS 均存在：`https://mainnet.base.org` / `wss://mainnet.base.org`；另有 Flashblocks HTTP/WSS。公共端点 rate-limited、not for production，官方未给本页固定数值配额。**这修正了旧附录“无公共 WSS”的过时说法。** | [Base connect](https://docs.base.org/base-chain/quickstart/connecting-to-base), [Base RPC overview](https://docs.base.org/base-chain/api-reference/rpc-overview), `https://mainnet.base.org` |

Solana 账户证据：

- Raydium `6truu3rZuiB9rKQg4VYC3Dt3QwV7DgwGqXrYUcrvnDDE`：owner `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`，space 1544，slot 438043367。
- Orca `Fae5dWVntUt6zbWu2voXxioDpMii7SqQwtsxBmoVCsHR`：owner `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`，space 653，slot 438043367。
- 这只证明 WP01 registry 的 slot/account read 能力；当前 Python paper runner 的 swap decoder 仍是 EVM-only，**不得称为完整 Solana LP tick**。

## 2. xStocks 当前池清单

识别口径：先一次 GET [xStocks 官方 token inventory](https://api.backed.fi/api/v1/token?type=xstocks)（641 token nodes），取 `deployments.network=Solana` 的 mint；再分别与 DEX 官方 API 当次返回的 token mint 做精确匹配。名称相似但 mint 不匹配的不计。

### Raydium API v3

直接来源：[Raydium API v3 文档](https://docs.raydium.io/api-reference/api-v3-endpoints/pools/get-pools-by-token-mint)；本次 GET `https://api-v3.raydium.io/pools/info/list?poolType=all&poolSortField=liquidity&sortType=desc&pageSize=1000&page=1`。返回 success=true、1000 rows、`hasNextPage=true`，其中精确匹配 36 个池。因此下表是**本次 top-1000 响应中的完整匹配清单，不是 Raydium 全协议穷举清单**；页外池标记为 unavailable/unverified，不能据此断言不存在。

| pool | xStock | pair | TVL USD | 24h volume USD |
|---|---|---|---:|---:|
| `6truu3rZuiB9rKQg4VYC3Dt3QwV7DgwGqXrYUcrvnDDE` | SPYx | SPYx/USDC | 2,754,797.60 | 437,266.90 |
| `GMjGLWzvK75LPetrgAmdeXnvxc4fUuQPwJxeQqTDU1aG` | QQQx | QQQx/USDC | 2,661,428.21 | 465,234.32 |
| `G39wywquKbHK8F2wZZZFX3fcsyG91VCCbbr6WEVp5axy` | CRCLx | CRCLx/USDC | 2,598,976.84 | 777,394.85 |
| `49iMatQtoyabsYAQc8GafVq6aeBFVDxSRH44oiatyyw6` | NVDAx | NVDAx/USDC | 2,462,895.22 | 287,131.22 |
| `8aDaBQkTrS6HVMjyc6EZebgdiaXhLYGriDWKWWp1NpFF` | TSLAx | TSLAx/USDC | 1,895,611.24 | 247,193.35 |
| `GYqHjuDzTiw7i52Xv1qohDE6eJr6eSZpsrBVikGZyaFV` | CRCLx | CRCLx/USDC | 1,830,147.98 | 127,492.89 |
| `w7SGmPeXoMCsjvXqgsAmUn56uypyDsjAtsxeVkaiqxa` | COINx | COINx/USDC | 715,313.67 | 122,641.11 |
| `AHNN6JmvaGG6XUoSg7sEr38gRYDB2jTbUvqXVuqaRHpq` | SPCXx | SPCXx/USDC | 632,673.34 | 467,250.14 |
| `DU9dgBU6Yh2JjsYcjtRY21G14dhQxn6Xm5PT949Sa4tA` | STRCx | STRCx/USDC | 578,139.07 | 7,044.37 |
| `HHQUnUbmWLrYzkscDY1C3deEFbGtiGBGoHjpANogmvum` | TSLAx | TSLAx/USDC | 572,261.96 | 14,070.49 |
| `2ngTuP7xA581dqX9uJkGRqxmKuehY3k4SDfPebeoRG2J` | MSTRx | WSOL/MSTRx | 549,885.35 | 266,342.74 |
| `7WQcQi2dDgZDnpJKwoY7F9cALk3QEUG4kAyhtjZVkVa1` | GLDx | GLDx/XAUt0 | 449,877.11 | 61,118.47 |
| `DXWbip5LducMAbDSSpLYz9Xik3253EPeAYQufQtx7LXs` | HOODx | HOODx/USDC | 385,101.11 | 26,417.34 |
| `7a8xxAJBELDo6P9dikSYctdw6ce8F4mWr3ahcAD8Ao49` | SPYx | SPYx/STONK | 383,785.93 | 963,455.76 |
| `RyhF4cksVZY7vcqJpoytHcxcGNKRp27PEGhSnEPpbGv` | MSTRx | MSTRx/USDC | 365,433.87 | 169,019.71 |
| `6m5aXAve4uh6Kt4ytKyCLWNMjd8PYP5vujwNCtycrUiD` | AMZNx | AMZNx/USDC | 355,087.39 | 88,399.87 |
| `78ReVNMLGRWmjtf2HmBoHUe2pRcsctXTTbxJnbhchyze` | GLDx | GLDx/USDC | 354,810.98 | 336,201.15 |
| `4pCZCVEiYyT4efNdXUdL2tJF8VGMgiMXrZWq6FiNXhRw` | SPYx | SPYx/USDC | 311,181.44 | 1,296,904.08 |
| `CLu4kFM4nb67xrdN7vJnMxXXir8Z5hA4HJUzPFccXjsL` | MSFTx | MSFTx/USDC | 277,990.80 | 15,634.88 |
| `B8YAwjGYk6qidWzGBXMAxP7nYfG8g74EZ3Y4gFSsobRw` | GOOGLx | GOOGLx/USDC | 275,811.73 | 15,677.06 |
| `9NJ7rtJzEnfwvoM6HyB2v6YHcsfS6ZY9DFGprphVX6W` | COINx | WSOL/COINx | 210,368.34 | 66,045.69 |
| `4KqQN6u1pFKroFE2jVEhoepAMRKPcuAzWVDCgm9zRBYN` | NVDAx | NVDAx/USDC | 154,425.57 | 8,415.80 |
| `7sHMnvE7WqP7vQFWJGEnMT4vZg6Za9K7PpddDoXJCqME` | SPYx | SPYx/USDC | 137,903.85 | 808.53 |
| `FknDV1F5n6QaA7rLmjquDjuU6wcPMNm5RYq7zWbqhpZw` | QQQx | QQQx/USDC | 133,203.11 | 2,484.10 |
| `EkpbWmPzrzFsv2xkJRdvWs61aRuDBVdrJK7WQmctBFnB` | AVGOx | AVGOx/USDC | 129,478.24 | 1,333.69 |
| `3LbRQkdRnahJfAEBBRajCMki8ZBMhBhidmxbgMzp8nVu` | COINx | COINx/USDC | 122,165.10 | 5,421.32 |
| `B6FEtQdwsq8Wuw4G52pW9WEWEA7ALGfyUgXDRKigDSHH` | QQQx | WSOL/QQQx | 121,939.64 | 29,580.41 |
| `DUzBLHZ5RZdftPuWVijsvjupndogRM1adGJpsR7YTJro` | SPCXx | SPCX/SPCXx | 118,712.17 | 667,359.97 |
| `3zozghHn3cCmbAVPF3Bm5AiyT7VorSdHwTt2qJjLfDo2` | CRCLx | WSOL/CRCLx | 105,649.89 | 11,723.15 |
| `DppCVaAGq5VA9gGK32u21JNqBf5d7jqH7RGDEvj39gQY` | STRCx | STRCx/USDC | 102,478.76 | 1,783.35 |
| `BS9uyGV6XmNnPkM4f3xgxCdQEaFv7RSKs6fwrpvYHxfL` | SPYx | WSOL/SPYx | 102,271.39 | 210,357.93 |
| `3L7KbPVaAQA4UTecaGQYsm6UCq5F3sZM9zAYkxqYt63j` | METAx | METAx/USDC | 101,051.70 | 15,208.51 |
| `92ntxmz5vWkRAE1iSQ9HpX7y6bxMiNTaMf1Sh6rSa9BC` | GLDx | GLDx/XAUt0 | 98,158.35 | 1,256.81 |
| `CKmjDiqBCRqR8xk5FjnFiQXuCFsGchiLv9YwYVnE5RJ8` | TSLAx | WSOL/TSLAx | 76,671.95 | 18,272.11 |
| `CKwJZwm7oj3nu4653N1EpDrqXbXAYXoPFiPeEnLouF8y` | AAPLx | AAPLx/USDC | 59,460.89 | 36,208.81 |
| `6HqstnfN8RN5sAdRZMCr88tD2GKpuWBjRntwyKxLG75V` | MCDx | MCDx/FRIES | 54,897.07 | 159,193.86 |

Raydium response 的 `day.fee` 对这些行均为 null；本文没有用 APR 倒推或伪造 fee。

### Orca Public API

直接来源：[Orca API 文档](https://docs.orca.so/api-reference/whirlpools)；本次 GET `https://api.orca.so/v2/solana/pools?sortBy=tvl&sortDirection=desc&size=1000&stats=24h,7d`。返回 1000 rows、`meta.next=null`，精确匹配 38 个池；这是该响应内完整匹配清单。

| pool | xStock | pair | feeRate raw | TVL USD | 24h volume USD |
|---|---|---|---:|---:|---:|
| `Fae5dWVntUt6zbWu2voXxioDpMii7SqQwtsxBmoVCsHR` | SPYx | SPYx/USDC | 200 | 210,251.79 | 107,741.97 |
| `9crUEFyBGQ1psMqpEVe4SzriVjZ2BFPpbEBEbQrvgLmx` | GLDx | GLDx/USDC | 3000 | 132,986.93 | 13,646.75 |
| `6R4r93V5fcMzc13CL2enEepDSYcr4Qx3ptZBDwudTXCo` | NVDAx | NVDAx/USDC | 200 | 130,888.01 | 37,261.26 |
| `9p7abUFv31ycgu9kckvnoqMMvBy67dqTDM2m6HP9xokN` | TSLAx | TSLAx/USDC | 200 | 106,634.91 | 2,547.87 |
| `Bztq1RwZmU4L7cCnkh5pVz4LnRZ2YUMBzQ5VC2ETg789` | TQQQx | TQQQx/SPYx | 10000 | 82,514.18 | 2,373.30 |
| `5bY2fh9rgTYaBDxFGFJmddhaDkm5zwiWP6b2ZsjJZyP` | PLTRx | PLTRx/USDC | 6500 | 66,580.46 | 95,477.46 |
| `Cp2Uze3Zn7SUGoJ9HkG14Q5ykmAYLjBMnL7Q13GKFmsZ` | GMEx | GMEx/USDC | 20000 | 28,665.70 | 9,936.40 |
| `5wZoi4gUp8PxZHMgCTDSyDDQDoem5t2vFKh4p4oTPNaH` | CRCLx | SOL/CRCLx | 20000 | 20,343.21 | 506.13 |
| `HuAhgQ8EV9s6GGufF6Vb9gSSSiaXm9SeK2JLpQivaLST` | CRCLx | CRCLx/USDC | 3000 | 19,777.31 | 194.49 |
| `3GVB4bXtcrP3MM376mrcJDwfTNThvyorLmVgSTf6kxFt` | QQQx | QQQx/USDC | 1600 | 16,307.13 | 1,085.22 |
| `gef4pD5g6GJSjX7hfXKUfhCVpE89BzX9TXnXJNW6kSt` | SPYx | SPYx/USDC | 100 | 13,431.78 | 6,900.69 |
| `HxrqS96uHco2a8LxTvUwb9e2tS963Ec6nYkvZso9TDii` | GLDx | SOL/GLDx | 3000 | 13,064.60 | 13,275.50 |
| `BG7f49R2sb2UBCMu3AHuDmgDRyzqVgeMpDEk9S9gvQhy` | KOx | KOx/USDC | 6500 | 13,018.89 | 34,867.76 |
| `qS1KtqE4UK61pM3BB3YYTCB6YaeUMoWPeJdghgTzb7q` | GLDx | GLDx/XAUt0 | 1600 | 11,147.76 | 306.90 |
| `5ThN8VGdJvRQUQcejyrGbe6KMpmuurgEw5q9J3L8qsK3` | CRCLx | CRCLx/USDC | 200 | 10,942.23 | 1,391.86 |
| `5bw4rMm8eHoo38dCh1UhLvebvrYHiTGLYnvLxK1XD6Z2` | GMEx | GMEx/USDC | 10000 | 9,605.98 | 49,882.29 |
| `CN32jwmQBFHM4NYrgkxefihRK8boR8M9n4RUBvgLe816` | SPCXx | SOL/SPCXx | 1600 | 8,244.70 | 18,367.70 |
| `FTw5jCaWibNK8GeeJXAy8dEWW57UxZquX82P7vZbSoBJ` | SPCXx | SPCXx/NVDAx | 10000 | 7,459.39 | 1,338.20 |
| `HzyHKnwmRnnu3yZKzvqfhm2VeWo8V4qWtyNVGVLXrcjC` | MSTRx | SOL/MSTRx | 10000 | 6,958.33 | 1,108.41 |
| `9rC9wbXD16odLdNzhgk1nacZwXJPRn74auDNmFhSJLZ7` | HOODx | HOODx/USDC | 10000 | 6,319.64 | 4,539.63 |
| `9cAwQoDuGFnzRYamnfcWYYCNuUxEBVKcs9JWuuudiQCN` | TQQQx | TQQQx/USDY | 10000 | 6,310.70 | 59.88 |
| `A4D97SV1dfCffDo58FEJtZoYycqVTaGVZiDdLiZffDNK` | COINx | SOL/COINx | 1600 | 5,956.09 | 8,769.62 |
| `EBJyPRtXTiUtjKZ5JDNLPmdjTyat48jEpmSD5VDLrHyq` | NVDAx | SKHY/NVDAx | 3000 | 5,940.56 | 133.43 |
| `EjKgT6qpSjgocwFAetsdJVA3XVRMh7EhnUuY3dJ8CwCh` | DFDVx | DFDVx/USDC | 500 | 5,778.78 | 0.16 |
| `5i53aEmnkx28vFcXYsr6ZQApvUDKDgqEeE8uvdHMMu1q` | MCDx | MCDx/USDC | 20000 | 5,752.91 | 3,795.62 |
| `HiyUy53Ytjfw2Wz2Rs6n5y3AVYc9r4w9sx3nX9HoWbzy` | QQQx | QQQx/SPYx | 1600 | 5,474.38 | 146.80 |
| `BCvzjDbADhnT3K35kc5TSeMAafNgu9KZVywUq9zWH2mA` | MSTRx | MSTRx/USDC | 400 | 5,349.73 | 12,742.75 |
| `DauJvXRsc5YUtabDd2jGTcSvTn63qpmteGcVGkRcjBGa` | SPYx | SPYx/USDY | 10000 | 5,094.16 | 0.00 |
| `BtTEuKWDnujPVUmYe9uhcp7sH9fq1H4enYnDbWdompX6` | DFDVx | SOL/DFDVx | 20000 | 4,436.22 | 684.29 |
| `FaGxc8NXSXBrT6idTxjw3o8et4MmFjxRMQvVF7ChsgZV` | GOOGLx | GOOGLx/USDC | 3000 | 4,285.86 | 485.31 |
| `7ouGUDRMy4C9RJpTgPizRyfcxyJusAEe9ZbjqYv7BSqe` | COINx | COINx/USDC | 1600 | 4,171.00 | 12,694.82 |
| `7gNaoXga7LS5mtnm5k4RLsn1uMdokfgWK1WhhSjX4B8L` | GMEx | GMEx/USDC | 10000 | 4,114.64 | 209.85 |
| `7mYFrN2TQtYc2HMZEXuVfWkPu9n5EFfX9Ha59X3n6PWE` | QQQx | QQQx/SPYx | 500 | 3,784.22 | 1,702.34 |
| `9zxCtrokbSGApeqFBr1LC3BzTb3drYQj4fmH6sT7Zxym` | MCDx | SOL/MCDx | 10000 | 3,088.91 | 4,871.63 |
| `2isk3qMgAtB8Pmc2wUJAt7ZnoeGkgKfVYnuR9RU86S6z` | SPCXx | SPCXx/EDS | 3000 | 2,697.64 | 184.84 |
| `6m6UoVxnmGePnHQ8V6gGrgDba5p1v7MCpM9Ji1LBBVPJ` | SPYx | SPYx/USDT | 100 | 2,576.36 | 0.00 |
| `4RbPzfze9MsZ1Y6z3N5G8unFm3NYHpY7caHxnSeg7UzJ` | PLTRx | SOL/PLTRx | 6500 | 2,496.43 | 5,459.35 |
| `26UY4D6pBHgxYdPWuBP3sfyc4jJf6qQjPDxCJPhtUx3H` | TSLAx | SOL/TSLAx | 20000 | 2,108.03 | 4.83 |

`feeRate` 保留 Orca API raw integer，不在快照中擅自换算；38 行 `stats.24h.rewards` 当次均为 0。

## 3. DefiLlama 当前数字

| 项 | 当前值 | 直接来源 |
|---|---:|---|
| Uniswap v4 TVL | $772,791,421.73 | `https://api.llama.fi/tvl/uniswap-v4` |
| Uniswap v4 Base TVL | $43,176,817.62 | `https://api.llama.fi/protocol/uniswap-v4` → `currentChainTvls.Base` |
| Uniswap v4 Robinhood Chain TVL | $34,894,301.77 | `https://api.llama.fi/protocol/uniswap-v4` → `currentChainTvls["Robinhood Chain"]` |
| Uniswap v4 volume 24h / 7d / 30d | $674,946,254 / $4,756,322,270 / $25,569,658,475 | `https://api.llama.fi/summary/dexs/uniswap-v4?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true&dataType=dailyVolume` |
| Uniswap v4 fees 24h / 7d / 30d | $1,231,049 / $7,844,181 / $36,165,755 | `https://api.llama.fi/summary/fees/uniswap-v4?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true&dataType=dailyFees` |
| Robinhood Chain total TVL | $468,662,074.31（chainId 4663） | `https://api.llama.fi/v2/chains`（按 name 精确筛选） |
| Robinhood Chain 股票代币 AMM 构成 | **unavailable / 未证实** | DefiLlama chain total 不提供股票代币 AMM 构成拆分；不得拿总 TVL 冒充股票代币 AMM TVL。 |

## 4. 时效与失败语义

- API 数字是 2026-08-08T18:25Z 附近的一次响应，缓存/索引延迟由提供方决定；runner 不得把本文件当实时 oracle。
- Raydium 当次 `hasNextPage=true`，因此“页外无池”不可证；本文明确记为 unavailable/unverified。
- xStocks 官方 quote 在周末可能没有 bid/ask；这与 token inventory/pool inventory 是不同接口。本快照只证明 metadata/pool 列表，不证明当前可赎回、可交易或 anchor 新鲜。
- Uniswap v4 hook/LP fee/protocol fee 必须运行时读链；DefiLlama 汇总数不能满足 INV-V4-01。
