# BSC PancakeSwap V3 扩展设计

Chain: BSC (chain_id=56), Protocol: PancakeSwap V3

- 合约地址（官方文档来源）:
  - PancakeV3Factory: 0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865
  - PancakeV3PoolDeployer: 0x41ff9AA7e16B8B1a8a8dc4f0eFacd93D02d071c9
  - SwapRouterV3: 0x1b81D678ffb9C0263b24A97847620C99d213eB14
  - NonfungiblePositionManager: 0x46A15B0b27311cedF172AB29E4f4766fbE7F4364
  - QuoterV2: 0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997
  - TickLens: 0x9a489505a00cE272eAa5e07Dba6491314CaE3796
  - SmartRouter: 0x13f4EA83D0bd40E75C8222255bc855a974568Dd4

- 目标候选: WBNB/USDT, WBNB/USDC, ETH/USDT, BTCB/WBNB, BTCB/USDT, CAKE/WBNB, CAKE/USDT, FDUSD/USDT, USDT/USDC
- 费用层级采用动态发现+保守测试（0.01/0.05/0.25/1）
- 严格只读：不 swap/mint/signature/wallet
