# TP-J FIX-J3 — CLMM 换腿成本口径核查

结论：待验假设成立。对于从 token1 单资产建立、并在入场价处于区间内的 CLMM 仓位，进入时只需买入 LP 所需的 token0 库存，退出到 token1 时只需卖出 token0 库存；两次都不是全仓名义金额。原实现对两腿各按全额仓位报价，属于系统性偏高的保守上界，不能冒充实际机制成本。

V3 在价格 `P`、区间 `[P(1-r), P(1+r)]` 的库存为 `x=L(1/sqrt(P)-1/sqrt(P(1+r)))` 与 `y=L(sqrt(P)-sqrt(P(1-r)))`。因此每次 token0 换腿的 USD 名义为 `V × xP/(xP+y)`；这不是硬编码 1/2，20% 对称区间的解析值为 0.452100…，并由单测锁定。没有 `range_pct` 的遗留历史敏感性报告继续使用全额，但代码/注释明确其是保守上界。

## 六个真实 paper 仓位：更正前后

|池|单腿成本前($)|单腿成本后($)|NetCover 前|NetCover 后|
|---|---:|---:|---:|---:|
|WETH-CBBTC|8.0192|3.8076|0.581473|0.610635|
|WETH-USDC (Aerodrome)|2.4523|1.1300|8.066278|8.249658|
|WETH-USDC (Uniswap)|8.7989|4.1516|1.340943|1.567880|
|WETH-BRETT|2.0900|0.9766|1.267564|1.317242|
|USDC-SAPIEN|4.5200|2.0671|0.657604|0.698287|
|VIRTUAL-USDC|3.0000|1.3699|0.060263|0.062508|

细节和每项成本分解见 `J3_RECONCILIATION_CORRECTED.{json,md}`；J1 的全额基线保留在相邻 `20260814_j1/`，因此前后值可重放、不可混淆。

## 固定快照 Base 复核

以 SQLite backup API 从 `reports/lp_scanner/scanner.db` 制作 `scanner.J3.snapshot.db`，旧代码为 `c9419d5`，新代码为本提交的工作树；均在同一 6,812 行副本上只读重放。为让历史行经过与生产入口相同的已审计 Base 协议映射，replay 在内存中为 Aerodrome Slipstream/Uniswap V3 补入 `protocol_type=clmm`，不写回数据库。

|闸|旧|新|结果|
|---|---:|---:|---|
|NetCover pass|51|61|+10（成本口径更正的预期变化）|
|NetCover fail|6761|6751|-10|
|PositionCap pass|3107|3107|不变|
|PositionCap fail|3705|3705|不变|
|重放行数|6812|6812|不变|

3,245 行的 entry/exit/slippage 数值依 V3 实际腿比例改变；只有 54 行的 gate 显示字段发生改变，其中 10 行穿过 NetCover 1.0。固定快照的逐行 JSON 对照在 `BASE_INVARIANCE_COMPARISON.json`，新旧完整逐行重放在 `base_snapshot_{pre,post}_j3.json`。这不是为提高通过率调整阈值：`NETCOVER_SHADOW=1.0` 与六个保护常量均未修改。
