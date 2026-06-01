# V3 Pool State ABI Inventory

- `token0()` read_only_safe=`yes` selected_for_v1=`yes` notes=`pool token0 address`
- `token1()` read_only_safe=`yes` selected_for_v1=`yes` notes=`pool token1 address`
- `fee()` read_only_safe=`yes` selected_for_v1=`yes` notes=`fee tier for v3-like pool`
- `tickSpacing()` read_only_safe=`yes` selected_for_v1=`yes` notes=`tick spacing and compression`
- `liquidity()` read_only_safe=`yes` selected_for_v1=`yes` notes=`current in-range liquidity`
- `slot0()` read_only_safe=`yes` selected_for_v1=`yes` notes=`current tick and sqrtPriceX96`
- `ticks(int24)` read_only_safe=`yes` selected_for_v1=`yes` notes=`liquidityGross/liquidityNet and feeGrowthOutside`
- `tickBitmap(int16)` read_only_safe=`yes` selected_for_v1=`yes` notes=`initialized tick bitset per word`
- `observe(uint32[])` read_only_safe=`yes` selected_for_v1=`yes` notes=`twap-like observation and liquidity cumulatives`
- `observations(uint256)` read_only_safe=`yes` selected_for_v1=`no` notes=`optional, only if direct observation row needed`
- `mint` read_only_safe=`no` selected_for_v1=`no` notes=`forbidden state-changing`
- `burn` read_only_safe=`no` selected_for_v1=`no` notes=`forbidden state-changing`
- `collect` read_only_safe=`no` selected_for_v1=`no` notes=`forbidden state-changing`
- `swap` read_only_safe=`no` selected_for_v1=`no` notes=`forbidden state-changing`
- `flash` read_only_safe=`no` selected_for_v1=`no` notes=`forbidden state-changing`
- `increaseLiquidity` read_only_safe=`no` selected_for_v1=`no` notes=`forbidden state-changing`
- `decreaseLiquidity` read_only_safe=`no` selected_for_v1=`no` notes=`forbidden state-changing`
- `multicall(state-changing)` read_only_safe=`no` selected_for_v1=`no` notes=`forbidden if any subcall changes state`

## Forbidden
- `mint`
- `burn`
- `collect`
- `swap`
- `flash`
- `increaseLiquidity`
- `decreaseLiquidity`
- `multicall(state-changing)`
