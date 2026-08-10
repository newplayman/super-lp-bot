# LP universe second opinion v1（0 RPC）

范围：Base / aerodrome-slipstream, uniswap-v3；全网快照 15581 条，范围内 731 条。
proxy 可计算 727；proxy NetCover≥1 为 132，同时过 Stage-1 粗筛为 55，再同时 entry_eligible 为 34。
proxy 只用于第二意见与排序，不是入场闸；终端全成本 NetCover 与完整合取仍是唯一结论来源。

| # | 池 | quality | coarse | entry | proxy NC | IL 容忍 APR | coarse 原因 |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | USDC-PROS | B | True | False | 86.0214 | 21918.390% | ok |
| 2 | USDC-VFY | B | False | False | 81.6668 | 11738.711% | TVL 29922 < 150000 |
| 3 | WETH-USDC | A | False | False | 37.5841 | 1119.667% | TVL 146918 < 150000 |
| 4 | USDC-VELVET | B | True | False | 23.8798 | 4540.051% | ok |
| 5 | EURC-USDC | A | True | True | 22.7710 | 30.550% | ok |
| 6 | WETH-CBBTC | A | True | True | 16.8383 | 424.647% | ok |
| 7 | USDC-CBBTC | A | False | False | 16.5513 | 1144.503% | TVL 27101 < 150000 |
| 8 | WETH-COOKIE | B | False | False | 14.4249 | 246.624% | TVL 62322 < 150000 |
| 9 | USDC-CBBTC | A | True | False | 13.7996 | 662.110% | ok |
| 10 | MEZO-MUSD | C | False | False | 13.7204 | 601.006% | TVL 12795 < 150000 |
| 11 | CTR-USDC | B | True | False | 13.6737 | 4941.264% | ok |
| 12 | MSUSD-USDC | A | True | True | 12.1313 | 23.384% | ok |
| 13 | QUID-USDC | B | False | False | 11.2744 | 261.645% | TVL 43918 < 150000 |
| 14 | WETH-MSETH | A | True | True | 9.2565 | 17.345% | ok |
| 15 | XSGD-USDC | B | True | True | 9.0510 | 14.301% | ok |
| 16 | CADC-USDC | B | False | False | 9.0411 | 29.937% | TVL 129000 < 150000 |
| 17 | TOWNS-WETH | B | True | False | 9.0403 | 119.593% | ok |
| 18 | VLTX-WETH | B | False | False | 8.3052 | 33.831% | TVL 36734 < 150000 |
| 19 | HYPE-WETH | B | True | False | 7.3001 | 54.307% | ok |
| 20 | PROMPT-USDC | B | False | False | 7.2283 | 82.164% | TVL 101075 < 150000 |
| 21 | WETH-TIBBIR | B | True | False | 7.0670 | 110.827% | ok |
| 22 | SOL-WETH | B | False | False | 6.8515 | 84.198% | TVL 63330 < 150000 |
| 23 | GITLAWB-USDC | B | False | False | 6.1776 | 283.513% | TVL 17300 < 150000 |
| 24 | TGBP-FRXUSD | C | False | False | 6.0432 | 7.322% | TVL 60693 < 150000 |
| 25 | WETH-SURPLUS | B | False | False | 5.8052 | 135.199% | TVL 22734 < 150000 |
| 26 | WETH-COOKIE | B | False | False | 5.7998 | 89.766% | TVL 69984 < 150000 |
| 27 | SOSO-USDC | B | True | True | 5.4111 | 8.075% | ok |
| 28 | WETH-REPPO | B | False | False | 5.0092 | 187.138% | TVL 28684 < 150000 |
| 29 | WETH-KAITO | B | False | False | 4.8633 | 97.748% | TVL 17067 < 150000 |
| 30 | USDC-CBBTC | A | True | False | 4.6928 | 32.822% | ok |
| 31 | WETH-REPPO | B | False | False | 4.6592 | 148.308% | TVL 10285 < 150000 |
| 32 | CBETH-CBBTC | A | True | False | 4.6054 | 75.254% | ok |
| 33 | WETH-REI | B | False | False | 4.5826 | 300.184% | TVL 18446 < 150000 |
| 34 | USDC-ACU | B | True | False | 4.0836 | 87.625% | ok |
| 35 | USDC-TITN | B | False | False | 4.0721 | 200.242% | vol1d 241 < 50000 |
| 36 | WETH-CBBTC | A | True | True | 4.0090 | 69.099% | ok |
| 37 | WETH-CBBTC | A | True | True | 4.0045 | 12.570% | ok |
| 38 | ECHO-WETH | B | False | False | 3.9670 | 62.434% | TVL 20527 < 150000 |
| 39 | WETH-USDT | A | True | True | 3.7959 | 16.437% | ok |
| 40 | USDC-AVAIL | B | False | False | 3.7445 | 16.896% | TVL 125530 < 150000 |
| 41 | WETH-USDC | A | True | True | 3.6860 | 61.739% | ok |
| 42 | WETH-EURC | A | True | True | 3.6564 | 15.423% | ok |
| 43 | OUSDT-USDC | B | False | False | 3.6521 | 3.851% | TVL 102427 < 150000 |
| 44 | RAVE-USDC | B | True | True | 3.4770 | 144.150% | ok |
| 45 | WETH-VELVET | B | False | False | 3.4186 | 68.097% | TVL 12778 < 150000 |
| 46 | RECALL-USDC | B | True | True | 3.1948 | 35.398% | ok |
| 47 | TRUST-USDC | B | True | True | 3.1745 | 3.964% | ok |
| 48 | EURC-USDC | A | True | False | 3.1493 | 3.016% | ok |
| 49 | EURC-CBBTC | A | True | True | 3.1468 | 10.090% | ok |
| 50 | USDC-USDT | A | True | True | 3.1381 | 3.104% | ok |
