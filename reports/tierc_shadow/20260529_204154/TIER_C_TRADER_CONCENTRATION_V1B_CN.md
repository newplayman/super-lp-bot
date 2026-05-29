# Tier C Trader Concentration V1B

- coverage: 7/15
- 方法: Base RPC `eth_getLogs` 分片读取 24h swap logs，按 sender/recipient 做 unique trader 与 tx-share proxy concentration。
- 未覆盖池主要是非标准 pool_id 或无可解析 swap logs。
