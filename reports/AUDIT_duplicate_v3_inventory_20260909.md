# 调研报告：V3 仓位流动性 / 两腿数量 重复实现审计与整合方案

**报告日期**：2026-09-09  
**基准实现**：`scripts/lp_rh_v3_inventory_v1_readonly.py:inventory_for_position`（Decimal 高精度）  
**审计背景**：针对仓库中多处独立计算 Uniswap V3 仓位流动性（$L$）及两腿代币数量的实现进行数值对账、语义甄别、风险定级与整合设计。

---

## 一、一致性实测表（6 处 × 2 组 quote 的实际数值）

### 测试输入配置
- 基础参数：`size_usd = 1000`，`entry_price = 2484`（token1 per token0，即 USDC/WETH），`range_pct = 10`（$\pm 10\%$），`dec0 = 18`（WETH），`dec1 = 6`（USDC）。
- 线性价格区间：$P_{lower} = 2484 \times (1 - 0.10) = 2235.6$，$P_{upper} = 2484 \times (1 + 0.10) = 2732.4$。
- 对比两组 quote：
  - **组 A（`quote = 1.0`）**：1 token1 = $1.00 USD（如 USDC 完全针对于 USD 锚定）。
  - **组 B（`quote = 0.99`）**：1 token1 = $0.99 USD（脱锚场景，获得 $1000 USD 需购买更多 token1 计价资产）。

### 实测数值汇总表

| 编号 | 代码位置与函数 | 计算精度 / 类型 | 组 A (`quote=1.0`) 输出 | 组 B (`quote=0.99`) 输出 | 与基准对比结论 |
|:---|:---|:---|:---|:---|:---|
| **1 (基准)** | `scripts/lp_rh_v3_inventory_v1_readonly.py`<br>`inventory_for_position` | `Decimal` (prec=60) | **$L_{raw}$**: `205043081922807.992...`<br>**$q_{0,raw}$**: `191457128737724882.539...`<br>**$q_{1,raw}$**: `524420492.215...`<br>**$q_{0,human}$**: `0.1914571287...`<br>**$q_{1,human}$**: `524.420492215...`<br>**Recon USD**: `1000.000` | **$L_{raw}$**: `207114224164452.517...`<br>**$q_{0,raw}$**: `193391039129015032.868...`<br>**$q_{1,raw}$**: `529717668.904...`<br>**$q_{0,human}$**: `0.1933910391...`<br>**$q_{1,human}$**: `529.717668904...`<br>**Recon USD**: `1000.000` | **基准规范实现**。<br>准确响应 `quote` 脱锚对建仓规模的逆向缩放。 |
| **2** | `scripts/lp_v3_fee_share.py`<br>`position_liquidity_raw` | `float` (IEEE 754 64-bit) | **$L_{raw}$**: `205043081922808.22`<br>*(两腿未直接返回)* | **$L_{raw}$**: `205043081922808.22`<br>*(无 quote 参数，输出不变)* | `quote=1.0` 时与基准**一致**（相对误差 $< 10^{-14}$，仅浮点舍入差异）。<br>`quote≠1` 时**不一致**（偏差 1.01%）。 |
| **3** | `scripts/lp_il_inventory_engine_v1_readonly.py`<br>`_liquidity_for_capital` / `current_inventory` | `float`<br>(单位为 quote 代币本金，非 USD) | 当 `capital=1000` 时：<br>**$L_{human}$**: `205.04308192280822`<br>换算 $L_{raw}$ ($10^{12}$): `205043081922808.22`<br>**$q_{0,human}$**: `0.19145712873772488`<br>**$q_{1,human}$**: `524.4204922154914`<br>**NAV Quote**: `1000.0` | 若调用方未做 USD 换算（仍传 1000）：<br>数值与组 A 完全相同。<br>若调用方换算 `capital=1000/0.99`：<br>**$L_{raw}$**: `207114224164452.75`<br>**$q_{0}$**: `0.193391039...`<br>**$q_{1}$**: `529.717668...` | **数学公式完全一致**。<br>但单位是 quote-token 本金，缺乏 raw 换算与内置 quote 汇率支持，需要调用方手动对齐量纲。 |
| **4** | `scripts/lp_il_math_replay_v1_readonly.py`<br>`_reference_entry` | `float`<br>(单位为 quote 代币本金) | 当 `capital=1000` 时：<br>**$L_{human}$**: `205.04308192280822`<br>换算 $L_{raw}$: `205043081922808.22`<br>**$q_{0}$**: `0.19145712873772488`<br>**$q_{1}$**: `524.4204922154914` | 同编号 3：本身为 quote 本金接口。传 1000 则不感知脱锚；传 1010.101 则与基准一致。 | 与编号 3 属于同质数学公式的**重复实现**（被用于回测重演套件的黄金参考）。 |
| **5** | `scripts/strategy_evidence_r4c_independent_clmm_liquidity_replay.py`<br>`compute_l_position_independent` | `int` / `Decimal`<br>(Q64.96 定点数 & Tick 空间) | **$L_{pos}$**: `215348252277461`<br>**$q_{0,raw}$**: `201290901235140800`<br>**$q_{1,raw}$**: `500000000`<br>**Recon USD**: `1000.00` | 同组 A：该函数无 quote 参数，且假设 1 token1 = $1.00。 | **完全不一致**（$L_{pos}$ 偏大 5.03%，两腿被人工强制锁死为 50/50，且 range 被对齐为 Tick 对称）。 |
| **6** | `scripts/lp_base_m1_c5_dry_run_v1_readonly.py`<br>`_active_notional` 与 L158-159 构造 | `float` / `Decimal`<br>(链上 RPC 交互脚本) | **$L$**: 未计算仓位流动性。<br>`amount0_desired`: `201288244766505636`<br>`amount1_desired`: `500000000` | 无法计算（不感知 quote）。 | **语义完全不同**：<br>`_active_notional` 算的是**池子全局在活跃区间的流动性**（用于风控 Cap）；L158-159 仅用于构造 mint 模拟交易入参。 |

---

## 二、逐处性质判定（重复实现 / 语义不同）

### 1. `scripts/lp_rh_v3_inventory_v1_readonly.py` (基准实现)
- **判定**：**基准规范实现（Canonical Reference）**。
- **解析**：采用 `Decimal`（prec=60/80），具备完整的 `quote_usd_per_token1` 处理、严格的参数边界校验（fail-closed），同时产出 raw 和 human 两个尺度的 inventory 与 liquidity，经重构验算残差 $< 10^{-18}$。模块内部 `inventory_for_position` 与 `position_value_at` 具有自洽闭环。

### 2. `scripts/lp_v3_fee_share.py:position_liquidity_raw`
- **判定**：**核心重复实现（应当整合/逐步废弃）**。
- **解析**：
  - 核心公式推导：$v_{raw} = 2\sqrt{P} - \sqrt{P_{lo}} - \frac{P}{\sqrt{P_{hi}}}$，分子为 $size\_usd$，乘上 $10^{(\mathrm{dec0}+\mathrm{dec1})/2}$。
  - 该公式与基准实现在代数上完全等价：
    $$q_0 \cdot P + q_1 = L_{human} \left( \frac{\sqrt{P_b} - \sqrt{P}}{\sqrt{P}\sqrt{P_b}} \cdot P + (\sqrt{P} - \sqrt{P_a}) \right) = L_{human} \left( 2\sqrt{P} - \sqrt{P_a} - \frac{P}{\sqrt{P_b}} \right)$$
  - 区别仅在于：它是 `float` 运算，且硬编码假定了 $\text{quote\_usd} \equiv 1$。
  - 它在项目中被 7 个脚本及多个测试深度依赖，是典型的“旧版轻量快捷函数”。

### 3. `scripts/lp_il_inventory_engine_v1_readonly.py`
- **判定**：**重复实现（但保持分层接口，可代理到底层或保留为 float 轻量层）**。
- **解析**：
  - 该模块的设计目标是“纯 quote 计价资产的无常损失（IL）分析引擎”。
  - 其入参是 `capital`（在说明文档中明确指出为 quote token 计价的 NAV）。因此在数学逻辑上，它也是求解 V3 标准建仓两腿与流动性。
  - 相比基准，它缺乏 raw 代币转换，缺乏外部 quote 兑 USD 乘数（这是由其“以 quote 为基准本位”的领域模型决定的）。虽然其公式与基准一致，但目前以 float 运行。

### 4. `scripts/lp_il_math_replay_v1_readonly.py:_reference_entry`
- **判定**：**重复实现（内部测试用的独立验算桩，建议保留但加注释）**。
- **解析**：
  - 文件头部明确标注：“`Independent V3 reference math. Keep separate from the production engine.`”。
  - 它的初衷就是作为 `lp_il_inventory_engine` 的独立对照组，用于在轨迹测试中检测主引擎是否产生回归。
  - 这种设计符合“双重对照”测试规范，**不属于**需要被重构消除的生产重复，但必须注明其为测试对照专用。

### 5. `scripts/strategy_evidence_r4c_independent_clmm_liquidity_replay.py:compute_l_position_independent`
- **判定**：**非真实 V3 仓位模型（粗糙工程近似，非同一物理量）**。
- **解析**：
  - 该函数存在两处根本性偏差：
    1. **强制 50/50 分仓**：把 `size_usd` 一分为二，一半买 token0，一半买 token1。而在 Uniswap V3 中，即使线性价格对称（如 $\pm 10\%$），由于几何平均与平方根空间不对称，实际 token0 价值占比约为 47.56%，token1 约为 52.44%。强行 50/50 导致两腿算出的 $L_{from\_0} \ne L_{from\_1}$，最终不得不取 `min()`，截断丢弃了一部分资金有效性。
    2. **Tick 取整不对称**：将百分比换算为离散 tick 跨度（$\Delta tick = 954$），使得价格区间变为了 $[P \cdot 1.0001^{-954}, P \cdot 1.0001^{954}] \approx [P / 1.10, P \times 1.10]$，而非线性对称的 $[P \times 0.90, P \times 1.10]$。
  - 因此，它算出的 $L \approx 2.153 \times 10^{14}$ 比实际真实值 $2.050 \times 10^{14}$ 高出约 5.03%。该函数只用于特定策略报告里的粗略回测证据，**不能**作为通用仓位真实流动性。应当改名并注明“近似 50/50 估算”。

### 6. `scripts/lp_base_m1_c5_dry_run_v1_readonly.py:93-101, 158-159`
- **判定**：**语义完全不同（池子活跃流动性评估 + 链上 Mint 意图构造）**。
- **解析**：
  - `_active_notional(liquidity, sqrt_price_x96, lower, upper)` 计算的是**整个 Uniswap V3 交易池在指定区间内的活跃资金总市值（TVL/深度）**，其中 `liquidity` 是从 RPC 读取的池子总 $L$。这绝非“我方仓位的流动性”。
  - L158-159：
    ```python
    amount0_desired = int((notional / 2) / price_usdc_per_weth * 1e18)
    amount1_desired = int(notional / 2 * 1e6)
    ```
    这里是在构造发往 `NonfungiblePositionManager.mint` 合约的 `amount0Desired/amount1Desired` 意图参数。在 Uniswap V3 NPM 中，用户通常传入粗略的 desired 上限，合约内部会根据精准 tick 自动按比例转移代币并将剩余代币退还。因此它并未实现仓位 liquidity 算法。

---

## 三、整合方案（按风险从低到高排序）

为了彻底根治“多处重复、精度断层、脱锚静默失效”隐患，建议在后续实施阶段采用以下渐进式整合路径：

### 阶段 1：低风险——重命名与消除歧义（纯文档/名称澄清，零逻辑风险）
1. **`scripts/strategy_evidence_r4c_independent_clmm_liquidity_replay.py:compute_l_position_independent`**
   - **操作**：函数重命名为 `estimate_l_position_coarse_5050_approx`，并在 docstring 中写明：“*警告：此函数采用 50/50 静态分仓与离散 tick 截断，与真实 V3 仓位有 ~5% 偏差，仅用于离线敏捷验证，严禁用于正式清算或收益对账*”。
2. **`scripts/lp_base_m1_c5_dry_run_v1_readonly.py:_active_notional`**
   - **操作**：函数重命名为 `_pool_active_liquidity_notional_usd`，并在注释中澄清：“*计算的是全局 Uniswap V3 池子在当前 tick 邻域内的活跃资金规模，用于风控仓位上限判定，非自营仓位 inventory*”。
3. **`scripts/lp_il_math_replay_v1_readonly.py:_reference_entry`**
   - **操作**：保留现有代码，在函数上方添加显式注释：“*Oracle Test Harness: 作为 IL 引擎的数学对照桩保留，严禁向生产模块暴露*”。

### 阶段 2：中风险——为 `lp_v3_fee_share.py` 增加 quote 支持并提供 Decimal 桥接
当前有多个模块依赖 `position_liquidity_raw` 的轻量签名。如果在原函数中直接改返回类型为 `Decimal`，会破坏大量下游 float 计算。
- **改动位置**：`scripts/lp_v3_fee_share.py:position_liquidity_raw`
- **改动方案**：
  1. 增加可选参数 `quote_usd_per_token1: float = 1.0`。
  2. 内部底座改写为复用 `lp_rh_v3_inventory_v1_readonly.inventory_for_position`：
     ```python
     def position_liquidity_raw(size_usd, entry_price, range_pct, dec0=18, dec1=6, quote_usd_per_token1=1.0):
         if entry_price <= 0 or size_usd <= 0 or quote_usd_per_token1 <= 0:
             return 0.0
         inv = inventory_for_position(
             position_usd=size_usd,
             entry_price=entry_price,
             range_pct=range_pct,
             dec0=dec0,
             dec1=dec1,
             quote_usd_per_token1=quote_usd_per_token1,
         )
         return float(inv.liquidity_raw)
     ```
  3. 这样保证历史调用方（未传 quote）行为 100% 保持原有精度，新调用方可正确传递脱锚 quote，且底层计算由唯一的基准模块统一驱动。

### 阶段 3：较高风险——替换生产/影子运行路径的直接调用点（需跑通回归测试）
将生产核算链路从 float 版本的 `position_liquidity_raw` 迁移至 `inventory_for_position`：
1. **`scripts/lp_rh_shadow_runner_v1_readonly.py:391`**
   - **现状**：将 `position_usd` 转为 float 调 `position_liquidity_raw`，再将返回值 `str()` 转回 `Decimal`。
   - **改动方案**：直接调用 `inventory_for_position`，将 `sample` 中的 `quote_usd_per_token1` 一同传入，直接获取 `Decimal` 的 `inv.liquidity_raw`。
   - **消除隐患**：彻底消除 float 往返转化的精度漂移，并首次将 runner 的仓位流动性与真实 quote 汇率联动。
2. **`scripts/lp_netcover_inputs_v1_readonly.py:604-608`**
   - **现状**：先算 `position_quote = size_usd / quote_usd`，再调 `position_liquidity_raw`。
   - **改动方案**：直接传入 `position_usd=size_usd, quote_usd_per_token1=quote_usd`，调用基准模块。
3. **`scripts/lp_portfolio_paper_runner_v1_readonly.py:202`** 与 **`scripts/lp_swap_cost_model_v1_readonly.py:177`**
   - **改动方案**：由 `effective_fee_share` 等函数逐步将底层切换至 `inventory_for_position`。

---

## 四、position_liquidity_raw 的 quote 问题深度分析

### 1. 是缺陷还是设计？
- **判定结论**：**是设计时的简化假设，但在脱锚/跨币种场景下演变成了隐蔽缺陷（Silent Drift Defect）**。
- **原因剖析**：
  - 在早期的设计假设中，token1 被默认为 USDC 或 USDT 等美元稳定币，开发者假设了 $1 \text{ token1} = \$1.00 \text{ USD}$。
  - 在该假设下，仓位规模 $S_{usd} = S_{quote}$。
  - 然而在实际市场中：
    1. 稳定币存在日常脱锚或价格微波动（如 USDC 脱锚至 0.99 或 0.88）。
    2. 如果 token1 不是美元稳定币（例如在 `WETH-USDC` 池中如果反转 token 对，或者在 `ARB-WETH`、`SOL-USDC` 等池子中），token1 根本不是 USD。
    3. 如果实际 quote 为 0.99，投入 $1000 USD 理论上等价于 $1010.10$ 个 token1 价值，建立的仓位 $L$ 应为 $207114224164452$，但旧函数依然返回 $205043081922808$。这导致仓位流动性被低估约 $1\%$，进而导致手续费分摊比例（Fee Share）被系统性低估。

### 2. 它现在被谁调用？调用方实际传什么？

通过对全仓库 `scripts/` 与 `tests/` 的逐行检索，实际调用清单如下：

| 调用文件与行号 | 调用参数列表 | 是否存在 quote 补偿处理 |
|:---|:---|:---|
| `scripts/lp_rh_shadow_runner_v1_readonly.py:391` | `(float(position_usd), pool_meta["input_price_usd"], pool_meta["range_pct"], dec0, dec1)` | **无**。虽然该函数后文（L402）在折算手续费为 USD 时乘了 `quote`，但在建仓计算 $L_{pos}$ 时未传 quote，**存在口径撕裂**。 |
| `scripts/lp_netcover_inputs_v1_readonly.py:604-608` | `(position_quote, price, reference_range, dec0, dec1)` | **有外部补丁**。该文件在外部先做了 `position_quote = size_usd / float(quote_usd)`，然后传给 `position_liquidity_raw`。相当于调用者自己修补了该缺陷！这证实了函数本身缺失该功能。 |
| `scripts/lp_portfolio_paper_runner_v1_readonly.py:202` | `(1.0, anchor, range_pct, int(dec0), int(dec1))` | **无**。固定传入单位规模 1.0，假设 1.0 对应 1.0 quote 且等于 1.0 USD。 |
| `scripts/lp_swap_cost_model_v1_readonly.py:177` | `(size_usd, entry_price, range_pct, dec0, dec1)` | **无**。直接传入 `size_usd`，隐式假设 quote=1.0。 |
| `scripts/strategy_pivot_d4_realtime_paper_shadow_validation.py:412` | `(self.size_usd, eth_usd, self.range_pct)` | **无**。默认 dec0=18, dec1=6，未感知 quote。 |
| `scripts/lp_tier_b_level2_replay_v1_readonly.py:200, 238, 278` | `(capital, anchor, range_pct, dec0, dec1)` | **无**。直接传入 capital。 |
| `tests/test_lp_rh_fee_accrual_dimensional_v1_readonly.py:103` | `(float(pos), pm["input_price_usd"], ...)` | 测试 oracle，直接固定 quote=1。 |
| `tests/test_lp_rh_first_step_accrual_v1_readonly.py:103` | `(float(pos), pm["input_price_usd"], ...)` | 测试 oracle，直接固定 quote=1。 |
| `tests/test_lp_rh_v3_inventory_v1_readonly.py:81` | `(1000.0, 2484.0, 10.0, 18, 6)` | 显式用于与新基准在 quote=1 时的对比测试。 |
| `tests/test_lp_v3_fee_share.py:9-50` | 多个单测用例 | 均只测试 `(size, price, range, dec0, dec1)`，没有 quote 测试。 |

**调用方行为总结**：
1. **全仓库没有一个调用点向 `position_liquidity_raw` 传递 quote 参数**（因为函数根本不接受该入参）。
2. 在大部分模块中，调用方都是盲目假定 `quote = 1.0`；
3. 唯一的例外是 `lp_netcover_inputs_v1_readonly.py:599`，那里的开发者意识到了该问题，被迫在函数外部手动先除了 `quote_usd`，绕过了函数的限制。这从侧面直接证明：**由底层统一支持 `quote` 是完全必要且势在必行的**。

---

## 五、结论与后续行动建议

1. **唯一权威基准**：确认 `scripts/lp_rh_v3_inventory_v1_readonly.py:inventory_for_position` 为全仓库唯一的 V3 仓位与流动性金标实现。
2. **严守变更红线**：本次调研未对既有代码进行任何修改，所有验证数据均已就绪。
3. **建议任务编排**：
   - 任务一：在 `scripts/strategy_evidence_r4c_...` 与 `scripts/lp_base_m1_c5_...` 中完成命名与注释隔离，消除认知混淆。
   - 任务二：将 `scripts/lp_v3_fee_share.py:position_liquidity_raw` 代理至 `lp_rh_v3_inventory_v1_readonly`，补充 `quote` 参数并保持向后兼容。
   - 任务三：优先切除 `lp_rh_shadow_runner_v1_readonly.py` 中的 float 中转调用，升级为直接对接 Decimal 基准。
