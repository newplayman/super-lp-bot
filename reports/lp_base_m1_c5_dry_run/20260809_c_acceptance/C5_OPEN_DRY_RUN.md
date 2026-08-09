# C5 开仓 dry-run

- Base block: `49755184`
- pool: `0xd0b53D9277642d899DF5C87A3966A349A798F224` (Uniswap v3 WETH/USDC 0.05%)
- PositionCap: `60.0000 U`; planned: `50.00 U`
- tick range: `-200980 .. -200480`
- slippage hard limit: `75 bps`
- approve: exact amounts only; full calldata is in JSON
- mint simulate: `True`; gas: `390218`
- five preflights: `{'simulate': True, 'quote': True, 'basis': True, 'rpc_health': True, 'wallet_balance': True}`
- signed: `false`; keystore loaded: `false`; **broadcast_count: `0`**

此报告只证明构建与 eth_call 管路；不构成 C6 放行或 live 入场许可。
