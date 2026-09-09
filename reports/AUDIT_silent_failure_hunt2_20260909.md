# 第二轮「静默假绿」猎杀审计报告（2026-09-09）

本轮审计严格聚焦于第一轮（`reports/AUDIT_silent_failure_hunt_20260909.md`）未覆盖的路径，重点排查了 `scripts/` 下非 `lp_rh_` 开头的经济计算、风控放行闸门、指标统计与回测/证据回写模块，以及 `tests/` 目录下的共享 fixture 与测试断言机制。

---

# 新发现（按危害排序）

### 1 | `scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py:58-64,259-260,303-316`
- **属于 21 类里的哪一类**：第 6 类（宽容默认值）+ 第 20 类（字典键名缺失默认导致错判）+ 第 15 类（量纲归一化失真）
- **触发条件**：
  在评估非固定 5 种代币的池子时（`PRICES_USD` 仅包含 `WBNB`、`USDT`、`USDC`、`BUSD`、`DAI`），或者池中代币 symbol 大小写不匹配 / 为空 / 为其他币（如 `CAKE`、`BTCB`、`ETH`、`FDUSD`）时，`PRICES_USD.get(...)` 默认返回 `Decimal("0")`。
  当 `p0_usd` 或 `p1_usd` 为 0 时：
  ```python
  vol0 = (Decimal(abs(d["amount0"])) / (Decimal(10) ** meta["token0_decimals"])) * p0_usd
  vol1 = (Decimal(abs(d["amount1"])) / (Decimal(10) ** meta["token1_decimals"])) * p1_usd
  v = max(vol0, vol1)
  volume_usd_proxy += v
  pool_fee_usd_proxy += v * fee_fraction
  ```
  若其中一个是计价稳定币（如 USDT），另一个是 CAKE（未在字典中），则 `v = max(vol0, 0) = vol0`，仅凭单边计算；若两个代币均不在字典中（例如 CAKE-WETH 或其他交易对），`vol0 = 0` 且 `vol1 = 0`，导致整个交易对被计算为 `volume_usd_proxy = 0` 且 `pool_fee_usd_proxy = 0`。
  更严重的是：当其中一边在字典中时，若该 token 精度不对或者属于反向流，`v = max(vol0, vol1)` 会静默把未命中端视作价值为 $0，导致滑点和成交量在某些方向上丢失甚至产生数量级低估。
- **错多少**：
  若遇到未在预设字典内的代币对，计算出的 `volume_usd_proxy` 直接从成千上万美金跌落为 `0`（相对误差 **-100%**）；对于单边未命中代币对，交易量/费率代理直接被截断或低估 50%~100%。不报任何异常，照常输出回填记录。
- **建议修法**：
  禁止在经济量计算中使用 `PRICES_USD.get(..., Decimal("0"))`。对未知资产价格必须返回 `None` 并将该 pool/window 标记为 `INPUTS_UNAVAILABLE` 或抛出未定价资产异常，严禁使用 0 作为价格默认值参与成交量乘积。

---

### 2 | `scripts/lp_survival_horizon_ev_model_v1_readonly.py:96-101`
- **属于 21 类里的哪一类**：第 6 类（宽容默认值）+ 第 8 类（手填经济假设与不连续台阶）
- **触发条件**：
  函数 `slippage_cost_usd(notional: float, capacity_proxy: float)` 中：
  ```python
  if capacity_proxy <= 0:
      return notional * 0.01  # worst case 1%
  return notional * (SLIPPAGE_BPS_AT_FULL_CAPACITY / 10000.0) * max(0.0, 1.0 - capacity_proxy)
  ```
  在满容量（`capacity_proxy = 1.0`）时，滑点被直接计算为 `notional * 0.005 * (1.0 - 1.0) = 0.0`！
  而在容量稍微低于 1.0（如 `0.99`）时，滑点仅为 `notional * 0.005 * 0.01 = 0.00005 * notional`（0.5 个基点）。
  但是，当 `capacity_proxy <= 0` 时，滑点瞬间跳跃为 `notional * 0.01`（100 个基点）。
  如果输入的池子未提供 `capacity_N` 字段，`cap = pool.get(cap_field, 0.0) or 0.0`，此时 `cap == 0.0`，滑点被硬编码赋值为 100 bps，掩盖了真实池子流动性不足或深度未测的事实；更关键的是在 `capacity_proxy = 1.0` 时算出的滑点恒为 0，相当于认定满额流动性下兑换无滑点。
- **错多少**：
  满容量时将实际存在的真实滑点（至少几个 bps）低估为 **0.0**；而在缺字段时直接硬塞 100 bps，跳跃达 **200 倍**，且输出数字表面看似正常（几美分到几十美分），使得生存期收益模型（EV）输出假正或假负。
- **建议修法**：
  不能用 `pool.get(..., 0.0)` 将缺失容量当成容量为 0，缺失时应置为 `None` 并中断；滑点必须基于实际 `dx / (L + dx)` 或已测定的深度曲线计算，不可在线性插值中把满容量算为 0 滑点。

---

### 3 | `scripts/strategy_pivot_d4_realtime_paper_shadow_validation.py:283-288`
- **属于 21 类里的哪一类**：第 1 类（原始比值当归一化价格）/ 第 15 类（量纲与刻度非线性误差）
- **触发条件**：
  在确定当前 tick 的价格区间上下界时：
  ```python
  def tick_lower_upper(current_tick, range_pct):
      """Return (lower_tick, upper_tick) for ±range_pct% around current tick."""
      # 1% price move ≈ 100 ticks (since 1.0001^100 ≈ 1.01005)
      delta = int(round(range_pct * 100))
      return current_tick - delta, current_tick + delta
  ```
  Uniswap V3 中价格与 tick 的精确数学关系是 $P = 1.0001^{\text{tick}}$。
  对于 $+r\%$，理论上 $\text{tick}_{\text{upper}} = \text{current\_tick} + \frac{\ln(1 + r/100)}{\ln(1.0001)}$；
  对于 $-r\%$，理论上 $\text{tick}_{\text{lower}} = \text{current\_tick} + \frac{\ln(1 - r/100)}{\ln(1.0001)}$。
  例如当 `range_pct = 5`（即 $\pm 5\%$）时：
  - 代码计算：`delta = 500` ticks。
  - 真实 $\text{lower}$: $\ln(0.95) / \ln(1.0001) \approx -512.9$ ticks（相差 **13 个 tick**）。
  - 真实 $\text{upper}$: $\ln(1.05) / \ln(1.0001) \approx +487.9$ ticks（相差 **12 个 tick**）。
  当 `range_pct = 10` 时：
  - 代码计算：`delta = 1000` ticks。
  - 真实 $\text{lower}$: $\ln(0.90) / \ln(1.0001) \approx -1053.6$ ticks（相差 **54 个 tick**）。
  - 真实 $\text{upper}$: $\ln(1.10) / \ln(1.0001) \approx +953.1$ ticks（相差 **47 个 tick**）。
- **错多少**：
  非线性对数偏移导致区间上下不对称：下界 tick 过高（区间变窄，过早判断为跌出区间），上界 tick 过高（区间变宽，过晚判断为涨出区间）。导致 `in_range` 判定在边界附近完全失准，手续费累积和在区间时间比例偏离实际经济行为，且对数误差随 `range_pct` 增大迅速放大。
- **建议修法**：
  使用精确公式计算 tick 边界：
  `lower_tick = int(math.floor(current_tick + math.log(1.0 - range_pct / 100.0) / math.log(1.0001)))`
  `upper_tick = int(math.ceil(current_tick + math.log(1.0 + range_pct / 100.0) / math.log(1.0001)))`

---

### 4 | `scripts/lp_survival_out_of_range_risk_v1_readonly.py:86-87`
- **属于 21 类里的哪一类**：第 6 类（宽容默认值）+ 第 8 类（手填常量伪造实际观测）
- **触发条件**：
  ```python
  if is_base_candidate and base_hist:
      sd_hr = base_hist.get("p95_abs_drift", 700) / math.sqrt(8.0)
  ```
  当 upstream monitor 的历史 CSV 文件不存在或为空时，`base_hist` 为空字典 `{}`；但若 `base_hist` 传入了一个缺少 `"p95_abs_drift"` 的字典（例如样本数少于 2 时返回 `{}`），或者使用了空值，默认值 `700` 会直接参与计算：
  `sd_hr = 700 / 2.8284 = 247.48` ticks/hr。
  而常量表 `TICK_STDDEV_PER_HR["Base"]` 的基准值是 `60.0` ticks/hr。
- **错多少**：
  默认值 700 产生的波动率是预设基准（60.0）的 **4.12 倍**！导致 Base 候选池计算出的出界风险（`oor_risk`）被人为严重夸大，原本存活率大于 80% 的安全窗口被误判为 `high` 风险，将合格池子全数拒之门外，而没有任何日志或警告提示“缺少真实 p95 观测”。
- **建议修法**：
  缺失 `"p95_abs_drift"` 时严禁回退到手填魔数 700；必须显式使用已校准的系统基准值 `TICK_STDDEV_PER_HR["Base"]`，或者直接将该特征标记为数据不可用。

---

### 5 | `scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py:165-173`
- **属于 21 类里的哪一类**：第 4 类（补码与位宽截断错误）
- **触发条件**：
  PancakeSwap V3 的 Swap 事件中，`tick` 是 `int24`（有符号 24 位整数）。
  在 EVM ABI 编码中，每个槽位是 32 字节（256 位）。
  代码实现为：
  ```python
  def to_int(h: str, signed: bool, bits: int) -> int:
      full = int(h, 16)
      mask = (1 << bits) - 1
      v = full & mask
      if signed and v >= (1 << (bits - 1)):
          v -= 1 << bits
      return v
  ```
  在 PancakeSwap V3 合约触发日志时，若合约使用标准 ABI 编码，`int24` 往往在整个 256 位槽中进行了符号扩展（即负 tick 前面填充了 `f`）。若按照 `full & mask` 截断后再做 `v >= (1 << (bits - 1))`，虽然当该字段严格对齐在最低 24 位且无其他位时能勉强还原，但一旦上游节点或 ABI 解码器对紧凑打包或不同版本的 PancakeSwap 槽位采用高位对齐（或非标准补码填充），截断逻辑将静默读出错误的正数 tick。
- **错多少**：
  若发生偏移或扩展不一致，负数 tick（例如 -2000）将变成正数（如 +16775216），导致 tick 价格转换发生天文数字级偏离（$1.0001^{16775216} \to \infty$）。
- **建议修法**：
  遵循标准库或显式校验槽位的高位是否符合符号扩展规则：`if signed: int.from_bytes(bytes.fromhex(h)[-3:], "big", signed=True)` 并断言前 29 字节要么全 0 要么全 0xff。

---

# 已查过但判定为安全的路径

- `scripts/lp_pool_resolve_and_rank_v1_readonly.py`：检查了 `composite_score`、`_project_key`、`_coerce_list`，对于 wash_flag、非 OK 状态均直接截断返回 0.0，未发现假绿放行。
- `scripts/lp_netcover_engine_v1_readonly.py`：`evaluate_netcover` 和 `absolute_profit_gate` 中的 `_finite` 与 `_amount` 校验严格，非有限数值会抛出 ValueError 阻断。
- `scripts/lp_swap_cost_model_v1_readonly.py`：`slippage_bps_for_swap`、`price_impact_frac` 和 `human_liquidity` 均使用了严密的非正数与分母防御（返回 0.0 或 clamp），无除以零导致的静默溢出。
- `scripts/lp_c6_preflight_v1_readonly.py`：广播锁、RPC 探测、文件权限等检查均使用严格布尔判断，失败时 `passed=False`，无宽松吞异常放行行为。
- `scripts/lp_stock_tier_policy_v1_readonly.py`：`evaluate_position` 和 `evaluate_c_gate` 均具有完整的 FAIL_CLOSED 保护，任何无效的数字输入（如 NaN、None、负数）均会进入异常分支并置失败标志。
- `tests/conftest.py`：审计了 collection 忽略项和 `LEGACY_ENVIRONMENT_BOUND_NODEIDS`，所有 skip 标记均有明确的归档说明，未发现静默压制常规核心逻辑断言的情况。

---

# 我不确定的

1. `scripts/strategy_pivot_d3_aerodrome_reward_edge.py:219`
   - 代码片段：`fee_per_dollar_per_day = R4C_FEES[pool_addr].get(rng, 0.005)`
   - 疑问：当 `rng` 不在 `R4C_FEES[pool_addr]` 预设键中时，回退到 `0.005`（即每日千分之五的手续费收益假设）。如果这是纯离线研究脚本而非生产决策闸门，其危害仅限于回测预期虚高；但尚未确认上游是否有自动化流水线依赖此回测结果做出上机决定。

2. `scripts/lp_evm_v3_pool_readiness_probe_v1_readonly.py:310`
   - 代码片段：`out[f"capacity_{n}"] = 1.0 if liq > n * 10**6 * 100 else 0.0`
   - 疑问：在未配置 Quoter 节点时，粗暴地根据池子原始流动性是否大于金额的 100 倍赋予 `1.0` 或 `0.0`。这里的 `liq` 既未考虑代币 decimals 差异（假定恒为 6-decimal stable），也未考虑集中流动性分布。由于下游可能读取该字段用于滑点计算，存在导致滑点评估过低的不确定性。
